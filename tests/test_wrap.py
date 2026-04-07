import os
from pathlib import Path
from unittest.mock import patch

import pytest

from dojo.wrap import (
    PlaceholderContext,
    _setup_env,
    resolve_placeholders,
    run_wrap,
)


def test_resolve_placeholders_basic():
    ctx = PlaceholderContext(
        in_file="/src/file.md",
        out_file="/out/file.html",
        src_dir="/src",
        out_dir="/out",
        build_dir="/build",
    )

    # Test {in_abs}
    assert resolve_placeholders("{in_abs}", ctx) == Path("/src/file.md").resolve().as_posix()

    # Test {out_abs}
    assert resolve_placeholders("{out_abs}", ctx) == Path("/out/file.html").resolve().as_posix()

    # Test {in_abs_dir}
    assert resolve_placeholders("{in_abs_dir}", ctx) == Path("/src").resolve().as_posix()

    # Test {out_abs_dir}
    assert resolve_placeholders("{out_abs_dir}", ctx) == Path("/out").resolve().as_posix()

    # Test {src_dir_val}
    ctx_src = PlaceholderContext(
        in_file="/build/content/sub/file.md", build_dir="/build", src_dir="/src_real"
    )
    with patch("pathlib.Path.resolve", autospec=True) as mock_resolve:
        mock_resolve.side_effect = lambda self: self
        val = resolve_placeholders("{src_dir_val}", ctx_src)
        assert val == "/src_real/content/sub"


def test_resolve_placeholders_windows_simulation():
    """Verify that forward slashes are used even when resolving Windows-like paths."""
    # We use mocking to simulate a Path that has backslashes and see if .as_posix() is called
    ctx = PlaceholderContext(
        in_file="C:\\Users\\Dojo\\in.md",
    )
    with patch("dojo.wrap.Path") as mock_path:
        mock_instance = mock_path.return_value
        mock_instance.resolve.return_value.as_posix.return_value = "C:/Users/Dojo/in.md"
        mock_instance.resolve.return_value.parent.as_posix.return_value = "C:/Users/Dojo"

        val = resolve_placeholders("{in_abs}", ctx)
        assert "\\" not in val
        assert val == "C:/Users/Dojo/in.md"


def test_resolve_placeholders_root_val():
    # root_val is relpath from out_abs_dir to out_dir
    ctx = PlaceholderContext(
        out_file="/out/subdir/file.html",
        out_dir="/out",
    )

    # Surgical mock of Path.resolve that returns the path itself
    with patch("pathlib.Path.resolve", autospec=True) as mock_resolve:
        mock_resolve.side_effect = lambda self: self
        val = resolve_placeholders("{root_val}", ctx)
        assert val == ".."


def test_resolve_placeholders_rel_src_dir():
    ctx = PlaceholderContext(in_file="/build/content/index.md", build_dir="/build")

    with patch("pathlib.Path.resolve", autospec=True) as mock_resolve:
        mock_resolve.side_effect = lambda self: self
        val = resolve_placeholders("{rel_src_dir}", ctx)
        assert val == "content"


def test_setup_env_path_manipulation(monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    new_path = "/custom/bin:/another/bin"

    # Note: _setup_env converts colon to os.pathsep
    env = _setup_env(new_path)

    assert env["PATH"].startswith(f"/custom/bin{os.pathsep}/another/bin")


def test_setup_env_no_path(monkeypatch):
    monkeypatch.delenv("PATH", raising=False)
    env = _setup_env("/custom/bin")
    assert env["PATH"] == "/custom/bin"


def test_handle_copy_success(tmp_path):
    src = tmp_path / "src.txt"
    src.write_text("hello")
    dst = tmp_path / "dst.txt"

    with patch("sys.exit") as mock_exit:
        from dojo.wrap import _handle_copy

        _handle_copy(str(src), str(dst))
        mock_exit.assert_called_once_with(0)
    assert dst.read_text() == "hello"


def test_handle_copy_failure(tmp_path):
    with patch("sys.exit") as mock_exit, patch("sys.stderr.write") as mock_stderr:
        from dojo.wrap import _handle_copy

        _handle_copy("/nonexistent", "/also/nonexistent")
        mock_exit.assert_called_once_with(1)
        mock_stderr.assert_called()


def test_handle_exec_with_log(tmp_path):
    log_file = tmp_path / "test.log"
    cmd = ["echo", "hello world"]
    from dojo.wrap import _handle_exec

    with patch("sys.exit") as mock_exit:
        _handle_exec(cmd, os.environ.copy(), str(tmp_path), str(log_file))
        mock_exit.assert_called()

    assert log_file.exists()
    assert "hello world" in log_file.read_text()


def test_handle_exec_failure():
    from dojo.wrap import _handle_exec

    with patch("sys.exit") as mock_exit, patch("sys.stderr.write") as mock_stderr:
        # Non-existent command
        _handle_exec(["non_existent_command_xyz"], {}, None, None)
        mock_exit.assert_called_once_with(1)
        mock_stderr.assert_called()


@patch("dojo.wrap._handle_exec")
def test_run_wrap_no_command(mock_exec):
    with pytest.raises(SystemExit) as cm, patch("sys.stderr.write") as mock_stderr:
        run_wrap([])
    assert cm.value.code == 1
    mock_stderr.assert_called_with("Error: No command provided to dojo wrap\n")


@patch("dojo.wrap._handle_copy")
def test_run_wrap_copy_missing_args(mock_copy):
    with pytest.raises(SystemExit) as cm, patch("sys.stderr.write") as mock_stderr:
        run_wrap(["--copy", "src_only"])
    assert cm.value.code == 1
    mock_stderr.assert_called_with("Error: Copy requires source and destination\n")


@patch("dojo.wrap._handle_exec")
def test_run_wrap_double_dash(mock_exec):
    argv = ["--", "echo", "hello"]
    with patch("sys.exit"):
        run_wrap(argv)
    mock_exec.assert_called_once()
    assert mock_exec.call_args[0][0] == ["echo", "hello"]


def test_run_wrap_ensure_dir(tmp_path):
    target_dir = tmp_path / "new_dir"
    argv = ["--ensure-dir", str(target_dir), "--", "echo", "done"]
    with patch("sys.exit"):
        run_wrap(argv)
    assert target_dir.exists()


@patch("dojo.wrap._handle_copy")
def test_run_wrap_copy_integration(mock_copy):
    argv = ["--copy", "src.txt", "dst.txt"]
    with patch("sys.exit"):
        run_wrap(argv)
    mock_copy.assert_called_once_with("src.txt", "dst.txt")
