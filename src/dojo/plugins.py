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
    from .config import CustomRule, OutputConfig

logger = logging.getLogger(__name__)


class PluginInterface:
    """Base interface for plugins.

    Plugins can modify the build process by:
    - Adding custom Ninja rules
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

    def modify_output_config(self, output_config: OutputConfig, _content_type: str) -> OutputConfig:
        """Modify output configuration before processing.

        Args:
            output_config: Original output configuration
            content_type: Content type being processed

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


def load_plugin(plugin_path: str) -> PluginInterface | None:
    """Dynamically load a plugin from a Python file.

    Args:
        plugin_path: Path to plugin Python file

    Returns:
        Plugin instance or None if loading fails

    """
    try:
        path = Path(plugin_path).resolve()
        if not path.exists():
            logger.error("Plugin file not found: %s", path)
            return None

        spec = importlib.util.spec_from_file_location("plugin", path)
        if spec is None or spec.loader is None:
            logger.error("Failed to load plugin spec: %s", path)
            return None

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Look for a class that inherits from PluginInterface
        for item_name in dir(module):
            item = cast("object", getattr(module, item_name))
            if (
                isinstance(item, type)  # type: ignore[misc]
                and issubclass(item, PluginInterface)
                and item is not PluginInterface
            ):
                logger.info("Loaded plugin: %s from %s", item_name, path)
                return item()

    except Exception:
        logger.exception("Failed to load plugin %s", plugin_path)
        return None

    else:
        logger.error("No PluginInterface implementation found in %s", path)
        return None
