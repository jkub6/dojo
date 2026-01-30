from dojo.plugins import PluginInterface, load_plugin


class TestPlugin(PluginInterface):
    """Test plugin implementation."""

    pass


def test_load_plugin_not_found():
    """Test loading a non-existent plugin."""
    assert load_plugin("non_existent_plugin.py") is None


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

    # We need to make sure dojo is in path for the plugin to import it
    # pytest should handle this if dojo is installed or in PYTHONPATH
    # But just in case, we can't easily modify sys.path for the subprocess import
    # importlib.util.spec_from_file_location used in plugins.py handles file paths directly.

    plugin = load_plugin(str(plugin_file))
    assert plugin is not None
    assert isinstance(plugin, PluginInterface)


def test_load_plugin_no_interface(tmp_path, caplog):
    """Test loading a plugin that doesn't implement PluginInterface."""
    plugin_file = tmp_path / "bad_plugin.py"
    content = """
class BadPlugin:
    pass
"""
    plugin_file.write_text(content)

    plugin = load_plugin(str(plugin_file))
    assert plugin is None


def test_load_plugin_import_error(tmp_path, caplog):
    """Test loading a plugin that raises an error on import."""
    plugin_file = tmp_path / "error_plugin.py"
    content = """
raise ValueError("Boom!")
"""
    plugin_file.write_text(content)

    plugin = load_plugin(str(plugin_file))
    assert plugin is None
    assert "Failed to load plugin" in caplog.text
    assert "Boom!" in caplog.text


def test_interface_methods():
    """Test default methods of PluginInterface."""
    plugin = PluginInterface()
    assert plugin.get_custom_rules() == []
    assert plugin.modify_output_config("config", "type") == "config"
    assert plugin.post_process_ninja("content") == "content"
