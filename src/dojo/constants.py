"""Global constants and enumerations for the Dojo project.

Defines shared identifiers for build rules, configuration defaults,
and internal system paths.
"""

from enum import StrEnum


class RuleName(StrEnum):
    """Ninja rule names to avoid magic strings."""

    REGENERATE = "regenerate"
    COMPILE = "compile"
    RENDER = "render"
    COPY = "copy"
    MINIFY = "minify"
    GHOSTSCRIPT = "ghostscript"
    DECKTAPE = "decktape"
    STAMP = "stamp"


# Asset keys that implicitly reference files that should be tracked/copied
ASSET_KEYS = [
    "css",
    "bibliography",
    "csl",
    "template",
    "include-before",
    "include-after",
    "metadata-files",
]
