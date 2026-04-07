import os
from unittest.mock import patch

from dojo.yaml_utils import _load_and_validate_yaml_dict, get_recursive_yaml_deps


def test_defaults_expansion(tmp_path):
    root = tmp_path / "subdir" / "root.yaml"
    root.parent.mkdir()

    other = tmp_path / "subdir" / "other.yaml"
    other.write_text("foo: bar")

    root_content = """
defaults: ${.}/other.yaml
some_path: ${.}/data
env_test: ${MY_TEST_VAR}
    """
    root.write_text(root_content)

    with patch.dict(os.environ, {"MY_TEST_VAR": "expanded_var"}):
        # 1. Test dependency resolution (public usage)
        deps = get_recursive_yaml_deps(root)
        assert other.resolve() in deps

        # 2. Test values explicitly (private usage)
        data = _load_and_validate_yaml_dict(root)

    assert data["defaults"] == str(root.parent / "other.yaml")
    assert data["some_path"] == str(root.parent / "data")
    assert data["env_test"] == "expanded_var"


def test_defaults_expansion_nested(tmp_path):
    root = tmp_path / "root.yaml"
    root_content = """
list_item:
    - ${.}/item1
    - ${MY_VAR}
nested:
    key: ${.}/nested
    """
    root.write_text(root_content)

    with patch.dict(os.environ, {"MY_VAR": "foo"}):
        data = _load_and_validate_yaml_dict(root)

    assert data["list_item"][0] == str(root.parent / "item1")
    assert data["list_item"][1] == "foo"
    assert data["nested"]["key"] == str(root.parent / "nested")


def test_defaults_expansion_escaped(tmp_path):
    root = tmp_path / "root.yaml"
    # YAML: foo: \${VAR} -> string value "\${VAR}"
    # Dojo expansion should verify it returns "${VAR}" if escaped
    root.write_text(r"foo: \${VAR}")

    data = _load_and_validate_yaml_dict(root)
    assert data["foo"] == "${VAR}"
