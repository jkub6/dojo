"""Shared helpers for defaults file handling across pipeline stages."""

from __future__ import annotations

from pathlib import Path

from dojo.paths import ninja_escape, shell_quote
from dojo.yaml_utils import get_recursive_yaml_deps


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
    # Each defaults file must be shell-quoted, then the whole string ninja-escaped
    # to be safe for Ninja variable value.
    cmd_parts = [f"-d {shell_quote(d)}" for d in defaults]
    return " ".join(ninja_escape(p) for p in cmd_parts)


def resolve_stage_dependencies(
    *sources: str | list[str] | None,
    pandoc_data_dir: str | Path | None = None,
) -> tuple[str, list[Path]]:
    """Resolve all dependencies for a build stage.

    Args:
        *sources: Default files or lists of default files to merge.
        pandoc_data_dir: Optional data directory for recursive lookup.

    Returns:
        A tuple of (ninja_defaults_string, list_of_implicit_dependency_paths).

    """
    defaults = merge_defaults(*sources)
    if not defaults:
        return "", []

    defaults_var = format_defaults_var(defaults)

    raw_deps: list[Path] = []
    data_dir = Path(pandoc_data_dir) if pandoc_data_dir else None

    for df in defaults:
        raw_deps.append(df)
        raw_deps.extend(get_recursive_yaml_deps(df, data_dir_override=data_dir))

    implicit = sorted(set(raw_deps))
    return defaults_var, implicit
