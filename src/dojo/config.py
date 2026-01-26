import sys
from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator

from .constants import RuleName


class ToolPaths(BaseModel):
    """Configurable paths to external tools."""

    python: str = Field(default=sys.executable, description="Python interpreter path")
    pandoc: str = Field(default="pandoc", description="Pandoc executable path")
    minify: str = Field(default="minify", description="Minify executable path")
    ghostscript: str = Field(default="gs", description="Ghostscript executable path")
    decktape: str = Field(default="decktape", description="Decktape executable path")


class OutputConfig(BaseModel):
    """Configuration for a single output format."""

    id: str | None = Field(default=None, description="Unique identifier for this output")
    extension: str = Field(description="File extension for output")
    defaults: str = Field(description="Path to Pandoc defaults file")
    suffix: str = Field(default="", description="Suffix to add to filename before extension")
    post_process: str | None = Field(default=None, description="Post-processing tool name")
    source: str | None = Field(default=None, description="Source output ID for derived outputs")
    tool: str | None = Field(default=None, description="Tool to use for derived outputs")

    @field_validator("defaults")
    @classmethod
    def validate_defaults_path(cls, v: str) -> str:
        """Validate that defaults file exists."""
        path = Path(v)
        if not path.exists():
            raise ValueError(f"Defaults file not found: {path}")
        return v

    @model_validator(mode="after")
    def validate_derived_output(self) -> "OutputConfig":
        """Validate that derived outputs have required fields."""
        if self.source is not None and self.tool is None:
            raise ValueError("Outputs with 'source' must also specify 'tool'")
        return self


class TypeConfig(BaseModel):
    """Configuration for a content type."""

    outputs: list[OutputConfig] = Field(description="List of output formats")


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

    @model_validator(mode="after")
    def validate_default_type(self) -> "Config":
        """Validate default_type exists in types."""
        if self.default_type not in self.types:
            raise ValueError(f"default_type '{self.default_type}' not found in types")
        return self


def load_config(config_path: str | None = None) -> "tuple[Config, Path]":
    """
    Load configuration from multiple sources with priority:
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
        return Config(**data), selected_path
    except Exception as e:
        raise ValueError(f"Invalid configuration in {selected_path}: {e}") from e
