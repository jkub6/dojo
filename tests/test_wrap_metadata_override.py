import json
from unittest.mock import patch

from dojo.wrap import run_wrap


@patch("dojo.wrap._handle_exec")
def test_run_wrap_metadata_override_slide_level_string(mock_exec, tmp_path):
    ast_path = tmp_path / "test.json"
    ast_path.write_text(json.dumps({"meta": {"slide-level": {"t": "MetaString", "c": "3"}}}))

    argv = ["--in-file", str(ast_path), "--", "pandoc", "input.json", "-o", "output.html"]
    with patch("sys.exit"):
        run_wrap(argv)

    # Check if --slide-level=3 was injected
    called_cmd = mock_exec.call_args[0][0]
    assert called_cmd[0] == "pandoc"
    assert called_cmd[1] == "--slide-level=3"


@patch("dojo.wrap._handle_exec")
def test_run_wrap_metadata_override_slide_level_inlines(mock_exec, tmp_path):
    ast_path = tmp_path / "test.json"
    ast_path.write_text(
        json.dumps({"meta": {"slide-level": {"t": "MetaInlines", "c": [{"t": "Str", "c": "4"}]}}})
    )

    argv = ["--in-file", str(ast_path), "--", "pandoc", "input.json", "-o", "output.html"]
    with patch("sys.exit"):
        run_wrap(argv)

    # Check if --slide-level=4 was injected
    called_cmd = mock_exec.call_args[0][0]
    assert called_cmd[0] == "pandoc"
    assert called_cmd[1] == "--slide-level=4"


@patch("dojo.wrap._handle_exec")
def test_run_wrap_metadata_override_toc_true(mock_exec, tmp_path):
    ast_path = tmp_path / "test.json"
    ast_path.write_text(json.dumps({"meta": {"toc": {"t": "MetaBool", "c": True}}}))

    argv = ["--in-file", str(ast_path), "--", "pandoc", "input.json", "-o", "output.html"]
    with patch("sys.exit"):
        run_wrap(argv)

    called_cmd = mock_exec.call_args[0][0]
    assert "--toc" in called_cmd


@patch("dojo.wrap._handle_exec")
def test_run_wrap_metadata_override_toc_false(mock_exec, tmp_path):
    ast_path = tmp_path / "test.json"
    ast_path.write_text(json.dumps({"meta": {"toc": {"t": "MetaBool", "c": False}}}))

    # It should remove --toc if it was there
    argv = ["--in-file", str(ast_path), "--", "pandoc", "--toc", "input.json", "-o", "output.html"]
    with patch("sys.exit"):
        run_wrap(argv)

    called_cmd = mock_exec.call_args[0][0]
    assert "--toc" not in called_cmd
