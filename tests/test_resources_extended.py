import pytest

from dojo.resources import clear_resource_cache, find_resource


def test_find_resource_symlink(tmp_path):
    clear_resource_cache()
    # Create a real file
    real_file = tmp_path / "real_defaults.yaml"
    real_file.write_text("key: value")

    # Create a symlink to it
    link_file = tmp_path / "link_defaults.yaml"
    try:
        link_file.symlink_to(real_file)
    except OSError:
        pytest.skip("Symlinks not supported on this platform")

    # Resolving the link should return the resolved real path
    found = find_resource("defaults", str(link_file))
    assert found == real_file.resolve()


def test_find_resource_broken_symlink(tmp_path):
    clear_resource_cache()
    real_file = tmp_path / "will_be_deleted.yaml"
    real_file.touch()
    link_file = tmp_path / "broken_link.yaml"
    try:
        link_file.symlink_to(real_file)
    except OSError:
        pytest.skip("Symlinks not supported on this platform")

    real_file.unlink()

    # Broken symlink should return None or handled gracefully
    assert find_resource("defaults", str(link_file)) is None


def test_find_resource_pathological_names(tmp_path):
    clear_resource_cache()
    # Test names with special characters
    special_name = "!@#$%^&()_+-=.yaml"
    f = tmp_path / special_name
    f.touch()

    assert find_resource("defaults", str(f)) == f.resolve()


def test_find_resource_deep_nesting(tmp_path):
    clear_resource_cache()
    # 20 levels deep
    parent = tmp_path
    for i in range(20):
        parent = parent / f"level_{i}"
    parent.mkdir(parents=True)

    f = parent / "deep.yaml"
    f.touch()

    assert find_resource("defaults", str(f)) == f.resolve()


def test_find_resource_case_sensitivity(tmp_path):
    """Verify behavior on case-sensitive vs case-insensitive file systems."""
    clear_resource_cache()
    f = tmp_path / "Uppercase.yaml"
    f.touch()

    # On most Linux filesystems, this should be None
    # We just check that it doesn't crash
    find_resource("defaults", str(tmp_path / "uppercase.yaml"))

    # If the filesystem is case-insensitive (like some CI environments), this might pass.
    # We don't assert either way, just ensure no error.
    pass
