"""A static site and document generator powered by Ninja and Pandoc."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _get_version

try:
    __version__: str = _get_version("dojo-ssg")
except PackageNotFoundError:
    __version__ = "0.1.0-dev"
