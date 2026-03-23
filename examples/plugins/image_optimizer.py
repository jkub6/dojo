"""Example plugin: Image optimization for Dojo builds.

This plugin adds custom Ninja rules for optimizing PNG and JPEG images.
Enable in dojo.yaml:

    plugins:
      - examples/plugins/image_optimizer.py

Then use the rules in your output configurations or custom build scripts.
"""

from __future__ import annotations

import logging

from dojo.config import CustomRule
from dojo.plugins import PluginInterface

logger = logging.getLogger(__name__)


class ImageOptimizerPlugin(PluginInterface):
    """Add image optimization rules to the build.

    Provides two rules:
    - optimize_png: Optimize PNG images using optipng
    - optimize_jpeg: Optimize JPEG images using jpegoptim
    """

    # Run early to make rules available
    priority = 50

    def get_custom_rules(self) -> list[CustomRule]:
        """Add optimization rules for PNG and JPEG images."""
        logger.info("ImageOptimizerPlugin: Adding image optimization rules")

        return [
            CustomRule(
                name="optimize_png",
                command="optipng -o5 -quiet $in -out $out",
                description="🖼️  OPTIMIZE PNG $out",
            ),
            CustomRule(
                name="optimize_jpeg",
                command="jpegoptim --strip-all --max=85 --stdout $in > $out",
                description="🖼️  OPTIMIZE JPEG $out",
            ),
        ]
