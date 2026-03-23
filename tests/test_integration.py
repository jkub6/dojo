
import pytest

from dojo.cli import main


@pytest.fixture
def temp_project(tmp_path):
    """Create a temporary project structure for integration testing."""
    project_dir = tmp_path

    content_dir = project_dir / "content"
    content_dir.mkdir()
    output_dir = project_dir / "_site"
    build_dir = project_dir / "_build"
    defaults_dir = project_dir / "defaults"
    defaults_dir.mkdir()

    # Create defaults file
    defaults_file = defaults_dir / "page.yaml"
    defaults_file.write_text("standalone: true\n")

    # Use absolute paths in config
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

    return project_dir, config_path


def test_build_command_in_process(temp_project, capsys):
    """Test the full build command execution in-process (Integration)."""
    project_dir, config_path = temp_project

    try:
        main(["build", "-c", str(config_path)])
    except SystemExit as exc:
        assert exc.code == 0

    captured = capsys.readouterr()
    assert "Build configuration generated successfully" in captured.out

    # Check if build.ninja was created
    build_ninja = project_dir / "_build" / "build.ninja"
    assert build_ninja.exists()
    assert "rule compile" in build_ninja.read_text()


def test_cli_version_in_process(capsys):
    """Test version command in-process."""
    # version command itself might not raise SystemExit if it just prints and returns
    # but cli.py uses argparse which might exit on some versions
    try:
        main(["--version"])
    except SystemExit as exc:
        assert exc.code == 0

    captured = capsys.readouterr()
    assert "dojo" in captured.out or "dojo" in captured.err


def test_build_no_config_in_process(tmp_path, capsys):
    """Test failure when no config found in-process."""
    # Run in empty temp dir
    import os

    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        with pytest.raises(SystemExit) as exc:
            main(["build"])
        assert exc.value.code != 0
    finally:
        os.chdir(old_cwd)

    captured = capsys.readouterr()
    assert "Error" in captured.out or "Error" in captured.err
