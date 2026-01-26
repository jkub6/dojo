from enum import Enum


class RuleName(str, Enum):
    """Ninja rule names to avoid magic strings."""

    REGENERATE = "regenerate"
    COMPILE = "compile"
    RENDER = "render"
    MINIFY = "minify"
    GHOSTSCRIPT = "ghostscript"
    DECKTAPE = "decktape"


class PoolName(str, Enum):
    """Ninja pool names to avoid magic strings."""

    HEAVY_PROCESSING = "heavy_processing"
