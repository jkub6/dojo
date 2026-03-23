"""End-to-End Integration Tests for Optional Tools (Decktape, Minify, Ghostscript).

These tests run the full build pipeline verifying that post-processing
and derived outputs execute external binaries correctly.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from dojo.cli import main


def tool_available(name: str) -> bool:
    """Check if a tool is available in PATH."""
    return shutil.which(name) is not None


# Skip all tests in this module if ninja, pandoc, or the specific tools are not available
pytestmark = [
    pytest.mark.skipif(not tool_available("ninja"), reason="ninja not available"),
    pytest.mark.skipif(not tool_available("pandoc"), reason="pandoc not available"),
    pytest.mark.skipif(not tool_available("decktape"), reason="decktape not available"),
    pytest.mark.skipif(not tool_available("minify"), reason="minify not available"),
    pytest.mark.skipif(not tool_available("gs"), reason="ghostscript not available"),
]


@pytest.fixture
def tools_project(tmp_path: Path) -> tuple[Path, Path]:
    """Create a sample project configured with optional tools."""
    project = tmp_path / "project"
    project.mkdir()

    content = project / "content"
    content.mkdir()

    defaults = project / "defaults"
    defaults.mkdir()

    # Create defaults file for slides
    defaults_file = defaults / "slides.yaml"
    defaults_file.write_text("standalone: true\nto: revealjs\n")

    # Create sample content
    (content / "index.md").write_text(
        "---\ntitle: Presentation\n---\n# Slide 1\n\nContent\n\n---\n\n# Slide 2\n"
    )

    # Create config utilizing decktape, minify, and ghostscript
    config_path = project / "dojo.yaml"
    config_content = f"""\
src_dir: "{content}"
output_dir: "{project / "_site"}"
build_dir: "{project / "_build"}"
default_type: presentation
types:
  presentation:
    outputs:
      - id: html_slides
        extension: html
        defaults: "{defaults_file}"
        post_process:
          - tool: minify
      - id: pdf_slides
        extension: pdf
        source: html_slides
        tool: decktape
        # Essential for running headless chromium inside isolated Nix builders
        args: ["--chrome-arg=--no-sandbox", "--size=1920x1080"]
      - id: pdf_compressed
        extension: compressed.pdf
        source: pdf_slides
        tool: ghostscript
        args: ["-dPDFSETTINGS=/screen"]
"""
    config_path.write_text(config_content)

    return project, config_path


class TestOptionalToolsPipeline:
    """Tests for build pipeline invoking decktape, minify, and ghostscript."""

    def test_generates_and_executes_tools(
        self,
        tools_project: tuple[Path, Path],
    ) -> None:
        """Test that dojo generates build.ninja and ninja executes all tools successfully."""
        project, config_path = tools_project

        # Step 1: Run dojo build (In-process for coverage)
        main(["build", "-c", str(config_path)])

        # Verify build.ninja was created
        build_ninja = project / "_build" / "build.ninja"
        assert build_ninja.exists(), "build.ninja not created"

        # Verify ninja config contains the explicitly mapped tools
        ninja_content = build_ninja.read_text()
        assert "rule minify" in ninja_content
        assert "rule decktape" in ninja_content
        assert "rule ghostscript" in ninja_content

        # Step 2: Run ninja
        ninja_result = subprocess.run(
            ["ninja", "-v", "-f", str(build_ninja)],
            capture_output=True,
            text=True,
            cwd=str(project),
            check=False,
        )
        assert ninja_result.returncode == 0, (
            f"ninja failed: {ninja_result.stderr}\n{ninja_result.stdout}"
        )

        # Verify HTML was created and minified (should have very few newlines)
        output_html = project / "_site" / "index.html"
        assert output_html.exists(), "HTML output not created"
        html_content = output_html.read_text()
        assert "Presentation" in html_content

        # Verify PDF was created via Decktape
        output_pdf = project / "_site" / "index.pdf"
        assert output_pdf.exists(), "Decktape PDF output not created"
        assert output_pdf.stat().st_size > 0, "Decktape PDF is empty"

        # Verify Compressed PDF was created via Ghostscript
        output_compressed = project / "_site" / "index.compressed.pdf"
        assert output_compressed.exists(), "Ghostscript output not created"
        assert output_compressed.stat().st_size > 0, "Ghostscript PDF is empty"
