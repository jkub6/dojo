from pathlib import Path

from dojo.config import Config
from dojo.rules import get_builtin_rules


def test_config_defaults():
    c = Config(
        src_dir="src",
        output_dir="site",
        build_dir="build",
        default_type="page",
        types={"page": {"outputs": []}},
    )
    assert c.root_ref_dir == "."
    assert c.xdg_data_home is None
    assert c.add_resource_path is True


def test_config_overrides(tmp_path: Path):
    c = Config(
        src_dir="src",
        output_dir="site",
        build_dir="build",
        default_type="page",
        types={"page": {"outputs": []}},
        root_ref_dir="..",
        xdg_data_home=str(tmp_path / "data"),
        add_resource_path=False,
    )
    assert c.root_ref_dir == ".."
    assert c.xdg_data_home == str(tmp_path / "data")
    assert c.add_resource_path is False


def test_rule_generation_defaults():
    c = Config(
        src_dir="src",
        output_dir="site",
        build_dir="build",
        default_type="page",
        types={"page": {"outputs": []}},
    )
    rules = get_builtin_rules(c, Path("config.yaml"))
    compile_rule = next(r for r in rules if r.name == "compile")

    # Check for setup variables
    assert "in_abs=$$(realpath $in_shell)" in compile_rule.command
    assert "root_val=$$(realpath -m --relative-to=$$(dirname $in_shell) .)" in compile_rule.command

    # Check for defaults
    assert "cd " not in compile_rule.command
    assert "--resource-path=.:$$(dirname $$in_abs)" in compile_rule.command
    assert "-V root=$$root_val" in compile_rule.command


def test_rule_generation_custom(tmp_path: Path):
    c = Config(
        src_dir="src",
        output_dir="site",
        build_dir="build",
        default_type="page",
        types={"page": {"outputs": []}},
        root_ref_dir="root_ref",
        xdg_data_home=str(tmp_path / "work"),
        add_resource_path=False,
    )
    rules = get_builtin_rules(c, Path("config.yaml"))
    compile_rule = next(r for r in rules if r.name == "compile")

    # Check for custom values
    assert (
        "root_val=$$(realpath -m --relative-to=$$(dirname $in_shell) root_ref)"
        in compile_rule.command
    )
    assert f"XDG_DATA_HOME={tmp_path}/work " in compile_rule.command
    assert "--resource-path" not in compile_rule.command
