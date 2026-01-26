import sys
from unittest.mock import patch

import pytest

from dojo.cli import main


def test_cli_help():
    """Test that the CLI can be invoked and prints help."""
    with patch.object(sys, "argv", ["dojo", "--help"]):
        with pytest.raises(SystemExit) as cm:
            main()
        assert cm.value.code == 0
