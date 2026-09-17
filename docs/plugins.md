# Dojo Plugin Development Guide

Dojo provides an extensible plugin system that enables developers to customize and augment the build
process. Plugins can:

- Register custom Ninja build rules
- Dynamically inspect and modify output configurations
- Post-process the generated `build.ninja` file before execution

## Quick Start

Create a Python module (for example, `plugins/my_plugin.py`):

```python
from dojo.config import CustomRule, OutputConfig
from dojo.plugins import PluginInterface


class MyPlugin(PluginInterface):
    """Example plugin that adds custom Ninja rules and modifies output configurations."""

    # Optional: Set execution priority (lower = earlier, default = 100)
    priority = 100

    def get_custom_rules(self) -> list[CustomRule]:
        """Register custom Ninja rules."""
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
        """Modify output configuration before build edge generation."""
        # Example: Add a suffix to all PDF outputs for slide types
        if content_type == "slide" and output_config.extension == "pdf":
            output_config = output_config.model_copy(update={"suffix": "-slides"})
        return output_config

    def post_process_ninja(self, ninja_content: str) -> str:
        """Post-process the generated Ninja file content."""
        # Example: Append a comment or custom targets to the Ninja file
        return ninja_content + "\n# Processed by MyPlugin\n"
```

## Configuration

Enable plugins by adding their file paths to `dojo.yaml`:

```yaml
plugins:
  - ./plugins/my_plugin.py
  - /path/to/another_plugin.py
```

Paths can be relative to the project root (where `dojo` is executed) or absolute.

## Plugin Lifecycle and Interface

All plugins inherit from `PluginInterface`.

### Execution Priority

```python
priority: int = 100
```

Execution priority determines the order in which plugins execute. Plugins with lower priority values
run first. Use this attribute to ensure dependencies between plugins are respected.

Recommended priority tiers:

- `0 - 49`: Early validation and preprocessing plugins
- `50 - 99`: Configuration transformation plugins
- `100`: Default priority (standard transformations)
- `101 - 200`: Late post-processing and finalization plugins

### Methods

#### 1. `get_custom_rules() -> list[CustomRule]`

Called during build generation to register custom Ninja rules.

```python
def get_custom_rules(self) -> list[CustomRule]:
    return [
        CustomRule(
            name="compress_pdf",
            command=(
                "gs -sDEVICE=pdfwrite -dCompatibilityLevel=1.4 "
                "-dPDFSETTINGS=/ebook -dNOPAUSE -dQUIET -dBATCH "
                "-sOutputFile=$out $in"
            ),
            description="🗜️  COMPRESS $out",
            pool="heavy",  # Optional: must match a pool defined in dojo.yaml
        )
    ]
```

##### `CustomRule` Fields

- `name` (`str`, required): Unique rule identifier. Must not conflict with built-in rules.
- `command` (`str`, required): Shell command string to execute.
- `description` (`str` or `None`, optional): Short progress message shown by Ninja during builds.
- `pool` (`str` or `None`, optional): Concurrency pool name (must be declared in `pools`).
- `depfile` (`str` or `None`, optional): Path to a Makefile-style dependency file (`$out.d`).
- `deps` (`str` or `None`, optional): Dependency parser type (`"gcc"` or `"msvc"`).
- `generator` (`bool`, optional): If `True`, rule regenerates build files on rerun.
- `variables` (`dict[str, str]` or `None`, optional): Rule-level default variable assignments.

> **Warning: Reserved Rule Names**
>
> Custom rule names must not conflict with Dojo built-in rules: `regenerate`, `compile`, `render`,
> `copy`, `minify`, `ghostscript`, `decktape`, `stamp`, `crunch`. Attempting to register a rule with
> any of these names raises `CustomRuleConflictError`.

#### 2. `modify_output_config(output_config, content_type) -> OutputConfig`

Invoked for each output format defined in a content type before generating Ninja build edges.

```python
from dojo.config import OutputConfig, PipelineStep


def modify_output_config(
    self,
    output_config: OutputConfig,
    content_type: str,
) -> OutputConfig:
    # Append print-background argument for slide PDF generation
    if content_type == "slide" and output_config.extension == "pdf":
        new_args = list(output_config.args or [])
        new_args.append("--print-background")
        return output_config.model_copy(update={"args": new_args})
    return output_config
```

##### `OutputConfig` Fields

- `id` (`str` or `None`): Unique identifier for this output within the content type.
- `extension` (`str`): Output file extension (e.g., `"html"`, `"pdf"`).
- `defaults` (`str` or `list[str]` or `None`): Path(s) to Pandoc YAML defaults file(s).
- `suffix` (`str`): Filename suffix appended before the extension (e.g., `"-dark"`).
- `post_process` (`list[PipelineStep]`): List of `PipelineStep(tool="...", args=[...])` instances.
- `args` (`list[str]` or `None`): Extra arguments passed to the initial rendering tool.
- `source` (`str` or `list[str]` or `None`): Source output ID(s) for derived outputs.
- `tool` (`str` or `None`): Tool or rule name for derived outputs (e.g., `"decktape"`).
- `label` (`str` or `None`): Display label for cross-format navigation links.

> **Important: Immutability**
>
> Always return a new `OutputConfig` using `output_config.model_copy(update={...})`. When modifying
> `post_process`, construct explicit `PipelineStep` instances:
> `PipelineStep(tool="minify", args=["--html-keep-document-tags"])`.

#### 3. `post_process_ninja(ninja_content: str) -> str`

Called after all build edges and variables have been generated, immediately before the `build.ninja`
file is written to disk.

```python
def post_process_ninja(self, ninja_content: str) -> str:
    # Add a custom default build target
    return ninja_content + "\ndefault _site/index.html\n"
```

## Ninja Rule Variables

When writing commands for custom rules, the following Ninja variables and placeholders are
available:

- `$in`: Raw input file path(s) provided by Ninja.
- `$out`: Raw output file path(s) provided by Ninja.
- `$in_shell`: Shell-quoted input path (quoted with `shlex.quote` for space safety).
- `$out_shell`: Shell-quoted output path.
- `$args`: Additional command-line arguments configured on the output format.
- `$defaults`: Resolved, space-separated list of Pandoc defaults flags (`-d ...`).
- `$dojo_stem`: Document stem (base filename without extension).

## Example Plugins

### 1. Image Optimizer Plugin

Adds custom rules for optimizing image assets using `optipng` and `jpegoptim`. See
`examples/plugins/image_optimizer.py` for the complete file:

```python
from __future__ import annotations

import logging

from dojo.config import CustomRule
from dojo.plugins import PluginInterface

logger = logging.getLogger(__name__)


class ImageOptimizerPlugin(PluginInterface):
    """Add image optimization rules to the build graph."""

    priority = 50

    def get_custom_rules(self) -> list[CustomRule]:
        logger.info("ImageOptimizerPlugin: Registering image optimization rules")
        return [
            CustomRule(
                name="optimize_png",
                command="optipng -o5 -quiet $in -out $out",
                description="🖼️  OPTIMIZE PNG $out",
            ),
            CustomRule(
                name="optimize_jpeg",
                command="jpegoptim --strip-all --max=85 --stdout $in > $out",
                description="🖼️  OPTIMIZE JPEG $out",
            ),
        ]
```

### 2. Automatic Minification Plugin

Enforces HTML minification across all HTML outputs:

```python
from __future__ import annotations

from dojo.config import OutputConfig, PipelineStep
from dojo.plugins import PluginInterface


class AutoMinifyPlugin(PluginInterface):
    """Automatically append minification to all HTML outputs."""

    priority = 150

    def modify_output_config(
        self,
        output_config: OutputConfig,
        content_type: str,
    ) -> OutputConfig:
        if output_config.extension == "html" and not output_config.post_process:
            step = PipelineStep(tool="minify")
            return output_config.model_copy(update={"post_process": [step]})
        return output_config
```

### 3. Greeting or Comment Plugin

Prepends an informational header to the generated Ninja build file. See
`examples/plugins/hello_plugin.py`:

```python
from __future__ import annotations

from dojo.plugins import PluginInterface


class HelloPlugin(PluginInterface):
    """Simple plugin that prepends a comment to the generated Ninja file."""

    priority = 100

    def post_process_ninja(self, ninja_content: str) -> str:
        greeting = "# 👋 Generated with Dojo and HelloPlugin\n"
        return greeting + ninja_content
```

## Plugin Loading and Error Handling

During configuration initialization (`load_config`), Dojo processes each path in `config.plugins`:

1. Resolves the plugin file path.
2. Dynamically loads the module using `importlib`.
3. Discovers classes that subclass `PluginInterface` (excluding `PluginInterface` itself).
4. Instantiates the discovered plugin class.
5. Sorts all loaded plugins in ascending order by their `priority` attribute.

> **Strict Error Handling**
>
> If a plugin file is missing, encounters a syntax or runtime error during import, or fails to
> define a `PluginInterface` subclass, Dojo raises `PluginLoadError` and halts the build process
> immediately. This prevents inconsistent build graphs or broken incremental states.

## Debugging and Testing Plugins

### Debugging with CLI Flags

Global CLI flags must be specified before the subcommand:

```bash
# Enable verbose debug logging
dojo --verbose build -c dojo.yaml

# Perform a dry-run without writing build.ninja or directories
dojo build --dry-run -c dojo.yaml

# Inspect the generated build file
cat _build/build.ninja
```

### Writing Tests for Plugins

Because plugins are standard Python classes, they can be tested directly with `pytest`:

```python
from dojo.config import OutputConfig, PipelineStep
from my_plugin import AutoMinifyPlugin


def test_auto_minify_plugin():
    plugin = AutoMinifyPlugin()
    config = OutputConfig(extension="html", defaults="defaults/html.yaml")

    modified = plugin.modify_output_config(config, "page")
    assert len(modified.post_process) == 1
    assert modified.post_process[0].tool == "minify"
```

## Best Practices

1. **Immutability**: Never mutate `OutputConfig` instances directly; always use
   `output_config.model_copy(update={...})`.
2. **Deterministic Output**: Keep `post_process_ninja` transformations idempotent and deterministic to
   avoid unexpected cache invalidations.
3. **Structured Logging**: Use Python standard `logging.getLogger(__name__)` to emit meaningful
   messages during plugin execution.
4. **Validation**: Validate that any custom tools used by your rules are installed, or catch missing
   dependencies early.
