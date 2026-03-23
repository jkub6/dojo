"""End-to-End Integration Tests.

These tests run the full build pipeline including Ninja execution
to verify the complete workflow from Markdown source to final output.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from dojo.cli import main


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
pools:
  test_pool: 1
rule_pools:
  compile: test_pool
types:
  page:
    outputs:
      - id: html
        extension: html
        defaults: "{defaults_file}"
"""
    config_path.write_text(config_content)

    return project, config_path


class TestFullBuildPipeline:
    """Tests for complete build + ninja execution."""

    def test_generates_and_builds_html(
        self,
        sample_project: tuple[Path, Path],
        file_regression,
        normalize_ninja,
    ) -> None:
        """Test that dojo generates build.ninja and ninja produces HTML output."""
        project, config_path = sample_project

        # Step 1: Run dojo build
        main(["build", "-c", str(config_path)])

        # Verify build.ninja was created
        build_ninja = project / "_build" / "build.ninja"
        assert build_ninja.exists(), "build.ninja not created"

        # Verify build.ninja (Normalized)
        ninja_content = build_ninja.read_text()

        # Use shared normalization utility
        dojo_root = Path(__file__).parent.parent.resolve()
        normalized_content = normalize_ninja(ninja_content, project, dojo_root)

        # Verify entire build graph via snapshot
        file_regression.check(normalized_content, extension=".ninja")

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
    ) -> None:
        """Verify that Ninja correctly handles incremental builds (no-op when nothing changed)."""
        project, config_path = sample_project

        # First build
        main(["build", "-c", str(config_path)])

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
    ) -> None:
        """Verify that modifying a source file triggers a rebuild in Ninja."""
        project, config_path = sample_project

        # Initial build
        main(["build", "-c", str(config_path)])

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
    """Tests for asset dependency handling and copying."""

    def test_css_asset_copied(
        self,
        tmp_path: Path,
    ) -> None:
        """Verify that CSS files referenced in frontmatter are correctly copied to the output."""
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
        main(["build", "-c", str(config_path)])

        subprocess.run(
            ["ninja", "-f", str(project / "_build" / "build.ninja")],
            cwd=str(project),
            check=True,
        )

        # Verify CSS was copied
        output_css = project / "_site" / "assets" / "style.css"
        assert output_css.exists(), "CSS file not copied to output"
        assert "color: red" in output_css.read_text()

    def test_recursive_asset_copying(
        self,
        tmp_path: Path,
    ) -> None:
        """Verify that assets referenced within other assets (e.g., Image in CSS) are recursively copied."""
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

        # Create Image file
        img_file = assets / "bg.png"
        img_file.touch()

        # Create CSS file referencing the image
        css_file = assets / "style.css"
        css_file.write_text("body { background: url('bg.png'); }\n")

        # Create markdown referencing the CSS
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
        main(["build", "-c", str(config_path)])

        subprocess.run(
            ["ninja", "-f", str(project / "_build" / "build.ninja")],
            cwd=str(project),
            check=True,
        )

        # Verify both CSS and the recursively discovered Image were copied
        assert (project / "_site" / "assets" / "style.css").exists()
        assert (project / "_site" / "assets" / "bg.png").exists()


class TestErrorHandling:
    """Tests for error cases and system-exit scenarios."""

    def test_missing_source_directory(
        self,
        tmp_path: Path,
    ) -> None:
        """Verify that a non-existent source directory causes a non-zero system exit."""
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

        with pytest.raises(SystemExit) as exc:
            main(["build", "-c", str(config_path)])

        assert exc.value.code != 0
