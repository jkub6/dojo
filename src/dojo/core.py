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

from .paths import should_process_file
from .plugins import PluginInterface, load_plugin
from .rules import get_builtin_rules
from .stages import AssetProcessor, CompileStage, RenderStage, format_defaults_var, merge_defaults
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
    """

    def __init__(
        self,
        config: Config,
        config_path: Path,
        *,
        quiet: bool = False,
        dry_run: bool = False,
    ) -> None:
        """Initialize the NinjaBuilder."""
        self.config = config
        self.config_path = config_path.resolve()
        self.quiet = quiet
        self.dry_run = dry_run

        # Configure paths
        self.src = Path(self.config.src_dir).resolve()
        self.out_dir = Path(self.config.output_dir).resolve()
        self.build_dir = Path(self.config.build_dir).resolve()
        self.ninja_file = self.build_dir / "build.ninja"

        # Create build directory
        self.build_dir.mkdir(parents=True, exist_ok=True)

        # Buffer and Emitter
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

    # Keep legacy methods for backward compatibility with tests
    def _get_merged_defaults(self, *sources: str | list[str] | None) -> list[Path]:
        """Merge default files from multiple sources and return absolute paths."""
        return merge_defaults(*sources)

    def _format_defaults_var(self, defaults: list[Path]) -> str:
        """Format list of defaults into ninja variable string."""
        return format_defaults_var(defaults)

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

        filter_path = Path(__file__).parent / "resources" / "format_links.lua"

        for type_name, type_config in self.config.types.items():
            # Only generate for types with multiple outputs
            min_outputs = 2
            if len(type_config.outputs) < min_outputs:
                continue

            for out_config in type_config.outputs:
                # Skip derived outputs (they don't go through Pandoc render)
                if out_config.source is not None:
                    continue

                output_id = out_config.id or out_config.extension

                # Compute siblings: all OTHER outputs in this type
                siblings = []
                for sibling in type_config.outputs:
                    if sibling is out_config:
                        continue
                    sibling_id = sibling.id or sibling.extension
                    siblings.append(
                        {
                            "label": sibling.label or sibling_id.upper(),
                            "suffix": sibling.suffix,
                            "extension": sibling.extension,
                        }
                    )

                # Build defaults YAML content
                defaults_data: dict[str, object] = {
                    "filters": [str(filter_path.resolve())],
                    "metadata": {
                        "dojo-current-suffix": out_config.suffix,
                        "dojo-sibling-formats": siblings,
                    },
                }

                # Write the defaults file
                defaults_path = dojo_dir / f"format-links-{type_name}-{output_id}.yaml"
                with open(defaults_path, "w", encoding="utf-8") as f:
                    yaml.dump(
                        defaults_data,
                        f,
                        default_flow_style=False,
                        allow_unicode=True,
                    )

                self._format_link_defaults[(type_name, output_id)] = defaults_path.resolve()

                logger.debug(
                    "Generated format link defaults: %s (%d siblings)",
                    defaults_path.name,
                    len(siblings),
                )

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
            self.emitter.fp.write(f"pool {pool_name}\n")
            self.emitter.variable("depth", str(depth), indent=1)
            self.emitter.newline()

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

        md_files = sorted(self.src.rglob("*.md"))
        filtered_files = [
            f
            for f in md_files
            if should_process_file(f, self.src, self.config.include, self.config.exclude)
        ]

        if not filtered_files:
            logger.warning("No Markdown files found in %s", self.src)
        else:
            logger.info("Found %d Markdown file(s)", len(filtered_files))

        progress: Iterable[Path] = tqdm(
            filtered_files, desc="Processing", unit="file", disable=self.quiet
        )
        for md_file in progress:
            try:
                self.process_content(md_file)
            except Exception:
                logger.exception("Failed to process %s", md_file)
                raise

        ninja_content = self._buffer.getvalue()

        # Plugin Hook: Post-process Ninja content
        for plugin in self.plugins:
            ninja_content = plugin.post_process_ninja(ninja_content)

        # Dry-run mode: show plan without writing
        if self.dry_run:
            self._log_dry_run_summary(len(filtered_files))
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
        try:
            with open(self.ninja_file, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception:
            logger.exception("Failed to write %s", self.ninja_file)
            raise

    def _log_completion_summary(self) -> None:
        """Log the completion summary after successful generation."""
        logger.info("Generated: %s", self.ninja_file)
        logger.info("Outputs: %d file(s) will be built", len(self.all_outputs))
        logger.info("")
        logger.info("Next steps:")
        try:
            rel_ninja = self.ninja_file.relative_to(Path.cwd())
        except ValueError:
            rel_ninja = self.ninja_file
        logger.info("  ninja -f %s", rel_ninja)
