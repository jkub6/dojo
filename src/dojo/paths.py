"""Path utilities for Ninja build file generation.

This module provides functions for path escaping, quoting, and security
validation used throughout the dojo build pipeline.
"""

from __future__ import annotations

import fnmatch
import shlex
from pathlib import Path

from .exceptions import SecurityError


def ninja_escape(path: Path | str) -> str:
    """Escape a path for Ninja build files.

    Ninja requires:
    - Spaces → '$ '
    - Colons → '$:'  (on non-Windows)
    - Dollar signs → '$$'
    - Always forward slashes
    """
    s = path.as_posix() if isinstance(path, Path) else str(path).replace("\\", "/")
    s = s.replace("$", "$$")
    s = s.replace(" ", "$ ")
    return s.replace(":", "$:")


def shell_quote(path: Path | str) -> str:
    """Quote a path for use in shell commands.

    Uses shlex.quote to safely escape the path for POSIX shells.
    """
    s = path.as_posix() if isinstance(path, Path) else path
    return shlex.quote(s)


def sanitize_path(base: Path, relative: Path) -> Path:
    """Sanitize a path to prevent traversal attacks.

    Args:
        base: Base directory that paths should remain within
        relative: Relative path to sanitize

    Returns:
        Sanitized absolute path

    Raises:
        SecurityError: If path traversal is detected

    """
    # Resolve to absolute path
    full_path = (base / relative).resolve()

    # Ensure the resolved path is within base
    try:
        full_path.relative_to(base.resolve())
    except ValueError:
        raise SecurityError(relative, base) from None

    return full_path


def should_process_file(
    path: Path,
    src_dir: Path,
    includes: list[str],
    excludes: list[str],
) -> bool:
    """Determine if a file should be processed based on include/exclude patterns.

    Args:
        path: Absolute path to the file
        src_dir: Absolute path to source directory
        includes: List of glob patterns to include (if empty, include all)
        excludes: List of glob patterns to exclude

    Returns:
        True if file should be processed

    """
    try:
        rel_path = path.relative_to(src_dir)
    except ValueError:
        # File not in source directory
        return False

    rel_str = str(rel_path.as_posix())

    # 1. Exclude Logic (Priority)
    if any(fnmatch.fnmatch(rel_str, pattern) for pattern in excludes):
        return False

    # 2. Include Logic
    if not includes:
        # Default: include everything not excluded
        return True

    # Check if matches ANY include pattern
    return any(fnmatch.fnmatch(rel_str, pattern) for pattern in includes)
