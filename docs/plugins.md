# Dojo Plugin Development Guide

Dojo supports plugins to extend the build process. Plugins can:
- Add custom Ninja rules
- Modify output configurations
- Post-process the generated Ninja file

## Quick Start

Create a Python file (e.g., `my_plugin.py`):

```python
from dojo.plugins import PluginInterface
from dojo.config import CustomRule, OutputConfig


class MyPlugin(PluginInterface):
    """Example plugin that adds a custom optimization step."""

    # Optional: Set execution priority (lower = earlier, default = 100)
    priority = 100

    def get_custom_rules(self) -> list[CustomRule]:
        """Add custom Ninja rules."""
        return [
            CustomRule(
                name="optimize_images",
                command="optipng -o7 $in -out $out",
                description="🖼️  OPTIMIZE $out",
            )
        ]

    def modify_output_config(
        self,
        output_config: OutputConfig,
        content_type: str,
    ) -> OutputConfig:
        """Modify output configuration before processing."""
        # Example: Add suffix to all PDF outputs
        if output_config.extension == "pdf":
            output_config = output_config.model_copy(
                update={"suffix": "-optimized"}
            )
        return output_config

    def post_process_ninja(self, ninja_content: str) -> str:
        """Post-process the generated Ninja file."""
        # Example: Add a comment at the end
        return ninja_content + "\n# Processed by MyPlugin\n"
```

## Configuration

Enable your plugin in `dojo.yaml`:

```yaml
plugins:
  - ./my_plugin.py
  - /path/to/another_plugin.py
```

## Plugin Interface

### Class Attributes

#### `priority: int = 100`

Execution order for plugins (lower numbers run first). Use this to ensure your plugin runs before or after others.

Recommended ranges:
- `0-49`: Validation/preprocessing plugins
- `50-99`: Transformation plugins
- `100`: Default priority
- `101-200`: Post-processing plugins

### Methods

#### `get_custom_rules() -> list[CustomRule]`

Return a list of custom Ninja rules. Each rule must have:
- `name`: Unique rule name (must not conflict with built-in rules)
- `command`: Shell command to execute
- `description`: (Optional) Shown during build

**Built-in rule names you cannot use:**
- `regenerate`, `compile`, `render`, `minify`, `ghostscript`, `decktape`

**Example:**
```python
def get_custom_rules(self) -> list[CustomRule]:
    return [
        CustomRule(
            name="compress_pdf",
            command="gs -sDEVICE=pdfwrite -dCompatibilityLevel=1.4 "
                    "-dPDFSETTINGS=/ebook -dNOPAUSE -dQUIET -dBATCH "
                    "-sOutputFile=$out $in",
            description="🗜️  COMPRESS $out",
            pool="heavy_processing",  # Limit concurrent runs
        )
    ]
```

#### `modify_output_config(output_config, content_type) -> OutputConfig`

Called for each output configuration before generating build edges.
Return a modified copy of the config (use `model_copy()`).

**Arguments:**
- `output_config`: The OutputConfig being processed
- `content_type`: The content type (e.g., "page", "slide")

**Example:**
```python
def modify_output_config(
    self,
    output_config: OutputConfig,
    content_type: str,
) -> OutputConfig:
    # Add print-specific args for slides
    if content_type == "slide" and output_config.extension == "pdf":
        new_args = list(output_config.args or [])
        new_args.append("--print-background")
        return output_config.model_copy(update={"args": new_args})
    return output_config
```

#### `post_process_ninja(ninja_content) -> str`

Called after all build edges are generated but before writing to disk.
Return the modified Ninja file content.

**Example:**
```python
def post_process_ninja(self, ninja_content: str) -> str:
    # Add a default target
    return ninja_content + "\ndefault all\n"
```

## Ninja Rule Variables

When defining custom rules, you can use these Ninja variables:

| Variable | Description |
|----------|-------------|
| `$in` | Input file(s) |
| `$out` | Output file(s) |
| `$in_shell` | Shell-quoted input path |
| `$out_shell` | Shell-quoted output path |
| `$args` | Extra arguments from output config |
| `$defaults` | Pandoc defaults files |

## Best Practices

1. **Don't modify inputs in-place** — always return new/copied objects using `model_copy()`

2. **Log plugin actions** — use `logging.getLogger(__name__)` for debugging:
   ```python
   import logging
   logger = logging.getLogger(__name__)
   
   def get_custom_rules(self):
       logger.debug("Loading custom rules from MyPlugin")
       return [...]
   ```

3. **Handle errors gracefully** — raise meaningful exceptions with context

4. **Test your plugins** — create unit tests for your plugin logic:
   ```python
   def test_my_plugin_rules():
       plugin = MyPlugin()
       rules = plugin.get_custom_rules()
       assert len(rules) == 1
       assert rules[0].name == "optimize_images"
   ```

5. **Use type hints** — for better IDE support and error detection

## Example Plugins

### Image Optimization Plugin

See [examples/plugins/image_optimizer.py](../examples/plugins/image_optimizer.py) for a complete example that adds PNG and JPEG optimization rules.

### Minification Plugin

```python
from dojo.plugins import PluginInterface
from dojo.config import OutputConfig


class MinifyPlugin(PluginInterface):
    """Automatically enable minification for HTML outputs."""

    priority = 150  # Run after default processing

    def modify_output_config(
        self,
        output_config: OutputConfig,
        content_type: str,
    ) -> OutputConfig:
        # Add minification post-processing for HTML
        if output_config.extension == "html" and not output_config.post_process:
            return output_config.model_copy(update={"post_process": ["minify"]})
        return output_config
```

## Debugging Plugins

1. **Enable verbose logging:**
   ```bash
   dojo build --verbose -c dojo.yaml
   ```

2. **Use dry-run mode:**
   ```bash
   dojo build --dry-run -c dojo.yaml
   ```

3. **Check the generated Ninja file:**
   ```bash
   cat _build/build.ninja
   ```

## Plugin Loading

Dojo loads plugins in the order they appear in the config file, then sorts them by `priority`. The loading process:

1. Parse plugin path from config
2. Load Python module from file
3. Find class that inherits from `PluginInterface`
4. Instantiate the plugin class
5. Sort all plugins by priority

If a plugin fails to load, Dojo logs an error and continues with remaining plugins.
