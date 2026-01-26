import pytest
import yaml

from dojo.config import Config, load_config


def test_config_validation_valid(tmp_path):
    src = tmp_path / "src"
    src.mkdir()

    data = {"src_dir": str(src), "default_type": "markdown", "types": {"markdown": {"outputs": []}}}

    config = Config(**data)
    assert config.src_dir == str(src)


def test_config_missing_src(tmp_path):
    data = {"src_dir": str(tmp_path / "nonexistent"), "default_type": "markdown", "types": {}}

    with pytest.raises(ValueError, match="Source directory not found"):
        Config(**data)


def test_config_invalid_default_type(tmp_path):
    src = tmp_path / "src"
    src.mkdir()

    data = {
        "src_dir": str(src),
        "default_type": "missing_type",
        "types": {"markdown": {"outputs": []}},
    }

    with pytest.raises(ValueError, match="not found in types"):
        Config(**data)


def test_load_config_local(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    config_file = tmp_path / "dojo.yaml"
    src = tmp_path / "content"
    src.mkdir()

    data = {"src_dir": "content", "default_type": "md", "types": {"md": {"outputs": []}}}

    with open(config_file, "w") as f:
        yaml.dump(data, f)

    config, path = load_config()
    assert config.src_dir == "content"
    assert path == config_file
