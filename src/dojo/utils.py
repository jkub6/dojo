import fnmatch
import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


def should_process_file(path: Path, src_dir: Path, includes: list[str], excludes: list[str]) -> bool:
    """
    Determine if a file should be processed based on include/exclude patterns.

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


def ninja_escape(path: Path) -> str:
    """
    Escape a path for Ninja build files.

    Ninja requires:
    - Spaces → '$ '
    - Colons → '$:'  (on non-Windows)
    - Dollar signs → '$$'
    - Always forward slashes
    """
    s = str(path.as_posix())
    s = s.replace("$", "$$")
    s = s.replace(" ", "$ ")
    s = s.replace(":", "$:")
    return s


def sanitize_path(base: Path, relative: Path) -> Path:
    """
    Sanitize a path to prevent traversal attacks.

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
        raise ValueError(f"Path traversal detected: {relative} escapes {base}") from None

    return full_path


def get_recursive_yaml_deps(
    yaml_path: Path, visited: set[Path] | None = None, stack: list[Path] | None = None
) -> list[Path]:
    """
    Recursively scans YAML files for 'defaults' keys to build dependency lists.

    This allows Ninja to track implicit dependencies - if a parent template changes,
    all outputs that use it are automatically rebuilt.

    Args:
        yaml_path: Path to YAML file to scan
        visited: Set of already-processed files (prevents infinite loops)
        stack: Current traversal stack (for circular dependency detection)

    Returns:
        List of all dependent YAML files

    Raises:
        ValueError: If a circular dependency is detected
    """
    if visited is None:
        visited = set()
    if stack is None:
        stack = []

    # Circular dependency detection
    if yaml_path in stack:
        cycle = " → ".join(str(p) for p in [*stack, yaml_path])
        raise ValueError(f"Circular dependency detected: {cycle}")

    # Already processed
    if yaml_path in visited:
        return []

    # File doesn't exist
    if not yaml_path.exists():
        return []

    deps: list[Path] = []
    visited.add(yaml_path)
    stack.append(yaml_path)

    try:
        with open(yaml_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data:
            return deps

        # Extract defaults (adjust this logic based on your YAML structure)
        raw_defaults = data.get("defaults", [])
        if isinstance(raw_defaults, str):
            raw_defaults = [raw_defaults]

        for default_ref in raw_defaults:
            dep_path = Path(default_ref)
            if dep_path.exists():
                deps.append(dep_path)
                # Recurse with updated stack
                deps.extend(get_recursive_yaml_deps(dep_path, visited, stack[:]))

    except ValueError:
        raise
    except yaml.YAMLError as e:
        logger.warning(f"Could not parse {yaml_path}: {e}")
    except Exception as e:
        logger.warning(f"Error processing {yaml_path}: {e}")
    finally:
        stack.pop()

    return deps


def parse_frontmatter_type(md_path: Path, default_type: str) -> str:
    """
    Extracts the 'type' field from YAML frontmatter.

    Returns default_type if:
    - No frontmatter exists
    - Frontmatter is malformed
    - No 'type' field is present

    This is a lightweight parser - only reads until end of frontmatter.
    """
    try:
        with open(md_path, encoding="utf-8") as f:
            # Check for frontmatter delimiter
            first_line = f.readline()
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
            frontmatter = yaml.safe_load(frontmatter_text)

            if frontmatter and "type" in frontmatter:
                return str(frontmatter["type"]).strip()

    except Exception as e:
        logger.warning(f"Could not parse frontmatter in {md_path}: {e}")
        logger.debug(f"Using default type: {default_type}")

    return default_type
