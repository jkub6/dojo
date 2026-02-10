"""Dependency scanning utilities.

This module provides functions for scanning CSS and HTML files to discover
their dependencies (referenced assets), and for resolving glob patterns
to file paths.
"""

from __future__ import annotations

import glob
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def resolve_glob_dependencies(
    base_dir: Path,
    patterns: list[str],
) -> list[Path]:
    """Resolve a list of glob patterns to a list of absolute file paths.

    Args:
        base_dir: Directory to resolve patterns relative to
        patterns: List of glob patterns (e.g. ["./*", "assets/*.png"])

    Returns:
        List of absolute paths to existing files (directories are skipped)

    """
    resolved_paths: list[Path] = []

    for pattern in patterns:
        # Glob patterns are relative to base_dir
        # We need to construct a search path
        # glob.glob supports recursive ** if recursive=True is passed

        # If the pattern is absolute, warn and skip? Or treat as absolute?
        # Standard convention for deps is relative to the file.

        full_pattern = base_dir / pattern
        full_pattern_str = str(full_pattern)

        matches = glob.glob(full_pattern_str, recursive=True)

        for match in matches:
            path = Path(match).resolve()
            if path.is_file():
                resolved_paths.append(path)

    return sorted(set(resolved_paths))


def scan_css_dependencies(css_path: Path) -> list[Path]:
    """Scan a CSS file for url(...) dependencies.

    Returns:
        List of absolute paths to referenced assets.

    """
    assets: list[Path] = []
    try:
        content = css_path.read_text(encoding="utf-8")
    except OSError:
        logger.warning("Could not read CSS file: %s", css_path)
        return []

    # Regex to match url('...') url("...") or url(...)
    # Capture group 2 is quotes, group 3 is unquoted
    # Simple regex: url\(\s*(?:(["'])(.*?)\1|([^)]*))s*\)
    url_pattern = re.compile(r"url\(\s*(?:([\"'])(.*?)\1|([^)]*?))\s*\)", re.IGNORECASE)

    for match in url_pattern.finditer(content):
        # group 2 is quoted value, group 3 is unquoted value
        raw_val = match.group(2) or match.group(3)
        url_val = str(raw_val).strip() if raw_val else ""

        if not url_val:
            continue

        # Ignore data URIs and remote URLs
        if url_val.startswith(("data:", "http:", "https:")):
            continue

        # Resolve relative to CSS file
        asset_path = css_path.parent / url_val
        try:
            asset_path = asset_path.resolve()
            if asset_path.exists() and asset_path.is_file():
                assets.append(asset_path)
        except OSError:
            pass

    return assets


def scan_html_dependencies(html_path: Path) -> list[Path]:
    """Scan an HTML file for src and href dependencies.

    Note: This is a best-effort regex scanner to avoid adding a heavy HTML parser dependency.
    It looks for src="..." and href="..." references to local files.

    Returns:
        List of absolute paths to referenced assets.

    """
    assets: list[Path] = []
    try:
        content = html_path.read_text(encoding="utf-8")
    except OSError:
        logger.warning("Could not read HTML file: %s", html_path)
        return []

    # Matches src="..." src='...' href="..." href='...'
    # We want to match src or href, then = then quoted string.
    # Group 2 is the value.
    link_pattern = re.compile(r"(?:src|href)\s*=\s*(?:([\"'])(.*?)\1)", re.IGNORECASE)

    for match in link_pattern.finditer(content):
        raw_val = match.group(2)
        url_val = str(raw_val).strip() if raw_val else ""

        if not url_val:
            continue

        # Ignore invalid start characters for local files
        if url_val.startswith(("http:", "https:", "data:", "mailto:", "#")):
            continue

        # Resolve relative to HTML file
        asset_path = html_path.parent / url_val
        try:
            asset_path = asset_path.resolve()
            if asset_path.exists() and asset_path.is_file():
                assets.append(asset_path)
        except OSError:
            pass

    return assets
