import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dojo.cli import entry_point, main, run_ninja


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
    """Test init command creates a complete starter project."""
    monkeypatch.chdir(tmp_path)
    main(["init"])

    assert (tmp_path / "dojo.yaml").exists()
    assert (tmp_path / "content" / "index.md").exists()
    assert (tmp_path / "defaults" / "html.yaml").exists()
    captured = capsys.readouterr()
    assert "Created starter project" in captured.out


def test_init_existing_file(tmp_path, monkeypatch, capsys):
    """Test init command fails if file exists."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "dojo.yaml").touch()

    with pytest.raises(SystemExit) as cm:
        main(["init"])
    assert cm.value.code == 1

    captured = capsys.readouterr()
    assert "already exists" in captured.out


def test_init_existing_content_and_defaults(tmp_path, monkeypatch, capsys):
    """Test init preserves existing content and defaults files if dojo.yaml does not exist."""
    monkeypatch.chdir(tmp_path)
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    (content_dir / "index.md").write_text("existing content", encoding="utf-8")

    defaults_dir = tmp_path / "defaults"
    defaults_dir.mkdir()
    (defaults_dir / "html.yaml").write_text("existing defaults", encoding="utf-8")

    main(["init"])

    assert (content_dir / "index.md").read_text(encoding="utf-8") == "existing content"
    assert (defaults_dir / "html.yaml").read_text(encoding="utf-8") == "existing defaults"
    captured = capsys.readouterr()
    assert "Created starter project" in captured.out


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


def test_build_generate_only(tmp_path, monkeypatch, capsys):
    """Test build command with --generate-only flag."""
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

    main(["build", "-c", "dojo.yaml", "--generate-only"])

    assert (tmp_path / "_build" / "build.ninja").exists()
    captured = capsys.readouterr()
    assert "Build configuration generated successfully" in captured.out
    assert "Running build via Ninja" not in captured.out


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
        sigint_exit_code = 130
        assert cm.value.code == sigint_exit_code

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


def test_build_dry_run(tmp_path, monkeypatch, capsys):
    """Test dry-run mode doesn't write files."""
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
    (tmp_path / "content" / "test.md").write_text("# Test\n")

    main(["build", "-c", "dojo.yaml", "--dry-run"])

    # Verify no build.ninja was written
    assert not (tmp_path / "_build" / "build.ninja").exists()

    captured = capsys.readouterr()
    assert "Dry-run" in captured.out


def test_build_dry_run_with_outputs(tmp_path, monkeypatch, capsys):
    """Test dry-run mode shows output summary."""
    monkeypatch.chdir(tmp_path)
    defaults_file = tmp_path / "defaults.yaml"
    defaults_file.write_text("standalone: true\n")

    (tmp_path / "dojo.yaml").write_text(f"""
src_dir: content
output_dir: _site
build_dir: _build
default_type: page
types:
  page:
    outputs:
      - extension: html
        defaults: {defaults_file}
""")
    (tmp_path / "content").mkdir()
    (tmp_path / "content" / "index.md").write_text("# Index\n")

    main(["build", "-c", "dojo.yaml", "-n"])

    # Verify no files written
    assert not (tmp_path / "_build" / "build.ninja").exists()
    assert not (tmp_path / "_site").exists()

    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert "Dry-run" in output
    # Should show the build plan
    assert "source file" in output.lower() or "Build plan" in output


def test_check_verbose_invalid_config(tmp_path, monkeypatch, capsys):
    """Test check command in verbose mode logs exception when config is invalid."""
    monkeypatch.chdir(tmp_path)
    bad_config = tmp_path / "bad_dojo.yaml"
    bad_config.write_text("not a valid yaml: [unclosed")
    with pytest.raises(SystemExit) as exc:
        main(["-v", "check", "-c", str(bad_config)])
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert (
        "Unexpected error during configuration check" in captured.out
        or "Unexpected error during configuration check" in captured.err
    )


def test_run_ninja_missing(monkeypatch, capsys):
    """Test run_ninja exits when ninja binary is not found."""
    monkeypatch.setattr("shutil.which", lambda _bin: None)
    with pytest.raises(SystemExit) as exc:
        run_ninja(Path("build.ninja"))
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "not found in PATH" in captured.out


def test_run_ninja_options_and_failure(monkeypatch):
    """Test run_ninja passes targets, jobs, quiet, and exits on failure."""
    monkeypatch.setattr("shutil.which", lambda _bin: "/bin/ninja")
    mock_run = MagicMock(return_value=subprocess.CompletedProcess(args=[], returncode=42))
    monkeypatch.setattr("subprocess.run", mock_run)

    with pytest.raises(SystemExit) as exc:
        run_ninja(
            Path("build.ninja"),
            targets=["out.html"],
            jobs=8,
            quiet=True,
        )
    assert exc.value.code == 42
    mock_run.assert_called_once_with(
        ["/bin/ninja", "-f", "build.ninja", "-j", "8", "out.html"],
        cwd=None,
        check=False,
    )
