"""Validate published local references and HTML identifiers without network IO.

This module provides HTML and CSS static asset validation for compiled sites,
verifying that internal links, local media, fonts, stylesheets, and HTML identifiers
resolve correctly without 404s or DOM ID collisions.
"""

from __future__ import annotations

import base64
import binascii
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import TYPE_CHECKING
from urllib.parse import unquote, unquote_to_bytes, urlsplit

from .crunch import decode_html

if TYPE_CHECKING:
    from pathlib import Path


class Page(HTMLParser):
    """HTML parser extracting DOM IDs, resource URLs, and stylesheet links."""

    def __init__(self) -> None:
        """Initialize parser state for collecting IDs and URLs."""
        super().__init__()
        self.ids: set[str] = set()
        self.duplicates: set[str] = set()
        self.urls: list[tuple[str, str]] = []
        self.in_style = False
        self.reveal_routes = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Record element IDs, resource URLs, and inline style declarations."""
        values = dict(attrs)
        if tag == "div" and "reveal" in (values.get("class") or "").split():
            self.reveal_routes = True
        identifier = values.get("id")
        if identifier:
            if identifier in self.ids:
                self.duplicates.add(identifier)
            self.ids.add(identifier)
        for key in ("src", "href", "poster", "data-src", "data-background-image"):
            val = values.get(key)
            if val:
                self.urls.append((tag, str(val)))
        style_val = values.get("style")
        if style_val:
            self.urls.extend(("css", url) for url in css_urls(str(style_val)))
        srcset_val = values.get("srcset")
        if srcset_val:
            self.urls.extend((tag, url) for url in srcset_urls(str(srcset_val)))
        if tag == "style":
            self.in_style = True

    def handle_endtag(self, tag: str) -> None:
        """Handle closing tag and reset style block flag."""
        if tag == "style":
            self.in_style = False

    def handle_data(self, data: str) -> None:
        """Extract URLs embedded inside <style> blocks."""
        if self.in_style:
            self.urls.extend(("css", url) for url in css_urls(data))


def srcset_urls(value: str) -> list[str]:
    """Parse candidates, retaining the comma within data URLs."""
    result = []
    while value := re.sub(r"^[\s,]+", "", value):
        match = re.match(r"data:[^\s]+|[^\s,]+", value)
        assert match is not None  # noqa: S101 - nonempty, non-whitespace input
        url = match[0].rstrip(",")
        result.append(url)
        remainder = value[match.end() :]
        if match[0].endswith(",") or remainder.startswith(","):
            value = remainder
        else:
            _, _, value = remainder.partition(",")
    return result


def embedded_urls(url: str) -> list[tuple[str, str]]:
    """Inspect embedded CSS, SVG, and HTML resources for nested references."""
    header, _, payload = url.partition(",")
    mime = header[5:].split(";")[0].lower()
    if mime not in {"text/css", "text/html", "image/svg+xml"}:
        return []
    raw = (
        base64.b64decode(payload, validate=True)
        if ";base64" in header
        else unquote_to_bytes(payload)
    )
    text = raw.decode("utf-8")
    if mime == "text/css":
        return [("css", item) for item in css_urls(text)]
    page = Page()
    page.feed(text)
    external = []
    for tag, reference in page.urls:
        if reference.startswith("#"):
            if unquote(reference[1:]) not in page.ids:
                message = f"missing embedded anchor {reference}"
                raise ValueError(message)
        else:
            external.append((tag, reference))
    return external


def css_urls(text: str) -> list[str]:
    """Extract url() and @import resource paths from CSS text."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    urls = [match[1].strip() for match in re.findall(r"url\(\s*(['\"]?)([^)'\"]+)\1\s*\)", text)]
    urls.extend(re.findall(r"@import\s+['\"]([^'\"]+)['\"]", text))
    # Fragment-only CSS values need selector/cascade evaluation, including states
    # created by JavaScript. They are not resource files. SVG <use href> and HTML
    # anchors remain validated in their own document scope.
    return [url for url in urls if not url.startswith("#")]


@dataclass(frozen=True, slots=True)
class UrlChecker:
    """Validator for individual resource and anchor URLs."""

    root: Path
    pages: dict[Path, Page]
    links: bool
    offline: bool

    def check(self, path: Path, tag: str, url: str) -> str | None:
        """Validate a single URL referenced within an HTML or CSS document."""
        if tag == "a" and not self.links:
            return None
        parsed = urlsplit(url)
        if parsed.scheme or parsed.netloc:
            if self.offline and tag != "a" and parsed.scheme != "data":
                return f"{path}: external resource in offline output: {url}"
            return None
        target = (
            self.root / unquote(parsed.path.lstrip("/"))
            if parsed.path.startswith("/")
            else path.parent / unquote(parsed.path)
        )
        if not parsed.path:
            target = path
        if target.is_dir():
            target /= "index.html"
        target = target.resolve()
        if not target.is_relative_to(self.root) or not target.is_file():
            return f"{path}: missing local resource {url}"
        if (
            self.links
            and parsed.fragment
            and target in self.pages
            and not valid_fragment(self.pages[target], unquote(parsed.fragment))
        ):
            return f"{path}: missing anchor {url}"
        return None


def valid_fragment(page: Page, fragment: str) -> bool:
    """Resolve standard anchors and Reveal's documented hash route form."""
    if fragment in page.ids:
        return True
    if page.reveal_routes and fragment.startswith("/"):
        return fragment[1:] in page.ids or re.fullmatch(r"/\d+(?:/\d+){0,2}", fragment) is not None
    return False


def linked_resources(
    root: Path, pages: dict[Path, Page], *, single_file: bool
) -> list[tuple[Path, list[tuple[str, str]]]]:
    """Traverse all stylesheets and extract recursively linked resources."""
    resources = [(path, page.urls) for path, page in pages.items()]
    queue: list[Path] = [] if single_file else sorted(root.rglob("*.css"))
    seen: set[Path] = set()
    index = 0
    while index < len(resources) or queue:
        if index < len(resources):
            origin, urls = resources[index]
            index += 1
            for _, url in urls:
                parsed = urlsplit(url)
                if not parsed.scheme and not parsed.netloc and parsed.path.endswith(".css"):
                    queue.append(
                        root / unquote(parsed.path.lstrip("/"))
                        if parsed.path.startswith("/")
                        else origin.parent / unquote(parsed.path)
                    )
        if queue:
            path = queue.pop().resolve()
            if path in seen or not path.is_relative_to(root) or not path.is_file():
                continue
            seen.add(path)
            resources.append(
                (path, [("css", url) for url in css_urls(path.read_text(encoding="utf-8"))])
            )
    return resources


def validate_output(
    root: Path,
    *,
    links: bool = False,
    offline: bool = False,
    resource_root: Path | None = None,
) -> list[str]:
    """Validate HTML and CSS files within an output directory or single file.

    Args:
        root: Root directory containing compiled site output or a single HTML file.
        links: Whether to validate internal <a> links and anchor targets.
        offline: Whether to disallow external HTTP/HTTPS resources (excluding <a> links).
        resource_root: Explicit root directory for resolving local assets when root is a file.

    Returns:
        A list of validation error messages, or an empty list if valid.

    """
    root = root.resolve()
    single_file = root.is_file()
    paths = [root] if single_file else sorted(root.rglob("*.html"))
    if not paths:
        return [f"{root}: no HTML output found"]
    if root.is_file():
        root = resource_root.resolve() if resource_root else root.parent
    errors: list[str] = []
    pages: dict[Path, Page] = {}
    for path in paths:
        page = Page()
        try:
            page.feed(decode_html(path.read_text(encoding="utf-8")))
        except (ValueError, KeyError, UnicodeError) as decode_error:
            errors.append(f"{path}: invalid compressed output: {decode_error}")
            continue
        pages[path] = page
        errors.extend(
            f"{path}: duplicate HTML id {identifier}" for identifier in sorted(page.duplicates)
        )
    resources = linked_resources(root, pages, single_file=single_file)
    checker = UrlChecker(root, pages, links=links, offline=offline)
    for path, urls in resources:
        for tag, url in expand_embedded_urls(urls, path, errors):
            error = checker.check(path, tag, url)
            if error:
                errors.append(error)
    return errors


def expand_embedded_urls(
    urls: list[tuple[str, str]], path: Path, errors: list[str]
) -> list[tuple[str, str]]:
    """Expand embedded resources with bounded nesting and explicit diagnostics."""
    result = list(urls)
    pending = list(urls)
    for _ in range(16):
        nested = []
        for _, url in pending:
            if url.startswith("data:"):
                try:
                    nested.extend(embedded_urls(url))
                except (ValueError, UnicodeError, binascii.Error) as error:
                    errors.append(f"{path}: malformed embedded resource: {error}")
        if not nested:
            return result
        result.extend(nested)
        pending = nested
    errors.append(f"{path}: embedded resource nesting exceeds 16 levels")
    return result
