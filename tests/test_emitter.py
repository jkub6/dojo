import io

from dojo.emitter import NinjaEmitter


def test_emitter_comment():
    fp = io.StringIO()
    emitter = NinjaEmitter(fp)
    emitter.comment("Test comment")
    assert fp.getvalue() == "# Test comment\n"


def test_emitter_newline():
    fp = io.StringIO()
    emitter = NinjaEmitter(fp)
    emitter.newline()
    assert fp.getvalue() == "\n"


def test_emitter_variable():
    fp = io.StringIO()
    emitter = NinjaEmitter(fp)
    emitter.variable("name", "value")
    emitter.variable("indented", "val", indent=1)
    assert fp.getvalue() == "name = value\n  indented = val\n"


def test_emitter_rule_full():
    fp = io.StringIO()
    emitter = NinjaEmitter(fp)
    emitter.rule(
        "complex",
        "echo $in",
        description="Complex rule",
        pool="heavy",
        depfile="deps.d",
        deps="gcc",
        generator=True,
        variables={"custom": "val"},
    )
    output = fp.getvalue()
    assert "rule complex\n" in output
    assert "  command = echo $in\n" in output
    assert "  description = Complex rule\n" in output
    assert "  pool = heavy\n" in output
    assert "  depfile = deps.d\n" in output
    assert "  deps = gcc\n" in output
    assert "  generator = 1\n" in output
    assert "  custom = val\n" in output


def test_emitter_basic_build():
    fp = io.StringIO()
    emitter = NinjaEmitter(fp)
    emitter.build(outputs="out.html", rule="pandoc", inputs="in.md")
    content = fp.getvalue()
    assert "build out.html: pandoc in.md\n" in content


def test_emitter_escaping_spaces():
    fp = io.StringIO()
    emitter = NinjaEmitter(fp)
    emitter.build(outputs="out folder/file.html", rule="pandoc", inputs="in folder/file.md")
    content = fp.getvalue()
    # Ninja uses $ to escape spaces
    assert "build out$ folder/file.html: pandoc in$ folder/file.md\n" in content


def test_emitter_variables():
    fp = io.StringIO()
    emitter = NinjaEmitter(fp)
    emitter.build(
        outputs="out.html",
        rule="pandoc",
        inputs="in.md",
        variables={"args": "--standalone", "path": "some$path"},
    )
    content = fp.getvalue()
    assert "  args = --standalone\n" in content
    assert "  path = some$path\n" in content


def test_emitter_implicit_order_deps():
    fp = io.StringIO()
    emitter = NinjaEmitter(fp)
    emitter.build(
        outputs="out.html",
        rule="pandoc",
        inputs="in.md",
        implicit="style.css",
        order_only="config.yaml",
    )
    content = fp.getvalue()
    assert "build out.html: pandoc in.md | style.css || config.yaml\n" in content


def test_emitter_multiple_outputs():
    fp = io.StringIO()
    emitter = NinjaEmitter(fp)
    emitter.build(outputs=["out1.html", "out2.html"], rule="pandoc", inputs="in.md")
    content = fp.getvalue()
    assert "build out1.html out2.html: pandoc in.md\n" in content
