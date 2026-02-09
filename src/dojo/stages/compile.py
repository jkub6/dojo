"""Compile stage: Markdown → JSON AST conversion.

This module handles the first stage of the build pipeline, converting
Markdown source files to Pandoc JSON AST format.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from dojo.constants import RuleName
from dojo.emitter import NinjaEmitter
from dojo.paths import ninja_escape, sanitize_path, shell_quote
from dojo.yaml_utils import get_recursive_yaml_deps

if TYPE_CHECKING:
    from dojo.config import Config, TypeConfig


class CompileStage:
    """Handles Markdown to JSON AST compilation.

    Attributes:
        config: Build configuration
        build_dir: Path to build artifacts directory
        emitter: Ninja file emitter

    """

    def __init__(
        self,
        config: Config,
        build_dir: Path,
        emitter: NinjaEmitter,
    ) -> None:
        """Initialize the compile stage.

        Args:
            config: Build configuration
            build_dir: Path to build artifacts directory
            emitter: Ninja file emitter

        """
        self.config = config
        self.build_dir = build_dir
        self.emitter = emitter

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

    def compile(
        self,
        md_path: Path,
        rel_stem: Path,
        type_config: TypeConfig,
    ) -> Path:
        """Convert Markdown to JSON (Pandoc AST).

        Args:
            md_path: Absolute path to source Markdown file
            rel_stem: Relative path without extension
            type_config: Type configuration for this content

        Returns:
            Path to the generated JSON AST file

        """
        json_node = sanitize_path(self.build_dir, rel_stem.with_suffix(".json"))

        compile_defaults = self._get_merged_defaults(
            self.config.defaults,
            type_config.defaults,
        )
        variables = {
            "in_shell": shell_quote(md_path),
            "out_shell": shell_quote(json_node),
        }
        implicit: list[Path] = []

        if compile_defaults:
            variables["defaults"] = self._format_defaults_var(compile_defaults)
            raw_deps: list[Path] = []
            data_dir = Path(self.config.pandoc_data_dir) if self.config.pandoc_data_dir else None
            for df in compile_defaults:
                raw_deps.append(df)
                raw_deps.extend(get_recursive_yaml_deps(df, data_dir_override=data_dir))
            implicit = sorted(set(raw_deps))

        self.emitter.build(
            outputs=json_node,
            rule=RuleName.COMPILE.value,
            inputs=md_path,
            implicit=implicit,
            variables=variables,
        )
        return json_node
