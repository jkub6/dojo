import os
import subprocess
import sys

import pytest


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


def test_build_command_subprocess(temp_project):
    """Test the full build command execution via subprocess (Integration)."""
    project_dir, config_path = temp_project

    # Run dojo build
    # We use sys.executable to ensure we use the same python interpreter
    # We assume 'dojo' package is in PYTHONPATH (e.g. src)
    env = os.environ.copy()
    # Add src to PYTHONPATH if not already potentially set by test runner
    src_path = os.path.abspath("src")
    if "PYTHONPATH" in env:
        env["PYTHONPATH"] = f"{src_path}:{env['PYTHONPATH']}"
    else:
        env["PYTHONPATH"] = src_path

    result = subprocess.run(
        [sys.executable, "-m", "dojo", "build", "-c", str(config_path)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(project_dir),
        check=False,
    )

    assert result.returncode == 0, f"Build failed: {result.stderr}"
    assert (
        "Build configuration generated successfully" in result.stdout
        or "Build configuration generated successfully" in result.stderr
    )

    # Check if build.ninja was created
    build_ninja = project_dir / "_build" / "build.ninja"
    assert build_ninja.exists()
    assert "rule compile" in build_ninja.read_text()


def test_cli_version_subprocess():
    """Test version command via subprocess."""
    env = os.environ.copy()
    src_path = os.path.abspath("src")
    if "PYTHONPATH" in env:
        env["PYTHONPATH"] = f"{src_path}:{env['PYTHONPATH']}"
    else:
        env["PYTHONPATH"] = src_path

    result = subprocess.run(
        [sys.executable, "-m", "dojo", "--version"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0
    assert "dojo" in result.stdout or "dojo" in result.stderr


def test_build_no_config_subprocess(tmp_path):
    """Test failure when no config found via subprocess."""
    env = os.environ.copy()
    src_path = os.path.abspath("src")
    if "PYTHONPATH" in env:
        env["PYTHONPATH"] = f"{src_path}:{env['PYTHONPATH']}"
    else:
        env["PYTHONPATH"] = src_path

    # Run in empty temp dir
    result = subprocess.run(
        [sys.executable, "-m", "dojo", "build"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_path),
        check=False,
    )

    assert result.returncode != 0
    assert "Error" in result.stdout or "Error" in result.stderr
