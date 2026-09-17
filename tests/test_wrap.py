import os
import urllib.request
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from dojo.wrap import (
    PlaceholderContext,
    _handle_copy,
    _handle_exec,
    _inject_metadata_overrides,
    _inject_slide_level,
    _inject_toc,
    _setup_env,
    _start_server,
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
        _handle_copy(str(src), str(dst))
        mock_exit.assert_called_once_with(0)
    assert dst.read_text() == "hello"


def test_handle_copy_failure(tmp_path):
    with patch("sys.exit") as mock_exit, patch("sys.stderr.write") as mock_stderr:
        _handle_copy("/nonexistent", "/also/nonexistent")
        mock_exit.assert_called_once_with(1)
        mock_stderr.assert_called()


def test_handle_exec_with_log(tmp_path):
    log_file = tmp_path / "test.log"
    cmd = ["echo", "hello world"]

    with patch("sys.exit") as mock_exit:
        with log_file.open("a", encoding="utf-8") as lf:
            _handle_exec(cmd, os.environ.copy(), str(tmp_path), log_handler=lf)
        mock_exit.assert_called()

    assert log_file.exists()
    assert "hello world" in log_file.read_text()


def test_handle_exec_failure():
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


def test_resolve_placeholders_url():
    ctx = PlaceholderContext(
        in_file="/src/file.md",
        serve_dir="/src",
        serve_port=8080,
    )
    # Surgical mock of Path.resolve
    with patch("pathlib.Path.resolve", autospec=True) as mock_resolve:
        mock_resolve.side_effect = lambda self: self
        val = resolve_placeholders("{url}", ctx)
        assert val == "http://localhost:8080/file.md"


def test_start_server(tmp_path):
    serve_dir = tmp_path / "serve"
    serve_dir.mkdir()
    (serve_dir / "index.html").write_text("hello")

    log_handler = StringIO()
    server, port = _start_server(str(serve_dir), log_handler)

    try:
        assert port > 0
        assert "DOJO SERVER: Starting" in log_handler.getvalue()
        assert str(serve_dir) in log_handler.getvalue()
    finally:
        server.shutdown()
        server.server_close()


def test_run_wrap_with_log_file(tmp_path):
    log_file = tmp_path / "wrap.log"
    argv = ["--log-file", str(log_file), "--", "echo", "logged message"]

    with patch("sys.exit"), patch("dojo.wrap._handle_exec") as mock_exec:
        run_wrap(argv)
        mock_exec.assert_called_once()
        # Verify log file was created
        assert log_file.exists()


def test_run_wrap_with_server(tmp_path):
    serve_dir = tmp_path / "serve"
    serve_dir.mkdir()
    argv = ["--serve-dir", str(serve_dir), "--", "echo", "server test"]

    with (
        patch("sys.exit"),
        patch("dojo.wrap._start_server") as mock_start,
        patch("dojo.wrap._handle_exec"),
    ):
        mock_start.return_value = (patch("http.server.ThreadingHTTPServer").start(), 1234)
        run_wrap(argv)
        mock_start.assert_called_once()


def test_resolve_placeholders_complex_paths():
    """Test more complex path resolutions including root_val and rel_src_dir."""
    ctx = PlaceholderContext(
        in_file="/build/content/posts/first.md",
        out_file="/out/posts/first.html",
        src_dir="/src",
        out_dir="/out",
        build_dir="/build",
    )

    with patch("pathlib.Path.resolve", autospec=True) as mock_resolve:
        mock_resolve.side_effect = lambda self: self
        # root_val: relpath from out_abs_dir (/out/posts) to out_dir (/out) -> ..
        assert resolve_placeholders("{root_val}", ctx) == ".."

        # rel_src_dir: relpath from in_abs_dir (/build/content/posts) to build_dir (/build) -> content/posts
        assert resolve_placeholders("{rel_src_dir}", ctx) == "content/posts"

        # src_dir_val: src_dir (/src) + rel_src_dir (content/posts) -> /src/content/posts
        assert resolve_placeholders("{src_dir_val}", ctx) == "/src/content/posts"


def test_handle_exec_unlinks_on_nonzero_exit(tmp_path):
    """Verify _handle_exec removes out_file if command returns non-zero."""
    out_file = tmp_path / "failed_output.html"
    out_file.write_text("partial output", encoding="utf-8")

    with (
        patch("sys.exit") as mock_exit,
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value.returncode = 2
        _handle_exec(["fake_cmd"], {}, None, out_file=str(out_file))
        assert not out_file.exists()
        mock_exit.assert_called_once_with(2)


def test_handle_exec_unlinks_on_oserror(tmp_path):
    """Verify _handle_exec removes out_file if command execution raises OSError."""
    out_file = tmp_path / "failed_output.html"
    out_file.write_text("partial output", encoding="utf-8")

    with (
        patch("sys.exit") as mock_exit,
        patch("subprocess.run", side_effect=OSError("Exec failed")),
    ):
        _handle_exec(["fake_cmd"], {}, None, out_file=str(out_file))
        assert not out_file.exists()
        mock_exit.assert_called_once_with(1)


def test_resolve_placeholders_out_abs_dir_not_in_build():
    """Verify root_val falls back to out_dir when out_abs_dir is outside build_dir."""
    ctx = PlaceholderContext(
        out_file="/out/site/index.html",
        out_dir="/out/site",
        build_dir="/different/build",
    )
    with patch("pathlib.Path.resolve", autospec=True) as mock_resolve:
        mock_resolve.side_effect = lambda self: self
        root = resolve_placeholders("{root_val}", ctx)
        assert root == "."


def test_inject_metadata_overrides_corrupt_json(tmp_path, capsys):
    """Verify _inject_metadata_overrides gracefully handles invalid JSON in AST."""
    corrupt_file = tmp_path / "corrupt.json"
    corrupt_file.write_text("not json", encoding="utf-8")

    cmd = ["pandoc", "input.json", "-o", "output.html"]
    _inject_metadata_overrides(cmd, str(corrupt_file))
    captured = capsys.readouterr()
    assert "Failed to extract metadata from AST" in captured.err


def test_resolve_placeholders_out_abs_dir_inside_build():
    """Verify root_val uses build_dir when out_abs_dir is within build_dir."""
    ctx = PlaceholderContext(
        out_file="/build/site/index.html",
        out_dir="/build/site",
        build_dir="/build",
    )
    with patch("pathlib.Path.resolve", autospec=True) as mock_resolve:
        mock_resolve.side_effect = lambda self: self
        root = resolve_placeholders("{root_val}", ctx)
        assert root == ".."


def test_get_srv_repls_value_error():
    """Verify _get_srv_repls gracefully ignores ValueError from relpath."""
    ctx = PlaceholderContext(
        serve_dir="/srv",
        serve_port=8000,
        in_file="/other/file.html",
    )
    with patch("os.path.relpath", side_effect=ValueError("different drives")):
        assert resolve_placeholders("{url}", ctx) == "{url}"


def test_handle_exec_non_existent_out_file_on_error(tmp_path):
    """Verify _handle_exec does not attempt unlink if out_file does not exist."""
    missing = tmp_path / "missing.html"
    with (
        patch("sys.exit") as mock_exit,
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value.returncode = 1
        _handle_exec(["cmd"], {}, None, out_file=str(missing))
        mock_exit.assert_called_once_with(1)

    with (
        patch("sys.exit") as mock_exit,
        patch("subprocess.run", side_effect=OSError("Boom")),
    ):
        _handle_exec(["cmd"], {}, None, out_file=str(missing))
        mock_exit.assert_called_once_with(1)


def test_start_server_logging_and_http_request(tmp_path):
    """Verify _start_server request logging with and without log_handler."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello", encoding="utf-8")

    # With log_handler
    log_buf = StringIO()
    server1, port1 = _start_server(str(tmp_path), log_buf)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port1}/test.txt") as resp:
            assert resp.read() == b"hello"
    finally:
        server1.shutdown()
        server1.server_close()
    assert "DOJO SERVER: Starting" in log_buf.getvalue()
    assert "HTTP:" in log_buf.getvalue()

    # Without log_handler (writes to sys.stderr)
    server2, port2 = _start_server(str(tmp_path), None)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port2}/test.txt") as resp:
            assert resp.read() == b"hello"
    finally:
        server2.shutdown()
        server2.server_close()


def test_inject_slide_level_edge_cases():
    """Verify _inject_slide_level handles non-dict and unhandled AST types."""
    cmd = ["pandoc"]
    _inject_slide_level(cmd, {"slide-level": "not_a_dict"})
    assert cmd == ["pandoc"]

    _inject_slide_level(cmd, {"slide-level": {"t": "MetaList", "c": []}})
    assert cmd == ["pandoc"]


def test_inject_toc_edge_cases():
    """Verify _inject_toc handles invalid structures and redundant flags."""
    cmd = ["pandoc"]
    _inject_toc(cmd, {"toc": "not_a_dict"})
    assert cmd == ["pandoc"]

    _inject_toc(cmd, {"toc": {"t": "MetaString", "c": "true"}})
    assert cmd == ["pandoc"]

    # When --toc is already present and c is True
    cmd_with_toc = ["pandoc", "--toc"]
    _inject_toc(cmd_with_toc, {"toc": {"t": "MetaBool", "c": True}})
    assert cmd_with_toc == ["pandoc", "--toc"]

    # When --toc is not present and c is False
    cmd_without_toc = ["pandoc"]
    _inject_toc(cmd_without_toc, {"toc": {"t": "MetaBool", "c": False}})
    assert cmd_without_toc == ["pandoc"]


def test_run_wrap_ensure_dir_resolves_to_empty():
    """Verify run_wrap skips mkdir if resolve_placeholders returns empty string."""
    with (
        patch("dojo.wrap.resolve_placeholders", return_value=""),
        patch("dojo.wrap._handle_exec") as mock_exec,
        patch("pathlib.Path.mkdir") as mock_mkdir,
    ):
        run_wrap(["--ensure-dir", "placeholder_to_empty", "--", "echo", "hi"])
        mock_mkdir.assert_not_called()
        mock_exec.assert_called_once()
