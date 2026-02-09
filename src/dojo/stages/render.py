"""Render stage: JSON AST → Output format conversion.

This module handles the second stage of the build pipeline, converting
Pandoc JSON AST to final output formats (HTML, PDF, etc.) including
both standard rendering and derived outputs.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from dojo.constants import RuleName
from dojo.emitter import NinjaEmitter
from dojo.exceptions import DependencyError, OutputSourceMissingError, OutputToolMissingError
from dojo.paths import ninja_escape, sanitize_path, shell_quote
from dojo.yaml_utils import get_recursive_yaml_deps

if TYPE_CHECKING:
    from dojo.config import Config, OutputConfig

logger = logging.getLogger(__name__)


class RenderStage:
    """Handles JSON AST to output format rendering.

    Supports both standard rendering (JSON → HTML) and derived outputs
    (HTML → PDF via decktape, etc.).

    Attributes:
        config: Build configuration
        out_dir: Path to output directory
        build_dir: Path to build artifacts directory
        emitter: Ninja file emitter
        all_outputs: List tracking all final output paths

    """

    def __init__(
        self,
        config: Config,
        out_dir: Path,
        build_dir: Path,
        emitter: NinjaEmitter,
        all_outputs: list[Path],
    ) -> None:
        """Initialize the render stage.

        Args:
            config: Build configuration
            out_dir: Path to output directory
            build_dir: Path to build artifacts directory
            emitter: Ninja file emitter
            all_outputs: Shared list tracking all final output paths

        """
        self.config = config
        self.out_dir = out_dir
        self.build_dir = build_dir
        self.emitter = emitter
        self.all_outputs = all_outputs

    def _get_merged_defaults(self, *sources: str | list[str] | None) -> list[Path]:
        """Merge default files from multiple sources and return absolute paths."""
        merged = []
        for src in sources:
            if not src:
                continue
            if isinstance(src, str):
                merged.append(Path(src))
            else:
                merged.extend(Path(s) for s in src)
        return merged

    def _format_defaults_var(self, defaults: list[Path]) -> str:
        """Format list of defaults into ninja variable string."""
        if not defaults:
            return ""
        return "-d " + " -d ".join(ninja_escape(d) for d in defaults)

    def render(
        self,
        out_config: OutputConfig,
        json_node: Path,
        rel_stem: Path,
        local_registry: dict[str, Path],
    ) -> None:
        """Convert JSON to output format or derived output.

        Args:
            out_config: Output configuration
            json_node: Path to JSON AST file
            rel_stem: Relative path without extension
            local_registry: Registry of output IDs to paths for this content

        """
        if out_config.source:
            self._derive_output(out_config, rel_stem, local_registry)
        else:
            self._standard_render(out_config, rel_stem, json_node, local_registry)

    def _standard_render(
        self,
        out_config: OutputConfig,
        rel_stem: Path,
        json_node: Path,
        local_registry: dict[str, Path],
    ) -> None:
        """Render standard Pandoc with optional post-processing."""
        filename = f"{rel_stem.name}{out_config.suffix}.{out_config.extension}"
        final_path = sanitize_path(self.out_dir, rel_stem.parent / filename)

        post_tool = out_config.post_process
        if post_tool:
            render_target = sanitize_path(
                self.build_dir,
                Path("intermediates") / rel_stem.parent / filename,
            )
        else:
            render_target = final_path

        # Gather dependencies for rendering
        all_defaults = self._get_merged_defaults(out_config.defaults)
        variables: dict[str, str] = {}
        implicit: list[Path] = []

        if all_defaults:
            variables["defaults"] = self._format_defaults_var(all_defaults)
            raw_deps: list[Path] = []
            data_dir = Path(self.config.pandoc_data_dir) if self.config.pandoc_data_dir else None
            for df in all_defaults:
                raw_deps.append(df)
                raw_deps.extend(get_recursive_yaml_deps(df, data_dir_override=data_dir))
            implicit = sorted(set(raw_deps))

        variables["in_shell"] = shell_quote(json_node)
        variables["out_shell"] = shell_quote(render_target)

        if out_config.args:
            variables["args"] = " ".join(out_config.args)

        self.emitter.build(
            outputs=render_target,
            rule=RuleName.RENDER.value,
            inputs=json_node,
            implicit=implicit,
            variables=variables,
        )

        if post_tool:
            self.emitter.build(
                outputs=final_path,
                rule=post_tool,
                inputs=render_target,
                variables={
                    "in_shell": shell_quote(render_target),
                    "out_shell": shell_quote(final_path),
                },
            )

        if out_config.id:
            local_registry[out_config.id] = final_path

        self.all_outputs.append(final_path)

    def _derive_output(
        self,
        out_config: OutputConfig,
        rel_stem: Path,
        local_registry: dict[str, Path],
    ) -> None:
        """Derive output from other build products (e.g. HTML -> PDF)."""
        filename = f"{rel_stem.name}{out_config.suffix}.{out_config.extension}"
        final_path = sanitize_path(self.out_dir, rel_stem.parent / filename)

        if out_config.source is None:
            raise OutputSourceMissingError()
        raw_source = out_config.source

        source_ids_list: list[str] = [raw_source] if isinstance(raw_source, str) else raw_source

        source_paths = []
        for parent_id in source_ids_list:
            if parent_id not in local_registry:
                logger.error(
                    "Missing dependency '%s' for output '%s'",
                    parent_id,
                    out_config.id,
                )
                raise DependencyError(parent_id)
            source_paths.append(local_registry[parent_id])

        variables = {
            "in_shell": " ".join(shell_quote(p) for p in source_paths),
            "out_shell": shell_quote(final_path),
        }
        if out_config.args:
            variables["args"] = " ".join(out_config.args)

        if out_config.tool is None:
            raise OutputToolMissingError()

        self.emitter.build(
            outputs=final_path,
            rule=out_config.tool,
            inputs=source_paths,
            variables=variables,
        )

        if out_config.id:
            local_registry[out_config.id] = final_path

        self.all_outputs.append(final_path)
