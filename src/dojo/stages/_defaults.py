"""Shared helpers for defaults file handling across pipeline stages."""

from __future__ import annotations

from pathlib import Path

from dojo.paths import ninja_escape


def merge_defaults(*sources: str | list[str] | None) -> list[Path]:
    """Merge default files from multiple sources and return absolute paths."""
    merged = []
    for src in sources:
        if not src:
            continue
        if isinstance(src, str):
            merged.append(Path(src))
        else:
            merged.extend(Path(s) for s in src)
    return merged


def format_defaults_var(defaults: list[Path]) -> str:
    """Format list of defaults into ninja variable string."""
    if not defaults:
        return ""
    return "-d " + " -d ".join(ninja_escape(d) for d in defaults)
