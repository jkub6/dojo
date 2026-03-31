"""Core build generator for the dojo static site pipeline.

This module provides the NinjaGenerator class that orchestrates the build
pipeline using decomposed stage classes for better maintainability.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from tqdm import tqdm

from .constants import RuleName
from .emitter import NinjaEmitter

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .config import Config, CustomRule, OutputConfig

from .paths import sanitize_path, shell_quote, should_process_file
from .plugins import PluginInterface, load_plugin
from .rules import get_builtin_rules
from .stages import AssetProcessor, CompileStage, RenderStage
from .yaml_utils import parse_frontmatter_type

logger = logging.getLogger(__name__)


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

    def __init__(
        self,
        config: Config,
        config_path: Path,
        *,
        quiet: bool = False,
        dry_run: bool = False,
        emitter: NinjaEmitter | None = None,
    ) -> None:
        """Initialize the NinjaBuilder."""
        self.config = config
        self.config_path = Path(config_path).absolute()
        self.quiet = quiet
        self.dry_run = dry_run

        # Configure paths
        self.src = Path(self.config.src_dir).absolute()
        self.out_dir = Path(self.config.output_dir).absolute()
        self.build_dir = Path(self.config.build_dir).absolute()
        self.ninja_file = self.build_dir / "build.ninja"

        # Create build directory
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
        self.plugins: list[PluginInterface] = []
        for plugin_path in self.config.plugins:
            plugin = load_plugin(plugin_path)
            if plugin:
                self.plugins.append(plugin)

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

        for type_name, type_config in self.config.types.items():
            # Only generate for types with multiple outputs
            if len(type_config.outputs) < 2:  # noqa: PLR2004
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
        if target.exists():
            try:
                current_content = target.read_text(encoding="utf-8")
                if current_content == content:
                    return False
            except OSError as e:
                logger.warning("Failed to read %s for change detection: %s", target, e)

        try:
            with open(target, "w", encoding="utf-8") as f:
                f.write(content)
        except OSError:
            logger.exception("Failed to write %s", target)
            raise
        else:
            return True

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

    def process_content(self, md_path: Path) -> None:
        """Generate Ninja build rules for a single Markdown source file."""
        try:
            rel_path = md_path.relative_to(self.src)
        except ValueError:
            logger.warning("Source file outside source directory: %s", md_path)
            return

        rel_stem = rel_path.with_suffix("")

        # Identify content type
        content_type = parse_frontmatter_type(md_path, self.config.default_type)
        type_config = self.config.types.get(
            content_type,
            self.config.types[self.config.default_type],
        )

        # Stage 1: Compile
        try:
            src_comment = md_path.relative_to(Path.cwd())
        except ValueError:
            src_comment = md_path

        self.emitter.comment(f"Source: {src_comment}")
        json_node = self._compile_stage.compile(md_path, rel_stem, type_config)
        self.emitter.newline()

        if not type_config.outputs:
            return

        # Stage 2: Render/Derive
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

            self._render_stage.render(current_config, json_node, rel_stem, local_registry)

        self.emitter.newline()

        # Stage 3: Asset processing
        self._asset_processor.process_assets(md_path)

    def generate(self) -> None:
        """Scan source files and generate build.ninja."""
        logger.info("Scanning source directory: %s", self.src)

        # Generate format link defaults before processing content
        if self.config.format_links:
            self._generate_format_link_defaults()

        self.emit_header()

        filtered_files = self._get_filtered_files()
        if not filtered_files:
            logger.warning("No Markdown files found in %s", self.src)
        else:
            logger.info("Found %d Markdown file(s)", len(filtered_files))
            self._process_markdown_files(filtered_files)

        # Stage 4: Static assets
        self._process_static_assets()

        # Stage 5: Post-process the final content via plugins
        self._post_process_and_write(len(filtered_files))

    def _get_filtered_files(self) -> list[Path]:
        """Scan and filter Markdown source files."""
        md_files = sorted(self.src.rglob("*.md"))
        return [
            f
            for f in md_files
            if should_process_file(f, self.src, self.config.include, self.config.exclude)
        ]

    def _process_markdown_files(self, files: list[Path]) -> None:
        """Iterate over and process multiple Markdown files."""
        progress: Iterable[Path] = tqdm(files, desc="Processing", unit="file", disable=self.quiet)
        for md_file in progress:
            try:
                self.process_content(md_file)
            except Exception:
                logger.exception("Failed to process %s", md_file)
                raise

    def _process_static_assets(self) -> None:
        """Handle Stage 4: Copy static assets to output directory."""
        for static_dir in self.config.static_dirs:
            static_path = (
                Path(self.src / static_dir).resolve()
                if not Path(static_dir).is_absolute()
                else Path(static_dir).resolve()
            )
            if not static_path.exists():
                continue

            for file in static_path.rglob("*"):
                if not file.is_file():
                    continue

                try:
                    rel_file = file.relative_to(static_path)
                except ValueError:
                    continue

                final_path = sanitize_path(self.out_dir, rel_file)
                if final_path not in self.copied_assets:
                    self.emitter.build(
                        outputs=final_path,
                        rule=RuleName.COPY.value,
                        inputs=file,
                        variables={
                            "in_shell": shell_quote(file),
                            "out_shell": shell_quote(final_path),
                        },
                    )
                    self.copied_assets.add(final_path)
                    self.all_outputs.append(final_path)

    def _post_process_and_write(self, source_count: int) -> None:
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

        # Dry-run mode: show plan without writing
        if self.dry_run:
            self._log_dry_run_summary(source_count)
            return

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
