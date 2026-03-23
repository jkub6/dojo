from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dojo.config import Config, OutputConfig
from dojo.emitter import NinjaEmitter
from dojo.stages.assets import AssetProcessor
from dojo.stages.render import RenderStage


@pytest.fixture
def mock_emitter():
    return MagicMock(spec=NinjaEmitter)


@pytest.fixture
def mock_config():
    config = MagicMock(spec=Config)
    config.src_dir = Path("/src")
    config.output_dir = Path("/out")
    config.build_dir = Path("/build")
    config.pandoc_data_dir = None
    return config


class TestRenderStage:
    def test_standard_render_emits_correct_ninja_rule(self, mock_config, mock_emitter):
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
        from dojo.exceptions import SourceRequiresToolError
        stage = RenderStage(mock_config, Path("/out"), Path("/build"), mock_emitter, [])
        # source requires tool (pydantic validation)
        with pytest.raises(SourceRequiresToolError):
            OutputConfig(extension="pdf", source="html", tool=None, id="pdf")

    def test_derive_output_missing_source_in_registry_raises(self, mock_config, mock_emitter):
        from dojo.exceptions import DependencyError
        stage = RenderStage(mock_config, Path("/out"), Path("/build"), mock_emitter, [])
        out_config = OutputConfig(extension="pdf", source="missing_id", tool="decktape", id="pdf", defaults=["d.yaml"])
        
        with pytest.raises(DependencyError):
            stage.render(out_config, Path("any.json"), Path("any"), {})

    def test_derive_output_missing_tool_at_runtime_raises(self, mock_config, mock_emitter):
        from dojo.exceptions import OutputToolMissingError
        stage = RenderStage(mock_config, Path("/out"), Path("/build"), mock_emitter, [])
        out_config = OutputConfig(extension="pdf", source="html", tool="decktape", id="pdf", defaults=["d.yaml"])
        # Manually set tool to None AFTER pydantic validation to trigger runtime check
        out_config.tool = None # type: ignore
        
        with pytest.raises(OutputToolMissingError):
            stage.render(out_config, Path("any.json"), Path("any"), {"html": Path("in.html")})

    def test_standard_render_with_post_process(self, mock_config, mock_emitter):
        from dojo.config import PipelineStep
        stage = RenderStage(mock_config, Path("/out"), Path("/build"), mock_emitter, [])
        
        out_config = OutputConfig(
            extension="html",
            defaults=["d.yaml"],
            post_process=[PipelineStep(tool="minify", args=["--fast"])]
        )
        
        with patch("dojo.stages._defaults.get_recursive_yaml_deps", return_value=[]):
            stage.render(out_config, Path("in.json"), Path("index"), {})
            
        # Should call emitter twice: once for RENDER, once for MINIFY
        assert mock_emitter.build.call_count == 2
        rules = [call.kwargs["rule"] for call in mock_emitter.build.call_args_list]
        assert "render" in rules
        assert "minify" in rules
    def test_standard_render_with_args(self, mock_config, mock_emitter):
        stage = RenderStage(mock_config, Path("/out"), Path("/build"), mock_emitter, [])
        out_config = OutputConfig(
            extension="html",
            args=["--mathjax", "--self-contained"],
            defaults=[]
        )
        stage.render(out_config, Path("in.json"), Path("idx"), {})
        
        call_args = mock_emitter.build.call_args
        assert "--mathjax --self-contained" in call_args.kwargs["variables"]["args"]

    def test_derive_output_missing_source_raises(self, mock_config, mock_emitter):
        from dojo.exceptions import OutputSourceMissingError
        stage = RenderStage(mock_config, Path("/out"), Path("/build"), mock_emitter, [])
        out_config = OutputConfig(extension="pdf", source="html", tool="decktape")
        # Manually break it
        out_config.source = None # type: ignore
        # Call private method directly for coverage of the safety check
        with pytest.raises(OutputSourceMissingError):
            stage._derive_output(out_config, Path("idx"), {})

class TestAssetProcessor:
    def test_asset_processor_skips_outside_src(self, mock_emitter, caplog):
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
        processor = AssetProcessor(
            src=Path("/src"),
            out_dir=Path("/out"),
            emitter=mock_emitter,
            copied_assets=set(),
            all_outputs=[],
        )

        style_css = Path("/src/style.css")
        bg_png = Path("/src/bg.png")

        with patch("dojo.stages.assets.get_frontmatter_assets", return_value=[style_css]):
            with patch("dojo.stages.assets.scan_css_dependencies", return_value=[bg_png]):
                processor.process_assets(Path("/src/index.md"))

        # Should be called twice: once for CSS, once for PNG
        assert mock_emitter.build.call_count == 2
        outputs = [call.kwargs["outputs"] for call in mock_emitter.build.call_args_list]
        assert Path("/out/style.css") in outputs
        assert Path("/out/bg.png") in outputs

    def test_asset_processor_dependencies_glob(self, mock_emitter, tmp_path):
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
        assert mock_emitter.build.call_args.kwargs["inputs"] == (tmp_path / "src" / "data" / "file.txt").resolve()

    def test_asset_processor_skips_self_reference(self, mock_emitter, tmp_path):
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
