from pathlib import Path

import pytest

from dojo.deps import (
    resolve_glob_dependencies,
    scan_css_dependencies,
    scan_html_dependencies,
)


def test_resolve_glob_dependencies(tmp_path):
    base_dir = tmp_path / "base"
    base_dir.mkdir()
    
    # Create some files matching and not matching
    (base_dir / "file1.txt").touch()
    (base_dir / "file2.txt").touch()
    
    subdir = base_dir / "subdir"
    subdir.mkdir()
    (subdir / "target.png").touch()
    (subdir / "ignore.jpg").touch()
    
    # Nested dir to test recursive glob
    deepdir = subdir / "deep"
    deepdir.mkdir()
    (deepdir / "target.png").touch()

    # Should resolve basic files
    deps = resolve_glob_dependencies(base_dir, ["*.txt", "subdir/*.png", "**/*.png"])
    
    assert base_dir / "file1.txt" in deps
    assert base_dir / "file2.txt" in deps
    assert subdir / "target.png" in deps
    assert deepdir / "target.png" in deps
    
    # Should not include ignore.jpg or directories
    assert subdir / "ignore.jpg" not in deps
    assert subdir not in deps


def test_scan_css_dependencies(tmp_path):
    # Setup test file
    css_file = tmp_path / "style.css"
    css_content = """
    @import url('fonts.css');
    body {
        background-image: url("bg.png");
    }
    .icon {
        mask-image: url(icon.svg);
    }
    .external {
        background: url(https://example.com/ext.png);
    }
    .data-uri {
        background: url(data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==);
    }
    """
    css_file.write_text(css_content)

    # Create target files so they exist
    (tmp_path / "fonts.css").touch()
    (tmp_path / "bg.png").touch()
    (tmp_path / "icon.svg").touch()
    
    # Run scan
    assets = scan_css_dependencies(css_file)
    
    assert tmp_path / "fonts.css" in assets
    assert tmp_path / "bg.png" in assets
    assert tmp_path / "icon.svg" in assets
    assert len(assets) == 3


def test_scan_css_dependencies_missing_file_ignored(tmp_path):
    css_file = tmp_path / "style.css"
    css_file.write_text("body { background: url('missing.png'); }")
    
    assets = scan_css_dependencies(css_file)
    assert assets == []


def test_scan_html_dependencies(tmp_path):
    html_file = tmp_path / "index.html"
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <link rel="stylesheet" href="style.css">
        <link rel="icon" href='favicon.ico' />
    </head>
    <body>
        <img src="image.jpg" alt="test">
        <script src='script.js'></script>
        
        <!-- Should be ignored -->
        <a href="https://example.com">Link</a>
        <a href="mailto:test@user.com">Mail</a>
        <a href="#section">Hash</a>
        <img src="data:image/png;base64,123">
    </body>
    </html>
    """
    html_file.write_text(html_content)

    # Create target files
    (tmp_path / "style.css").touch()
    (tmp_path / "favicon.ico").touch()
    (tmp_path / "image.jpg").touch()
    (tmp_path / "script.js").touch()
    
    assets = scan_html_dependencies(html_file)

    assert tmp_path / "style.css" in assets
    assert tmp_path / "favicon.ico" in assets
    assert tmp_path / "image.jpg" in assets
    assert tmp_path / "script.js" in assets
    assert len(assets) == 4


def test_scan_html_dependencies_malformed_ignored(tmp_path, caplog):
    html_file = tmp_path / "bad.html"
    # Testing graceful skip when file physically doesn't exist
    assets = scan_html_dependencies(html_file)
    assert assets == []
    assert "Could not read HTML file" in caplog.text


def test_scan_css_dependencies_malformed_ignored(tmp_path, caplog):
    css_file = tmp_path / "bad.css"
    assets = scan_css_dependencies(css_file)
    assert assets == []
    assert "Could not read CSS file" in caplog.text
