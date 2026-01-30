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
