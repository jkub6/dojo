from pathlib import Path

import pytest

from dojo.config import Config
from dojo.core import NinjaGenerator


@pytest.fixture
def basic_config(tmp_path):
    src = tmp_path / "content"
    src.mkdir()

    return Config(
        src_dir=str(src),
        output_dir=str(tmp_path / "_site"),
        build_dir=str(tmp_path / "_build"),
        default_type="markdown",
        types={"markdown": {"outputs": []}},
    ), tmp_path / "config.yaml"


def test_generator_initialization(basic_config):
    config, path = basic_config
    generator = NinjaGenerator(config, path)

    assert generator.src == Path(config.src_dir).resolve()
    assert generator.build_dir == Path(config.build_dir).resolve()
    assert generator.ninja_file.name == "build.ninja"


def test_header_generation(basic_config):
    config, path = basic_config
    generator = NinjaGenerator(config, path)

    generator.emit_header()

    content = "\n".join(generator.buffer)
    assert "ninja_required_version" in content
    assert "rule regenerate" in content
    assert "rule compile" in content
