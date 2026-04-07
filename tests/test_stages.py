from pathlib import Path
from unittest.mock import patch

import pytest

from dojo.config import OutputConfig
from dojo.stages.assets import AssetProcessor
from dojo.stages.render import RenderStage


class TestRenderStage:
    """Tests for the RenderStage class."""

    def test_standard_render_emits_correct_ninja_rule(self, mock_config, mock_emitter):
        """Verify that a standard render call emits the correct Ninja build rule."""
        stage = RenderStage(
            config=mock_config,
            out_dir=Path("/out"),
            build_dir=Path("/build"),
            emitter=mock_emitter,
            all_outputs=[],
        )

        out_config = OutputConfig(
            extension="html",
            defaults=["/src/defaults.yaml"],
            id="my-output",
        )
        json_node = Path("/build/input.json")
        rel_stem = Path("pages/index")
        local_registry = {}

        with patch("dojo.stages._defaults.get_recursive_yaml_deps", return_value=[]):
            stage.render(out_config, json_node, rel_stem, local_registry)

        # Verify ninja rule was emitted
        mock_emitter.build.assert_called_once()
        call_args = mock_emitter.build.call_args
        assert call_args.kwargs["outputs"] == Path("/out/pages/index.html")
        assert call_args.kwargs["rule"] == "render"
        assert call_args.kwargs["inputs"] == json_node
        assert local_registry["my-output"] == Path("/out/pages/index.html")

    def test_derive_output_missing_tool_raises(self, mock_config, mock_emitter):
        """Verify that missing a requested tool raises SourceRequiresToolError."""
        from dojo.exceptions import SourceRequiresToolError

        # source requires tool (pydantic validation)
        with pytest.raises(SourceRequiresToolError):
            OutputConfig(extension="pdf", source="html", tool=None, id="pdf")

    def test_derive_output_missing_source_in_registry_raises(self, mock_config, mock_emitter):
        """Verify that referencing a missing source ID in the registry raises DependencyError."""
        from dojo.exceptions import DependencyError

        stage = RenderStage(mock_config, Path("/out"), Path("/build"), mock_emitter, [])
        out_config = OutputConfig(
            extension="pdf", source="missing_id", tool="decktape", id="pdf", defaults=["d.yaml"]
        )

        with pytest.raises(DependencyError):
            stage.render(out_config, Path("any.json"), Path("any"), {})

    def test_derive_output_missing_tool_at_runtime_raises(self, mock_config, mock_emitter):
        """Verify that a missing tool at runtime raises OutputToolMissingError."""
        from dojo.exceptions import OutputToolMissingError

        stage = RenderStage(mock_config, Path("/out"), Path("/build"), mock_emitter, [])
        out_config = OutputConfig(
            extension="pdf", source="html", tool="decktape", id="pdf", defaults=["d.yaml"]
        )
        # Manually set tool to None AFTER pydantic validation to trigger runtime check
        out_config.tool = None  # type: ignore

        with pytest.raises(OutputToolMissingError):
            stage.render(out_config, Path("any.json"), Path("any"), {"html": Path("in.html")})

    def test_standard_render_with_post_process(self, mock_config, mock_emitter):
        """Verify that post-processing pipeline steps are correctly emitted as Ninja rules."""
        from dojo.config import PipelineStep

        stage = RenderStage(mock_config, Path("/out"), Path("/build"), mock_emitter, [])

        out_config = OutputConfig(
            extension="html",
            defaults=["d.yaml"],
            post_process=[PipelineStep(tool="minify", args=["--fast"])],
        )

        with patch("dojo.stages._defaults.get_recursive_yaml_deps", return_value=[]):
            stage.render(out_config, Path("in.json"), Path("index"), {})

        # Should call emitter twice: once for RENDER, once for MINIFY
        assert mock_emitter.build.call_count == 2
        rules = [call.kwargs["rule"] for call in mock_emitter.build.call_args_list]
        assert "render" in rules
        assert "minify" in rules

    def test_standard_render_with_args(self, mock_config, mock_emitter):
        """Verify that command line arguments are correctly passed to the render rule."""
        stage = RenderStage(mock_config, Path("/out"), Path("/build"), mock_emitter, [])
        out_config = OutputConfig(
            extension="html", args=["--mathjax", "--self-contained"], defaults=[]
        )
        stage.render(out_config, Path("in.json"), Path("idx"), {})

        call_args = mock_emitter.build.call_args
        assert "--mathjax --self-contained" in call_args.kwargs["variables"]["args"]

    def test_derive_output_missing_source_raises(self, mock_config, mock_emitter):
        """Verify that a missing source during output derivation raises OutputSourceMissingError."""
        from dojo.exceptions import OutputSourceMissingError

        stage = RenderStage(mock_config, Path("/out"), Path("/build"), mock_emitter, [])
        out_config = OutputConfig(extension="pdf", source="html", tool="decktape")
        # Manually break it
        out_config.source = None  # type: ignore
        # Call private method directly for coverage of the safety check
        with pytest.raises(OutputSourceMissingError):
            stage._derive_output(out_config, Path("idx"), {})


class TestAssetProcessor:
    """Tests for the AssetProcessor class."""

    def test_asset_processor_skips_outside_src(self, mock_emitter, caplog):
        """Verify that assets referenced outside the source directory are skipped with a warning."""
        processor = AssetProcessor(
            src=Path("/src"),
            out_dir=Path("/out"),
            emitter=mock_emitter,
            copied_assets=set(),
            all_outputs=[],
        )

        # Asset outside /src
        external_asset = Path("/outside/style.css")

        with patch("dojo.stages.assets.get_frontmatter_assets", return_value=[external_asset]):
            processor.process_assets(Path("/src/index.md"))

        assert "Referenced asset outside source directory" in caplog.text
        mock_emitter.build.assert_not_called()

    def test_asset_processor_recursive_discovery(self, mock_emitter):
        """Verify that assets (like CSS) are recursively scanned for dependencies (like images)."""
        processor = AssetProcessor(
            src=Path("/src"),
            out_dir=Path("/out"),
            emitter=mock_emitter,
            copied_assets=set(),
            all_outputs=[],
        )

        style_css = Path("/src/style.css")
        bg_png = Path("/src/bg.png")

        with (
            patch("dojo.stages.assets.get_frontmatter_assets", return_value=[style_css]),
            patch("dojo.stages.assets.scan_css_dependencies", return_value=[bg_png]),
        ):
            processor.process_assets(Path("/src/index.md"))

        # Should be called twice: once for CSS, once for PNG
        assert mock_emitter.build.call_count == 2
        outputs = [call.kwargs["outputs"] for call in mock_emitter.build.call_args_list]
        assert Path("/out/style.css") in outputs
        assert Path("/out/bg.png") in outputs

    def test_asset_processor_dependencies_glob(self, mock_emitter, tmp_path):
        """Verify that glob patterns in frontmatter dependencies are correctly expanded and processed."""
        # We need a real path for parse_frontmatter to work or we mock it
        processor = AssetProcessor(
            src=tmp_path / "src",
            out_dir=tmp_path / "out",
            emitter=mock_emitter,
            copied_assets=set(),
            all_outputs=[],
        )
        (tmp_path / "src").mkdir()
        (tmp_path / "out").mkdir()
        (tmp_path / "src" / "data").mkdir()
        (tmp_path / "src" / "data" / "file.txt").touch()

        md_file = tmp_path / "src" / "index.md"
        md_file.write_text("---\ndependencies:\n  - data/*.txt\n---\n", encoding="utf-8")

        processor.process_assets(md_file)

        mock_emitter.build.assert_called_once()
        assert (
            mock_emitter.build.call_args.kwargs["inputs"]
            == (tmp_path / "src" / "data" / "file.txt").resolve()
        )

    def test_asset_processor_skips_self_reference(self, mock_emitter, tmp_path):
        """Verify that the source file itself is not processed as an asset (cycle prevention)."""
        processor = AssetProcessor(
            src=tmp_path / "src",
            out_dir=tmp_path / "out",
            emitter=mock_emitter,
            copied_assets=set(),
            all_outputs=[],
        )
        (tmp_path / "src").mkdir()
        md_file = tmp_path / "src" / "index.md"
        md_file.touch()

        # If glob somehow includes the md file itself
        with patch("dojo.stages.assets.get_frontmatter_assets", return_value=[md_file]):
            processor.process_assets(md_file)

        mock_emitter.build.assert_not_called()

    def test_asset_processor_scans_html(self, mock_emitter, tmp_path):
        """Verify that HTML files are scanned for internal assets like <img> tags."""
        processor = AssetProcessor(
            src=tmp_path / "src",
            out_dir=tmp_path / "out",
            emitter=mock_emitter,
            copied_assets=set(),
            all_outputs=[],
        )
        (tmp_path / "src").mkdir()
        html_file = tmp_path / "src" / "index.html"
        html_file.write_text('<img src="img.png">')
        (tmp_path / "src" / "img.png").touch()

        with patch("dojo.stages.assets.get_frontmatter_assets", return_value=[html_file]):
            processor.process_assets(tmp_path / "src" / "index.md")

        # One for HTML, one for img.png
        assert mock_emitter.build.call_count == 2

    def test_asset_processor_deduplication(self, mock_emitter, tmp_path):
        """Verify that multiple references to the same asset are deduplicated during processing."""
        # Test line 95: asset in processed_assets
        processor = AssetProcessor(
            src=tmp_path / "src",
            out_dir=tmp_path / "out",
            emitter=mock_emitter,
            copied_assets=set(),
            all_outputs=[],
        )
        (tmp_path / "src").mkdir()
        asset = tmp_path / "src" / "style.css"
        asset.touch()

        with patch("dojo.stages.assets.get_frontmatter_assets", return_value=[asset, asset]):
            processor.process_assets(tmp_path / "src" / "index.md")

        assert mock_emitter.build.call_count == 1

    def test_asset_processor_global_deduplication(self, mock_emitter, tmp_path):
        """Verify that assets already processed in other stages are not re-processed."""
        # Test line 115: final_path in self.copied_assets
        copied = {Path(tmp_path / "out" / "style.css")}
        processor = AssetProcessor(
            src=tmp_path / "src",
            out_dir=tmp_path / "out",
            emitter=mock_emitter,
            copied_assets=copied,
            all_outputs=[],
        )
        (tmp_path / "src").mkdir()
        asset = tmp_path / "src" / "style.css"
        asset.touch()

        with patch("dojo.stages.assets.get_frontmatter_assets", return_value=[asset]):
            processor.process_assets(tmp_path / "src" / "index.md")

        mock_emitter.build.assert_not_called()

    def test_asset_processor_self_reference_resolve(self, mock_emitter, tmp_path):
        """Verify that self-references are correctly identified after path resolution."""
        # Test line 95 specifically with resolved paths
        processor = AssetProcessor(
            src=tmp_path / "src",
            out_dir=tmp_path / "out",
            emitter=mock_emitter,
            copied_assets=set(),
            all_outputs=[],
        )
        (tmp_path / "src").mkdir()
        md_file = tmp_path / "src" / "index.md"
        md_file.touch()

        # Reference the same file via a different path string that resolves to the same path
        with patch("dojo.stages.assets.get_frontmatter_assets", return_value=[Path(str(md_file))]):
            processor.process_assets(md_file)

        mock_emitter.build.assert_not_called()

    def test_asset_processor_circular_css(self, mock_emitter, tmp_path):
        """Verify that circular CSS @import references are handled correctly without hanging."""
        processor = AssetProcessor(
            src=tmp_path / "src",
            out_dir=tmp_path / "out",
            emitter=mock_emitter,
            copied_assets=set(),
            all_outputs=[],
        )
        (tmp_path / "src").mkdir()
        (tmp_path / "out").mkdir()

        css_a = tmp_path / "src" / "a.css"
        css_b = tmp_path / "src" / "b.css"

        css_a.write_text("@import url('b.css');", encoding="utf-8")
        css_b.write_text("@import url('a.css');", encoding="utf-8")

        # This should complete and not hang, as it uses processed_assets set
        # We patch to return css_a as the initial discovered asset
        with patch("dojo.stages.assets.get_frontmatter_assets", return_value=[css_a]):
            processor.process_assets(tmp_path / "src" / "index.md")

        # Should be called twice (a.css and b.css)
        assert mock_emitter.build.call_count == 2
        outputs = [call.kwargs["outputs"] for call in mock_emitter.build.call_args_list]
        assert (tmp_path / "out" / "a.css") in outputs
        assert (tmp_path / "out" / "b.css") in outputs

    def test_asset_processor_query_strings(self, mock_emitter, tmp_path):
        """Verify that assets with query strings in CSS are discovered correctly."""
        processor = AssetProcessor(
            src=tmp_path / "src",
            out_dir=tmp_path / "out",
            emitter=mock_emitter,
            copied_assets=set(),
            all_outputs=[],
        )
        (tmp_path / "src").mkdir()
        (tmp_path / "out").mkdir()

        # CSS with query strings (e.g. for cache busting)
        css_file = tmp_path / "src" / "style.css"
        css_file.write_text("body { background: url('bg.png?v=1.2'); }", encoding="utf-8")
        (tmp_path / "src" / "bg.png").touch()

        with patch("dojo.stages.assets.get_frontmatter_assets", return_value=[css_file]):
            processor.process_assets(tmp_path / "src" / "index.md")

        # bg.png should be discovered and copied (stripping query string for path)
        outputs = [call.kwargs["outputs"] for call in mock_emitter.build.call_args_list]
        assert (tmp_path / "out" / "style.css") in outputs
        assert (tmp_path / "out" / "bg.png") in outputs

    def test_asset_processor_symlinks(self, mock_emitter, tmp_path):
        """Verify that symlinked assets are correctly handled and resolved."""
        src = tmp_path / "src"
        src.mkdir()
        out = tmp_path / "out"
        out.mkdir()

        external_dir = tmp_path / "external"
        external_dir.mkdir()
        real_file = external_dir / "real.jpg"
        real_file.touch()

        # Symlink inside src to external file
        link_file = src / "link.jpg"
        link_file.symlink_to(real_file)

        processor = AssetProcessor(
            src=src,
            out_dir=out,
            emitter=mock_emitter,
            copied_assets=set(),
            all_outputs=[],
        )

        with patch("dojo.stages.assets.get_frontmatter_assets", return_value=[link_file]):
            processor.process_assets(src / "index.md")

        # The link should be copied to output
        mock_emitter.build.assert_called_once()
        assert mock_emitter.build.call_args.kwargs["outputs"] == out / "link.jpg"
        # The input should be the symlink itself (let Ninja/cp handle it)
        assert mock_emitter.build.call_args.kwargs["inputs"] == link_file
