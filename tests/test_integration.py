import os
import sys
from unittest.mock import patch

import pytest

from dojo.cli import main


@pytest.fixture
def clean_cwd(tmp_path):
    """Run test in a clean directory."""
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(old_cwd)


@pytest.fixture
def temp_project(clean_cwd):
    """Create a temporary project structure for integration testing."""
    project_dir = clean_cwd

    content_dir = project_dir / "content"
    content_dir.mkdir()
    output_dir = project_dir / "_site"
    build_dir = project_dir / "_build"
    defaults_dir = project_dir / "defaults"
    defaults_dir.mkdir()

    # Create defaults file
    defaults_file = defaults_dir / "page.yaml"
    defaults_file.write_text("standalone: true\n")

    # Use absolute paths so dojo can find them regardless of CWD
    # We reference the defaults file we just created.
    config_content = f"""
src_dir: "{content_dir}"
output_dir: "{output_dir}"
build_dir: "{build_dir}"
default_type: "page"
types:
  page:
    outputs:
      - id: "html"
        extension: "html"
        defaults: "{defaults_file}"
"""
    config_path = project_dir / "dojo.yaml"
    config_path.write_text(config_content)

    (content_dir / "index.md").write_text("# Hello World\n\nThis is a test.")

    return config_path


def test_build_command(temp_project, capsys):
    """Test the full build command execution."""
    config_path = str(temp_project)
    with patch.object(sys, "argv", ["dojo", "build", "-c", config_path]):
        # Mocking sys.exit to prevent test exit if it calls it (it shouldn't on success?)
        # cli.py cmd_build doesn't explicitly exit 0 on success, it just ends.
        # But failure exits 1.
        try:
            main()
        except SystemExit as e:
            # If it exits with 0, that's fine (though current impl doesn't).
            # If it exits with 1, it failed.
            assert e.code == 0

    # logic in cmd_build:
    # generator.generate()
    # console.print("Build configuration generated successfully!")
    # No sys.exit(0) at the end.

    captured = capsys.readouterr()
    assert "Build configuration generated successfully" in captured.out


def test_cli_version(capsys):
    """Test that the version flag works."""
    with patch.object(sys, "argv", ["dojo", "--version"]):
        # main() calls cmd_version() then returns.
        main()
        captured = capsys.readouterr()
        assert "dojo" in captured.out or "dojo" in captured.err


def test_build_no_config(clean_cwd, capsys):
    """Test behavior when no config is found."""
    # clean_cwd ensures we are in a temp dir with no dojo.yaml

    with patch.object(sys, "argv", ["dojo", "build", "-c", "non_existent.yaml"]):
        with pytest.raises(SystemExit) as cm:
            main()
        assert cm.value.code == 1
