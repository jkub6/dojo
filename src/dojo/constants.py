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
    CRUNCH = "crunch"


# Asset keys that implicitly reference files that should be tracked/copied
ASSET_KEYS = [
    "css",
    "bibliography",
    "csl",
    "template",
    "filters",
    "lua-filter",
    "include-in-header",
    "include-before-body",
    "include-after-body",
    "reference-doc",
    "syntax-definition",
    "include-before",
    "include-after",
    "metadata-files",
    "abbreviations",
    "citation-abbreviations",
]

# Only these inputs are also linked publication assets.
PUBLIC_ASSET_KEYS = ["css"]
