"""Example Plugin: Hello World.

This simple plugin demonstrates the basic plugin structure by adding
a comment to the generated Ninja file.

Usage:
    Add to dojo.yaml:

    plugins:
      - examples/plugins/hello_plugin.py
"""

from __future__ import annotations

from dojo.plugins import PluginInterface


class HelloPlugin(PluginInterface):
    """Simple plugin that adds a greeting comment to Ninja output.

    This serves as a minimal example for plugin development.
    See docs/PLUGINS.md for more advanced examples.
    """

    priority = 100  # Default priority

    def post_process_ninja(self, ninja_content: str) -> str:
        """Add a greeting comment to the top of the Ninja file.

        Args:
            ninja_content: Original Ninja file content

        Returns:
            Modified content with greeting prepended

        """
        greeting = "# 👋 Hello from HelloPlugin!\n"
        return greeting + ninja_content
