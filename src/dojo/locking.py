"""Serialize generation and publication within a project on supported POSIX hosts."""

from __future__ import annotations

import fcntl
import os
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@contextmanager
def build_lock(build_dir: Path, *, dry_run: bool = False) -> Iterator[None]:
    """Hold the build transaction; Ninja regeneration inherits its parent's lock."""
    path = (build_dir / "build.lock").resolve()
    key = "DOJO_BUILD_LOCK"
    previous = os.environ.get(key)
    if dry_run or previous == str(path):
        yield
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        os.environ[key] = str(path)
        try:
            yield
        finally:
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous
