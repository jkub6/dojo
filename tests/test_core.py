from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dojo.config import Config, OutputConfig
from dojo.constants import RuleName
from dojo.core import NinjaGenerator
from dojo.exceptions import DefaultsRequiredError, DependencyError, SourceRequiresToolError


@pytest.fixture
def core_config_data(tmp_path):
    src = tmp_path / "content"
    src.mkdir()
    (src / "test.md").write_text("---\ntype: page\n---\n# Test")

    defaults = tmp_path / "defaults.yaml"
    defaults.touch()

    return {
        "src_dir": str(src),
        "output_dir": str(tmp_path / "site"),
        "build_dir": str(tmp_path / "build"),
        "default_type": "page",
        "types": {
            "page": {"outputs": [{"id": "html", "extension": "html", "defaults": str(defaults)}]},
        },
        "defaults": str(defaults),
    }


@pytest.fixture
def core_config(core_config_data, tmp_path):
    return Config(**core_config_data), tmp_path / "dojo.yaml"


def test_generator_init(core_config):
    cfg, path = core_config
    gen = NinjaGenerator(cfg, path)
    assert gen.ninja_file.name == "build.ninja"
    assert gen.build_dir.exists()


def test_emit_header(core_config):
    cfg, path = core_config
    gen = NinjaGenerator(cfg, path)
    gen.emit_header()
    content = gen._buffer.getvalue()
    assert "ninja_required_version" in content
    assert "rule regenerate" in content


def test_get_merged_defaults(core_config):
    cfg, path = core_config
    gen = NinjaGenerator(cfg, path)

    # Test None
    assert gen._get_merged_defaults(None) == []
    # Test single
    p = str(Path("a").resolve())
    assert gen._get_merged_defaults(p)[0] == Path("a").resolve()
    # Test list
    expected_count = 2
    assert len(gen._get_merged_defaults([p, p])) == expected_count


def test_process_content_outside_src(core_config, tmp_path, caplog):
    cfg, path = core_config
    gen = NinjaGenerator(cfg, path)

    # Create file outside src
    outside = tmp_path / "outside.md"
    outside.touch()

    gen.process_content(outside)

    # Check log message
    assert "Source file outside source directory" in caplog.text


def test_process_content_valid(core_config):
    cfg, path = core_config
    gen = NinjaGenerator(cfg, path)

    md = Path(cfg.src_dir) / "test.md"
    gen.process_content(md)

    content = gen._buffer.getvalue()
    assert "build" in content
    assert "compile" in content
    assert "render" in content


def test_derive_output_missing_dependency(core_config_data, tmp_path):
    # Setup config with derived output but missing source
    core_config_data["types"]["page"]["outputs"].append(
        {"id": "pdf", "extension": "pdf", "source": "missing_html", "tool": "decktape"},
    )

    cfg = Config(**core_config_data)
    gen = NinjaGenerator(cfg, tmp_path / "dojo.yaml")

    md = Path(cfg.src_dir) / "test.md"

    with pytest.raises(DependencyError, match="Missing dependency"):
        gen.process_content(md)


def test_generate_no_files(core_config, tmp_path, caplog):
    cfg, path = core_config
    # Clear src dir
    for f in Path(cfg.src_dir).glob("*"):
        f.unlink()

    gen = NinjaGenerator(cfg, path)
    gen.generate()

    assert f"No Markdown files found in {cfg.src_dir}" in caplog.text


def test_generate_exception_handling(core_config, caplog):
    cfg, path = core_config
    gen = NinjaGenerator(cfg, path)

    # We mock process_content just to trigger an exception conveniently during the loop
    # This is an acceptable use of mock because we are testing the exception handling wrapper
    with (
        patch("dojo.core.NinjaGenerator.process_content", side_effect=Exception("Boom")),
        pytest.raises(Exception, match="Boom"),
    ):
        gen.generate()


def test_plugin_integration(core_config, tmp_path):
    cfg, path = core_config
    # Mock a plugin
    plugin = MagicMock()
    plugin.get_custom_rules.return_value = []
    plugin.modify_output_config.side_effect = lambda c, t: c
    plugin.post_process_ninja.side_effect = lambda n: n + "\n# Plugin was here"

    gen = NinjaGenerator(cfg, path)
    gen.plugins = [plugin]

    gen.generate()

    # Read generated file
    ninja_content = gen.ninja_file.read_text()
    assert "# Plugin was here" in ninja_content


def test_format_defaults_var_empty(core_config):
    cfg, path = core_config
    gen = NinjaGenerator(cfg, path)
    assert gen._format_defaults_var([]) == ""


def test_derive_output_none_source():
    # Pydantic validation now catches this
    # Pydantic validation now catches this
    with pytest.raises(DefaultsRequiredError):
        OutputConfig(id="pdf", extension="pdf", source=None, tool="decktape")


def test_derive_output_none_tool():
    # Source is "html" which is in registry
    # Pydantic validation catches this
    # Pydantic validation catches this
    with pytest.raises(SourceRequiresToolError):
        OutputConfig(id="pdf", extension="pdf", source="html", tool=None)


def test_process_content_no_outputs(core_config):
    cfg, path = core_config
    # Modify config to have no outputs for page type
    cfg.types["page"].outputs = []

    gen = NinjaGenerator(cfg, path)
    md = Path(cfg.src_dir) / "test.md"

    # Should run without error and produce minimal output (compile only)
    gen.process_content(md)
    content = gen._buffer.getvalue()
    assert "build" in content
    # Should have compile rule but not render rule
    # Rule definitions are in header, but usage looks like "build ... compile"
    assert RuleName.COMPILE.value in content


def test_generate_write_failure(core_config, caplog):
    cfg, path = core_config
    gen = NinjaGenerator(cfg, path)

    # Mock open to raise exception
    with (
        patch("builtins.open", side_effect=OSError("Write failed")),
        pytest.raises(OSError, match="Write failed"),
    ):
        gen.generate()

    assert "Failed to write" in caplog.text


def test_plugin_loading_success(core_config):
    cfg, path = core_config
    cfg.plugins = ["my_plugin"]

    mock_plugin = MagicMock()
    mock_plugin.get_custom_rules.return_value = []

    with patch("dojo.core.load_plugin", return_value=mock_plugin):
        gen = NinjaGenerator(cfg, path)
        assert len(gen.plugins) == 1
        assert gen.plugins[0] == mock_plugin


def test_plugin_loading_failure(core_config):
    cfg, path = core_config
    cfg.plugins = ["bad_plugin"]

    with patch("dojo.core.load_plugin", return_value=None):
        gen = NinjaGenerator(cfg, path)
        assert len(gen.plugins) == 0
