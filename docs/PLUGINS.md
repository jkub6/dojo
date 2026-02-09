# Plugin Development Guide

Dojo supports plugins to extend the build pipeline without modifying core code.

## Quick Start

```python
# plugins/hello_plugin.py
from dojo.plugins import PluginInterface

class HelloPlugin(PluginInterface):
    """Example plugin that adds a comment to the Ninja file."""
    
    priority = 100  # Default priority
    
    def post_process_ninja(self, ninja_content: str) -> str:
        return f"# Built with HelloPlugin\n{ninja_content}"
```

Enable in configuration:
```yaml
# dojo.yaml
plugins:
  - plugins/hello_plugin.py
```

## Plugin Interface

All plugins must implement `PluginInterface` from `dojo.plugins`:

```python
class PluginInterface:
    priority: int = 100
    
    def get_custom_rules(self) -> list[CustomRule]:
        """Add custom Ninja rules."""
        return []
    
    def modify_output_config(
        self, 
        output_config: OutputConfig, 
        content_type: str
    ) -> OutputConfig:
        """Transform output configuration before processing."""
        return output_config
    
    def post_process_ninja(self, ninja_content: str) -> str:
        """Modify the generated Ninja file content."""
        return ninja_content
```

## Priority System

Plugins execute in priority order (lower = earlier):

| Range | Purpose |
|-------|---------|
| 0-49 | Validation, preprocessing |
| 50-99 | Transformations |
| 100 | Default priority |
| 101-200 | Post-processing |

```python
class EarlyPlugin(PluginInterface):
    priority = 10  # Runs before default plugins
```

## Hook Reference

### `get_custom_rules()`

Add custom Ninja rules for new tools or processing steps:

```python
from dojo.config import CustomRule
from dojo.constants import PoolName

class ImageOptimizerPlugin(PluginInterface):
    def get_custom_rules(self) -> list[CustomRule]:
        return [
            CustomRule(
                name="optimize_png",
                command="optipng -o7 $in -out $out",
                description="🖼️ OPTIMIZE $out",
                pool=PoolName.HEAVY_PROCESSING.value,
            )
        ]
```

### `modify_output_config()`

Transform output configurations dynamically:

```python
class MinifyAllPlugin(PluginInterface):
    def modify_output_config(
        self, 
        output_config: OutputConfig, 
        content_type: str
    ) -> OutputConfig:
        # Force minification for all HTML outputs
        if output_config.extension == "html":
            return output_config.model_copy(
                update={"post_process": "minify"}
            )
        return output_config
```

### `post_process_ninja()`

Modify the generated Ninja file before writing:

```python
class StatsPlugin(PluginInterface):
    priority = 150  # Run after other plugins
    
    def post_process_ninja(self, ninja_content: str) -> str:
        rule_count = ninja_content.count("\nrule ")
        build_count = ninja_content.count("\nbuild ")
        stats = f"# Stats: {rule_count} rules, {build_count} build edges\n"
        return stats + ninja_content
```

## Complete Example

```python
"""
Watermark Plugin - Adds build timestamp to output.
"""
from datetime import datetime
from dojo.plugins import PluginInterface

class WatermarkPlugin(PluginInterface):
    """Adds build timestamp comment to Ninja file."""
    
    priority = 200  # Run last
    
    def post_process_ninja(self, ninja_content: str) -> str:
        timestamp = datetime.now().isoformat()
        header = f"# Generated: {timestamp}\n"
        return header + ninja_content
```

## Testing Plugins

```python
# tests/test_my_plugin.py
import pytest
from my_plugin import MyPlugin

def test_post_process():
    plugin = MyPlugin()
    result = plugin.post_process_ninja("# original")
    assert "my modification" in result
```

## Loading Behavior

1. Plugins are loaded from paths specified in `plugins` config
2. Plugin files must contain a class inheriting from `PluginInterface`
3. The first matching class is instantiated automatically
4. Loading errors are logged but don't stop the build
