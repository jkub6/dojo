"""Atomic, content-preserving writes for build state."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def write_changed(path: Path, content: str | bytes) -> bool:
    """Publish a complete file; preserve its mtime when its bytes are unchanged."""
    data = content.encode("utf-8") if isinstance(content, str) else content
    if path.is_file() and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".dojo-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return True
