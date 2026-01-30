from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

# Standard Pandoc data directory names
RESOURCE_CATEGORIES = {"defaults", "templates", "filters"}


def get_xdg_data_home() -> Path:
    """Get the XDG_DATA_HOME directory.

    Defaults to ~/.local/share if not set.
    """
    env_path = os.environ.get("XDG_DATA_HOME")
    if env_path:
        return Path(env_path).resolve()
    return Path.home() / ".local" / "share"


def get_pandoc_data_dirs(
    extra_data_dirs: list[Path] | None = None,
) -> list[Path]:
    """Get the list of directories where Pandoc looks for data files.

    Order is roughly:
    1. User specified data dirs (if any) - if specified, these OVERRIDE defaults.
    2. XDG_DATA_HOME/pandoc
    3. ~/.pandoc (legacy)
    """
    if extra_data_dirs:
        return [d.resolve() for d in extra_data_dirs if d.exists()]

    paths: list[Path] = []

    # XDG Data Home
    xdg_home = get_xdg_data_home()
    paths.append(xdg_home / "pandoc")

    # Legacy/Standard ~/.pandoc
    paths.append(Path.home() / ".pandoc")

    return [p for p in paths if p.exists()]


def find_resource(
    category: str,
    name: str,
    root_contexts: list[Path] | None = None,
    extra_data_dirs: list[Path] | None = None,
) -> Path | None:
    """Find a resource (file) by name in the specified category.

    Search precedence (based on Pandoc behavior):
    1. Exact path (if name contains directory separators or is absolute) inside CWD or root contexts.
    2. Data Directories (User XDG, System, and optionally CWD depending on category).
       Checks inside 'category' subdirectories.

    Args:
        category: "defaults", "templates", "filters"
        name: The resource name (e.g. "letter", "letter.yaml")
        root_contexts: Project directories to check. Usually just [cwd].
        extra_data_dirs: Additional data-dirs specified in config/cli

    Returns:
        Resolved absolute Path object or None if not found.

    """
    if category not in RESOURCE_CATEGORIES:
        raise ValueError(f"Unknown resource category: {category}")

    # 1. Exact Path Check
    # If it looks like a path, try it directly first
    path_check = _check_path_reference(name, root_contexts)
    if path_check is not False:
        return path_check  # Returns Path or None (if absolute and missing)

    # 2. Resource Name Resolution
    potential_names = _get_potential_names(name, category)

    # 3. Search Locations Construction
    search_roots = _get_search_roots(root_contexts, category, extra_data_dirs)

    # Execute Search
    for root in search_roots:
        for pname in potential_names:
            candidate = root / pname
            if candidate.exists() and candidate.is_file():
                return candidate.resolve()

    return None


def _check_path_reference(
    name: str, root_contexts: list[Path] | None
) -> Path | None | Literal[False]:
    """Check if name is an explicit path reference.

    Returns:
        Path: Found resource.
        None: Explicit failure (absolute path not found).
        False: Not a path reference or not found relative (continue search).

    """
    path_obj = Path(name)
    if path_obj.is_absolute():
        if path_obj.exists():
            return path_obj
        return None

    if len(path_obj.parts) > 1:
        # Relative path with separators (e.g. "foo/bar.yaml")
        cwd_path = Path.cwd() / path_obj
        if cwd_path.exists():
            return cwd_path.resolve()

        if root_contexts:
            for root in root_contexts:
                rel_path = root / path_obj
                if rel_path.exists():
                    return rel_path.resolve()

    return False


def _get_potential_names(name: str, category: str) -> list[str]:
    """Get list of potential filenames to search for."""
    potential_names = [name]
    if "." not in name and category == "defaults":
        potential_names.append(f"{name}.yaml")
    return potential_names


def _get_search_roots(
    root_contexts: list[Path] | None, category: str, extra_data_dirs: list[Path] | None
) -> list[Path]:
    """Get list of directories to search in."""
    search_roots = []

    # A. Root Contexts
    if root_contexts:
        for root in root_contexts:
            if not root.exists():
                continue
            search_roots.append(root)

    # B. XDG / Pandoc Data Dirs
    data_dirs = get_pandoc_data_dirs(extra_data_dirs)
    for dd in data_dirs:
        cat_dir = dd / category
        if cat_dir.exists():
            search_roots.append(cat_dir)

    return search_roots
