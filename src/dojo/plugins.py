"""Plugin system and dynamic tool integration.

Handles the discovery and invocation of external tools and
post-processing filters.
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from .config import Config, CustomRule, OutputConfig

from .exceptions import PluginLoadError

logger = logging.getLogger(__name__)


class PluginInterface:
    """Base interface for plugins.

    Plugins can modify the build process by:
    - Running pre-generation preparation/indexing
    - Adding custom Ninja rules
    - Modifying compile and render build edges
    - Supplying extra output assets
    - Modifying output configurations
    - Post-processing the generated Ninja file

    Attributes:
        priority: Execution order (lower = earlier). Default is 100.
            Use 0-49 for validation/preprocessing, 50-99 for transformations,
            100 for default, 101-200 for post-processing.

    """

    # Default priority - plugins execute in this order
    priority: int = 100

    def get_custom_rules(self) -> list[CustomRule]:
        """Return custom Ninja rules to add.

        Returns:
            List of CustomRule objects

        """
        return []

    def pre_generate(
        self,
        config: Config,
        build_dir: Path,
        *,
        refresh: bool = False,
        src_dir: Path | None = None,
    ) -> None:
        """Pre-process configuration and state before scanning Markdown files.

        Args:
            config: Dojo build configuration
            build_dir: Directory where intermediate build artifacts live
            refresh: Whether to bypass plugin-level preparation caches
            src_dir: Source directory root (absolute)

        """

    def modify_compile_edge(
        self,
        source: Path,
        rel_stem: Path,
        target_ast: Path,
        variables: dict[str, str],
        implicit_deps: list[Path],
    ) -> tuple[dict[str, str], list[Path]]:
        """Modify compile edge variables and implicit dependencies for an AST compile edge.

        Args:
            source: Source Markdown path
            rel_stem: Relative path without extension
            target_ast: Intermediate AST JSON path
            variables: Ninja rule variables dictionary
            implicit_deps: List of implicit dependency paths

        Returns:
            Tuple of (modified_variables, modified_implicit_deps)

        """
        return variables, implicit_deps

    def modify_render_edge(
        self,
        source_ast: Path,
        rel_stem: Path,
        target_output: Path,
        variables: dict[str, str],
        implicit_deps: list[Path],
    ) -> tuple[dict[str, str], list[Path]]:
        """Modify render edge variables and implicit dependencies for an output render edge.

        Args:
            source_ast: Intermediate AST JSON path
            rel_stem: Relative path without extension
            target_output: Destination output path in output_dir
            variables: Ninja rule variables dictionary
            implicit_deps: List of implicit dependency paths

        Returns:
            Tuple of (modified_variables, modified_implicit_deps)

        """
        return variables, implicit_deps

    def get_extra_assets(self, config: Config, out_dir: Path) -> dict[Path, Path]:
        """Return extra asset mappings {destination: source} to copy to output.

        Args:
            config: Dojo build configuration
            out_dir: Absolute path to the output directory

        Returns:
            Mapping of destination Path to source Path

        """
        return {}

    def modify_output_config(self, output_config: OutputConfig, _content_type: str) -> OutputConfig:
        """Modify output configuration before processing.

        Args:
            output_config: Original output configuration
            _content_type: Content type being processed

        Returns:
            Modified output configuration

        """
        return output_config

    def post_process_ninja(self, ninja_content: str) -> str:
        """Post-process the generated Ninja file content.

        Args:
            ninja_content: Original Ninja file content

        Returns:
            Modified Ninja file content

        """
        return ninja_content


def load_plugin(plugin_path: str, base_dir: Path | None = None) -> PluginInterface:
    """Dynamically load a plugin from a Python file.

    Args:
        plugin_path: Path to plugin Python file
        base_dir: Optional base directory to resolve relative paths against

    Returns:
        Plugin instance

    Raises:
        PluginLoadError: If the plugin cannot be loaded for any reason

    """
    path = Path(plugin_path)
    if not path.is_absolute() and base_dir is not None:
        path = (base_dir / path).resolve()
    else:
        path = path.resolve()
    if not path.exists():
        raise PluginLoadError(plugin_path, f"file not found: {path}")

    spec = importlib.util.spec_from_file_location("plugin", path)
    if spec is None or spec.loader is None:
        raise PluginLoadError(plugin_path, f"failed to create import spec: {path}")

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        raise PluginLoadError(plugin_path, str(e)) from e

    # Look for a class that inherits from PluginInterface
    for item_name in dir(module):
        item = cast("object", getattr(module, item_name))
        if (
            isinstance(item, type)
            and issubclass(item, PluginInterface)
            and item is not PluginInterface
        ):
            logger.info("Loaded plugin: %s from %s", item_name, path)
            return item()

    raise PluginLoadError(plugin_path, f"no PluginInterface implementation found in {path}")
