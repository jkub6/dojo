"""Regression tests for Ninja build caching.

Verifies that dojo does not unnecessarily update build files (mtime changes)
which would trigger Ninja to rebuild unchanged targets.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


def ninja_available() -> bool:
    """Check if ninja is available in PATH."""
    import shutil

    return shutil.which("ninja") is not None


@pytest.fixture
def env_with_pythonpath() -> dict[str, str]:
    """Create environment dict with PYTHONPATH set to src."""
    env = os.environ.copy()
    src_path = str(Path(__file__).parent.parent / "src")
    env["PYTHONPATH"] = src_path

    # Ensure current environment PATH is preserved for tools in nix shell
    if "PATH" not in env:
        env["PATH"] = os.environ.get("PATH", "")

    return env


@pytest.mark.skipif(not ninja_available(), reason="ninja not available")
def test_ninja_file_stability_with_format_links(
    tmp_path: Path, env_with_pythonpath: dict[str, str]
) -> None:
    """Test that build.ninja content and defaults are stable across identical builds."""
    project = tmp_path / "project"
    project.mkdir()

    content = project / "content"
    content.mkdir()

    defaults_dir = project / "defaults"
    defaults_dir.mkdir()
    (defaults_dir / "page.yaml").write_text("standalone: true\n")

    (content / "index.md").write_text("---\ntitle: Home\n---\n# Hello\n")

    # Create mock minify tool using python to avoid PATH issues
    mock_minify = project / "minify.py"
    mock_minify.write_text(f"""#!{sys.executable}
import sys
import shutil
# Args: [script] -o [output] [input]
if len(sys.argv) >= 4 and sys.argv[1] == '-o':
    shutil.copy2(sys.argv[3], sys.argv[2])
else:
    sys.exit(1)
""")
    mock_minify.chmod(0o755)

    config_path = project / "dojo.yaml"
    config_path.write_text(f"""
src_dir: "{content}"
output_dir: "{project / "_site"}"
build_dir: "{project / "_build"}"
default_type: page
format_links: true

types:
  page:
    outputs:
      - id: html
        extension: html
        defaults: "{defaults_dir / "page.yaml"}"
        post_process:
          - tool: minify
      - id: txt
        extension: txt
        defaults: "{defaults_dir / "page.yaml"}"

tools:
  minify: {mock_minify}
""")

    # First build
    subprocess.run(
        [sys.executable, "-m", "dojo", "build", "-c", str(config_path)],
        env=env_with_pythonpath,
        cwd=str(project),
        check=True,
    )

    # Run ninja first time to populate cache
    subprocess.run(
        ["ninja", "-f", str(project / "_build" / "build.ninja")],
        cwd=str(project),
        check=True,
    )

    # Second build (immediate re-run)
    subprocess.run(
        [sys.executable, "-m", "dojo", "build", "-c", str(config_path)],
        env=env_with_pythonpath,
        cwd=str(project),
        check=True,
    )

    # Run ninja second time - should do nothing
    result = subprocess.run(
        ["ninja", "-f", str(project / "_build" / "build.ninja")],
        cwd=str(project),
        check=True,
        capture_output=True,
        text=True,
    )

    assert "no work to do" in result.stdout
