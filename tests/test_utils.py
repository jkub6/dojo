from pathlib import Path

import pytest

from dojo.utils import (
    get_recursive_yaml_deps,
    ninja_escape,
    parse_frontmatter_type,
    sanitize_path,
)


def test_ninja_escape():
    assert ninja_escape(Path("simple/path")) == "simple/path"
    assert ninja_escape(Path("path with spaces")) == "path$ with$ spaces"
    assert ninja_escape(Path("path:with:colons")) == "path$:with$:colons"
    assert ninja_escape(Path("path$with$dollars")) == "path$$with$$dollars"
    assert (
        ninja_escape(Path("complex/path with/spaces:and$stuff"))
        == "complex/path$ with/spaces$:and$$stuff"
    )


def test_sanitize_path(tmp_path):
    base = tmp_path / "base"
    base.mkdir()

    # Valid paths
    assert sanitize_path(base, Path("file.txt")) == base / "file.txt"
    assert sanitize_path(base, Path("subdir/file.txt")) == base / "subdir" / "file.txt"

    # Traversal attempts
    with pytest.raises(ValueError, match="Path traversal detected"):
        sanitize_path(base, Path("../outside.txt"))

    with pytest.raises(ValueError, match="Path traversal detected"):
        sanitize_path(base, Path("subdir/../../outside.txt"))


def test_get_recursive_yaml_deps(tmp_path):
    # Setup files
    root = tmp_path / "root.yaml"
    dep1 = tmp_path / "dep1.yaml"
    dep2 = tmp_path / "dep2.yaml"

    with open(root, "w") as f:
        f.write(f"defaults: {dep1}")

    with open(dep1, "w") as f:
        f.write(f"defaults: {dep2}")

    with open(dep2, "w") as f:
        f.write("foo: bar")

    # Test recursion
    deps = get_recursive_yaml_deps(root)
    assert dep1 in deps
    assert dep2 in deps
    assert len(deps) == 2


def test_circular_deps(tmp_path):
    a = tmp_path / "a.yaml"
    b = tmp_path / "b.yaml"

    with open(a, "w") as f:
        f.write(f"defaults: {b}")

    with open(b, "w") as f:
        f.write(f"defaults: {a}")

    with pytest.raises(ValueError, match="Circular dependency detected"):
        get_recursive_yaml_deps(a)


def test_frontmatter_with_whitespace(tmp_path):
    """Test that frontmatter is detected even with leading whitespace."""
    f = tmp_path / "test.md"
    content = """
    ---
    type: slide
    ---
    # Content
    """
    # Write with leading newline/spaces (simulating user error)
    with open(f, "w") as file:
        file.write(content)

    assert parse_frontmatter_type(f, "default") == "slide"
