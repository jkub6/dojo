"""JSON Schema generation for dojo configuration.

This module provides functionality to generate JSON Schema from the
Pydantic configuration models, enabling external validation and IDE support.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .config import Config


def generate_schema() -> dict[str, object]:
    """Generate JSON Schema from the Config Pydantic model.

    Returns:
        JSON Schema dictionary representing the configuration schema

    """
    return Config.model_json_schema()


def write_schema(output_path: Path | None = None, *, pretty: bool = True) -> str:
    """Generate JSON Schema and optionally write to file.

    Args:
        output_path: If provided, write schema to this file. Otherwise, return string.
        pretty: If True, format with indentation for readability.

    Returns:
        JSON Schema as a string

    """
    schema = generate_schema()
    indent = 2 if pretty else None
    schema_json = json.dumps(schema, indent=indent, sort_keys=True)

    if output_path:
        output_path.write_text(schema_json + "\n", encoding="utf-8")

    return schema_json


def print_schema(*, pretty: bool = True) -> None:
    """Print JSON Schema to stdout.

    Args:
        pretty: If True, format with indentation for readability.

    """
    schema_json = write_schema(pretty=pretty)
    sys.stdout.write(schema_json + "\n")
