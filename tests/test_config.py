from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from dojo.config import Config, OutputConfig, ToolPaths, load_config

# --- ToolPaths Tests ---


def test_tool_paths_defaults():
    tp = ToolPaths()
    assert tp.python.endswith("python3")
    assert tp.pandoc.endswith("pandoc")


@patch("shutil.which")
def test_tool_paths_resolution(mock_which):
    mock_which.return_value = "/usr/bin/custom_python"
    tp = ToolPaths(python="python_alias")
    assert tp.python == "/usr/bin/custom_python"


@patch("shutil.which")
def test_tool_paths_missing_essential(mock_which):
    mock_which.return_value = None
    # Pydantic wraps validation errors
    with pytest.raises(Exception) as excinfo:
        ToolPaths(pandoc="missing_pandoc")
    assert "Essential tool 'python' not found" in str(excinfo.value)


def test_tool_paths_missing_optional():
    # Minify is optional in strict sense. config.py checks python, pandoc.
    with patch("shutil.which") as mock_which:
        # Mock essential tools to be found, but minify missing
        mock_which.side_effect = (
            lambda x: "/bin/found" if x in ["python", "python3", "pandoc"] else None
        )

        tp = ToolPaths(minify="nonexistent")
        # should not raise, just keep default or what was passed
        assert tp.minify == "nonexistent"


# --- OutputConfig Tests ---


def test_output_config_validation_source_tool():
    with pytest.raises(ValueError, match="Outputs with 'source' must also specify 'tool'"):
        OutputConfig(extension="pdf", source="html")


def test_output_config_validation_defaults_or_source():
    with pytest.raises(ValueError, match="Outputs without 'source' must specify 'defaults'"):
        OutputConfig(extension="html", defaults=None, source=None)


def test_output_config_defaults_not_found():
    with pytest.raises(ValueError, match="Defaults file not found"):
        OutputConfig(extension="html", defaults="nonexistent.yaml")


def test_output_config_valid_defaults(tmp_path):
    d = tmp_path / "defaults.yaml"
    d.touch()
    oc = OutputConfig(extension="html", defaults=str(d))
    assert oc.defaults == str(d)


# --- Config Validation Tests ---


@pytest.fixture
def valid_config_data(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "defaults.yaml").touch()
    return {
        "src_dir": str(tmp_path / "src"),
        "output_dir": str(tmp_path / "site"),
        "build_dir": str(tmp_path / "build"),
        "default_type": "page",
        "types": {
            "page": {
                "outputs": [
                    {"id": "html", "extension": "html", "defaults": str(tmp_path / "defaults.yaml")}
                ]
            }
        },
        "defaults": str(tmp_path / "defaults.yaml"),
    }


def test_config_valid(valid_config_data):
    cfg = Config(**valid_config_data)
    assert cfg.src_dir == valid_config_data["src_dir"]


def test_config_invalid_default_type(valid_config_data):
    valid_config_data["default_type"] = "post"
    with pytest.raises(ValueError, match="default_type 'post' not found"):
        Config(**valid_config_data)


def test_config_dir_conflict_equality(valid_config_data):
    valid_config_data["output_dir"] = valid_config_data["src_dir"]
    with pytest.raises(ValueError, match="Directory conflict"):
        Config(**valid_config_data)


def test_config_dir_conflict_nesting(valid_config_data):
    valid_config_data["output_dir"] = str(Path(valid_config_data["src_dir"]) / "site")
    with pytest.raises(ValueError, match="is inside"):
        Config(**valid_config_data)


def test_config_duplicate_output_ids(valid_config_data):
    valid_config_data["types"]["page"]["outputs"].append(
        {"id": "html", "extension": "htm", "defaults": valid_config_data["defaults"]}
    )
    with pytest.raises(ValueError, match="Duplicate output IDs"):
        Config(**valid_config_data)


def test_config_custom_rule_conflict(valid_config_data):
    valid_config_data["custom_rules"] = [{"name": "compile", "command": "echo"}]
    with pytest.raises(ValueError, match="conflicts with built-in rule"):
        Config(**valid_config_data)


def test_validate_src_dir_missing(valid_config_data):
    valid_config_data["src_dir"] = "nonexistent_src"
    with pytest.raises(ValueError, match="Source directory not found"):
        Config(**valid_config_data)


def test_validate_defaults_missing(valid_config_data):
    valid_config_data["defaults"] = "missing.yaml"
    with pytest.raises(ValueError, match="Defaults file not found"):
        Config(**valid_config_data)


# --- load_config Tests ---


def test_load_config_cli_arg(tmp_path):
    c = tmp_path / "my_conf.yaml"
    (tmp_path / "src").mkdir()
    c.write_text(
        yaml.dump(
            {"src_dir": str(tmp_path / "src"), "default_type": "t", "types": {"t": {"outputs": []}}}
        )
    )

    _, p = load_config(str(c))
    assert p == c.resolve()


def test_load_config_env_var(tmp_path, monkeypatch):
    c = tmp_path / "env_conf.yaml"
    (tmp_path / "src").mkdir()
    c.write_text(
        yaml.dump(
            {"src_dir": str(tmp_path / "src"), "default_type": "t", "types": {"t": {"outputs": []}}}
        )
    )

    monkeypatch.setenv("DOJO_CONFIG", str(c))
    _, p = load_config()
    assert p == c.resolve()


def test_load_config_not_found(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError, match="No configuration file found"):
        load_config()


def test_load_config_explicit_not_found(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError, match="Configuration file not found"):
        load_config("missing.yaml")


def test_load_config_invalid_yaml(tmp_path):
    c = tmp_path / "bad.yaml"
    c.write_text("invalid: [")
    with pytest.raises(ValueError, match="Error parsing configuration file"):
        load_config(str(c))


def test_load_config_invalid_schema(tmp_path):
    c = tmp_path / "bad_schema.yaml"
    c.write_text("src_dir: missing")
    with pytest.raises(ValueError, match="Invalid configuration"):
        load_config(str(c))
