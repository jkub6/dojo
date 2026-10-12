"""Compile stage: Markdown → JSON AST conversion.

This module handles the first stage of the build pipeline, converting
Markdown source files to Pandoc JSON AST format.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dojo.constants import RuleName
from dojo.paths import ninja_quote, sanitize_path
from dojo.stages._defaults import resolve_stage_dependencies

if TYPE_CHECKING:
    from pathlib import Path

    from dojo.config import Config, TypeConfig
    from dojo.emitter import NinjaEmitter
    from dojo.plugins import PluginInterface, PreparedInput

EXPECTED_HOOK_RESULT_SIZE = 2


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
        self.defaults_cache: dict[tuple[Path, ...], tuple[str, tuple[Path, ...]]] = {}

    def compile(
        self,
        md_path: Path,
        rel_stem: Path,
        type_config: TypeConfig,
        plugins: list[PluginInterface] | None = None,
        prepared: PreparedInput | None = None,
    ) -> Path:
        """Convert Markdown to JSON (Pandoc AST).

        Args:
            prepared: Declared plugin preparation products and metadata.
            md_path: Absolute path to source Markdown file
            rel_stem: Relative path without extension
            type_config: Type configuration for this content
            plugins: Optional list of loaded plugins

        Returns:
            Path to the generated JSON AST file

        """
        json_node = sanitize_path(self.build_dir, rel_stem.parent / (rel_stem.name + ".json"))

        defaults_var, implicit = resolve_stage_dependencies(
            self.config.defaults,
            type_config.defaults,
            pandoc_data_dir=self.config.pandoc_data_dir,
            project_root=self.config.project_root,
            build_dir=self.build_dir,
            cache=self.defaults_cache,
            pandoc=self.config.tools.pandoc,
        )

        variables = {}
        if defaults_var:
            variables["defaults"] = defaults_var

        variables.update(
            {
                "in_shell": ninja_quote(md_path),
                "out_shell": ninja_quote(json_node),
            }
        )

        if prepared:
            implicit.extend(prepared.inputs)
            metadata = " ".join(
                "-M " + ninja_quote(f"{key}={value}") for key, value in prepared.metadata.items()
            )
            variables["defaults"] = variables.get("defaults", "") + " " + metadata

        if plugins:
            for plugin in plugins:
                res = plugin.modify_compile_edge(
                    source=md_path,
                    rel_stem=rel_stem,
                    target_ast=json_node,
                    variables=variables,
                    implicit_deps=implicit,
                )
                if len(res) == EXPECTED_HOOK_RESULT_SIZE:
                    variables, implicit = res

        self.emitter.build(
            outputs=json_node,
            rule=RuleName.COMPILE.value,
            inputs=md_path,
            implicit=implicit,
            variables=variables,
        )
        return json_node
