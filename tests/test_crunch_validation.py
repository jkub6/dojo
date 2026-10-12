"""Inspect real payloads and reject damage before publication."""

from __future__ import annotations

import io
import json
import re
import zlib
from urllib.parse import quote

import pytest

from dojo.crunch import decode_base91, decode_html, encode_base91, generate_payloads
from dojo.validation import embedded_urls, expand_embedded_urls, srcset_urls, validate_output


def compressed_page():
    return b"".join(generate_payloads(io.BytesIO(b"<h1>Content</h1>"))).decode()


def replace_manifest(text, change):
    pattern = r'(<script id="dojo-crunch-manifest" type="application/json">)(.*?)(</script>)'

    def apply(match):
        data = json.loads(match[2])
        change(data)
        return match[1] + json.dumps(data) + match[3]

    return re.sub(pattern, apply, text)


@pytest.mark.parametrize("payload", ["<", "A", "é"])
def test_noncanonical_base91_is_rejected(payload):
    with pytest.raises(ValueError, match="Base91"):
        decode_base91(payload)


def test_binary_base91_round_trip():
    for length in range(257):
        value = bytes(range(length))
        assert decode_base91(encode_base91(value)) == value


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("chunks", 5, "size or chunk count"),
        ("size", -1, "size or chunk count"),
        ("size", 5, "length mismatch"),
        ("compressed", 1, "payload length mismatch"),
        ("size", "wrong type", "manifest"),
    ],
)
def test_damaged_manifest_is_reported_by_public_validator(tmp_path, key, value, message):
    page = tmp_path / "index.html"
    page.write_text(replace_manifest(compressed_page(), lambda data: data.update({key: value})))
    errors = validate_output(page)
    assert len(errors) == 1
    assert message in errors[0]


def test_missing_manifest_and_missing_payload_are_rejected():
    page = compressed_page()
    with pytest.raises(ValueError, match="lacks its validation manifest"):
        decode_html(page.replace('id="dojo-crunch-manifest"', 'id="missing"'))
    with pytest.raises(ValueError, match="no payload chunks"):
        decode_html(page.replace('type="application/octet-stream"', 'type="text/plain"'))


def test_invalid_zstd_with_correct_transport_checksum_is_rejected():
    page = compressed_page()
    pattern = r'<script type="application/octet-stream" data-crunch="[^"]+">.*?</script>'
    raw = b"invalid zstandard bytes"
    chunk = f'<script type="application/octet-stream" data-crunch="0:{zlib.crc32(raw):x}">{encode_base91(raw)}</script>'
    page = re.sub(pattern, lambda _: chunk, page, flags=re.DOTALL)
    page = replace_manifest(page, lambda data: data.update(compressed=len(raw)))
    with pytest.raises(ValueError, match="Zstandard"):
        decode_html(page)


def test_embedded_resources_keep_fragment_validation_and_external_dependencies(tmp_path):
    assert embedded_urls(
        'data:image/svg+xml,<svg id="local"><use href="%23local"/><image href="https://example.invalid/image"/></svg>'
    ) == [("image", "https://example.invalid/image")]
    with pytest.raises(ValueError, match="missing embedded anchor"):
        embedded_urls('data:image/svg+xml,<svg><use href="%23absent"/></svg>')
    errors = []
    expand_embedded_urls([("img", "data:text/css;base64,broken!")], tmp_path, errors)
    assert "malformed embedded resource" in errors[0]
    assert srcset_urls("first.png,second.png") == ["first.png", "second.png"]
    assert srcset_urls("\f\v, \u00a0first.png 1x, second.png 2x\n") == ["first.png", "second.png"]


def test_embedded_nesting_is_bounded(tmp_path):
    resource = "missing.png"
    for _ in range(17):
        resource = "data:text/css," + quote(f'body {{ background: url("{resource}"); }}')
    errors = []
    expand_embedded_urls([("css", resource)], tmp_path, errors)
    assert "nesting exceeds 16" in errors[0]
