from pathlib import Path

from dojo.config import Config, ToolPaths, TypeConfig
from dojo.rules import _get_typst_flags, get_builtin_rules


def test_builtin_rules_basic():
    # Use real Config with minimal fields
    # Use model_construct to skip validation that requires real directories
    c = Config.model_construct(
        src_dir="src",
        output_dir="site",
        build_dir="build",
        default_type="page",
        types={"page": TypeConfig.model_construct(outputs=[])},
        tools=ToolPaths.model_construct(pandoc="pandoc"),
        root_ref_dir=".",
        add_resource_path=True,
        rule_pools={},
    )
    rules = get_builtin_rules(c, Path("config.yaml"))
    compile_rule = next(r for r in rules if r.name == "compile")

    # Verify dojo wrap injection
    assert "wrap.py" in compile_rule.command
    assert "--in-file $in_shell --out-file $out_shell" in compile_rule.command
    assert "-V root={root_val} -M root={root_val}" in compile_rule.command


def test_builtin_rules_with_custom_tool_paths(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    pandoc_exe = bin_dir / "pandoc"
    pandoc_exe.touch()

    # Use model_construct to avoid validation that might fail in test env
    tools = ToolPaths.model_construct(pandoc=str(pandoc_exe), python="python3")

    config = Config.model_construct(
        tools=tools,
        src_dir=str(tmp_path / "src"),
        output_dir=str(tmp_path / "_site"),
        build_dir=str(tmp_path / "_build"),
        root_ref_dir=".",
        add_resource_path=True,
        rule_pools={"compile": "heavy"},
        pools={"heavy": 4},
    )

    rules = get_builtin_rules(config, Path(tmp_path / "build" / "dojo.yaml"))

    compile_rule = next(r for r in rules if r.name == "compile")
    assert f"--path-env {bin_dir.as_posix()}" in compile_rule.command

    compile_rule = next(r for r in rules if r.name == "compile")
    assert compile_rule.pool == "heavy"


def test_builtin_rules_data_dir_relative_to_src(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    data_dir = src_dir / "assets" / "pandoc"
    data_dir.mkdir(parents=True)

    config = Config.model_construct(
        tools=ToolPaths.model_construct(pandoc="pandoc"),
        src_dir=str(src_dir),
        build_dir=str(tmp_path / "build"),
        root_ref_dir=str(src_dir),
        pandoc_data_dir=str(data_dir),
        add_resource_path=False,
        rule_pools={},
    )

    rules = get_builtin_rules(config, Path(tmp_path / "build" / "dojo.yaml"))
    render_rule = next(r for r in rules if r.name == "render")

    assert "dojo-data-dir=" in render_rule.command
    assert str(data_dir.resolve()) in render_rule.command


def test_builtin_rules_no_tools(tmp_path):
    config = Config.model_construct(
        tools=ToolPaths.model_construct(pandoc="pandoc"),
        src_dir="/src",
        build_dir="/build",
        root_ref_dir="/src",
        pandoc_data_dir=None,
        rule_pools={},
    )

    rules = get_builtin_rules(config, Path("dojo.yaml"))
    regen_rule = next(r for r in rules if r.name == "regenerate")
    assert "dojo build" in regen_rule.command
    assert "PYTHONPATH=" in regen_rule.command


def test_builtin_rules_crunch():
    c = Config.model_construct(
        src_dir="src",
        output_dir="site",
        build_dir="build",
        default_type="page",
        types={},
        tools=ToolPaths.model_construct(pandoc="pandoc"),
        root_ref_dir=".",
        add_resource_path=True,
        rule_pools={"crunch": "heavy"},
    )
    rules = get_builtin_rules(c, Path("config.yaml"))
    crunch_rule = next(r for r in rules if r.name == "crunch")
    assert "wrap.py" in crunch_rule.command
    assert "-m dojo.crunch" in crunch_rule.command
    assert crunch_rule.pool == "heavy"


def test_builtin_rules_ghostscript():
    c = Config.model_construct(
        src_dir="src",
        output_dir="site",
        build_dir="build",
        default_type="page",
        types={},
        tools=ToolPaths.model_construct(pandoc="pandoc", ghostscript="gs"),
        root_ref_dir=".",
        add_resource_path=True,
        rule_pools={"ghostscript": "heavy"},
    )
    rules = get_builtin_rules(c, Path("config.yaml"))
    gs_rule = next(r for r in rules if r.name == "ghostscript")
    assert "wrap.py" in gs_rule.command
    assert "gs -sDEVICE=pdfwrite" in gs_rule.command
    assert "-dCompatibilityLevel=1.7" in gs_rule.command
    assert "-dPDFSETTINGS=/printer" in gs_rule.command
    assert "-sColorConversionStrategy=LeaveColorUnchanged" in gs_rule.command
    assert "-dCompressFonts=true" in gs_rule.command
    assert "-dSubsetFonts=true" in gs_rule.command
    assert "-dDetectDuplicateImages=true" in gs_rule.command
    assert "-dFastWebView" not in gs_rule.command
    assert "-dNOPAUSE" in gs_rule.command
    assert "-dQUIET" in gs_rule.command
    assert "-dBATCH" in gs_rule.command
    assert "$args -sOutputFile={out_abs} {in_abs}" in gs_rule.command
    assert gs_rule.pool == "heavy"


def test_typst_flags(tmp_path, monkeypatch):
    """Test get_typst_flags with font_paths, pandoc_data_dir fonts, and TYPST_FONT_PATHS."""
    font_dir = tmp_path / "fonts"
    font_dir.mkdir()

    data_dir = tmp_path / "data"
    (data_dir / "fonts").mkdir(parents=True)

    monkeypatch.setenv("TYPST_FONT_PATHS", str(tmp_path / "env_fonts"))

    cfg = Config.model_construct(
        src_dir=str(tmp_path / "src"),
        font_paths=[str(font_dir)],
        pandoc_data_dir=str(data_dir),
    )

    flags = _get_typst_flags(cfg)
    flags_str = " ".join(flags)
    assert str(font_dir.resolve().as_posix()) in flags_str
    assert str((tmp_path / "env_fonts").as_posix()) in flags_str


def test_typst_flags_pandoc_data_dir_fonts(tmp_path):
    """Test get_typst_flags includes pandoc_data_dir/fonts when font_paths is not set."""
    data_dir = tmp_path / "data"
    (data_dir / "fonts").mkdir(parents=True)

    cfg = Config.model_construct(
        src_dir=str(tmp_path / "src"),
        font_paths=[],
        pandoc_data_dir=str(data_dir),
    )

    flags = _get_typst_flags(cfg)
    flags_str = " ".join(flags)
    assert str((data_dir / "fonts").as_posix()) in flags_str


def test_builtin_rules_decktape_log_file(tmp_path):
    """Test decktape rule includes --log-file when config.log_file is set."""
    log_file = tmp_path / "decktape.log"
    cfg = Config.model_construct(
        src_dir="src",
        output_dir="site",
        build_dir="build",
        default_type="page",
        types={},
        tools=ToolPaths.model_construct(pandoc="pandoc", decktape="decktape"),
        root_ref_dir=".",
        add_resource_path=True,
        rule_pools={},
        log_file=str(log_file),
    )
    rules = get_builtin_rules(cfg, Path("config.yaml"))
    decktape_rule = next(r for r in rules if r.name == "decktape")
    assert "--log-file" in decktape_rule.command
    assert log_file.resolve().as_posix() in decktape_rule.command
