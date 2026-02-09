"""End-to-End Integration Tests.

These tests run the full build pipeline including Ninja execution
to verify the complete workflow from Markdown source to final output.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def ninja_available() -> bool:
    """Check if ninja is available in PATH."""
    return shutil.which("ninja") is not None


def pandoc_available() -> bool:
    """Check if pandoc is available in PATH."""
    return shutil.which("pandoc") is not None


# Skip all tests in this module if ninja or pandoc is not available
pytestmark = [
    pytest.mark.skipif(not ninja_available(), reason="ninja not available"),
    pytest.mark.skipif(not pandoc_available(), reason="pandoc not available"),
]


@pytest.fixture
def sample_project(tmp_path: Path) -> tuple[Path, Path]:
    """Create a sample project for E2E testing.

    Returns:
        Tuple of (project_dir, config_path)

    """
    project = tmp_path / "project"
    project.mkdir()

    content = project / "content"
    content.mkdir()

    defaults = project / "defaults"
    defaults.mkdir()

    # Create defaults file
    defaults_file = defaults / "page.yaml"
    defaults_file.write_text("standalone: true\nto: html5\n")

    # Create sample content
    (content / "index.md").write_text("---\ntitle: Home\n---\n# Hello World\n")

    # Create config with absolute paths
    config_path = project / "dojo.yaml"
    config_content = f"""\
src_dir: "{content}"
output_dir: "{project / "_site"}"
build_dir: "{project / "_build"}"
default_type: page
types:
  page:
    outputs:
      - id: html
        extension: html
        defaults: "{defaults_file}"
"""
    config_path.write_text(config_content)

    return project, config_path


@pytest.fixture
def env_with_pythonpath() -> dict[str, str]:
    """Create environment dict with PYTHONPATH set to src."""
    env = os.environ.copy()
    src_path = str(Path(__file__).parent.parent / "src")
    env["PYTHONPATH"] = src_path
    return env


class TestFullBuildPipeline:
    """Tests for complete build + ninja execution."""

    def test_generates_and_builds_html(
        self,
        sample_project: tuple[Path, Path],
        env_with_pythonpath: dict[str, str],
    ) -> None:
        """Test that dojo generates build.ninja and ninja produces HTML output."""
        project, config_path = sample_project

        # Step 1: Run dojo build
        dojo_result = subprocess.run(
            [sys.executable, "-m", "dojo", "build", "-c", str(config_path)],
            capture_output=True,
            text=True,
            env=env_with_pythonpath,
            cwd=str(project),
            check=False,
        )
        assert dojo_result.returncode == 0, f"dojo build failed: {dojo_result.stderr}"

        # Verify build.ninja was created
        build_ninja = project / "_build" / "build.ninja"
        assert build_ninja.exists(), "build.ninja not created"

        # Step 2: Run ninja
        ninja_result = subprocess.run(
            ["ninja", "-f", str(build_ninja)],
            capture_output=True,
            text=True,
            cwd=str(project),
            check=False,
        )
        assert ninja_result.returncode == 0, f"ninja failed: {ninja_result.stderr}"

        # Verify output HTML was created
        output_html = project / "_site" / "index.html"
        assert output_html.exists(), "HTML output not created"

        # Verify content
        html_content = output_html.read_text()
        assert "Hello World" in html_content

    def test_incremental_build(
        self,
        sample_project: tuple[Path, Path],
        env_with_pythonpath: dict[str, str],
    ) -> None:
        """Test that ninja correctly handles incremental builds."""
        project, config_path = sample_project

        # First build
        subprocess.run(
            [sys.executable, "-m", "dojo", "build", "-c", str(config_path)],
            env=env_with_pythonpath,
            cwd=str(project),
            check=True,
        )
        build_ninja = project / "_build" / "build.ninja"
        subprocess.run(
            ["ninja", "-f", str(build_ninja)],
            cwd=str(project),
            check=True,
        )

        # Second build (no changes) should be no-op
        result = subprocess.run(
            ["ninja", "-f", str(build_ninja)],
            capture_output=True,
            text=True,
            cwd=str(project),
            check=True,
        )
        # Ninja reports "no work to do" or similar
        assert "no work" in result.stdout.lower() or result.stdout == ""

    def test_rebuild_on_source_change(
        self,
        sample_project: tuple[Path, Path],
        env_with_pythonpath: dict[str, str],
    ) -> None:
        """Test that modifying source triggers rebuild."""
        project, config_path = sample_project

        # Initial build
        subprocess.run(
            [sys.executable, "-m", "dojo", "build", "-c", str(config_path)],
            env=env_with_pythonpath,
            cwd=str(project),
            check=True,
        )
        build_ninja = project / "_build" / "build.ninja"
        subprocess.run(
            ["ninja", "-f", str(build_ninja)],
            cwd=str(project),
            check=True,
        )

        # Modify source
        index_md = project / "content" / "index.md"
        index_md.write_text("---\ntitle: Home\n---\n# Updated Content\n")

        # Rebuild should update output
        subprocess.run(
            ["ninja", "-f", str(build_ninja)],
            cwd=str(project),
            check=True,
        )

        output_html = project / "_site" / "index.html"
        assert "Updated Content" in output_html.read_text()


class TestAssetCopying:
    """Tests for asset dependency handling."""

    def test_css_asset_copied(
        self,
        tmp_path: Path,
        env_with_pythonpath: dict[str, str],
    ) -> None:
        """Test that CSS referenced in frontmatter is copied to output."""
        project = tmp_path / "project"
        project.mkdir()

        content = project / "content"
        content.mkdir()
        assets = content / "assets"
        assets.mkdir()

        defaults = project / "defaults"
        defaults.mkdir()
        defaults_file = defaults / "page.yaml"
        defaults_file.write_text("standalone: true\n")

        # Create CSS file
        css_file = assets / "style.css"
        css_file.write_text("body { color: red; }\n")

        # Create markdown with CSS reference
        (content / "index.md").write_text(
            "---\ntitle: Home\ncss:\n  - assets/style.css\n---\n# Hello\n"
        )

        # Create config
        config_path = project / "dojo.yaml"
        config_path.write_text(f"""\
src_dir: "{content}"
output_dir: "{project / "_site"}"
build_dir: "{project / "_build"}"
default_type: page
types:
  page:
    outputs:
      - id: html
        extension: html
        defaults: "{defaults_file}"
""")

        # Build
        subprocess.run(
            [sys.executable, "-m", "dojo", "build", "-c", str(config_path)],
            env=env_with_pythonpath,
            cwd=str(project),
            check=True,
        )
        subprocess.run(
            ["ninja", "-f", str(project / "_build" / "build.ninja")],
            cwd=str(project),
            check=True,
        )

        # Verify CSS was copied
        output_css = project / "_site" / "assets" / "style.css"
        assert output_css.exists(), "CSS file not copied to output"
        assert "color: red" in output_css.read_text()


class TestErrorHandling:
    """Tests for error cases."""

    def test_missing_source_directory(
        self,
        tmp_path: Path,
        env_with_pythonpath: dict[str, str],
    ) -> None:
        """Test error when source directory doesn't exist."""
        config_path = tmp_path / "dojo.yaml"
        config_path.write_text("""\
src_dir: nonexistent
output_dir: _site
build_dir: _build
default_type: page
types:
  page:
    outputs: []
""")

        result = subprocess.run(
            [sys.executable, "-m", "dojo", "build", "-c", str(config_path)],
            capture_output=True,
            text=True,
            env=env_with_pythonpath,
            cwd=str(tmp_path),
            check=False,
        )

        assert result.returncode != 0
        assert "not found" in result.stderr.lower() or "not found" in result.stdout.lower()
