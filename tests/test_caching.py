"""Regression tests for Ninja build caching.

Verifies that dojo does not unnecessarily update build files (mtime changes)
which would trigger Ninja to rebuild unchanged targets.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import pytest


def ninja_available() -> bool:
    """Check if ninja is available in PATH."""
    return shutil.which("ninja") is not None


@pytest.mark.skipif(not ninja_available(), reason="ninja not available")
def test_ninja_file_stability_with_format_links(
    tmp_path: Path,
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
# Args: [script] [flags...] -o [output] [input]
args = sys.argv[1:]
try:
    o_idx = args.index('-o')
    output = args[o_idx + 1]
    input_file = args[-1]
    shutil.copy2(input_file, output)
except (ValueError, IndexError):
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

    from dojo.cli import main

    # First build
    main(["build", "-c", str(config_path)])

    # Run ninja first time to populate cache
    subprocess.run(
        ["ninja", "-f", str(project / "_build" / "build.ninja")],
        cwd=str(project),
        check=True,
    )

    # Second build (immediate re-run)
    main(["build", "-c", str(config_path)])

    # Run ninja second time - should do nothing
    result = subprocess.run(
        ["ninja", "-f", str(project / "_build" / "build.ninja")],
        cwd=str(project),
        check=True,
        capture_output=True,
        text=True,
    )

    assert "no work to do" in result.stdout
