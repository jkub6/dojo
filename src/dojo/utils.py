import fnmatch
import logging
import os
import re
import shlex
from pathlib import Path
from typing import cast

import yaml

from .exceptions import CircularDependencyError, SecurityError
from .resources import find_resource

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


def ninja_escape(path: Path | str) -> str:
    """Escape a path for Ninja build files.

    Ninja requires:
    - Spaces → '$ '
    - Colons → '$:'  (on non-Windows)
    - Dollar signs → '$$'
    - Always forward slashes
    """
    s = path.as_posix() if isinstance(path, Path) else path
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
        ValueError: If path traversal is detected

    """
    # Resolve to absolute path
    full_path = (base / relative).resolve()

    # Ensure the resolved path is within base
    try:
        full_path.relative_to(base.resolve())
    except ValueError:
        raise SecurityError(relative, base) from None

    return full_path


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
        asset_keys = ["css", "bibliography", "csl", "template", "include-before", "include-after"]
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
        found = find_resource(
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


def parse_frontmatter_type(md_path: Path, default_type: str) -> str:
    """Extract the 'type' field from YAML frontmatter.

    Returns default_type if:
    - No frontmatter exists
    - Frontmatter is malformed
    - No 'type' field is present

    This is a lightweight parser - only reads until end of frontmatter.
    """
    try:
        with open(md_path, encoding="utf-8") as f:
            # Check for frontmatter delimiter
            first_line = ""
            for line in f:
                if line.strip():
                    first_line = line
                    break

            if first_line.strip() != "---":
                return default_type

            # Collect frontmatter content
            frontmatter_lines = []
            for line in f:
                if line.strip() == "---":
                    break
                frontmatter_lines.append(line)

            # Parse just the frontmatter
            frontmatter_text = "".join(frontmatter_lines)
            frontmatter_raw: object = yaml.safe_load(frontmatter_text)
            if not isinstance(frontmatter_raw, dict):
                return default_type
            frontmatter = cast("dict[str, object]", frontmatter_raw)

            if frontmatter and "type" in frontmatter:
                return str(frontmatter["type"]).strip()

    except (OSError, yaml.YAMLError) as e:
        logger.warning("Could not parse frontmatter in %s: %s", md_path, e)
        logger.debug("Using default type: %s", default_type)

    return default_type
