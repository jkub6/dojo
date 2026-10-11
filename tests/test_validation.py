"""Tests for the output validation module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dojo.validation import css_urls, validate_output

if TYPE_CHECKING:
    from pathlib import Path


def test_validate_output_empty_or_nonexistent(tmp_path: Path) -> None:
    """Non-existent or empty directories report no HTML output found."""
    assert validate_output(tmp_path) == [f"{tmp_path}: no HTML output found"]
    non_existent = tmp_path / "does_not_exist"
    assert validate_output(non_existent) == [f"{non_existent}: no HTML output found"]


def test_validate_output_valid_site(tmp_path: Path) -> None:
    """A valid site with HTML, CSS, images, and anchors passes without errors."""
    site = tmp_path / "_site"
    site.mkdir()
    (site / "image.png").write_bytes(b"dummy image")
    (site / "style.css").write_text("body { background: url('image.png'); }")
    (site / "index.html").write_text(
        """<!DOCTYPE html>
        <html>
        <head>
            <link rel="stylesheet" href="style.css">
        </head>
        <body>
            <h1 id="intro">Introduction</h1>
            <img src="image.png" alt="Test">
            <a href="#intro">Back to top</a>
        </body>
        </html>"""
    )

    errors = validate_output(site, links=True)
    assert errors == []


def test_validate_output_duplicate_ids(tmp_path: Path) -> None:
    """Detect duplicate HTML element IDs."""
    site = tmp_path / "_site"
    site.mkdir()
    page = site / "page.html"
    page.write_text(
        """<!DOCTYPE html>
        <html>
        <body>
            <div id="dup">First</div>
            <div id="dup">Second</div>
        </body>
        </html>"""
    )

    errors = validate_output(site)
    assert len(errors) == 1
    assert "duplicate HTML id dup" in errors[0]


def test_validate_output_missing_resources(tmp_path: Path) -> None:
    """Detect missing local resources across various tags and attributes."""
    site = tmp_path / "_site"
    site.mkdir()
    page = site / "page.html"
    page.write_text(
        """<!DOCTYPE html>
        <html>
        <head>
            <style>
                .hero { background: url('missing_bg.png'); }
            </style>
        </head>
        <body>
            <img src="missing_img.png">
            <video poster="missing_poster.jpg"></video>
            <div data-src="missing_data.png"></div>
            <div data-background-image="missing_attr_bg.png"></div>
            <div style="background-image: url('missing_inline.png')"></div>
            <picture>
                <source srcset="missing_1x.png 1x, missing_2x.png 2x">
            </picture>
        </body>
        </html>"""
    )

    errors = validate_output(site)
    assert any("missing local resource missing_bg.png" in e for e in errors)
    assert any("missing local resource missing_img.png" in e for e in errors)
    assert any("missing local resource missing_poster.jpg" in e for e in errors)
    assert any("missing local resource missing_data.png" in e for e in errors)
    assert any("missing local resource missing_attr_bg.png" in e for e in errors)
    assert any("missing local resource missing_inline.png" in e for e in errors)
    assert any("missing local resource missing_1x.png" in e for e in errors)
    assert any("missing local resource missing_2x.png" in e for e in errors)


def test_validate_output_links_and_anchors(tmp_path: Path) -> None:
    """Validate internal links and fragments when links=True."""
    site = tmp_path / "_site"
    site.mkdir()
    sub = site / "sub"
    sub.mkdir()

    (site / "index.html").write_text(
        """<!DOCTYPE html>
        <html>
        <body>
            <h1 id="main">Main</h1>
            <a href="sub/">Sub</a>
            <a href="sub/#section">Sub Section</a>
            <a href="sub/#missing-anchor">Broken Anchor</a>
            <a href="nonexistent.html">Broken Page</a>
            <a href="#main">Self Valid</a>
            <a href="#nonexistent">Self Broken</a>
        </body>
        </html>"""
    )

    (sub / "index.html").write_text(
        """<!DOCTYPE html>
        <html>
        <body>
            <h2 id="section">Section</h2>
            <a href="/index.html#main">Root Valid</a>
        </body>
        </html>"""
    )

    # When links=False, broken <a> links are ignored
    errors_no_links = validate_output(site, links=False)
    assert errors_no_links == []

    # When links=True, broken links and anchors are reported
    errors = validate_output(site, links=True)
    assert any("missing anchor sub/#missing-anchor" in e for e in errors)
    assert any("missing local resource nonexistent.html" in e for e in errors)
    assert any("missing anchor #nonexistent" in e for e in errors)
    assert not any("missing local resource sub/" in e for e in errors)
    assert not any("missing anchor sub/#section" in e for e in errors)
    assert not any("Root Valid" in e for e in errors)


def test_validate_output_offline_check(tmp_path: Path) -> None:
    """Validate offline mode flags external resources but permits <a> links and data URIs."""
    site = tmp_path / "_site"
    site.mkdir()
    (site / "index.html").write_text(
        """<!DOCTYPE html>
        <html>
        <body>
            <a href="https://example.com/external">External Link</a>
            <img src="https://example.com/image.png">
            <img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=">
        </body>
        </html>"""
    )

    # Without offline check, external resources are ignored
    assert validate_output(site, offline=False) == []

    # With offline check, external <img> is flagged, but external <a> and data: are allowed
    errors = validate_output(site, offline=True)
    assert len(errors) == 1
    assert "external resource in offline output: https://example.com/image.png" in errors[0]


def test_validate_output_single_file_and_resource_root(tmp_path: Path) -> None:
    """Validate a single HTML file with custom resource root."""
    site = tmp_path / "_site"
    site.mkdir()
    assets = site / "assets"
    assets.mkdir()
    (assets / "logo.svg").write_text("<svg></svg>")

    page = site / "standalone.html"
    page.write_text(
        """<!DOCTYPE html>
        <html>
        <body>
            <img src="/assets/logo.svg">
            <img src="assets/logo.svg">
        </body>
        </html>"""
    )

    # Validating single file with resource_root specified
    errors = validate_output(page, resource_root=site)
    assert errors == []

    # Validating single file defaulting resource_root to parent
    errors_default = validate_output(page)
    assert errors_default == []


def test_single_page_offline_check_follows_only_used_stylesheets(tmp_path: Path) -> None:
    """A single page check only traverses linked stylesheets, ignoring unused files."""
    (tmp_path / "unused.css").write_text('@import "https://example.com/unused.css";')
    page = tmp_path / "deck.html"
    page.write_text('<link rel="stylesheet" href="used.css">')
    (tmp_path / "used.css").write_text('@import "nested.css";')
    (tmp_path / "nested.css").write_text("body {color: black}")
    assert validate_output(page, offline=True) == []

    (tmp_path / "nested.css").write_text('body {background: url("https://example.com/image.jpg")}')
    errors = validate_output(page, offline=True)
    assert any("external resource in offline output" in e for e in errors)


def test_css_urls_parsing() -> None:
    """Test css_urls handles comments, url() variants, and @import statements."""
    css = """
    /* Comment with url('ignore.png') */
    @import "imported.css";
    @import 'single.css';
    .hero {
        background: url(unquoted.png);
        background-image: url('single_quoted.png');
        cursor: url("double_quoted.png");
    }
    """
    extracted = css_urls(css)
    assert "imported.css" in extracted
    assert "single.css" in extracted
    assert "unquoted.png" in extracted
    assert "single_quoted.png" in extracted
    assert "double_quoted.png" in extracted
    assert "ignore.png" not in extracted


def test_path_traversal_outside_root(tmp_path: Path) -> None:
    """Resource path attempting to escape root is flagged as missing."""
    site = tmp_path / "_site"
    site.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("outside")

    (site / "index.html").write_text(
        """<!DOCTYPE html>
        <html>
        <body>
            <img src="../secret.txt">
        </body>
        </html>"""
    )

    errors = validate_output(site)
    assert any("missing local resource ../secret.txt" in e for e in errors)


def test_linked_resources_multiple_css_in_page(tmp_path: Path) -> None:
    """Trigger branch where index reaches len(resources) while queue still has items."""
    site = tmp_path / "_site"
    site.mkdir()
    page = site / "index.html"
    page.write_text(
        '<link rel="stylesheet" href="missing1.css"><link rel="stylesheet" href="missing2.css">'
    )
    errors = validate_output(page)
    assert any("missing local resource missing1.css" in e for e in errors)
    assert any("missing local resource missing2.css" in e for e in errors)
