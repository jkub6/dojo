"""YAML and frontmatter parsing utilities.

This module provides functions for parsing YAML files, extracting frontmatter
from Markdown files, and resolving YAML dependencies.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import cast

import yaml
from dojo.constants import ASSET_KEYS

from .exceptions import CircularDependencyError
from .resources import find_resource as _find_resource

logger = logging.getLogger(__name__)


def _recursive_expand(data: object, yaml_path: Path) -> object:
    """Recursively expand environment variables in data structure."""
    if isinstance(data, dict):
        return {
            k: _recursive_expand(v, yaml_path) for k, v in cast("dict[str, object]", data).items()
        }
    if isinstance(data, list):
        return [_recursive_expand(v, yaml_path) for v in data]
    if isinstance(data, str):
        return _expand_value(data, yaml_path)
    return data


def _expand_value(value: str, yaml_path: Path) -> str:
    """Expand ${.} and environment variables in string value."""
    # Matches \${VAR} (escaped) or ${VAR} (unescaped)
    pattern = re.compile(r"(\\)?\$\{([^}]+)\}")

    def repl(match: re.Match[str]) -> str:
        escape = match.group(1)
        var: str = match.group(2)
        if escape:
            # It was \${VAR}, return ${VAR} (unescaped)
            return f"${{{var}}}"

        # It was ${VAR}, expand it
        if var == ".":
            return str(yaml_path.parent)
        return os.environ.get(var, "")

    return pattern.sub(repl, value)


def _extract_paths(data: dict[str, object], keys: list[str]) -> list[str]:
    """Extract a list of paths from a dict for given keys."""
    paths = []
    for key in keys:
        val = data.get(key)
        if not val:
            continue
        if isinstance(val, str):
            paths.append(val)
        elif isinstance(val, list):
            paths.extend(str(v) for v in val)
    return paths


def _load_and_validate_yaml_dict(yaml_path: Path) -> dict[str, object] | None:
    """Safe load YAML and ensure it is a dict."""
    if not yaml_path.exists():
        return None

    try:
        with open(yaml_path, encoding="utf-8") as f:
            raw_data: object = yaml.safe_load(f)

        if not isinstance(raw_data, dict):
            return None

        # Expand environment variables and ${.}
        expanded_data = _recursive_expand(raw_data, yaml_path)
        return cast("dict[str, object]", expanded_data)

    except (OSError, yaml.YAMLError) as e:
        logger.warning("Error reading %s: %s", yaml_path, e)
        return None


def parse_frontmatter(md_path: Path) -> dict[str, object] | None:
    """Parse YAML frontmatter from a markdown file.

    Returns None if:
    - No frontmatter exists
    - Frontmatter is malformed
    - File cannot be read

    Efficiency: Only reads until the end of the frontmatter block.
    """
    try:
        with open(md_path, encoding="utf-8") as f:
            # Skip optional leading whitespace/newlines
            line = f.readline()
            while line and not line.strip():
                line = f.readline()
            
            if not line or line.strip() != "---":
                return None

            # Collect frontmatter content iteratively
            frontmatter_lines = []
            for line in f:
                stripped = line.strip()
                if stripped == "---":
                    break
                frontmatter_lines.append(line)
            else:
                # No closing --- found
                return None

            # Parse just the collected frontmatter
            frontmatter_text = "".join(frontmatter_lines)
            if not frontmatter_text.strip():
                return {}

            frontmatter_raw: object = yaml.safe_load(frontmatter_text)
            if not isinstance(frontmatter_raw, dict):
                return None

            return cast("dict[str, object]", frontmatter_raw)

    except (OSError, yaml.YAMLError) as e:
        logger.warning("Could not parse frontmatter in %s: %s", md_path, e)

    return None


def parse_frontmatter_type(md_path: Path, default_type: str) -> str:
    """Extract the 'type' field from YAML frontmatter.

    Returns default_type if:
    - No frontmatter exists
    - Frontmatter is malformed
    - No 'type' field is present

    This is a lightweight parser - only reads until end of frontmatter.
    """
    frontmatter = parse_frontmatter(md_path)
    if frontmatter and "type" in frontmatter:
        return str(frontmatter["type"]).strip()

    return default_type


def get_frontmatter_assets(md_path: Path) -> list[Path]:
    """Extract asset paths from markdown frontmatter."""
    frontmatter = parse_frontmatter(md_path)
    if not frontmatter:
        return []

    # Asset keys that implicitly reference files we might need to copy
    # We only care about assets that need to be present in the output directory
    # For now, let's focus on css, but others might be needed too.
    # Pandoc uses 'css' for stylesheets.
    # 'bibliography' and 'csl' are used for citation processing, not output assets usually?
    # Actually bibliography are read by pandoc, not linked in HTML (unless served?)
    # But files referenced in `css` definitely need to be served.
    asset_keys = ASSET_KEYS

    raw_assets = _extract_paths(frontmatter, asset_keys)

    assets = []
    for asset_ref in raw_assets:
        # Resolve relative to the markdown file
        asset_path = Path(asset_ref)
        if not asset_path.is_absolute():
            asset_path = md_path.parent / asset_path

        if asset_path.exists():
            assets.append(asset_path.resolve())

    return assets


def get_recursive_yaml_deps(
    yaml_path: Path,
    data_dir_override: Path | None = None,
    visited: set[Path] | None = None,
    stack: list[Path] | None = None,
) -> list[Path]:
    """Recursively scans YAML files for dependencies to build dependency lists for Ninja.

    Tracks:
    - 'defaults': Recursively scanned. Resolved relative to CWD or via data-dir.
    - 'css', 'bibliography', 'csl', 'template', 'include-before', 'include-after':
      Added as assets. Resolved relative to CWD (Pandoc's behavior).

    Args:
        yaml_path: Path to the root YAML file
        data_dir_override: Directory to use as data-dir for this file's direct references
        visited: Already processed files
        stack: Current recursion stack for cycle detection

    Returns:
        Deduplicated list of absolute Paths

    """
    if visited is None:
        visited = set()
    if stack is None:
        stack = []

    # Path should be absolute for reliable visiting/stack checks
    yaml_path = yaml_path.resolve()

    # Circular dependency detection
    if yaml_path in stack:
        cycle = " -> ".join(str(p) for p in [*stack, yaml_path])
        raise CircularDependencyError(cycle)

    if yaml_path in visited:
        return []

    deps: list[Path] = []
    visited.add(yaml_path)
    stack.append(yaml_path)

    try:
        data = _load_and_validate_yaml_dict(yaml_path)
        if not data:
            return []

        # Determine the data-dir for this file's references
        # 1. 'data-dir' variable in the file itself (highest priority)
        # 2. data_dir_override (from Dojo config or parent) - wait, user says:
        #    "each default file even when 'imported' by another will go back to XDG_DATA_DIR
        #     unless it has it's own data-dir variable set"
        # This means we DO NOT inherit data_dir_override for nested search of children.
        # But we DO use it for resolving refs IN this file if this file doesn't have its own.

        local_data_dir_val = cast("str | None", data.get("data-dir"))
        current_data_dirs = []
        if local_data_dir_val:
            current_data_dirs = [Path(local_data_dir_val).resolve()]
        elif data_dir_override:
            current_data_dirs = [data_dir_override]

        # 1. Handle Recursive Defaults
        defaults = _extract_paths(data, ["defaults"])
        _resolve_default_deps(defaults, yaml_path, current_data_dirs, deps, visited, stack)

        # 2. Handle Leaf Assets (CSS, templates, etc)
        # Pandoc behavior: relative paths are relative to CWD (executable location).
        asset_keys = ASSET_KEYS
        assets = _extract_paths(data, asset_keys)
        _resolve_assets(assets, deps)

    finally:
        stack.pop()

    return sorted(set(deps))


def _resolve_default_deps(  # noqa: PLR0913
    defaults: list[str],
    yaml_path: Path,
    current_data_dirs: list[Path],
    deps: list[Path],
    visited: set[Path],
    stack: list[Path],
) -> None:
    """Resolve default dependencies."""
    for default_ref in defaults:
        # Resolve the default file
        # Pandoc behavior: relative paths are relative to CWD.
        # Shorthand names are searched in data-dir/defaults/.
        found = _find_resource(
            "defaults",
            default_ref,
            root_contexts=[Path.cwd()],
            extra_data_dirs=current_data_dirs,
        )

        if found:
            deps.append(found)
            # Recurse. Nested files do NOT inherit our data_dir_override.
            deps.extend(get_recursive_yaml_deps(found, visited=visited, stack=stack[:]))
        else:
            logger.warning(
                "Default file referenced in %s not found: %s",
                yaml_path,
                default_ref,
            )


def _resolve_assets(assets: list[str], deps: list[Path]) -> None:
    """Resolve asset paths."""
    for asset_ref in assets:
        asset_path = Path(asset_ref)
        if not asset_path.is_absolute():
            asset_path = Path.cwd() / asset_path

        asset_path = asset_path.resolve()
        # We don't check if it exists here for assets as they might be build products,
        # but we add them to Ninja deps anyway if they seem to be local files.
        # However, for robustness, we only add them if they exist or look like they should.
        # The original code checked .exists().
        if asset_path.exists():
            deps.append(asset_path)

    return deps



