from pathlib import Path

import pytest

from dojo.config import load_config
from dojo.core import NinjaGenerator
from dojo.exceptions import PluginLoadError
from dojo.plugins import PluginInterface, load_plugin


class TestPlugin(PluginInterface):
    """Test plugin implementation."""


def test_load_plugin_not_found():
    """Test loading a non-existent plugin raises PluginLoadError."""
    with pytest.raises(PluginLoadError, match="file not found"):
        load_plugin("non_existent_plugin.py")


def test_load_plugin_valid(tmp_path):
    """Test loading a valid plugin."""
    plugin_file = tmp_path / "my_plugin.py"
    content = """
from dojo.plugins import PluginInterface

class MyPlugin(PluginInterface):
    def get_custom_rules(self):
        return []
"""
    plugin_file.write_text(content)

    plugin = load_plugin(str(plugin_file))
    assert isinstance(plugin, PluginInterface)


def test_load_plugin_no_interface(tmp_path):
    """Test loading a plugin that doesn't implement PluginInterface raises."""
    plugin_file = tmp_path / "bad_plugin.py"
    content = """
class BadPlugin:
    pass
"""
    plugin_file.write_text(content)

    with pytest.raises(PluginLoadError, match="no PluginInterface implementation found"):
        load_plugin(str(plugin_file))


def test_load_plugin_import_error(tmp_path):
    """Test loading a plugin that raises an error on import."""
    plugin_file = tmp_path / "error_plugin.py"
    content = """
raise ValueError("Boom!")
"""
    plugin_file.write_text(content)

    with pytest.raises(PluginLoadError, match="Boom!"):
        load_plugin(str(plugin_file))


def test_interface_methods():
    """Test default methods of PluginInterface."""
    plugin = PluginInterface()
    assert plugin.get_custom_rules() == []
    assert plugin.modify_output_config("config", "type") == "config"
    assert plugin.post_process_ninja("content") == "content"
    # New lifecycle methods
    assert plugin.pre_generate(None, Path(), refresh=False) is None
    vars_dict, deps = plugin.modify_compile_edge(
        Path("in.md"), Path("in"), Path("out.json"), {"var": "1"}, [Path("dep.md")]
    )
    assert vars_dict == {"var": "1"}
    assert deps == [Path("dep.md")]
    render_vars, render_deps = plugin.modify_render_edge(
        Path("out.json"), Path("in"), Path("site/out.html"), {"v": "2"}, [Path("style.css")]
    )
    assert render_vars == {"v": "2"}
    assert render_deps == [Path("style.css")]
    assert plugin.get_extra_assets(None, Path("site")) == {}


def test_plugin_priority_default():
    """Test that default plugin priority is 100."""
    plugin = PluginInterface()
    expected_default = 100
    assert plugin.priority == expected_default


def test_plugin_priority_custom(tmp_path):
    """Test plugin with custom priority."""
    plugin_file = tmp_path / "priority_plugin.py"
    content = """
from dojo.plugins import PluginInterface

class PriorityPlugin(PluginInterface):
    priority = 50
"""
    plugin_file.write_text(content)

    plugin = load_plugin(str(plugin_file))
    expected_priority = 50
    assert plugin.priority == expected_priority


def test_plugin_priority_sorting():
    """Test plugins are sorted correctly by priority."""

    class LowPriority(PluginInterface):
        priority = 200

    class HighPriority(PluginInterface):
        priority = 10

    class DefaultPriority(PluginInterface):
        """Uses default priority 100."""

    plugins = [LowPriority(), DefaultPriority(), HighPriority()]
    sorted_plugins = sorted(plugins, key=lambda p: getattr(p, "priority", 100))

    assert isinstance(sorted_plugins[0], HighPriority)
    assert isinstance(sorted_plugins[1], DefaultPriority)
    assert isinstance(sorted_plugins[2], LowPriority)


def test_load_plugin_spec_none(tmp_path, monkeypatch):
    """Test load_plugin raises PluginLoadError when spec_from_file_location returns None."""
    f = tmp_path / "dummy_plugin.py"
    f.touch()
    monkeypatch.setattr("importlib.util.spec_from_file_location", lambda *_args, **_kwargs: None)
    with pytest.raises(PluginLoadError, match="failed to create import spec"):
        load_plugin(str(f))


def test_load_plugin_with_base_dir(tmp_path):
    """Test load_plugin resolves relative path against base_dir."""
    sub_dir = tmp_path / "plugins"
    sub_dir.mkdir()
    plugin_file = sub_dir / "my_plugin.py"
    content = """
from dojo.plugins import PluginInterface

class RelativePlugin(PluginInterface):
    pass
"""
    plugin_file.write_text(content)

    plugin = load_plugin("plugins/my_plugin.py", base_dir=tmp_path)
    assert isinstance(plugin, PluginInterface)


def test_plugin_full_lifecycle(tmp_path, monkeypatch):
    """Test plugin lifecycle hooks (pre_generate, compile, render, extra assets)."""
    monkeypatch.chdir(tmp_path)
    src = tmp_path / "content"
    src.mkdir()
    (src / "test.md").write_text("# Hello\n")
    defaults_file = tmp_path / "defaults.yaml"
    defaults_file.write_text("standalone: true\n")

    extra_file = tmp_path / "extra.css"
    extra_file.write_text("body { color: red; }\n")

    (tmp_path / "dojo.yaml").write_text(f"""
src_dir: "{src}"
output_dir: "{tmp_path / "_site"}"
build_dir: "{tmp_path / "_build"}"
default_type: page
types:
  page:
    outputs:
      - extension: html
        defaults: "{defaults_file}"
""")

    class LifecyclePlugin(PluginInterface):
        def __init__(self) -> None:
            self.pre_gen_called = False

        def pre_generate(self, config, build_dir, *, refresh=False, src_dir=None):
            self.pre_gen_called = True
            self.refresh_arg = refresh
            self.src_dir_arg = src_dir

        def modify_compile_edge(self, source, rel_stem, target_ast, variables, implicit_deps):
            new_vars = dict(variables)
            new_vars["custom_compile_var"] = "comp_val"
            return new_vars, [*implicit_deps, Path("extra_input.txt")]

        def modify_render_edge(self, source_ast, rel_stem, target_output, variables, implicit_deps):
            new_vars = dict(variables)
            new_vars["custom_render_var"] = "rend_val"
            return new_vars, [*implicit_deps, Path("extra_render_dep.txt")]

        def get_extra_assets(self, config, out_dir):
            return {out_dir / "extra.css": extra_file}

    class DuplicateAssetPlugin(PluginInterface):
        priority = 60

        def get_extra_assets(self, config, out_dir):
            return {out_dir / "extra.css": extra_file}

    plugin = LifecyclePlugin()
    duplicate_plugin = DuplicateAssetPlugin()
    config, config_path = load_config(str(tmp_path / "dojo.yaml"))
    generator = NinjaGenerator(
        config,
        config_path,
        quiet=True,
        plugins=[plugin, duplicate_plugin],
    )
    generator.generate()

    assert plugin.pre_gen_called is True
    assert plugin.refresh_arg is False
    assert plugin.src_dir_arg == src.resolve()

    ninja_text = (tmp_path / "_build" / "build.ninja").read_text()
    assert "custom_compile_var = comp_val" in ninja_text
    assert "extra_input.txt" in ninja_text
    assert "custom_render_var = rend_val" in ninja_text
    assert "extra_render_dep.txt" in ninja_text
    assert "extra.css" in ninja_text
