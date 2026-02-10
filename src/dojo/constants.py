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


class PoolName(StrEnum):
    """Ninja pool names to avoid magic strings."""

    HEAVY_PROCESSING = "heavy_processing"
