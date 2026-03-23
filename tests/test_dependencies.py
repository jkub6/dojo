import shutil
import subprocess
from pathlib import Path

import pytest

from dojo.utils import get_recursive_yaml_deps

# -----------------------------------------------------------------------------
# Unit Test: CSS/Asset Path Resolution in Utils
# -----------------------------------------------------------------------------


def test_get_recursive_yaml_deps_resolves_relative_paths(tmp_path, monkeypatch):
    """Verify asset resolution in defaults file.

    Verify that assets (css, bibliography) referenced in a defaults file
    are resolved relative to the CWD (Pandoc executable location), not the defaults file.
    """
    # Layout:
    # /work (CWD)
    #   style.css
    #   subdir/
    #     page.yaml  --> css: style.css (should resolve to /work/style.css)

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


# -----------------------------------------------------------------------------
# Integration Test: Lua Filter via Pandoc
# -----------------------------------------------------------------------------


def test_lua_dependencies_filter(tmp_path):
    """Verify dependencies.lua filter.

    Run pandoc with the dependencies.lua filter to verify it produces
    the correct depfile content for images and folder inputs.
    """
    pandoc_exe = shutil.which("pandoc")
    if not pandoc_exe:
        pytest.skip("Pandoc not found")

    # Locate the filter relative to the installed package location
    # Since we are running tests, we assume source is in PYTHONPATH or we find it relative to here
    # Best guess for test environment:
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
    # We expect:
    # test.json: ... image.png ... data_folder/data.csv ...

    assert str(output_json) + ":" in content
    assert "image.png" in content
    assert "data_folder/data.csv" in content


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
    assert len(deps) == 2


def test_get_recursive_yaml_deps_assets_extraction(tmp_path, monkeypatch):
    """Verify extraction of various asset keys."""
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
    """Verify data-dir overrides and fallback logic.
    
    Structure:
    /root.yaml (defaults: child.yaml)
    /data1/child.yaml (defaults: leaf.yaml, data-dir: /data2)
    /data2/defaults/leaf.yaml
    """
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
