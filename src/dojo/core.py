"""Core build generator for the dojo static site pipeline.

This module provides the NinjaGenerator class that orchestrates the build
pipeline using decomposed stage classes for better maintainability.
"""

from __future__ import annotations

import io
import logging
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from tqdm import tqdm

from .artifacts import (
    MANIFEST_NAME,
    check_publication_paths,
    finalize_publication,
    import_legacy_publication,
    load_publication,
    reconcile_outputs,
    repair_media,
)
from .constants import RuleName
from .emitter import NinjaEmitter

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .config import Config, CustomRule, OutputConfig

from .io import write_changed
from .paths import source_files
from .plugins import BuildContext, BuildContribution, PluginInterface, PreparedInput, load_plugin
from .resources import clear_resource_cache
from .rules import get_builtin_rules
from .stages import AssetProcessor, CompileStage, RenderStage
from .stages._defaults import consumes_assets
from .yaml_utils import parse_frontmatter_type

logger = logging.getLogger(__name__)

# Constants
MINIMUM_MULTIPLE_OUTPUTS = 2


class NinjaGenerator:
    """Generates Ninja build files for a static site pipeline.

    The build process has these stages:
    1. Compile: Markdown → JSON (Pandoc AST)
    2. Render: JSON → Output format (HTML, PDF, etc)
    3. Post-process: Output → Optimized (minify, compress)
    4. Derive: Output → Derived format (HTML → PDF via Decktape)

    This class orchestrates the pipeline using specialized stage classes:
    - CompileStage: Handles Markdown to JSON AST conversion
    - RenderStage: Handles JSON to output format rendering
    - AssetProcessor: Handles dependency tracking and asset copying

    Ninja Rules and Variables Convention:
    -----------------------------------
    Dojo uses several Ninja variables to ensure shell-quoted path safety:
    - $in, $out: Standard Ninja input/output variables.
    - $in_shell, $out_shell: Shell-quoted variants of $in and $out, safe for
      use in command lines.
    - $args: Extra command-line arguments passed to the tool.
    - $defaults: Space-separated list of Pandoc defaults files.

    All paths emitted as variables are pre-quoted using `shlex.quote`.
    """

    def __init__(  # noqa: PLR0913
        self,
        config: Config,
        config_path: Path,
        *,
        quiet: bool = False,
        dry_run: bool = False,
        refresh: bool = False,
        emitter: NinjaEmitter | None = None,
        plugins: list[PluginInterface] | None = None,
    ) -> None:
        """Initialize the NinjaGenerator."""
        self.config = config
        self.config_path = Path(config_path).absolute()
        self.quiet = quiet
        self.dry_run = dry_run
        self.refresh = refresh

        # Configure paths
        self.src = Path(self.config.src_dir).absolute()
        self.out_dir = Path(self.config.output_dir).absolute()
        self.build_dir = Path(self.config.build_dir).absolute()
        self.ninja_file = self.build_dir / "build.ninja"
        inventory = self.build_dir / "publication.json"
        self.previous_publication = load_publication(
            inventory if inventory.is_file() else self.out_dir / MANIFEST_NAME
        )
        if not self.previous_publication.artifacts and not self.dry_run:
            self.previous_publication = import_legacy_publication(self.out_dir, self.ninja_file)

        # Create build directory
        if not self.dry_run:
            self.build_dir.mkdir(parents=True, exist_ok=True)

        # Buffer and Emitter
        if emitter:
            self.emitter = emitter
            self._buffer = None  # Plugins requiring buffer will be disabled
        else:
            self._buffer = io.StringIO()
            self.emitter = NinjaEmitter(self._buffer)

        # Track all final outputs
        self.all_outputs: list[Path] = []
        self.copied_assets: set[Path] = set()

        # Load plugins
        if plugins is not None:
            self.plugins = list(plugins)
        else:
            self.plugins = [
                load_plugin(path, base_dir=self.config_path.parent) for path in self.config.plugins
            ]

        # Sort plugins by priority (lower = earlier)
        self.plugins.sort(key=lambda p: p.priority)

        # Collect rules: Built-in + Config Custom + Plugin Custom
        self.rules: list[CustomRule] = get_builtin_rules(self.config, self.config_path)
        self.rules.extend(self.config.custom_rules)
        for plugin in self.plugins:
            self.rules.extend(plugin.get_custom_rules())

        # Initialize pipeline stages
        self._compile_stage = CompileStage(
            config=self.config,
            build_dir=self.build_dir,
            emitter=self.emitter,
        )
        self._render_stage = RenderStage(
            config=self.config,
            out_dir=self.out_dir,
            build_dir=self.build_dir,
            emitter=self.emitter,
            all_outputs=self.all_outputs,
        )
        self._asset_processor = AssetProcessor(
            src=self.src,
            out_dir=self.out_dir,
            emitter=self.emitter,
            copied_assets=self.copied_assets,
            all_outputs=self.all_outputs,
        )

        # Format link defaults: populated by _generate_format_link_defaults()
        self._format_link_defaults: dict[tuple[str, str], Path] = {}
        self.contributions: list[BuildContribution] = []
        self.prepared: dict[Path, PreparedInput] = {}
        self.sources: tuple[Path, ...] = ()
        self.asset_consumption: dict[str, bool] = {}
        self._validate_rules()
        self._register_rule_dependencies()

    def _validate_rules(self) -> None:
        """Reject ambiguous rule ownership and invalid tool references."""
        names = [rule.name for rule in self.rules]
        if len(names) != len(set(names)):
            msg = "Conflicting build rule names from configuration/plugins"
            raise ValueError(msg)
        for rule in self.rules:
            if rule.pool and rule.pool not in self.config.pools:
                message = f"Rule {rule.name!r} references undefined pool {rule.pool!r}"
                raise ValueError(message)
        if unknown := self.config.rule_pools.keys() - set(names):
            message = f"Pool assignments reference unknown rules: {sorted(unknown)}"
            raise ValueError(message)
        for kind in self.config.types.values():
            for output in kind.outputs:
                for tool in [output.tool, *(step.tool for step in output.post_process)]:
                    if tool and tool not in names:
                        msg = f"Unknown output tool: {tool}"
                        raise ValueError(msg)

    def _register_rule_dependencies(self) -> None:
        """Track tool binaries, bundled implementations, and explicit custom inputs."""
        runtime = Path(__file__).parent
        code = {
            "compile": ["resources/dependencies.lua"],
            "render": ["resources/fix_typst_csl.lua", "resources/format_links.lua"],
            "crunch": [
                "crunch.py",
                "exceptions.py",
                "resources/fzstd.js",
                "resources/fzstd.LICENSE",
            ],
        }
        tool_inputs = {
            "compile": [self.config.tools.pandoc],
            "render": [self.config.tools.pandoc, self.config.tools.typst],
            "decktape": [self.config.tools.decktape],
            "ghostscript": [self.config.tools.ghostscript],
            "minify": [self.config.tools.minify],
        }
        fonts = [
            path
            for folder in self.config.font_paths
            for path in Path(folder).rglob("*")
            if path.is_file()
        ]
        for rule in self.rules:
            declared = [self.config.project_root / name for name in rule.dependencies]
            if rule.name in {name.value for name in RuleName} - {"regenerate", "stamp"}:
                declared.append(runtime / "wrap.py")
                declared.extend(runtime / name for name in code.get(rule.name, []))
                declared.extend(
                    Path(name) for name in tool_inputs.get(rule.name, []) if Path(name).is_file()
                )
            if rule.name == "render":
                declared.extend(fonts)
            self.emitter.rule_dependencies[rule.name] = sorted(
                set(declared), key=lambda path: (path.name, str(path))
            )

    def _generate_format_link_defaults(self) -> None:
        """Generate Pandoc defaults files for cross-format links.

        For each (type, output) pair where the type has multiple outputs,
        creates a YAML defaults file containing:
        - A reference to the bundled format_links.lua filter
        - Metadata with the current output's suffix and sibling format specs

        The generated files are stored in ``_build/_dojo/`` and recorded in
        ``self._format_link_defaults`` for later use by ``_apply_format_link_defaults()``.
        """
        dojo_dir = self.build_dir / "_dojo"
        dojo_dir.mkdir(parents=True, exist_ok=True)

        filter_path = (Path(__file__).parent / "resources" / "format_links.lua").resolve()

        # Only generate for types with multiple outputs
        for type_name, type_config in self.config.types.items():
            if len(type_config.outputs) < MINIMUM_MULTIPLE_OUTPUTS:
                continue

            for out_config in type_config.outputs:
                # Skip derived outputs (they don't go through Pandoc render)
                if out_config.source is not None:
                    continue

                output_id = out_config.id or out_config.extension
                siblings = self._get_sibling_formats(type_config.outputs, out_config)

                # Build defaults YAML content
                defaults_data: dict[str, object] = {
                    "filters": [str(filter_path)],
                    "metadata": {
                        "dojo-current-suffix": out_config.suffix,
                        "dojo-sibling-formats": siblings,
                    },
                }

                # Write the defaults file
                defaults_path = dojo_dir / f"format-links-{type_name}-{output_id}.yaml"
                new_content = yaml.dump(
                    defaults_data,
                    default_flow_style=False,
                    allow_unicode=True,
                )

                if self._write_if_changed(defaults_path, new_content):
                    logger.debug(
                        "Generated format link defaults: %s (%d siblings)",
                        defaults_path.name,
                        len(siblings),
                    )

                self._format_link_defaults[(type_name, output_id)] = defaults_path.resolve()

    def _get_sibling_formats(
        self,
        outputs: list[OutputConfig],
        current: OutputConfig,
    ) -> list[dict[str, str | None]]:
        """Compute sibling formats for cross-format links."""
        siblings: list[dict[str, str | None]] = []
        for sibling in outputs:
            if sibling is current:
                continue
            sibling_id = sibling.id or sibling.extension
            siblings.append(
                {
                    "label": sibling.label or sibling_id.upper(),
                    "suffix": sibling.suffix,
                    "extension": sibling.extension,
                }
            )
        return siblings

    def _write_if_changed(self, target: Path, content: str) -> bool:
        """Write content to target file only if it has changed.

        Returns:
            True if the file was written, False if it was unchanged.

        """
        return write_changed(target, content)

    def _apply_format_link_defaults(
        self,
        out_config: OutputConfig,
        content_type: str,
    ) -> OutputConfig:
        """Prepend format link defaults to an output config if applicable.

        Only modifies standard render outputs (not derived outputs).
        Returns the original config unchanged if format links are disabled
        or no defaults were generated for this (type, output) pair.

        Args:
            out_config: Output configuration to potentially modify
            content_type: Content type name for registry lookup

        Returns:
            Modified output config with format link defaults prepended,
            or the original config if not applicable.

        """
        if not self._format_link_defaults:
            return out_config

        # Skip derived outputs
        if out_config.source is not None:
            return out_config

        output_id = out_config.id or out_config.extension
        format_key = (content_type, output_id)

        if format_key not in self._format_link_defaults:
            return out_config

        extra_default = str(self._format_link_defaults[format_key])

        # Prepend format link defaults (lower priority) before user defaults
        existing = out_config.defaults
        if existing is None:
            new_defaults: str | list[str] = [extra_default]
        elif isinstance(existing, str):
            new_defaults = [extra_default, existing]
        else:
            new_defaults = [extra_default, *existing]

        return out_config.model_copy(update={"defaults": new_defaults})

    def emit_header(self) -> None:
        """Generate Ninja file header with version, pools, and rules."""
        self.emitter.comment("Auto-generated by dojo - DO NOT EDIT MANUALLY")
        self.emitter.comment(f"Source: {self.config_path}")
        self.emitter.newline()
        self.emitter.variable("ninja_required_version", "1.3")
        self.emitter.newline()

        # Pools
        self.emitter.comment("Resource pools prevent CPU/memory saturation")
        for pool_name, depth in self.config.pools.items():
            self.emitter.pool(pool_name, depth)

        # Rules
        self.emitter.comment("Rules")
        for rule in self.rules:
            self.emitter.rule(
                name=rule.name,
                command=rule.command,
                description=rule.description,
                pool=rule.pool,
                depfile=rule.depfile,
                deps=rule.deps,
                generator=rule.generator,
                variables=rule.variables,
            )

            # Special case for REGENERATE: emit the build edge immediately
            if rule.name == RuleName.REGENERATE.value:
                self.emitter.build(
                    outputs=self.ninja_file,
                    rule=RuleName.REGENERATE.value,
                    inputs=self.config_path,
                )
                self.emitter.newline()

    def process_content(self, md_path: Path, static_deps: list[Path] | Path | None = None) -> None:
        """Generate Ninja build rules for a single Markdown source file."""
        try:
            rel_path = md_path.relative_to(self.src)
        except ValueError:
            logger.warning("Source file outside source directory: %s", md_path)
            return

        rel_stem = rel_path.with_suffix("")

        # Identify content type
        content_type = parse_frontmatter_type(md_path, self.config.default_type)
        if content_type not in self.config.types:
            message = f"{md_path}: unknown content type {content_type!r}"
            raise ValueError(message)
        type_config = self.config.types[content_type]

        # Stage 1: Compile
        try:
            src_comment = md_path.relative_to(Path.cwd())
        except ValueError:
            src_comment = md_path

        self.emitter.comment(f"Source: {src_comment}")
        json_node = self._compile_stage.compile(
            md_path,
            rel_stem,
            type_config,
            plugins=self.plugins,
            prepared=self.prepared.get(md_path),
        )
        self.emitter.newline()

        if not type_config.outputs:
            return

        # Stage 2: Asset processing
        # Discovers assets (CSS, JS, images) and adds COPY rules.
        # Returns list of asset output paths to use as implicit dependencies for rendering.
        asset_deps = self._asset_processor.process_assets(md_path)

        # Combine explicit asset deps with global static deps
        all_deps = list(asset_deps)
        prepared = self.prepared.get(md_path)
        if prepared:
            all_deps.extend(self.out_dir / relative for relative in prepared.assets.values())

        # Stage 3: Render/Derive
        local_registry: dict[str, Path] = {}
        for out_config in type_config.outputs:
            # Plugin Hook: Modify output config
            current_config = out_config
            for plugin in self.plugins:
                current_config = plugin.modify_output_config(current_config, content_type)

            # Format Links: Prepend generated defaults for standard renders
            current_config = self._apply_format_link_defaults(
                current_config,
                content_type,
            )

            output_deps = list(all_deps)
            output_deps.extend(
                self.config.project_root / name for name in current_config.dependencies
            )
            if static_deps and self._consumes_assets(current_config):
                output_deps.extend([static_deps] if isinstance(static_deps, Path) else static_deps)
            self._render_stage.render(
                current_config,
                json_node,
                rel_stem,
                local_registry,
                implicit_deps=output_deps,
                order_only=static_deps,
                plugins=self.plugins,
            )

        self.emitter.newline()

    def _consumes_assets(self, output: OutputConfig) -> bool:
        """Cache the resource-consumption decision per output configuration."""
        key = output.model_dump_json()
        if key not in self.asset_consumption:
            self.asset_consumption[key] = consumes_assets(
                output,
                project_root=self.config.project_root,
                data_dir=Path(self.config.pandoc_data_dir) if self.config.pandoc_data_dir else None,
            )
        return self.asset_consumption[key]

    def _run_pre_generate_hooks(self) -> None:
        """Execute pre_generate hooks for all loaded plugins."""
        context = BuildContext(
            config=self.config.model_copy(deep=True),
            config_path=self.config_path,
            project_root=self.config_path.parent,
            src_dir=self.src,
            build_dir=self.build_dir,
            output_dir=self.out_dir,
            sources=self.sources,
            refresh=self.refresh,
        )
        for plugin in self.plugins:
            isolated = context.config.model_copy(deep=True)
            contribution = plugin.prepare(replace(context, config=isolated))
            if isolated != context.config:
                message = (
                    f"{type(plugin).__name__}.prepare mutated config; return a BuildContribution"
                )
                raise ValueError(message)
            self.contributions.append(contribution)
            for prepared in contribution.prepared:
                if prepared.source in self.prepared:
                    msg = f"Multiple plugins prepare {prepared.source}"
                    raise ValueError(msg)
                self.prepared[prepared.source] = prepared

    def _process_plugin_extra_assets(self) -> None:
        """Process extra assets declared by plugins."""
        for plugin in self.plugins:
            extra_assets = plugin.get_extra_assets(self.config, self.out_dir)
            self._asset_processor.copy_assets(
                {
                    source: destination.relative_to(self.out_dir)
                    for destination, source in extra_assets.items()
                }
            )

    def generate(self) -> None:
        """Scan source files and generate build.ninja."""
        logger.info("Scanning source directory: %s", self.src)

        clear_resource_cache()
        self.sources = tuple(self._get_filtered_files())
        if self.dry_run:
            self._log_dry_run_summary(len(self.sources))
            return

        # Generate format link defaults before processing content
        if self.config.format_links:
            self._generate_format_link_defaults()

        # Plugin Hook: Pre-generation lifecycle hook
        self._run_pre_generate_hooks()

        self.emit_header()

        # Stage 2: Static assets
        # Process these first so they can be used as dependencies for content rendering
        static_dirs = list(self.config.static_dirs)
        replacements = [
            item.static_dirs for item in self.contributions if item.static_dirs is not None
        ]
        if len(replacements) > 1:
            msg = "Only one plugin may select the project's static directories"
            raise ValueError(msg)
        if replacements:
            static_dirs = [str(path) for path in replacements[0]]
        static_outputs = self._asset_processor.process_static_assets(static_dirs)
        for contribution in self.contributions:
            self._asset_processor.copy_assets(contribution.assets)
            static_outputs.extend(self.out_dir / path for path in contribution.assets.values())
        for prepared in self.prepared.values():
            self._asset_processor.copy_assets(prepared.assets)

        # Stage 2b: Plugin extra assets
        self._process_plugin_extra_assets()

        # Membership is an input too: Ninja otherwise misses removals, including
        # the transition to zero assets. Keep the stamp present for every graph.
        membership = self.build_dir / "static-assets.txt"
        write_changed(
            membership,
            "".join(
                path.relative_to(self.out_dir).as_posix() + "\n"
                for path in sorted(set(static_outputs))
            ),
        )
        static_deps = self.build_dir / ".static_assets.stamp"
        self.emitter.build(
            outputs=static_deps,
            rule=RuleName.STAMP.value,
            inputs=[membership, *sorted(set(static_outputs))],
        )
        self.emitter.newline()

        # Stage 3: Content processing
        filtered_files = list(self.sources)
        if not filtered_files:
            logger.warning("No Markdown files found in %s", self.src)
        else:
            logger.info("Found %d Markdown file(s)", len(filtered_files))
            self._process_markdown_files(filtered_files, static_deps=static_deps)

        # Stage 4: Post-process the final content via plugins
        self._post_process_and_write()

    def _get_filtered_files(self) -> list[Path]:
        """Scan and filter Markdown source files."""
        return source_files(self.src, self.config.include, self.config.exclude)

    def _process_markdown_files(
        self,
        files: list[Path],
        static_deps: list[Path] | Path | None = None,
    ) -> None:
        """Iterate over and process multiple Markdown files."""
        progress: Iterable[Path] = tqdm(files, desc="Processing", unit="file", disable=self.quiet)
        for md_file in progress:
            try:
                self.process_content(md_file, static_deps=static_deps)
            except Exception:
                logger.exception("Failed to process %s", md_file)
                raise

    def _post_process_and_write(self) -> None:
        """Handle Stage 5: Plugin post-processing and actual file output."""
        # If an external emitter was used, we don't have a buffer to post-process.
        if self._buffer is None:
            logger.debug("Skipping plugin post-processing (external emitter in use)")
            self._log_completion_summary()
            return

        ninja_content = self._buffer.getvalue()

        # Plugin Hook: Post-process Ninja content
        for plugin in self.plugins:
            ninja_content = plugin.post_process_ninja(ninja_content)

        check_publication_paths(self.out_dir, self.all_outputs)
        reconcile_outputs(self.out_dir, self.all_outputs, self.previous_publication)
        repair_media(self.out_dir, self.build_dir, self.previous_publication)
        inventory_path = self.build_dir / "publication.json"
        if not inventory_path.exists() and self.previous_publication.artifacts:
            write_changed(
                inventory_path, self.previous_publication.model_dump_json(indent=2) + "\n"
            )
        self._write_ninja_file(ninja_content)
        self._log_completion_summary()

    def _log_dry_run_summary(self, source_count: int) -> None:
        """Log the build plan summary for dry-run mode."""
        logger.info("Dry-run mode: would generate %s", self.ninja_file)
        logger.info("")
        logger.info("Build plan:")
        logger.info("  - %d source file(s) processed", source_count)
        logger.info("  - %d output file(s) would be built", len(self.all_outputs))

        if not self.quiet and self.all_outputs:
            logger.info("")
            logger.info("Outputs:")
            max_display = 10
            for output in self.all_outputs[:max_display]:
                try:
                    rel_output = output.relative_to(Path.cwd())
                except ValueError:
                    rel_output = output
                logger.info("    → %s", rel_output)
            if len(self.all_outputs) > max_display:
                logger.info("    ... and %d more", len(self.all_outputs) - max_display)

    def _write_ninja_file(self, content: str) -> None:
        """Write the Ninja build file to disk."""
        if self._write_if_changed(self.ninja_file, content):
            logger.info("Generated: %s", self.ninja_file)
        else:
            logger.debug("Ninja file unchanged, skipping write")

    def finalize(self) -> None:
        """Publish ownership only after every requested build stage succeeds."""
        finalize_publication(
            self.out_dir,
            self.build_dir,
            self.all_outputs,
            self._render_stage.media_producers,
            self.previous_publication,
            assets=self.copied_assets,
            provenance=tuple(
                path for contribution in self.contributions for path in contribution.provenance
            ),
        )

    def _log_completion_summary(self) -> None:
        """Log the completion summary after successful generation."""
        logger.info("Outputs: %d file(s) will be built", len(self.all_outputs))
        logger.info("")
        logger.info("Next steps:")
        try:
            rel_ninja = self.ninja_file.relative_to(Path.cwd())
        except ValueError:
            rel_ninja = self.ninja_file
        logger.info("  ninja -f %s", rel_ninja)
