from __future__ import annotations

import shutil
from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator  # type: ignore

from .constants import RuleName
from .resources import find_resource


def _resolve_defaults(
    v: str | list[str] | None, data_dir: str | None = None
) -> str | list[str] | None:
    """Resolve default files using optional data-dir."""
    if v is None:
        return None

    paths = [v] if isinstance(v, str) else v
    resolved_paths = []
    extra_dirs = [Path(data_dir).resolve()] if data_dir else None
    for p in paths:
        found = find_resource("defaults", p, root_contexts=[Path.cwd()], extra_data_dirs=extra_dirs)
        if found:
            resolved_paths.append(str(found))
        else:
            raise ValueError(
                f"Defaults file not found: {p} (checked exact, project, and data dirs)"
            )

    return resolved_paths[0] if isinstance(v, str) else resolved_paths


class ToolPaths(BaseModel):
    """Configurable paths to external tools."""

    pandoc: str = Field(default="pandoc", description="Pandoc executable path")
    python: str = Field(default="python3", description="Python interpreter path")
    minify: str = Field(default="minify", description="Minify executable path")
    ghostscript: str = Field(default="gs", description="Ghostscript executable path")
    decktape: str = Field(default="decktape", description="Decktape executable path")
    typst: str = Field(default="typst", description="Typst executable path")

    @model_validator(mode="after")
    def resolve_tool_paths(self) -> ToolPaths:
        """Resolve all tool paths to absolute paths and verify existence."""
        essential_tools = ["python", "pandoc"]
        for tool in ["python", "pandoc", "minify", "ghostscript", "decktape", "typst"]:
            current = getattr(self, tool)
            if current:
                resolved = shutil.which(current)
                if resolved:
                    setattr(self, tool, resolved)
                elif tool in essential_tools:
                    raise ValueError(f"Essential tool '{tool}' not found: {current}")
                else:
                    # Optional tool not found
                    # We accept this but if it is used later, it will fail at runtime
                    pass
        return self


class OutputConfig(BaseModel):
    """Configuration for a single output format."""

    id: str | None = Field(default=None, description="Unique identifier for this output")
    extension: str = Field(description="File extension for output")
    defaults: str | list[str] | None = Field(
        default=None, description="Path(s) to Pandoc defaults file(s)"
    )
    suffix: str = Field(default="", description="Suffix to add to filename before extension")
    post_process: str | None = Field(default=None, description="Post-processing tool name")
    args: list[str] | None = Field(
        default=None, description="Extra arguments to pass to the tool or post-processor"
    )
    source: str | list[str] | None = Field(
        default=None, description="Source output ID(s) for derived outputs"
    )
    tool: str | None = Field(default=None, description="Tool to use for derived outputs")

    @model_validator(mode="after")
    def validate_derived_output(self) -> OutputConfig:
        """Validate that derived outputs have required fields."""
        if self.source is not None and self.tool is None:
            raise ValueError("Outputs with 'source' must also specify 'tool'")

        if self.source is None and self.defaults is None:
            raise ValueError("Outputs without 'source' must specify 'defaults'")

        return self


class TypeConfig(BaseModel):
    """Configuration for a content type."""

    outputs: list[OutputConfig] = Field(description="List of output formats")
    defaults: str | list[str] | None = Field(
        default=None, description="Default render settings for this type"
    )


class CustomRule(BaseModel):
    """Configuration for a custom Ninja rule."""

    name: str = Field(description="Rule name")
    command: str = Field(description="Command to execute")
    description: str | None = Field(default=None, description="Description shown during build")
    pool: str | None = Field(default=None, description="Pool to use for this rule")
    depfile: str | None = Field(default=None, description="Dependency file path")
    deps: str | None = Field(default=None, description="Dependency style (gcc or msvc)")
    generator: bool = Field(
        default=False, description="Whether this is a generator rule (re-scans deps)"
    )
    variables: dict[str, str] | None = Field(
        default=None, description="Rule-level variable defaults"
    )

    # Validation moved to Config to allow internal use of built-in names
    # for standard rules like REGENERATE


class Config(BaseModel):
    """Main configuration schema."""

    src_dir: str = Field(default="content", description="Source directory")
    output_dir: str = Field(default="_site", description="Output directory")
    build_dir: str = Field(default="_build", description="Build directory")
    default_type: str = Field(description="Default content type")
    types: dict[str, TypeConfig] = Field(description="Content type definitions")
    tools: ToolPaths = Field(default_factory=ToolPaths, description="External tool paths")
    custom_rules: list[CustomRule] = Field(default_factory=list, description="Custom Ninja rules")
    plugins: list[str] = Field(default_factory=list, description="Plugin script paths")
    exclude: list[str] = Field(default_factory=list, description="Glob patterns to exclude")
    include: list[str] = Field(default_factory=list, description="Glob patterns to include")

    # New Pandoc Configuration Options
    root_ref_dir: str = Field(
        default=".", description="Directory to calculate root variable relative to"
    )

    add_resource_path: bool = Field(
        default=True,
        description="Whether to add the input file directory to the resource path",
    )

    defaults: str | list[str] | None = Field(
        default=None, description="Global default render settings"
    )

    pandoc_data_dir: str | None = Field(
        default=None, description="Directory to use as the pandoc data directory"
    )

    @field_validator("pandoc_data_dir")
    @classmethod
    def validate_pandoc_data_dir(cls, v: str | None) -> str | None:
        """Validate that the pandoc data directory exists."""
        if v is None:
            return None
        path = Path(v).resolve()
        if not path.exists():
            raise ValueError(f"Pandoc data directory not found: {path}")
        if not path.is_dir():
            raise ValueError(f"Pandoc data directory is not a directory: {path}")
        return str(path)

    @field_validator("custom_rules")
    @classmethod
    def validate_custom_rules(cls, v: list[CustomRule]) -> list[CustomRule]:
        """Validate that custom rules do not conflict with built-in rule names."""
        for rule in v:
            if rule.name in [r.value for r in RuleName]:
                raise ValueError(f"Custom rule name '{rule.name}' conflicts with built-in rule")
        return v

    @field_validator("src_dir")
    @classmethod
    def validate_src_dir(cls, v: str) -> str:
        """Validate source directory exists."""
        path = Path(v).resolve()
        if not path.exists():
            raise ValueError(f"Source directory not found: {path}")
        return v

    def _auto_exclude(self, child: Path, parent: Path) -> None:
        """Automatically exclude child directory from parent scanning."""
        try:
            rel = child.relative_to(parent)
            # Add implicit exclude pattern for the directory and its contents
            patterns = [str(rel), f"{rel}/*"]
            for pattern in patterns:
                if pattern not in self.exclude:
                    self.exclude.append(pattern)
        except ValueError:
            pass

    @model_validator(mode="after")
    def validate_config(self) -> Config:
        """Perform complex cross-field validations."""
        # 1. Validate default_type exists
        if self.default_type not in self.types:
            raise ValueError(f"default_type '{self.default_type}' not found in types")

        # 1.5. Resolve all defaults paths
        self.defaults = _resolve_defaults(self.defaults, self.pandoc_data_dir)
        for _type_name, type_conf in self.types.items():
            type_conf.defaults = _resolve_defaults(type_conf.defaults, self.pandoc_data_dir)
            for out_conf in type_conf.outputs:
                out_conf.defaults = _resolve_defaults(out_conf.defaults, self.pandoc_data_dir)

        # 2. Check for overlapping directories
        dirs = {
            "src_dir": Path(self.src_dir).resolve(),
            "output_dir": Path(self.output_dir).resolve(),
            "build_dir": Path(self.build_dir).resolve(),
        }
        for name1, path1 in dirs.items():
            for name2, path2 in dirs.items():
                if name1 == name2:
                    continue

                # Check for equality
                if path1 == path2:
                    raise ValueError(
                        f"Directory conflict: {name1} and {name2} are the same ({path1})"
                    )

                # Check if one is a parent of another
                try:
                    path1.relative_to(path2)
                except ValueError:
                    # Not a subpath, this is fine
                    pass
                else:
                    # If relative_to succeeds, path1 is a subpath of path2

                    # ALLOW: output_dir inside src_dir
                    if name1 == "output_dir" and name2 == "src_dir":
                        self._auto_exclude(path1, path2)
                        continue

                    # ALLOW: build_dir inside src_dir
                    if name1 == "build_dir" and name2 == "src_dir":
                        self._auto_exclude(path1, path2)
                        continue

                    raise ValueError(
                        f"Directory conflict: {name1} ({path1}) is inside {name2} ({path2})"
                    )

        # 3. Check for duplicate output IDs in each type
        for type_name, type_conf in self.types.items():
            ids = [o.id for o in type_conf.outputs if o.id]
            if len(ids) != len(set(ids)):
                duplicates = {x for x in ids if ids.count(x) > 1}
                raise ValueError(f"Duplicate output IDs in type '{type_name}': {duplicates}")

        return self


def load_config(config_path: str | None = None) -> tuple[Config, Path]:
    """Load configuration from multiple sources with priority.

    Sources:
    1. Explicit CLI argument
    2. Environment variable DOJO_CONFIG
    3. Local config.yaml / dojo.yaml
    4. User config (~/.config/dojo/config.yaml)

    Returns:
        Tuple containing (Config object, Path to loaded file)

    """
    import os

    import yaml

    paths_to_check = []

    # 1. CLI Argument
    if config_path:
        paths_to_check.append(Path(config_path))

    # 2. Environment Variable
    env_path = os.environ.get("DOJO_CONFIG")
    if env_path:
        paths_to_check.append(Path(env_path))

    # 3. Local config
    paths_to_check.append(Path("dojo.yaml"))
    paths_to_check.append(Path("config.yaml"))

    # 4. User config
    paths_to_check.append(Path.home() / ".config" / "dojo" / "config.yaml")

    selected_path = None
    for path in paths_to_check:
        if path.exists() and path.is_file():
            selected_path = path.resolve()
            break

    if not selected_path:
        # If specific config was requested but not found, raise error
        if config_path:
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        # Otherwise raise generic error
        raise FileNotFoundError("No configuration file found in search paths")

    with open(selected_path) as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"Error parsing configuration file {selected_path}: {e}") from e

    try:
        config = Config(**data)

        # Auto-exclude configuration file if it's inside src_dir
        # This prevents the config file itself from being treated as content
        src_path = Path(config.src_dir).resolve()
        try:
            rel_config = selected_path.relative_to(src_path)
            # Add implicit exclude pattern for the config file
            pattern = str(rel_config)
            if pattern not in config.exclude:
                config.exclude.append(pattern)
        except ValueError:
            # Config file is not in src_dir
            pass

        return config, selected_path
    except Exception as e:
        raise ValueError(f"Invalid configuration in {selected_path}: {e}") from e
