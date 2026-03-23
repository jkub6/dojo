import io
from pathlib import Path

from dojo.emitter import NinjaEmitter
from dojo.paths import ninja_escape


def test_ninja_escape_always_forward_slashes():
    """Verify that Ninja escape utility always produces forward slashes for cross-platform stability."""
    # Simulating a Windows-style path string
    s = "assets\\css\\style.css"
    escaped = ninja_escape(s)

    # Ninja specifically requires forward slashes in build files
    assert "\\" not in escaped
    assert "/" in escaped


def test_emitter_uses_posix_paths(mock_emitter):
    """Verify that the NinjaEmitter converts all Path objects to POSIX (forward-slash) format."""
    buf = io.StringIO()
    # Real emitter instead of mock for this specific check
    emitter = NinjaEmitter(buf)

    # Use a relative path that might be represented differently on other OSs
    rel_path = Path("content") / "subdir" / "index.md"

    emitter.build(outputs="dist/index.html", rule="render", inputs=rel_path)

    content = buf.getvalue()

    # Check that backslashes are never used in the generated Ninja output
    assert "\\" not in content
    assert "content/subdir/index.md" in content
