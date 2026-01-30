import io
from pathlib import Path

import pytest

from dojo.config import Config
from dojo.emitter import NinjaEmitter
from dojo.exceptions import DirectoryConflictError, DuplicateOutputIdError


def test_directory_conflict(tmp_path):
    src = tmp_path / "src"
    src.mkdir()

    # src_dir and build_dir same
    data = {
        "src_dir": str(src),
        "build_dir": str(src),
        "default_type": "markdown",
        "types": {"markdown": {"outputs": []}},
    }
    with pytest.raises(DirectoryConflictError, match="Directory conflict"):
        Config(**data)

    with pytest.raises(DirectoryConflictError, match="Directory conflict"):
        Config(**data)

    # one inside another - now allowed if child is output/build
    build = src / "build"
    build.mkdir()
    data["build_dir"] = str(build)

    # Validation should succeed now
    cfg = Config(**data)
    # And build dir should be excluded
    assert "build" in cfg.exclude


def test_duplicate_output_ids(tmp_path):
    src = tmp_path / "src"
    src.mkdir()

    data = {
        "src_dir": str(src),
        "default_type": "markdown",
        "types": {
            "markdown": {
                "outputs": [
                    {"id": "foo", "extension": "html", "defaults": []},
                    {"id": "foo", "extension": "pdf", "source": "foo", "tool": "bar"},
                ]
            }
        },
    }
    # Wait, the second one depends on 'foo', but its own id is 'foo'.
    # This should trigger duplicate ID validation.
    with pytest.raises(DuplicateOutputIdError, match="Duplicate output IDs"):
        Config(**data)


def test_ninja_emitter_basic():
    buf = io.StringIO()
    emitter = NinjaEmitter(buf)

    emitter.comment("Hello")
    emitter.variable("v", "1")
    emitter.rule("r", "cmd $in $out")
    emitter.build(Path("out"), "r", Path("in"), variables={"foo": "bar"})

    content = buf.getvalue()
    assert "# Hello" in content
    assert "v = 1" in content
    assert "rule r" in content
    assert "  command = cmd $in $out" in content
    assert "build out: r in" in content
    assert "  foo = bar" in content


def test_ninja_emitter_complex_build():
    buf = io.StringIO()
    emitter = NinjaEmitter(buf)

    emitter.build(
        outputs=[Path("out1"), Path("out2")],
        rule="myrule",
        inputs=[Path("in1"), Path("in2")],
        implicit=[Path("imp")],
        order_only=[Path("oo")],
        variables={"v": "val"},
    )

    content = buf.getvalue()
    assert "build out1 out2: myrule in1 in2 | imp || oo" in content
    assert "  v = val" in content
