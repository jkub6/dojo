"""Pipeline stages for the dojo build system.

This package contains the decomposed stages of the build pipeline:

- compile: Markdown → JSON AST conversion
- render: JSON → Output format (HTML, PDF, etc.)
- assets: Asset dependency tracking and copying
"""

from __future__ import annotations

from ._defaults import format_defaults_var, merge_defaults
from .assets import AssetProcessor
from .compile import CompileStage
from .render import RenderStage


__all__ = [
    "AssetProcessor",
    "CompileStage",
    "RenderStage",
    "format_defaults_var",
    "merge_defaults",
]
