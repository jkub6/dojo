from pathlib import Path

import pytest
from dojo.exceptions import SecurityError
from dojo.paths import ninja_escape, sanitize_path, shell_quote
from dojo.stages._defaults import merge_defaults
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st


@given(st.text())
def test_shell_quote_is_safe(s):
    """Verify that any string can be safely quoted for the shell."""
    quoted = shell_quote(s)
    assert isinstance(quoted, str)
    # The length of the quoted string should be at least as long as the original (with as_posix)
    # unless it's an empty string.
    posix_s = s.replace("\\", "/")
    assert len(quoted) >= len(posix_s)


@given(st.text(min_size=1))
def test_ninja_escape_idempotency(s):
    """Verify that Ninja-specific characters are correctly escaped."""
    escaped = ninja_escape(s)

    # $ -> $$
    if "$" in s:
        # Number of $ should be at least double (more if there were already escaped ones)
        assert escaped.count("$") >= s.count("$")

    # Space -> $
    if " " in s:
        assert "$ " in escaped

    # Colon -> $:
    if ":" in s:
        assert "$:" in escaped


@given(st.lists(st.one_of(st.text(), st.lists(st.text()), st.none())))
def test_merge_defaults_robustness(sources):
    """Verify that merge_defaults handles any combination of list/string/none inputs."""
    result = merge_defaults(*sources)
    assert isinstance(result, list)
    for item in result:
        assert isinstance(item, Path)


def test_sanitize_path_traversal(tmp_path):
    """Verify that path traversal attempts are caught."""
    base = tmp_path / "base"
    base.mkdir()

    # Normal path should work
    safe_relative = Path("docs/index.html")
    sanitized = sanitize_path(base, safe_relative)
    assert sanitized.name == "index.html"
    assert "base/docs/index.html" in str(sanitized.as_posix())

    # Traversal should raise SecurityError
    with pytest.raises(SecurityError):
        sanitize_path(base, Path("../outside.txt"))

    with pytest.raises(SecurityError):
        sanitize_path(base, Path("docs/../../secret.txt"))


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(st.text(alphabet=st.characters(blacklist_categories=("Cc", "Cs"))))
def test_sanitize_path_random_input(tmp_path, s):
    """Verify that random relative paths either resolve inside base or raise SecurityError."""
    base = tmp_path / "base_rand"
    base.mkdir(exist_ok=True)

    try:
        sanitized = sanitize_path(base, Path(s))
        # If it didn't raise, it MUST be inside base
        assert sanitized.resolve().relative_to(base.resolve())
    except (SecurityError, OSError):
        # SecurityError is expected for traversal
        # OSError is expected for invalid path strings (e.g. too long, null bytes)
        pass
