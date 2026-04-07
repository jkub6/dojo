import pytest

from dojo.exceptions import PluginLoadError
from dojo.plugins import PluginInterface, load_plugin


class TestPlugin(PluginInterface):
    """Test plugin implementation."""

    pass


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
        pass  # Uses default 100

    plugins = [LowPriority(), DefaultPriority(), HighPriority()]
    sorted_plugins = sorted(plugins, key=lambda p: getattr(p, "priority", 100))

    assert isinstance(sorted_plugins[0], HighPriority)
    assert isinstance(sorted_plugins[1], DefaultPriority)
    assert isinstance(sorted_plugins[2], LowPriority)
