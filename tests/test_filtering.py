import pytest

from dojo.utils import should_process_file


@pytest.fixture
def src_dir(tmp_path):
    return tmp_path / "content"


def test_no_patterns(src_dir):
    """If no patterns provided, should include everything."""
    path = src_dir / "foo.md"
    assert should_process_file(path, src_dir, includes=[], excludes=[]) is True


def test_exclude_only(src_dir):
    """Files matching exclude patterns should be rejected."""
    path = src_dir / "drafts" / "wip.md"
    excludes = ["drafts/*"]
    assert should_process_file(path, src_dir, includes=[], excludes=excludes) is False

    # Non-matching file
    path2 = src_dir / "posts" / "published.md"
    assert should_process_file(path2, src_dir, includes=[], excludes=excludes) is True


def test_include_only(src_dir):
    """If include patterns provided, ONLY matching files should be accepted."""
    includes = ["posts/*.md"]

    # Matching
    path = src_dir / "posts" / "hello.md"
    assert should_process_file(path, src_dir, includes=includes, excludes=[]) is True

    # Non-matching
    path2 = src_dir / "about.md"
    assert should_process_file(path2, src_dir, includes=includes, excludes=[]) is False


def test_exclude_precedence(src_dir):
    """Excludes should take priority over includes."""
    path = src_dir / "posts" / "wip.md"
    includes = ["posts/*"]
    excludes = ["*/wip.md"]

    # Matches both, but should be excluded
    assert should_process_file(path, src_dir, includes=includes, excludes=excludes) is False


def test_nested_patterns(src_dir):
    """Test patterns with nested paths."""
    path = src_dir / "a" / "b" / "c.md"

    # Match using ** (glob implementation might vary but fnmatch supports basic wildcards)
    # fnmatch: '*' matches everything, including directory separators on some platforms,
    # but strictly speaking `*` is usually non-recursive in shells.
    # Python `fnmatch` treats `/` as just another char, so `*` matches `/`.

    # Test `*` matching across directories
    # Python's fnmatch matches path separators with *, so a/* will match a/b/c.md
    # This means the file SHOULD be excluded.
    assert should_process_file(path, src_dir, includes=[], excludes=["a/*"]) is False


def test_file_outside_src_dir(src_dir, tmp_path):
    """Files outside source directory should always return False."""
    outside = tmp_path / "other" / "file.md"
    assert should_process_file(outside, src_dir, includes=[], excludes=[]) is False
