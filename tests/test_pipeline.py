import pytest

from dojo.config import Config
from dojo.core import NinjaGenerator


@pytest.fixture
def pipeline_config_data(tmp_path):
    src = tmp_path / "content"
    src.mkdir()
    (src / "test.md").write_text("---\ntype: slides\n---\n# Slides")

    defaults = tmp_path / "defaults.yaml"
    defaults.touch()

    return {
        "src_dir": str(src),
        "output_dir": str(tmp_path / "site"),
        "build_dir": str(tmp_path / "build"),
        "default_type": "slides",
        "types": {
            "slides": {
                "outputs": [
                    {"id": "html", "extension": "html", "defaults": str(defaults)},
                    {
                        "id": "pdf",
                        "extension": "pdf",
                        "source": "html",
                        "tool": "decktape",
                        "args": ["--size", "A4"],
                        "post_process": [
                            {"tool": "ghostscript", "args": ["-dPDFSETTINGS=/screen"]},
                            "minify",
                        ],
                    },
                ]
            }
        },
    }


def test_pipeline_generation(pipeline_config_data, tmp_path):
    # This test will fail until we implement the changes
    cfg = Config(**pipeline_config_data)
    gen = NinjaGenerator(cfg, tmp_path / "dojo.yaml")

    gen.generate()

    ninja_content = gen.ninja_file.read_text()

    # 1. Check decktape (initial tool) uses its args
    assert "decktape" in ninja_content
    assert "--size A4" in ninja_content

    # 2. Check ghostscript uses its args
    assert "ghostscript" in ninja_content
    assert "-dPDFSETTINGS=/screen" in ninja_content

    # 3. Check minify is called
    assert "minify" in ninja_content

    # 4. Check the chain: decktape -> GS -> minify
    # We expect intermediate files
    assert ".dojo-tmp-" in ninja_content
    # Depending on implementation, we might see .1, .2 suffixes or similar
