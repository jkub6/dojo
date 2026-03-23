from pathlib import Path

from dojo.config import Config, ToolPaths, TypeConfig
from dojo.rules import get_builtin_rules


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

    # Check for setup variables (Ninja uses $$ for literal $)
    assert "in_abs=$$(realpath $in_shell)" in compile_rule.command
    assert "root_val=$$(realpath -m --relative-to=$$(dirname $in_shell) .)" in compile_rule.command


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

    regen_rule = next(r for r in rules if r.name == "regenerate")
    assert f'PATH="{bin_dir}:' in regen_rule.command

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

    assert "dojo-data-dir=assets/pandoc" in render_rule.command


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
    assert regen_rule.command.startswith("dojo build")
