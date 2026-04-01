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
from dojo.stages._defaults import resolve_stage_dependencies

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

        defaults_var, implicit = resolve_stage_dependencies(
            self.config.defaults,
            type_config.defaults,
            pandoc_data_dir=self.config.pandoc_data_dir,
        )

        variables = {}
        if defaults_var:
            variables["defaults"] = defaults_var

        variables.update(
            {
                "in_shell": ninja_escape(shell_quote(md_path)),
                "out_shell": ninja_escape(shell_quote(json_node)),
            }
        )

        self.emitter.build(
            outputs=json_node,
            rule=RuleName.COMPILE.value,
            inputs=md_path,
            implicit=implicit,
            variables=variables,
        )
        return json_node
