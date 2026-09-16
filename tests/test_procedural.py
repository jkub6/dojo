from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from dojo.exceptions import SecurityError
from dojo.paths import sanitize_path, should_process_file


@st.composite
def path_and_base(draw):
    """Generate a base path and a relative path for testing path sanitization."""
    base = Path("/base")
    # Generate relative paths that might try to escape
    parts = draw(
        st.lists(
            st.text(min_size=1, alphabet="abcdefghijklmnopqrstuvwxyz0123456789._-"),
            min_size=1,
            max_size=5,
        )
    )
    rel = Path(*parts)
    return base, rel


@given(path_and_base())
def test_sanitize_path_properties(pair):
    """Verify properties of sanitized paths using property-based testing."""
    base, rel = pair
    try:
        result = sanitize_path(base, rel)
        # Property: Result must be absolute and start with base
        assert result.is_absolute()
        # On Linux, result.relative_to(base) should not raise ValueError
        result.relative_to(base)
    except SecurityError:
        # If it raises, it must be because it tried to escape
        # (Though with our strategy it might not happen often, we'll add a specific case)
        pass
    except Exception as e:
        # resolve() might fail on some weird strings depending on OS, but text() is mostly safe
        if "Circular symlink" in str(e):
            return
        raise


def test_sanitize_path_traversal_trap(tmp_path):
    """Verify that path traversal attempts are detected and trapped."""
    base = tmp_path / "dojo-test"
    base.mkdir(parents=True, exist_ok=True)
    with pytest.raises(SecurityError):
        sanitize_path(base, Path("../../../etc/passwd"))


@given(
    st.lists(st.text(min_size=1, alphabet="abcdefgh/.*")),
    st.lists(st.text(min_size=1, alphabet="abcdefgh/.*")),
)
def test_should_process_file_properties(includes, excludes):
    """Verify properties of the file processing filter."""
    src_dir = Path("/src")
    file_path = Path("/src/content/index.md")

    # Property 1: If an exclude pattern matches the relative path, it MUST return False regardless of includes
    assert not should_process_file(file_path, src_dir, includes, [*excludes, "content/*.md"])

    # Property 2: If includes is empty and no excludes match, it MUST return True
    non_matching_excludes = ["other/*", "nomatch.*"]
    assert should_process_file(file_path, src_dir, [], non_matching_excludes)

    # Property 3: Files outside src_dir must return False
    outside_file = Path("/other/dir/file.md")
    assert not should_process_file(outside_file, src_dir, includes, excludes)
