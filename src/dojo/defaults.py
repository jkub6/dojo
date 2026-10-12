"""Resolve Pandoc defaults once for both execution and dependency tracking."""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from .constants import ASSET_KEYS
from .io import write_changed
from .resources import find_resource
from .yaml_utils import _load_and_validate_yaml_dict, resolve_input


def materialize_defaults(
    path: Path,
    root: Path,
    data_dir: Path | None,
    destination: Path,
    stack: tuple[Path, ...] = (),
) -> Path:
    """Write defaults with stable absolute input paths, retaining linked CSS URLs."""
    if path in stack:
        message = f"Cyclic defaults: {(*stack, path)}"
        raise ValueError(message)
    data = _load_and_validate_yaml_dict(path)
    if data is None and path.is_file() and not path.read_text().strip():
        data = {}
    if data is None:
        message = f"Invalid or missing defaults: {path}"
        raise ValueError(message)
    local_data = data.get("data-dir")
    current = (root / str(local_data)).resolve() if local_data else data_dir
    if current:
        data["data-dir"] = str(current)
    dirs = [current] if current else []
    for key in ["defaults", *ASSET_KEYS]:
        value = data.get(key)
        if not value or key == "css":
            continue
        values = value if isinstance(value, list) else [value]
        resolved = [
            _resolve_value(key, item, root, dirs, destination, stack=(*stack, path))
            for item in values
        ]
        data[key] = resolved if isinstance(value, list) else resolved[0]
    target = destination / (hashlib.sha256(str(path).encode()).hexdigest() + ".yaml")
    write_changed(target, yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
    return target


def _resolve_value(  # noqa: PLR0913 - key/value plus resource context and recursion stack
    key: str,
    value: object,
    root: Path,
    dirs: list[Path],
    destination: Path,
    *,
    stack: tuple[Path, ...],
) -> object:
    if isinstance(value, dict) and key == "filters":
        result = dict(value)
        if "path" in result:
            result["path"] = _resolve_value(
                key, result["path"], root, dirs, destination, stack=stack
            )
        return result
    if not isinstance(value, str):
        return value
    if key == "defaults":
        found = find_resource("defaults", value, root_contexts=[root], extra_data_dirs=dirs)
        if found:
            return str(
                materialize_defaults(found, root, dirs[0] if dirs else None, destination, stack)
            )
    else:
        found = resolve_input(key, value, root, dirs)
        if found:
            return str(found)
        # Pandoc supplies the citeproc filter and built-in templates itself.
        if value == "citeproc" or (key == "template" and not Path(value).suffix):
            return value
        if "://" in value or value.startswith("data:"):
            return value
    message = f"Missing {key} input {value!r} referenced by {stack[-1]}"
    raise FileNotFoundError(message)
