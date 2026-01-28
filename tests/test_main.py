import runpy
import sys
from unittest.mock import patch


def test_main_module():
    """Test that python -m dojo runs the main function."""
    # We patch dojo.cli.main to verify it gets called
    with patch("dojo.cli.main") as mock_main, patch.object(sys, "argv", ["dojo", "--version"]):
        # Run the module
        runpy.run_module("dojo", run_name="__main__")

        # Assert main was called
        mock_main.assert_called_once()
