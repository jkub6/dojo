import shutil
import subprocess
from pathlib import Path

import pytest

from dojo.deps import (
    resolve_glob_dependencies,
    scan_css_dependencies,
    scan_html_dependencies,
)
from dojo.utils import get_recursive_yaml_deps

# =============================================================================
# UNIT TESTS: dojo.deps (Asset Discovery Logic)
# =============================================================================


def test_resolve_glob_dependencies(tmp_path):
    """Verify glob pattern resolution for assets."""
    base_dir = tmp_path / "base"
    base_dir.mkdir()

    # Create some files matching and not matching
    (base_dir / "file1.txt").touch()
    (base_dir / "file2.txt").touch()

    subdir = base_dir / "subdir"
    subdir.mkdir()
    (subdir / "target.png").touch()
    (subdir / "ignore.jpg").touch()

    # Nested dir to test recursive glob
    deepdir = subdir / "deep"
    deepdir.mkdir()
    (deepdir / "target.png").touch()

    # Should resolve basic files
    deps = resolve_glob_dependencies(base_dir, ["*.txt", "subdir/*.png", "**/*.png"])

    assert base_dir / "file1.txt" in deps
    assert base_dir / "file2.txt" in deps
    assert subdir / "target.png" in deps
    assert deepdir / "target.png" in deps

    # Should not include ignore.jpg or directories
    assert subdir / "ignore.jpg" not in deps
    assert subdir not in deps


def test_scan_css_dependencies(tmp_path):
    """Verify recursive discovery of assets in CSS files."""
    # Setup test file
    css_file = tmp_path / "style.css"
    css_content = """
    @import url('fonts.css');
    body {
        background-image: url("bg.png");
    }
    .icon {
        mask-image: url(icon.svg);
    }
    .external {
        background: url(https://example.com/ext.png);
    }
    .data-uri {
        background: url(data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==);
    }
    """
    css_file.write_text(css_content)

    # Create target files so they exist
    (tmp_path / "fonts.css").touch()
    (tmp_path / "bg.png").touch()
    (tmp_path / "icon.svg").touch()

    # Run scan
    assets = scan_css_dependencies(css_file)

    assert tmp_path / "fonts.css" in assets
    assert tmp_path / "bg.png" in assets
    assert tmp_path / "icon.svg" in assets
    assert len(assets) == 3  # noqa: PLR2004


def test_scan_css_dependencies_missing_file_ignored(tmp_path):
    """Missing files referenced in CSS should be gracefully ignored by the scanner."""
    css_file = tmp_path / "style.css"
    css_file.write_text("body { background: url('missing.png'); }")

    assets = scan_css_dependencies(css_file)
    assert assets == []


def test_scan_html_dependencies(tmp_path):
    """Verify recursive discovery of assets in HTML files."""
    html_file = tmp_path / "index.html"
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <link rel="stylesheet" href="style.css">
        <link rel="icon" href='favicon.ico' />
    </head>
    <body>
        <img src="image.jpg" alt="test">
        <script src='script.js'></script>

        <!-- Should be ignored -->
        <a href="https://example.com">Link</a>
        <a href="mailto:test@user.com">Mail</a>
        <a href="#section">Hash</a>
        <img src="data:image/png;base64,123">
    </body>
    </html>
    """
    html_file.write_text(html_content)

    # Create target files
    (tmp_path / "style.css").touch()
    (tmp_path / "favicon.ico").touch()
    (tmp_path / "image.jpg").touch()
    (tmp_path / "script.js").touch()

    assets = scan_html_dependencies(html_file)

    assert tmp_path / "style.css" in assets
    assert tmp_path / "favicon.ico" in assets
    assert tmp_path / "image.jpg" in assets
    assert tmp_path / "script.js" in assets
    assert len(assets) == 4  # noqa: PLR2004


def test_scan_html_dependencies_malformed_ignored(tmp_path, caplog):
    """Errors reading HTML files should be logged and ignored."""
    import logging

    html_file = tmp_path / "bad.html"
    # Testing graceful skip when file physically doesn't exist
    with caplog.at_level(logging.WARNING, logger="dojo.deps"):
        assets = scan_html_dependencies(html_file)
    assert assets == []
    assert "Could not read HTML file" in caplog.text


def test_scan_css_dependencies_malformed_ignored(tmp_path, caplog):
    """Errors reading CSS files should be logged and ignored."""
    import logging

    css_file = tmp_path / "bad.css"
    with caplog.at_level(logging.WARNING, logger="dojo.deps"):
        assets = scan_css_dependencies(css_file)
    assert assets == []
    assert "Could not read CSS file" in caplog.text


# =============================================================================
# UNIT TESTS: dojo.utils (YAML/Defaults Resolution)
# =============================================================================


def test_get_recursive_yaml_deps_resolves_relative_paths(tmp_path, monkeypatch):
    """Verify asset resolution in defaults file.

    Verify that assets (css, bibliography) referenced in a defaults file
    are resolved relative to the CWD (Pandoc executable location), not the defaults file.
    """
    monkeypatch.chdir(tmp_path)

    # Create the referenced asset in the base directory (CWD)
    style_css = tmp_path / "style.css"
    style_css.touch()

    # Create the defaults file in a subdirectory
    defaults_dir = tmp_path / "defaults"
    defaults_dir.mkdir()
    page_yaml = defaults_dir / "page.yaml"

    # Reference style.css (if it was relative to page.yaml, it would be '../style.css')
    # But now it's relative to CWD, so it's just 'style.css'
    page_yaml.write_text("css:\n  - style.css", encoding="utf-8")

    # Run the function
    deps = get_recursive_yaml_deps(page_yaml)

    # Expectation: The resolved path to style.css should be in deps
    assert style_css.resolve() in deps


def test_get_recursive_yaml_deps_list_defaults(tmp_path):
    """Verify that 'defaults' can be a list of files."""
    root = tmp_path / "root.yaml"
    d1 = tmp_path / "d1.yaml"
    d2 = tmp_path / "d2.yaml"

    d1.write_text("foo: 1", encoding="utf-8")
    d2.write_text("bar: 2", encoding="utf-8")
    root.write_text(f"defaults:\n  - {d1}\n  - {d2}", encoding="utf-8")

    deps = get_recursive_yaml_deps(root)
    assert d1.resolve() in deps
    assert d2.resolve() in deps
    assert len(deps) == 2  # noqa: PLR2004


def test_get_recursive_yaml_deps_assets_extraction(tmp_path, monkeypatch):
    """Verify extraction of various asset keys from YAML."""
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "root.yaml"

    # Create assets
    assets = {
        "style.css": "css",
        "bib.bib": "bibliography",
        "style.csl": "csl",
        "tmpl.html": "template",
        "before.md": "include-before",
        "after.md": "include-after",
    }
    for name in assets:
        (tmp_path / name).touch()

    # Create YAML referencing them
    content = "\n".join([f"{key}: {name}" for name, key in assets.items()])
    root.write_text(content, encoding="utf-8")

    deps = get_recursive_yaml_deps(root)

    for name in assets:
        assert (tmp_path / name).resolve() in deps


def test_get_recursive_yaml_deps_complex_data_dir(tmp_path, monkeypatch):
    """Verify data-dir overrides and fallback logic in recursive resolution."""
    monkeypatch.chdir(tmp_path)

    data1 = tmp_path / "data1"
    data1.mkdir()
    data2 = tmp_path / "data2"
    data2.mkdir()
    (data2 / "defaults").mkdir()

    root = tmp_path / "root.yaml"
    child = data1 / "child.yaml"
    leaf = data2 / "defaults" / "leaf.yaml"
    leaf.touch()

    root.write_text(f"defaults: {child}", encoding="utf-8")
    # child.yaml points to 'leaf' which should be found in data-dir/defaults/
    child.write_text(f"data-dir: {data2}\ndefaults: leaf", encoding="utf-8")

    deps = get_recursive_yaml_deps(root)

    assert child.resolve() in deps
    assert leaf.resolve() in deps


# =============================================================================
# INTEGRATION TESTS: Lua Filters (Pandoc Execution)
# =============================================================================


def test_lua_dependencies_filter(tmp_path):
    """Verify dependencies.lua filter produces correct depfile content."""
    pandoc_exe = shutil.which("pandoc")
    if not pandoc_exe:
        pytest.skip("Pandoc not found")

    # Locate the filter relative to the source tree
    base_dir = Path(__file__).parent.parent
    filter_path = base_dir / "src/dojo/resources/dependencies.lua"

    if not filter_path.exists():
        pytest.fail(f"Lua filter not found at {filter_path}")

    # Setup content
    content_md = tmp_path / "test.md"
    content_md.write_text(
        "---\ndependencies:\n  - data_folder/\n---\n![Img](image.png)",
        encoding="utf-8",
    )

    # Setup data folder
    data_folder = tmp_path / "data_folder"
    data_folder.mkdir()
    (data_folder / "data.csv").touch()

    depfile = tmp_path / "test.d"
    output_json = tmp_path / "test.json"

    # Run Pandoc
    cmd = [
        pandoc_exe,
        str(content_md),
        "-t",
        "json",
        "-o",
        str(output_json),
        "-M",
        f"depfile={depfile}",
        "-M",
        f"target={output_json}",
        "--lua-filter",
        str(filter_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=tmp_path, check=False)
    assert result.returncode == 0, f"Pandoc failed: {result.stderr}"

    # Check depfile content
    assert depfile.exists()
    content = depfile.read_text("utf-8")

    # Ninja depfile format: target: dep1 dep2 ...
    assert str(output_json) + ":" in content
    assert "image.png" in content
    assert "data_folder/data.csv" in content
