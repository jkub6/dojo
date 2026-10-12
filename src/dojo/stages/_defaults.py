"""Shared helpers for defaults file handling across pipeline stages."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from dojo.config import OutputConfig

from dojo.defaults import materialize_defaults
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
    project_root: Path | None = None,
    build_dir: Path | None = None,
    cache: dict[tuple[Path, ...], tuple[str, tuple[Path, ...]]] | None = None,
    pandoc: str = "pandoc",
) -> tuple[str, list[Path]]:
    """Resolve all dependencies for a build stage.

    Args:
        project_root: Project directory for relative resource references.
        build_dir: Directory for normalized execution defaults.
        pandoc: Executable used to resolve builtin partials.
        cache: Optional generation-scoped memoization, never shared between builds.
        *sources: Default files or lists of default files to merge.
        pandoc_data_dir: Optional data directory for recursive lookup.

    Returns:
        A tuple of (ninja_defaults_string, list_of_implicit_dependency_paths).

    """
    defaults = merge_defaults(*sources)
    if not defaults:
        return "", []
    key = tuple(defaults)
    if cache is not None and key in cache:
        saved_defaults, saved_inputs = cache[key]
        return saved_defaults, list(saved_inputs)

    resolved = (
        [
            materialize_defaults(
                path,
                project_root or Path.cwd(),
                Path(pandoc_data_dir) if pandoc_data_dir else None,
                build_dir / "defaults",
            )
            for path in defaults
        ]
        if build_dir
        else defaults
    )
    defaults_var = format_defaults_var(resolved)

    raw_deps: list[Path] = list(resolved)
    data_dir = Path(pandoc_data_dir) if pandoc_data_dir else None

    for df in defaults:
        raw_deps.append(df)
        raw_deps.extend(
            get_recursive_yaml_deps(
                df, data_dir_override=data_dir, root=project_root, pandoc=pandoc
            )
        )

    implicit = sorted(set(raw_deps))
    if cache is not None:
        cache[key] = defaults_var, tuple(implicit)
    return defaults_var, implicit


def consumes_assets(
    output: OutputConfig, *, project_root: Path | None = None, data_dir: Path | None = None
) -> bool:
    """Conservatively invalidate tools that bake copied resources into their output."""
    if output.consumes_assets is not None:
        return output.consumes_assets
    if output.source is not None or output.extension.lower() != "html":
        return True
    if output.args and any(arg in {"--embed-resources", "--self-contained"} for arg in output.args):
        return True
    # Execution defaults have already been normalized by graph generation. Walk
    # originals through the same dependency resolver so inherited settings count.
    for path in merge_defaults(output.defaults):
        for dependency in [
            path,
            *get_recursive_yaml_deps(path, root=project_root, data_dir_override=data_dir),
        ]:
            if dependency.suffix in {".yaml", ".yml"}:
                data = yaml.safe_load(dependency.read_text())
                if isinstance(data, dict) and (
                    data.get("embed-resources") or data.get("self-contained")
                ):
                    return True
    return False
