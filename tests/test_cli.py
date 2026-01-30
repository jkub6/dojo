from unittest.mock import patch

import pytest

from dojo.cli import entry_point, main


def test_cli_help(capsys):
    """Test that the CLI can be invoked and prints help."""
    with pytest.raises(SystemExit) as cm:
        main(["--help"])
    assert cm.value.code == 0

    captured = capsys.readouterr()
    assert "usage: dojo" in captured.out


def test_cli_no_args(capsys):
    """Test behavior when no args provided (prints help and exit 0)."""
    # main([]) equates to no arguments passed to argparse
    with pytest.raises(SystemExit) as cm:
        main([])
    assert cm.value.code == 0

    captured = capsys.readouterr()
    assert "usage: dojo" in captured.out


def test_cli_version(capsys):
    """Test version command."""
    main(["--version"])
    captured = capsys.readouterr()
    # Rich might print to stderr or stdout depending on config, checking both safe
    output = captured.out + captured.err
    assert "dojo" in output


def test_cli_version_subcommand(capsys):
    """Test version subcommand."""
    main(["version"])
    captured = capsys.readouterr()
    # Rich console prints to stdout by default
    assert "dojo" in captured.out


def test_init_creates_file(tmp_path, monkeypatch, capsys):
    """Test init command creates dojo.yaml."""
    monkeypatch.chdir(tmp_path)
    main(["init"])

    assert (tmp_path / "dojo.yaml").exists()
    captured = capsys.readouterr()
    assert "Created sample configuration" in captured.out


def test_init_existing_file(tmp_path, monkeypatch, capsys):
    """Test init command fails if file exists."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "dojo.yaml").touch()

    with pytest.raises(SystemExit) as cm:
        main(["init"])
    assert cm.value.code == 1

    captured = capsys.readouterr()
    assert "already exists" in captured.out


def test_check_valid_config(tmp_path, monkeypatch, capsys):
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

    main(["check", "-c", "dojo.yaml"])

    captured = capsys.readouterr()
    assert "Configuration valid" in captured.out
    assert "Src: content" in captured.out


def test_check_invalid_config(tmp_path, monkeypatch, capsys):
    """Test check command with invalid config."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "dojo.yaml").write_text("invalid: yaml: [")

    with pytest.raises(SystemExit) as cm:
        main(["check", "-c", "dojo.yaml"])
    assert cm.value.code == 1

    captured = capsys.readouterr()
    assert "Configuration invalid" in captured.out


def test_build_success(tmp_path, monkeypatch, capsys):
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

    main(["build", "-c", "dojo.yaml"])

    # build.ninja should exist (NinjaGenerator works)
    assert (tmp_path / "_build" / "build.ninja").exists()
    captured = capsys.readouterr()
    assert "Build configuration generated successfully" in captured.out


def test_build_quiet(tmp_path, monkeypatch, capsys):
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

    main(["--quiet", "build", "-c", "dojo.yaml"])

    captured = capsys.readouterr()
    assert "Build configuration generated successfully" not in captured.out
    assert captured.err == ""


def test_build_file_not_found(tmp_path, monkeypatch, capsys):
    """Test build command when config missing."""
    monkeypatch.chdir(tmp_path)
    # No dojo.yaml

    with pytest.raises(SystemExit) as cm:
        main(["build"])
    assert cm.value.code == 1

    captured = capsys.readouterr()
    assert "Error" in captured.out


def test_keyboard_interrupt(capsys):
    """Test keyboard interrupt handling."""
    # We mock main to raise KeyboardInterrupt to test the entry_point wrapper
    with patch("dojo.cli.main", side_effect=KeyboardInterrupt):
        with pytest.raises(SystemExit) as cm:
            entry_point()
        assert cm.value.code == 130

    captured = capsys.readouterr()
    assert "Interrupted by user" in captured.err


def test_build_verbose_exception(capsys):
    """Test that verbose flag prints tracebacks on error."""
    # Patch load_config to raise an exception
    with (
        patch("dojo.cli.load_config", side_effect=ValueError("Test Error")),
    ):
        with pytest.raises(SystemExit) as cm:
            main(["--verbose", "build"])
        assert cm.value.code == 1

    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert "Test Error" in output
    assert "ValueError" in output
