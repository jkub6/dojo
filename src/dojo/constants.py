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


# Asset keys that implicitly reference files that should be tracked/copied
ASSET_KEYS = [
    "css",
    "bibliography",
    "csl",
    "template",
    "include-before",
    "include-after",
]
