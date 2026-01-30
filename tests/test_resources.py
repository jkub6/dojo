from pathlib import Path

import pytest

from dojo.resources import find_resource, get_pandoc_data_dirs


def test_find_resource_absolute_path(tmp_path):
    f = tmp_path / "test.yaml"
    f.touch()
    assert find_resource("defaults", str(f)) == f.resolve()


def test_find_resource_cwd_relative(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "defaults").mkdir()
    f = tmp_path / "defaults" / "relative.yaml"
    f.touch()

    # Searching for "relative.yaml" inside defaults/ should trigger project search
    # But wait, find_resource logic:
    # 1. Exact path
    # 2. Resource name resolution -> search roots -> root/category/name

    # If I give "defaults/relative.yaml" and it exists in CWD, checking exact path logic (if parts > 1)

    # Case A: Explicit relative path
    rel_path = "defaults/relative.yaml"
    assert find_resource("defaults", rel_path) == f.resolve()


def test_find_resource_cwd_category_subdir_ignored(tmp_path, monkeypatch):
    # If file is in CWD/defaults/foo.yaml, and we ask for "foo", it should NOT be found
    # because Pandoc doesn't search CWD/category automatically.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "defaults").mkdir()
    (tmp_path / "defaults" / "ignored.yaml").touch()

    assert find_resource("defaults", "ignored") is None


def test_find_resource_no_recursive_upstream_search(tmp_path, monkeypatch):
    # User is in tmp_path/subdir
    # Resource is in tmp_path/defaults/mydefault.yaml
    monkeypatch.chdir(tmp_path)

    defaults_dir = tmp_path / "defaults"
    defaults_dir.mkdir()
    (defaults_dir / "mydefault.yaml").touch()

    subdir = tmp_path / "subdir"
    subdir.mkdir()

    # Context is subdir
    # Previously, this found the file by walking up. Now it should NOT find it.
    found = find_resource("defaults", "mydefault", root_contexts=[subdir])
    assert found is None


def test_find_resource_xdg_search(tmp_path, monkeypatch):
    # Mock XDG_DATA_HOME
    xdg_home = tmp_path / "share"
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_home))

    pandoc_defaults = xdg_home / "pandoc" / "defaults"
    pandoc_defaults.mkdir(parents=True)
    (pandoc_defaults / "system_default.yaml").touch()

    # Should find it even with no context
    found = find_resource("defaults", "system_default")
    assert found == (pandoc_defaults / "system_default.yaml").resolve()


def test_find_resource_not_found(tmp_path):
    assert find_resource("defaults", "nonexistent") is None


def test_find_resource_invalid_category():
    with pytest.raises(ValueError):
        find_resource("invalid_cat", "something")


def test_get_pandoc_data_dirs(tmp_path, monkeypatch):
    xdg = tmp_path / "xdg"
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg))

    (xdg / "pandoc").mkdir(parents=True)
    (Path.home() / ".pandoc").mkdir(
        parents=True, exist_ok=True
    )  # Might fail if real home not writable in test env?
    # Use mock home

    mock_home = tmp_path / "home"
    mock_home.mkdir()
    monkeypatch.setenv("HOME", str(mock_home))
    monkeypatch.setattr("pathlib.Path.home", lambda: mock_home)

    (mock_home / ".pandoc").mkdir()

    # create XDG dir
    (xdg / "pandoc").mkdir(parents=True, exist_ok=True)

    dirs = get_pandoc_data_dirs()
    assert (xdg / "pandoc") in dirs
    assert (mock_home / ".pandoc") in dirs


def test_get_pandoc_data_dirs_override(tmp_path, monkeypatch):
    """Verify that extra_data_dirs OVERRIDES default search paths."""
    xdg = tmp_path / "xdg"
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg))
    (xdg / "pandoc").mkdir(parents=True)

    extra = tmp_path / "extra"
    extra.mkdir()

    # If extra is provided, it should be the ONLY one returned
    dirs = get_pandoc_data_dirs(extra_data_dirs=[extra])
    assert dirs == [extra.resolve()]
    assert (xdg / "pandoc") not in dirs
