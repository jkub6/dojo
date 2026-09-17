import logging
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from dojo.config import (
    Config,
    CustomRule,
    OutputConfig,
    ToolPaths,
    _apply_config_file_exclusion,
    load_config,
)
from dojo.constants import RuleName
from dojo.exceptions import (
    ConfigError,
    ConfigLoadError,
    CustomRuleConflictError,
    DefaultsNotFoundError,
    DefaultsRequiredError,
    DefaultTypeNotFoundError,
    DirectoryConflictError,
    DuplicateOutputIdError,
    EssentialToolNotFoundError,
    PandocDataDirError,
    SourceDirNotFoundError,
    SourceRequiresToolError,
)

# --- ToolPaths Tests ---


def test_tool_paths_defaults():
    tp = ToolPaths()
    assert tp.pandoc.endswith("pandoc")


@patch("shutil.which")
def test_tool_paths_resolution(mock_which):
    mock_which.return_value = "/usr/bin/custom_pandoc"
    tp = ToolPaths(pandoc="pandoc_alias")
    assert tp.pandoc == "/usr/bin/custom_pandoc"


@patch("shutil.which")
def test_tool_paths_missing_essential(mock_which):
    mock_which.return_value = None
    # Pydantic wraps validation errors
    with pytest.raises(EssentialToolNotFoundError) as excinfo:
        ToolPaths(pandoc="missing_pandoc")
    assert "Essential tool 'pandoc' not found" in str(excinfo.value)


def test_tool_paths_missing_optional():
    # Minify is optional
    with patch("shutil.which") as mock_which:
        # Mock essential tools to be found, but minify missing
        mock_which.side_effect = lambda x: "/bin/found" if x == "pandoc" else None

        tp = ToolPaths(minify="nonexistent")
        # should not raise, just keep what was passed
        assert tp.minify == "nonexistent"


# --- OutputConfig Tests ---


def test_output_config_validation_source_tool():
    with pytest.raises(
        SourceRequiresToolError,
        match="Outputs with 'source' must also specify 'tool'",
    ):
        OutputConfig(extension="pdf", source="html")


def test_output_config_validation_defaults_or_source():
    with pytest.raises(
        DefaultsRequiredError,
        match="Outputs without 'source' must specify 'defaults'",
    ):
        OutputConfig(extension="html", defaults=None, source=None)


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
                    {
                        "id": "html",
                        "extension": "html",
                        "defaults": str(tmp_path / "defaults.yaml"),
                    },
                ],
            },
        },
        "defaults": str(tmp_path / "defaults.yaml"),
    }


def test_config_valid(valid_config_data):
    cfg = Config(**valid_config_data)
    assert cfg.src_dir == valid_config_data["src_dir"]


def test_config_invalid_default_type(valid_config_data):
    valid_config_data["default_type"] = "post"
    with pytest.raises(DefaultTypeNotFoundError, match="default_type 'post' not found"):
        Config(**valid_config_data)


def test_config_dir_conflict_equality(valid_config_data):
    valid_config_data["output_dir"] = valid_config_data["src_dir"]
    with pytest.raises(DirectoryConflictError, match="Directory conflict"):
        Config(**valid_config_data)


def test_config_dir_conflict_nesting(valid_config_data):
    # Test src_dir inside output_dir (still forbidden)
    nested_src = Path(valid_config_data["output_dir"]) / "src"
    nested_src.mkdir(parents=True, exist_ok=True)
    valid_config_data["src_dir"] = str(nested_src)
    with pytest.raises(DirectoryConflictError, match="is inside"):
        Config(**valid_config_data)


def test_config_nested_output_allowed(valid_config_data):
    # Test output_dir inside src_dir (now allowed)
    src = Path(valid_config_data["src_dir"])
    out = src / "site"
    valid_config_data["output_dir"] = str(out)

    cfg = Config(**valid_config_data)

    # Check that it didn't raise and added excludes
    # relative path is "site"
    assert "site" in cfg.exclude
    assert "site/*" in cfg.exclude


def test_config_nested_build_allowed(valid_config_data):
    # Test build_dir inside src_dir (now allowed)
    src = Path(valid_config_data["src_dir"])
    bld = src / "build_output"
    valid_config_data["build_dir"] = str(bld)

    cfg = Config(**valid_config_data)

    # Check that it didn't raise and added excludes
    assert "build_output" in cfg.exclude
    assert "build_output/*" in cfg.exclude


def test_config_duplicate_output_ids(valid_config_data):
    valid_config_data["types"]["page"]["outputs"].append(
        {"id": "html", "extension": "htm", "defaults": valid_config_data["defaults"]},
    )
    with pytest.raises(DuplicateOutputIdError, match="Duplicate output IDs"):
        Config(**valid_config_data)


def test_config_custom_rule_conflict(valid_config_data):
    valid_config_data["custom_rules"] = [{"name": "compile", "command": "echo"}]
    with pytest.raises(CustomRuleConflictError, match="conflicts with built-in rule"):
        Config(**valid_config_data)


def test_validate_src_dir_missing(valid_config_data):
    valid_config_data["src_dir"] = "nonexistent_src"
    with pytest.raises(SourceDirNotFoundError, match="Source directory not found"):
        Config(**valid_config_data)


def test_validate_defaults_missing(valid_config_data):
    valid_config_data["defaults"] = "missing.yaml"
    with pytest.raises(DefaultsNotFoundError, match=r"Defaults file not found: missing.yaml"):
        Config(**valid_config_data)


def test_load_config_auto_excludes_self(tmp_path):
    # Setup: config file inside src directory
    src = tmp_path
    c = src / "dojo.yaml"

    # Create config that points to its own directory as src
    c.write_text(
        yaml.dump(
            {
                "src_dir": str(src),
                "default_type": "page",
                "types": {"page": {"outputs": []}},
                "exclude": ["existing_pattern"],
            },
        ),
    )

    cfg, _ = load_config(str(c))

    # Verify dojo.yaml is added to excludes
    assert "dojo.yaml" in cfg.exclude
    # Verify existing excludes are preserved
    assert "existing_pattern" in cfg.exclude


# --- load_config Tests ---


def test_load_config_cli_arg(tmp_path):
    c = tmp_path / "my_conf.yaml"
    (tmp_path / "src").mkdir()
    c.write_text(
        yaml.dump(
            {
                "src_dir": str(tmp_path / "src"),
                "default_type": "t",
                "types": {"t": {"outputs": []}},
            },
        ),
    )

    _, p = load_config(str(c))
    assert p == c.resolve()


def test_load_config_env_var(tmp_path, monkeypatch):
    c = tmp_path / "env_conf.yaml"
    (tmp_path / "src").mkdir()
    c.write_text(
        yaml.dump(
            {
                "src_dir": str(tmp_path / "src"),
                "default_type": "t",
                "types": {"t": {"outputs": []}},
            },
        ),
    )

    monkeypatch.setenv("DOJO_CONFIG", str(c))
    _, p = load_config()
    assert p == c.resolve()


def test_load_config_not_found(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError, match="No configuration file found"):
        load_config()


def test_load_config_explicit_not_found(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError, match="Configuration file not found"):
        load_config("missing.yaml")


def test_load_config_invalid_yaml(tmp_path):
    c = tmp_path / "bad.yaml"
    c.write_text("invalid: [")
    with pytest.raises(ConfigError, match="Error parsing configuration file"):
        load_config(str(c))


def test_load_config_invalid_schema(tmp_path):
    c = tmp_path / "bad_schema.yaml"
    c.write_text("src_dir: missing")
    with pytest.raises(ConfigError, match="Invalid configuration"):
        load_config(str(c))


# --- pandoc_data_dir Tests ---


def test_config_pandoc_data_dir_valid(valid_config_data, tmp_path):
    data_dir = tmp_path / "pandoc_data"
    data_dir.mkdir()
    valid_config_data["pandoc_data_dir"] = str(data_dir)

    cfg = Config(**valid_config_data)
    assert cfg.pandoc_data_dir == str(data_dir.resolve())


def test_config_pandoc_data_dir_missing(valid_config_data):
    valid_config_data["pandoc_data_dir"] = "/nonexistent/data/dir"
    with pytest.raises(PandocDataDirError, match="Pandoc data directory not found"):
        Config(**valid_config_data)


def test_config_pandoc_data_dir_not_dir(valid_config_data, tmp_path):
    f = tmp_path / "file"
    f.touch()
    valid_config_data["pandoc_data_dir"] = str(f)
    with pytest.raises(PandocDataDirError, match="Pandoc data directory is not a directory"):
        Config(**valid_config_data)


def test_config_defaults_resolved_with_data_dir(tmp_path, valid_config_data):
    # Setup data dir and a defaults file inside it
    data_dir = tmp_path / "custom_data"
    (data_dir / "defaults").mkdir(parents=True)
    custom_yaml = data_dir / "defaults" / "my_custom.yaml"
    custom_yaml.touch()

    valid_config_data["pandoc_data_dir"] = str(data_dir)
    valid_config_data["defaults"] = "my_custom"  # Shorthand name

    cfg = Config(**valid_config_data)
    assert cfg.defaults == str(custom_yaml.resolve())


def test_config_type_output_defaults_resolved_with_data_dir(tmp_path, valid_config_data):
    data_dir = tmp_path / "custom_data"
    (data_dir / "defaults").mkdir(parents=True)
    type_yaml = data_dir / "defaults" / "type_def.yaml"
    type_yaml.touch()
    output_yaml = data_dir / "defaults" / "out_def.yaml"
    output_yaml.touch()

    valid_config_data["pandoc_data_dir"] = str(data_dir)
    valid_config_data["types"]["page"]["defaults"] = "type_def"
    valid_config_data["types"]["page"]["outputs"][0]["defaults"] = "out_def"

    cfg = Config(**valid_config_data)
    assert cfg.types["page"].defaults == str(type_yaml.resolve())
    assert cfg.types["page"].outputs[0].defaults == str(output_yaml.resolve())


# --- Additional Edge Cases ---


def test_tool_paths_non_dict():
    """Verify resolve_tool_paths returns data as-is if not a dict."""
    res = ToolPaths.resolve_tool_paths("non-dict")
    assert res == "non-dict"


def test_tool_paths_empty_or_non_string():
    """Verify resolve_tool_paths skips empty or non-string tool entries."""
    data = {"pandoc": "pandoc", "minify": ""}
    res = ToolPaths.resolve_tool_paths(data)
    assert isinstance(res, dict)
    assert res["minify"] == ""


def test_normalize_post_process_variations(tmp_path):
    """Test normalize_post_process handles None, single string, single dict, and invalid types."""
    d = tmp_path / "defaults.yaml"
    d.touch()

    # Single string
    oc1 = OutputConfig(extension="html", defaults=str(d), post_process="minify")
    assert len(oc1.post_process) == 1
    assert oc1.post_process[0].tool == "minify"

    # Single dict
    oc2 = OutputConfig(
        extension="html",
        defaults=str(d),
        post_process={"tool": "ghostscript", "args": ["-dQUIET"]},
    )
    assert len(oc2.post_process) == 1
    assert oc2.post_process[0].tool == "ghostscript"

    # Invalid type raises error
    with pytest.raises(TypeError):
        OutputConfig(extension="html", defaults=str(d), post_process=12345)


def test_custom_rule_conflict_with_builtin(valid_config_data):
    """Test that defining a custom rule named after a built-in rule raises CustomRuleConflictError."""
    valid_config_data["custom_rules"] = [
        CustomRule(name=RuleName.COMPILE.value, command="custom_compile $in")
    ]
    with pytest.raises(
        CustomRuleConflictError,
        match=f"Custom rule name '{RuleName.COMPILE.value}' conflicts with built-in rule",
    ):
        Config(**valid_config_data)


def test_undefined_pool_reference(valid_config_data):
    """Test that referencing an undefined pool raises ConfigInvalidError."""
    valid_config_data["rule_pools"] = {"render": "nonexistent_pool"}
    valid_config_data["pools"] = {"other_pool": 2}
    with pytest.raises(ConfigError, match="references undefined pool"):
        Config(**valid_config_data)


def test_auto_exclude_outside_parent(valid_config_data):
    """Test _auto_exclude gracefully handles child paths outside parent."""
    cfg = Config(**valid_config_data)
    child = Path("/entirely/different/path")
    parent = Path(cfg.src_dir).resolve()
    initial_exclude = list(cfg.exclude)
    cfg._auto_exclude(child, parent)
    assert cfg.exclude == initial_exclude


def test_load_config_non_dict_yaml(tmp_path):
    """Test load_config raises ConfigError when YAML is a list or scalar."""
    bad_yaml = tmp_path / "list_config.yaml"
    bad_yaml.write_text("- item1\n- item2\n")
    with pytest.raises(ConfigError, match="must be a dictionary"):
        load_config(str(bad_yaml))


def test_exception_messages_edge_cases():
    """Verify exception formatting for various error conditions."""
    err1 = EssentialToolNotFoundError("pandoc", "/opt/pandoc")
    assert "/opt/pandoc" in str(err1)

    err2 = DirectoryConflictError("dir1", "/path1", "dir2", "/path2", issue="conflict")
    assert "Directory conflict between dir1 and dir2" in str(err2)

    err3 = ConfigLoadError("Failed", "/path/to/cfg", ValueError("inner"))
    assert "inner" in str(err3)


def test_output_config_post_process_none():
    """Test that post_process=None normalizes to an empty list."""
    out = OutputConfig(extension="html", defaults="page.yaml", post_process=None)
    assert out.post_process == []


def test_config_pandoc_data_dir_none(valid_config_data):
    """Test that pandoc_data_dir=None validates successfully."""
    valid_config_data["pandoc_data_dir"] = None
    cfg = Config(**valid_config_data)
    assert cfg.pandoc_data_dir is None


def test_custom_rules_valid_list():
    """Test that validate_custom_rules successfully returns valid custom rules."""
    rules = [
        CustomRule(name="custom1", command="cmd1 $in"),
        CustomRule(name="custom2", command="cmd2 $in"),
    ]
    validated = Config.validate_custom_rules(rules)
    assert validated == rules


def test_auto_exclude_duplicate(valid_config_data):
    """Test _auto_exclude does not add duplicate exclusion patterns."""
    cfg = Config(**valid_config_data)
    child = Path(cfg.src_dir).resolve() / "sub"
    parent = Path(cfg.src_dir).resolve()
    cfg._auto_exclude(child, parent)
    count_before = len(cfg.exclude)
    # Calling it again should skip duplicates
    cfg._auto_exclude(child, parent)
    assert len(cfg.exclude) == count_before


def test_apply_config_file_exclusion_already_excluded(valid_config_data):
    """Test _apply_config_file_exclusion skips pattern if already present."""
    cfg = Config(**valid_config_data)
    config_file = Path(cfg.src_dir).resolve() / "dojo.yaml"
    _apply_config_file_exclusion(cfg, config_file)
    count_before = len(cfg.exclude)
    _apply_config_file_exclusion(cfg, config_file)
    assert len(cfg.exclude) == count_before


def test_load_config_unexpected_exception(tmp_path, caplog):
    """Test load_config logs unexpected error when validation fails with generic exception."""
    cfg_file = tmp_path / "valid.yaml"
    cfg_file.write_text("src_dir: content\n")
    with patch("dojo.config.Config.model_validate", side_effect=RuntimeError("Unexpected boom")):
        with (
            caplog.at_level(logging.ERROR),
            pytest.raises(ConfigLoadError, match="Unexpected boom"),
        ):
            load_config(str(cfg_file))
        assert "Unexpected error validating configuration" in caplog.text


def test_exceptions_edge_cases():
    """Test EssentialToolNotFoundError without path and ConfigLoadError without exc."""
    err1 = EssentialToolNotFoundError("ninja")
    assert str(err1) == "Essential tool 'ninja' not found"

    err2 = ConfigLoadError("Failed to open", Path("dojo.yaml"))
    assert str(err2) == "Failed to open: dojo.yaml"
