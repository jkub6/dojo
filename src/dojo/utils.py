"""Utility functions for dojo build pipeline.

This module provides a unified re-export interface for backward compatibility.
The actual implementations are now organized into focused modules:

- paths: Path escaping, quoting, and security validation
- yaml_utils: YAML and frontmatter parsing, dependency tracking
- deps: CSS/HTML dependency scanning, glob resolution
"""

from __future__ import annotations

# Re-export all public APIs for backward compatibility
from .deps import (
    resolve_glob_dependencies,
    scan_css_dependencies,
    scan_html_dependencies,
)
from .paths import (
    ninja_escape,
    sanitize_path,
    shell_quote,
    should_process_file,
)
from .yaml_utils import (
    get_frontmatter_assets,
    get_recursive_yaml_deps,
    parse_frontmatter,
    parse_frontmatter_type,
)


__all__ = [
    "get_frontmatter_assets",
    "get_recursive_yaml_deps",
    "ninja_escape",
    "parse_frontmatter",
    "parse_frontmatter_type",
    "resolve_glob_dependencies",
    "sanitize_path",
    "scan_css_dependencies",
    "scan_html_dependencies",
    "shell_quote",
    "should_process_file",
]
