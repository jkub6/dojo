from __future__ import annotations

from typing import Any


class DojoError(Exception):
    """Base exception for all dojo errors."""


class ConfigError(DojoError):
    """Configuration validation error."""

    def __init__(self, message: str):
        """Initialize ConfigError."""
        super().__init__(message)


class DefaultsNotFoundError(ConfigError):
    """Raised when a defaults file cannot be found."""

    def __init__(self, path: str):
        """Initialize DefaultsNotFoundError."""
        super().__init__(f"Defaults file not found: {path} (checked exact, project, and data dirs)")


class EssentialToolNotFoundError(ConfigError):
    """Raised when a required external tool is missing."""

    def __init__(self, tool: str, path: str | None = None):
        """Initialize EssentialToolNotFoundError."""
        msg = f"Essential tool '{tool}' not found"
        if path:
            msg = f"{msg}: {path}"
        super().__init__(msg)


class OutputConfigSourceError(ConfigError):
    """Raised when output source configuration is invalid."""

    def __init__(self, message: str):
        """Initialize OutputConfigSourceError."""
        super().__init__(message)


class OutputSourceMissingError(OutputConfigSourceError):
    """Raised when output source is None."""

    def __init__(self) -> None:
        """Initialize OutputSourceMissingError."""
        super().__init__("Output source cannot be None")


class OutputToolMissingError(OutputConfigSourceError):
    """Raised when output tool is None."""

    def __init__(self) -> None:
        """Initialize OutputToolMissingError."""
        super().__init__("Output tool cannot be None")


class SourceRequiresToolError(OutputConfigSourceError):
    """Raised when source is present but tool is missing."""

    def __init__(self) -> None:
        """Initialize SourceRequiresToolError."""
        super().__init__("Outputs with 'source' must also specify 'tool'")


class OutputConfigDefaultError(ConfigError):
    """Raised when output default configuration is invalid."""

    pass


class DefaultsRequiredError(OutputConfigDefaultError):
    """Raised when defaults are missing."""

    def __init__(self) -> None:
        """Initialize DefaultsRequiredError."""
        super().__init__("Outputs without 'source' must specify 'defaults'")


class PandocDataDirError(ConfigError):
    """Raised when pandoc data directory is invalid."""

    def __init__(self, path: Any, issue: str = "not found"):
        """Initialize PandocDataDirError."""
        if issue == "not directory":
            super().__init__(f"Pandoc data directory is not a directory: {path}")
        else:
            super().__init__(f"Pandoc data directory not found: {path}")


class CustomRuleConflictError(ConfigError):
    """Raised when a custom rule name conflicts with built-ins."""

    def __init__(self, name: str):
        """Initialize CustomRuleConflictError."""
        super().__init__(f"Custom rule name '{name}' conflicts with built-in rule")


class DirectoryConflictError(ConfigError):
    """Raised when configured directories conflict."""

    def __init__(
        self,
        name1: str,
        path1: Any,
        name2: str,
        path2: Any | None = None,
        issue: str = "conflict",
    ):
        """Initialize DirectoryConflictError."""
        if issue == "same":
            msg = f"Directory conflict: {name1} and {name2} are the same ({path1})"
        elif issue == "nested":
            msg = f"Directory conflict: {name1} ({path1}) is inside {name2} ({path2})"
        else:
            msg = f"Directory conflict between {name1} and {name2}"
        super().__init__(msg)


class DependencyError(ConfigError):
    """Raised when a dependency is missing."""

    def __init__(self, parent_id: str):
        """Initialize DependencyError."""
        super().__init__(f"Missing dependency: {parent_id}")


class DefaultTypeNotFoundError(ConfigError):
    """Raised when default_type is not found in types."""

    def __init__(self, default_type: str):
        """Initialize DefaultTypeNotFoundError."""
        super().__init__(f"default_type '{default_type}' not found in types")


class DuplicateOutputIdError(ConfigError):
    """Raised when duplicate output IDs are found."""

    def __init__(self, type_name: str, duplicates: Any):
        """Initialize DuplicateOutputIdError."""
        super().__init__(f"Duplicate output IDs in type '{type_name}': {duplicates}")


class ConfigFileNotFoundError(ConfigError):
    """Raised when configuration file is not found."""

    def __init__(self, path: str | None = None):
        """Initialize ConfigFileNotFoundError."""
        if path:
            super().__init__(f"Configuration file not found: {path}")
        else:
            super().__init__("No configuration file found in search paths")


class SourceDirNotFoundError(ConfigError):
    """Raised when source directory is not found."""

    def __init__(self, path: Any):
        """Initialize SourceDirNotFoundError."""
        super().__init__(f"Source directory not found: {path}")


class ConfigLoadError(ConfigError):
    """Raised when configuration cannot be loaded."""

    def __init__(self, message: str, path: Any, exc: Exception | None = None):
        """Initialize ConfigLoadError."""
        msg = f"{message}: {path}"
        if exc:
            msg = f"{msg}: {exc}"
        super().__init__(msg)


class ConfigParseError(ConfigLoadError):
    """Raised when configuration YAML parsing fails."""

    def __init__(self, path: Any, exc: Exception):
        """Initialize ConfigParseError."""
        super().__init__("Error parsing configuration file", path, exc)


class ConfigInvalidError(ConfigLoadError):
    """Raised when configuration validation fails."""

    def __init__(self, path: Any, exc: Exception):
        """Initialize ConfigInvalidError."""
        super().__init__("Invalid configuration", path, exc)


class ResourceError(DojoError):
    """Raised when a resource error occurs."""

    def __init__(self, message: str, resource: str):
        """Initialize ResourceError."""
        super().__init__(f"{message}: {resource}")


class UnknownResourceCategoryError(ResourceError):
    """Raised when a resource category is unknown."""

    def __init__(self, category: str):
        """Initialize UnknownResourceCategoryError."""
        super().__init__("Unknown resource category", category)


class SecurityError(DojoError):
    """Raised for security issues like path traversal."""

    def __init__(self, relative: Any, base: Any):
        """Initialize SecurityError."""
        super().__init__(f"Path traversal detected: {relative} escapes {base}")


class CircularDependencyError(DojoError):
    """Raised when a circular dependency is detected."""

    def __init__(self, cycle: str):
        """Initialize CircularDependencyError."""
        super().__init__(f"Circular dependency detected: {cycle}")
