from pathlib import Path
from unittest.mock import patch

import pytest

from dojo.exceptions import CircularDependencyError, SecurityError
from dojo.paths import ninja_escape, sanitize_path
from dojo.yaml_utils import (
    get_frontmatter_assets,
    get_recursive_yaml_deps,
    parse_frontmatter,
    parse_frontmatter_type,
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
    with pytest.raises(SecurityError, match="Path traversal detected"):
        sanitize_path(base, Path("../outside.txt"))

    with pytest.raises(SecurityError, match="Path traversal detected"):
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
    expected_deps_count = 2
    assert len(deps) == expected_deps_count


def test_circular_deps(tmp_path):
    a = tmp_path / "a.yaml"
    b = tmp_path / "b.yaml"

    with open(a, "w") as f:
        f.write(f"defaults: {b}")

    with open(b, "w") as f:
        f.write(f"defaults: {a}")

    with pytest.raises(CircularDependencyError, match="Circular dependency detected"):
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


def test_recursive_yaml_deps_missing_file(tmp_path):
    a = tmp_path / "missing.yaml"
    deps = get_recursive_yaml_deps(a)
    assert deps == []


def test_recursive_yaml_deps_invalid_yaml(tmp_path, caplog):
    a = tmp_path / "invalid.yaml"
    a.write_text("invalid: [")

    deps = get_recursive_yaml_deps(a)
    assert deps == []
    assert "Error reading" in caplog.text


def test_recursive_yaml_deps_missing_ref(tmp_path, caplog):
    a = tmp_path / "a.yaml"
    a.write_text("defaults: [missing.yaml]")

    deps = get_recursive_yaml_deps(a)
    # Should warn but not fail
    assert deps == []
    assert "Default file referenced" in caplog.text


def test_parse_frontmatter_exception(tmp_path, caplog):
    f = tmp_path / "test.md"
    f.touch()

    # Create a situation where yaml loading fails violently or file read fails in a way caught by generic exception
    # Mocking open might be easiest but we are inside a context manager in implementation
    with patch("builtins.open", side_effect=OSError("Read failed")):
        t = parse_frontmatter_type(f, "default")
        assert t == "default"
        assert "Could not parse frontmatter" in caplog.text


def test_sanitize_path_traversal_subdir(tmp_path):
    base = tmp_path / "base"
    base.mkdir()

    with pytest.raises(SecurityError, match="Path traversal detected"):
        sanitize_path(base, Path("subdir/../../outside.txt"))


def test_parse_frontmatter_no_end(tmp_path):
    """Test markdown with a starting --- but no end delimiter."""
    f = tmp_path / "test.md"
    f.write_text("---\ntitle: unterminated\nContent starts here", encoding="utf-8")

    # Implementation should return None if no closing --- is found
    assert parse_frontmatter(f) is None


def test_get_frontmatter_assets(tmp_path):
    """Test extraction of assets from markdown frontmatter."""
    f = tmp_path / "test.md"
    css_file = tmp_path / "style.css"
    css_file.touch()

    # Relative path in frontmatter should resolve relative to md file
    f.write_text("---\ncss:\n  - style.css\n---\n", encoding="utf-8")

    assets = get_frontmatter_assets(f)
    assert css_file.resolve() in assets
    assert len(assets) == 1


def test_get_frontmatter_assets_nested(tmp_path):
    """Test extraction of assets from markdown frontmatter in subdirectory."""
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    f = subdir / "test.md"
    css_file = tmp_path / "style.css"
    css_file.touch()

    # Reference parent dir asset
    f.write_text("---\ncss:\n  - ../style.css\n---\n", encoding="utf-8")

    assets = get_frontmatter_assets(f)
    assert css_file.resolve() in assets


def test_parse_frontmatter_empty_and_non_dict(tmp_path):
    """Test parse_frontmatter handles empty frontmatter block and non-dict frontmatter."""
    f_empty = tmp_path / "empty.md"
    f_empty.write_text("---\n\n---\n# Heading", encoding="utf-8")
    assert parse_frontmatter(f_empty) == {}

    f_non_dict = tmp_path / "scalar.md"
    f_non_dict.write_text("---\njust a scalar string\n---\n# Heading", encoding="utf-8")
    assert parse_frontmatter(f_non_dict) is None


def test_recursive_yaml_deps_diamond_and_metadata_files(tmp_path):
    """Test get_recursive_yaml_deps handles diamond dependencies and metadata-files."""
    root = tmp_path / "root.yaml"
    branch1 = tmp_path / "branch1.yaml"
    branch2 = tmp_path / "branch2.yaml"
    shared = tmp_path / "shared.yaml"
    shared.write_text("color: blue\n", encoding="utf-8")

    meta_file = tmp_path / "meta.yaml"
    meta_child = tmp_path / "meta_child.yaml"
    meta_child.write_text("tag: test\n", encoding="utf-8")
    meta_file.write_text(f"defaults: [{meta_child}]\n", encoding="utf-8")

    branch1.write_text(f"defaults: [{shared}]\n", encoding="utf-8")
    branch2.write_text(f"defaults: [{shared}]\n", encoding="utf-8")
    root.write_text(
        f"defaults:\n  - {branch1}\n  - {branch2}\nmetadata-files:\n  - {meta_file}\n",
        encoding="utf-8",
    )

    deps = get_recursive_yaml_deps(root)
    assert shared.resolve() in deps
    assert branch1.resolve() in deps
    assert branch2.resolve() in deps
    assert meta_child.resolve() in deps


def test_extract_paths_non_string_non_list():
    """Test extract_paths skips values that are neither strings nor lists."""
    from dojo.yaml_utils import extract_paths

    data = {"key_int": 123, "key_dict": {"nested": "value"}, "key_str": "path.txt"}
    paths = extract_paths(data, ["key_int", "key_dict", "key_str"])
    assert paths == ["path.txt"]
