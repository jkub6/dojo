"""Ninja Build Generator for Static Site Generation."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _get_version


try:
    __version__: str = _get_version("dojo")
except PackageNotFoundError:
    __version__ = "0.1.0-dev"
