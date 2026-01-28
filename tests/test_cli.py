import sys
from unittest.mock import MagicMock, patch

import pytest

from dojo.cli import entry_point, main


@pytest.fixture
def mock_sys_exit():
    with patch("sys.exit") as m:
        yield m


@pytest.fixture
def mock_console():
    with patch("dojo.cli.console") as m:
        yield m


@pytest.fixture
def mock_args():
    args = MagicMock()
    args.verbose = False
    args.quiet = False
    args.command = "build"
    args.config = "dojo.yaml"
    return args


def test_cli_help():
    """Test that the CLI can be invoked and prints help."""
    with patch.object(sys, "argv", ["dojo", "--help"]):
        with pytest.raises(SystemExit) as cm:
            main()
        assert cm.value.code == 0


def test_cli_no_args(mock_console):
    """Test behavior when no args provided (prints help and exit 0)."""
    with patch.object(sys, "argv", ["dojo"]):
        with pytest.raises(SystemExit) as cm:
            main()
        # The parser prints help and exits 0 as per logic in main()
        assert cm.value.code == 0


def test_cli_version(capsys):
    """Test version command."""
    with patch.object(sys, "argv", ["dojo", "--version"]):
        # main calls cmd_version and returns (no sys.exit)
        main()
        captured = capsys.readouterr()
        assert "dojo" in captured.out or "dojo" in captured.err
        # RICH prints to stdout usually, but we should check both


def test_cli_version_subcommand(capsys):
    """Test version subcommand."""
    with patch.object(sys, "argv", ["dojo", "version"]):
        main()
        captured = capsys.readouterr()
        assert "dojo" in captured.out


def test_init_creates_file(tmp_path, monkeypatch, mock_console):
    """Test init command creates dojo.yaml."""
    monkeypatch.chdir(tmp_path)
    with patch.object(sys, "argv", ["dojo", "init"]):
        main()

    assert (tmp_path / "dojo.yaml").exists()
    mock_console.print.assert_called()


def test_init_existing_file(tmp_path, monkeypatch, mock_console, mock_sys_exit):
    """Test init command fails if file exists."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "dojo.yaml").touch()

    with patch.object(sys, "argv", ["dojo", "init"]):
        main()

    mock_sys_exit.assert_called_with(1)
    mock_console.print.assert_any_call(
        "[bold red]Configuration file dojo.yaml already exists.[/bold red]"
    )


def test_check_valid_config(tmp_path, monkeypatch, mock_console):
    """Test check command with valid config."""
    monkeypatch.chdir(tmp_path)
    # Create valid config
    (tmp_path / "dojo.yaml").write_text("""
src_dir: content
output_dir: _site
build_dir: _build
default_type: page
types:
  page:
    outputs: []
""")
    (tmp_path / "content").mkdir()

    with patch.object(sys, "argv", ["dojo", "check", "-c", "dojo.yaml"]):
        main()

    # Check for success message
    # We can check call args to verify
    found_success = False
    for call in mock_console.print.call_args_list:
        if "Configuration valid" in str(call):
            found_success = True
            break
    assert found_success


def test_check_invalid_config(tmp_path, monkeypatch, mock_console, mock_sys_exit):
    """Test check command with invalid config."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "dojo.yaml").write_text("invalid: yaml: [")

    with patch.object(sys, "argv", ["dojo", "check", "-c", "dojo.yaml"]):
        main()

    mock_sys_exit.assert_called_with(1)
    # Check for error message logging
    # Check for error message logging
    # Match strictly or loosely? Loosely is safer for path changes.
    # The message contains "Configuration invalid:"
    found_msg = False
    for call in mock_console.print.call_args_list:
        if "[bold red]Configuration invalid:[/bold red]" in str(call):
            found_msg = True
            break
    assert found_msg, "Did not find invalid configuration error message"


def test_build_success(tmp_path, monkeypatch, mock_console):
    """Test build command success."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "dojo.yaml").write_text("""
src_dir: content
output_dir: _site
build_dir: _build
default_type: page
types:
  page:
    outputs: []
""")
    (tmp_path / "content").mkdir()

    with patch.object(sys, "argv", ["dojo", "build", "-c", "dojo.yaml"]):
        main()

    # build.ninja should exist (NinjaGenerator works)
    assert (tmp_path / "_build" / "build.ninja").exists()


def test_build_quiet(tmp_path, monkeypatch, mock_console):
    """Test build command with quiet flag."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "dojo.yaml").write_text("""
src_dir: content
output_dir: _site
build_dir: _build
default_type: page
types:
  page:
    outputs: []
""")
    (tmp_path / "content").mkdir()

    with patch.object(sys, "argv", ["dojo", "--quiet", "build", "-c", "dojo.yaml"]):
        main()

    # Check that console.print was NOT called (except potential errors, but here success)
    # mock_console is the 'dojo.cli.console' object.
    # But main code checks 'if HAS_RICH and not args.quiet'.
    # So print should not be called if quiet is True.
    # Note: validation printing happens in cmd_build.
    mock_console.print.assert_not_called()


def test_build_file_not_found(tmp_path, monkeypatch, mock_console, mock_sys_exit):
    """Test build command when config missing."""
    monkeypatch.chdir(tmp_path)
    # No dojo.yaml

    with patch.object(sys, "argv", ["dojo", "build"]):
        main()

    mock_sys_exit.assert_called_with(1)


def test_setup_logging_verbose(mock_args):
    """Test setup_logging with verbose."""
    with patch("dojo.cli.logging.basicConfig") as mock_basic_config:
        # We need to bypass the HAS_RICH check or mock it, but here we assume HAS_RICH=True
        from dojo import cli

        cli.setup_cli_logging(verbose=True, quiet=False)

        _, kwargs = mock_basic_config.call_args
        assert kwargs["level"] == 10  # DEBUG


def test_setup_logging_quiet(mock_args):
    """Test setup_logging with quiet."""
    with patch("dojo.cli.logging.basicConfig") as mock_basic_config:
        from dojo import cli

        cli.setup_cli_logging(verbose=False, quiet=True)

        _, kwargs = mock_basic_config.call_args
        assert kwargs["level"] == 40  # ERROR


def test_keyboard_interrupt(capsys):
    """Test keyboard interrupt handling."""
    # We mock main to raise KeyboardInterrupt
    with patch("dojo.cli.main", side_effect=KeyboardInterrupt):
        with pytest.raises(SystemExit) as cm:
            entry_point()
        assert cm.value.code == 130
