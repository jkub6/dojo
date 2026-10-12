import runpy
import sys
from importlib.metadata import PackageNotFoundError
from unittest.mock import patch

import dojo


def test_main_module():
    """Test that python -m dojo runs the main function."""
    # We patch dojo.cli.main to verify it gets called
    with patch("dojo.cli.main") as mock_main, patch.object(sys, "argv", ["dojo", "--version"]):
        # Run the module
        runpy.run_module("dojo", run_name="__main__")

        # Assert main was called
        mock_main.assert_called_once()


def test_installed_package_version():
    """Installed distributions expose their package version."""
    with patch("importlib.metadata.version", return_value="1.2.3") as version:
        namespace = runpy.run_path(dojo.__file__)

    assert namespace["__version__"] == "1.2.3"
    version.assert_called_once_with("dojo-ssg")


def test_source_checkout_version():
    """A source checkout remains importable without installed distribution metadata."""
    with patch("importlib.metadata.version", side_effect=PackageNotFoundError):
        namespace = runpy.run_path(dojo.__file__)

    assert namespace["__version__"] == "development"
