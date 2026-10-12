from pathlib import Path

import pytest

from dojo.config import Config, CustomRule
from dojo.core import NinjaGenerator
from dojo.exceptions import DefaultsRequiredError


@pytest.fixture
def flex_config(tmp_path):
    src = tmp_path / "content"
    src.mkdir()
    d1 = tmp_path / "d1.yaml"
    d2 = tmp_path / "d2.yaml"
    d1.touch()
    d2.touch()

    return Config(
        src_dir=str(src),
        output_dir=str(tmp_path / "_site"),
        build_dir=str(tmp_path / "_build"),
        default_type="md",
        types={
            "md": {
                "outputs": [
                    {"id": "multi_defaults", "extension": "html", "defaults": [str(d1), str(d2)]},
                    {
                        "id": "derived",
                        "extension": "pdf",
                        "source": "multi_defaults",
                        "tool": "decktape",
                        # No defaults required here
                    },
                ],
            },
        },
    ), tmp_path / "dojo.yaml"


def test_multiple_defaults_generation(flex_config):
    config, path = flex_config
    generator = NinjaGenerator(config, path)

    # Mock source file
    (Path(config.src_dir) / "test.md").touch()

    generator.generate()

    ninja_content = generator.ninja_file.read_text()

    assert len(list((Path(config.build_dir) / "defaults").glob("*.yaml"))) == 2
    assert str(Path(config.src_dir).parent / "d1.yaml") in ninja_content
    assert str(Path(config.src_dir).parent / "d2.yaml") in ninja_content


def test_optional_defaults(tmp_path):
    # Valid config: derived output has no defaults
    src = tmp_path / "content"
    src.mkdir()
    d1 = tmp_path / "d1.yaml"
    d1.touch()

    conf = Config(
        src_dir=str(src),
        default_type="md",
        types={
            "md": {
                "outputs": [
                    {"id": "base", "extension": "html", "defaults": str(d1)},
                    {"extension": "pdf", "source": "base", "tool": "decktape"},
                ],
            },
        },
    )
    assert conf.types["md"].outputs[1].defaults is None


def test_missing_defaults_error(tmp_path):
    src = tmp_path / "content"
    src.mkdir()

    # Invalid: non-derived output MUST have defaults
    with pytest.raises(
        DefaultsRequiredError,
        match="Outputs without 'source' must specify 'defaults'",
    ):
        Config(
            src_dir=str(src),
            default_type="md",
            types={"md": {"outputs": [{"extension": "html"}]}},
        )


def test_multiple_sources_generation(tmp_path):
    src = tmp_path / "content"
    src.mkdir()
    d1 = tmp_path / "d1.yaml"
    d1.touch()

    conf = Config(
        src_dir=str(src),
        output_dir=str(tmp_path / "_site"),
        build_dir=str(tmp_path / "_build"),
        default_type="md",
        types={
            "md": {
                "outputs": [
                    {"id": "p1", "extension": "html", "defaults": str(d1)},
                    {"id": "p2", "extension": "html", "suffix": "-second", "defaults": str(d1)},
                    {"extension": "pdf", "source": ["p1", "p2"], "tool": "merge_tool"},
                ],
            },
        },
    )

    conf.custom_rules = [CustomRule(name="merge_tool", command="cat $in > $out")]
    generator = NinjaGenerator(conf, tmp_path / "dojo.yaml")
    (src / "doc.md").touch()

    generator.generate()
    content = generator.ninja_file.read_text()

    assert "merge_tool" in content
    assert "doc-second.html" in content
