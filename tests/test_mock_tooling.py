import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from dojo.cli import main


@pytest.fixture
def mock_tool_path():
    return str(Path(__file__).parent / "scripts" / "mock_tool.py")


def test_build_with_failing_pandoc(tmp_path, mock_tool_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    (project / "content").mkdir()
    (project / "content" / "index.md").write_text("# Test")

    defaults_path = project / "defaults.yaml"
    defaults_path.write_text("standalone: true")

    # Create a config that uses our mock_tool as pandoc
    config_path = project / "dojo.yaml"
    # We use sys.executable and the path to mock_tool.py to be platform independent
    mock_cmd = f"{sys.executable} {mock_tool_path}"

    config_path.write_text(f"""
src_dir: content
output_dir: _site
build_dir: _build
default_type: page
tools:
  pandoc: {mock_cmd}
types:
  page:
    outputs:
      - id: html
        extension: html
        defaults: {defaults_path}
""")

    # Change CWD to project
    monkeypatch.chdir(project)

    # Mock shutil.which to return our mock tool string if it matches
    with patch("shutil.which", side_effect=lambda x: x if "mock_tool" in x else "/usr/bin/echo"):
        main(["build", "-c", "dojo.yaml"])

    build_ninja = project / "_build" / "build.ninja"
    assert build_ninja.exists()

    # Now run ninja with the failing mock tool
    # Set environment variable to make it fail
    env = os.environ.copy()
    env["MOCK_TOOL_EXIT"] = "1"
    env["MOCK_TOOL_STDOUT"] = "Pandoc Error: Simulated failure"
    env["PYTHONUNBUFFERED"] = "1"

    result = subprocess.run(
        ["ninja", "-f", "build.ninja"],
        cwd=project / "_build",
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    # Verify that ninja reported failure (meaning dojo wrap propagated the exit code)
    assert result.returncode != 0


def test_wrap_log_file_redirection(tmp_path, mock_tool_path, monkeypatch):
    """Verify that dojo wrap correctly redirects output to a log file."""
    log_file = tmp_path / "dojo.log"
    # We want to test dojo wrap directly
    from dojo.wrap import run_wrap

    env = os.environ.copy()
    env["MOCK_TOOL_STDOUT"] = "Log this message"
    monkeypatch.setitem(os.environ, "MOCK_TOOL_STDOUT", "Log this message")

    argv = ["--log-file", str(log_file), "--", sys.executable, mock_tool_path]

    with patch("sys.exit"):
        run_wrap(argv)

    assert log_file.exists()
    assert "Log this message" in log_file.read_text()
