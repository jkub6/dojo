"""Tests for the native crunch self-extracting HTML compressor module."""

from __future__ import annotations

import io
import os
import random
import re
import string
from typing import TYPE_CHECKING

import pytest
import zstandard as zstd

from dojo.cli import main as dojo_cli_main
from dojo.crunch import (
    BASE91_ALPHABET,
    base36_encode,
    chunked_reader,
    crunch_file,
    encode_base91,
    generate_payloads,
    make_footer,
    make_header,
)
from dojo.crunch import (
    main as crunch_main,
)
from dojo.exceptions import (
    IncompleteUtf8HtmlError,
    InvalidUtf8HtmlError,
    SameInputOutputError,
    StreamSizeMismatchError,
)

if TYPE_CHECKING:
    from pathlib import Path


def decode_base91_py(encoded: str, expected_len: int) -> bytes:
    """Decode base91 in reference Python for verification."""
    table = {c: i for i, c in enumerate(BASE91_ALPHABET)}
    output = bytearray(expected_len)
    accumulator = 0
    bits = 0
    pending = -1
    offset = 0

    for ch in encoded:
        val = table.get(ch, -1)
        assert val >= 0, f"Invalid Base91 character: {ch}"
        if pending < 0:
            pending = val
            continue
        pending += val * 91
        last_bits = 13 if (pending & 8191) > 88 else 14
        accumulator |= pending << bits
        bits += last_bits
        while bits > 7:
            output[offset] = accumulator & 255
            offset += 1
            accumulator >>= 8
            bits -= 8
        pending = -1

    if pending >= 0:
        output[offset] = accumulator | (pending << bits)
        offset += 1

    assert offset == expected_len, f"Length mismatch: {offset} vs {expected_len}"
    return bytes(output)


def test_base36_encode():
    assert base36_encode(0) == "0"
    assert base36_encode(1) == "1"
    assert base36_encode(35) == "z"
    assert base36_encode(36) == "10"


def test_base91_roundtrip():
    for size in [0, 1, 2, 3, 4, 13, 14, 15, 100, 4096, 65536]:
        data = os.urandom(size)
        encoded = encode_base91(data)
        assert all(c in BASE91_ALPHABET for c in encoded)
        if size > 0:
            decoded = decode_base91_py(encoded, size)
            assert decoded == data


def test_make_header():
    header = make_header()
    assert b"<!doctype html>" in header
    assert b"crunch-loader" in header
    assert b"spinner" in header


def test_make_footer():
    meta = {"size": 1000, "compressed": 500, "chunks": 2, "windowLog": 26}
    footer = make_footer(meta)
    assert b"document.addEventListener" in footer
    assert b"DecompressionStream" in footer
    assert b"Worker" in footer


def test_chunked_reader():
    stream = io.BytesIO(b"ABCDEFGHIJ")
    chunks = list(chunked_reader(stream, chunk_size=3))
    assert chunks == [b"ABC", b"DEF", b"GHI", b"J"]


def test_generate_payloads_decompression_fidelity():
    original_html = """<!DOCTYPE html>
<html>
<head><title>Test Presentation</title></head>
<body>
<h1>Heading 1</h1>
<p>This is a paragraph with special unicode characters: 🚀 🌟 🗜️.</p>
</body>
</html>"""
    original_bytes = original_html.encode("utf-8")

    chunks = list(generate_payloads(io.BytesIO(original_bytes), level=22, window_log=26))
    full_output = b"".join(chunks).decode("utf-8")

    assert "<!doctype html>" in full_output
    assert "Decompressing HTML..." in full_output

    # Extract payloads from script data-crunch tags
    script_pattern = re.compile(
        r'<script type="application/octet-stream" data-crunch="([^"]+)">([^<]+)</script>'
    )
    matches = script_pattern.findall(full_output)
    assert len(matches) > 0

    compressed_stream = bytearray()
    for idx_crc, b91_payload in matches:
        _idx_str, _crc_hex = idx_crc.split(":")
        chunk_data = bytearray()
        table = {c: i for i, c in enumerate(BASE91_ALPHABET)}
        accumulator = 0
        bits = 0
        pending = -1
        for ch in b91_payload:
            val = table[ch]
            if pending < 0:
                pending = val
                continue
            pending += val * 91
            last_bits = 13 if (pending & 8191) > 88 else 14
            accumulator |= pending << bits
            bits += last_bits
            while bits > 7:
                chunk_data.append(accumulator & 255)
                accumulator >>= 8
                bits -= 8
            pending = -1
        if pending >= 0:
            chunk_data.append(accumulator | (pending << bits))

        compressed_stream.extend(chunk_data)

    # Decompress using zstandard stream_reader (handles streaming frames without content size)
    dctx = zstd.ZstdDecompressor()
    decompressed = dctx.stream_reader(io.BytesIO(bytes(compressed_stream))).read()
    assert decompressed == original_bytes


def test_generate_payloads_large_content():
    # Generate content whose compressed size exceeds TRANSPORT_BYTES (256 KB)
    rng = random.Random(42)  # noqa: S311
    words = ["".join(rng.choices(string.ascii_letters, k=10)) for _ in range(50000)]
    large_html = "<p>" + " </p><p> ".join(words) + "</p>"
    large_bytes = large_html.encode("utf-8")

    chunks = list(generate_payloads(io.BytesIO(large_bytes), level=1, window_log=26))
    full_output = b"".join(chunks).decode("utf-8")

    script_pattern = re.compile(r'data-crunch="([^"]+)"')
    matches = script_pattern.findall(full_output)
    assert len(matches) >= 2


def test_generate_payloads_invalid_utf8():
    invalid_bytes = b"\xff\xfe\x00\x00\xff"
    with pytest.raises(InvalidUtf8HtmlError):
        list(generate_payloads(io.BytesIO(invalid_bytes)))


def test_generate_payloads_incomplete_utf8():
    incomplete_bytes = b"Hello \xc3"
    with pytest.raises(IncompleteUtf8HtmlError):
        list(generate_payloads(io.BytesIO(incomplete_bytes)))


def test_generate_payloads_size_mismatch():
    data = b"Hello World"
    with pytest.raises(StreamSizeMismatchError):
        list(generate_payloads(io.BytesIO(data), expected_size=100))


def test_crunch_file_to_file(tmp_path: Path):
    in_file = tmp_path / "input.html"
    out_file = tmp_path / "output.html"
    in_file.write_text("<h1>Hello from test_crunch_file</h1>", encoding="utf-8")

    crunch_file(in_file, out_file)
    assert out_file.exists()
    assert out_file.stat().st_size > 0
    assert "Decompressing HTML..." in out_file.read_text(encoding="utf-8")


def test_crunch_file_same_file_error(tmp_path: Path):
    same_file = tmp_path / "same.html"
    same_file.write_text("<h1>Test</h1>", encoding="utf-8")

    with pytest.raises(SameInputOutputError):
        crunch_file(same_file, same_file)


def test_crunch_file_nonexistent_input(tmp_path: Path):
    nonexistent = tmp_path / "nonexistent.html"
    out_file = tmp_path / "output.html"

    with pytest.raises(FileNotFoundError):
        crunch_file(nonexistent, out_file)


def test_crunch_main_cli(tmp_path: Path):
    in_file = tmp_path / "input.html"
    out_file = tmp_path / "output.html"
    in_file.write_text("<h1>Hello from CLI</h1>", encoding="utf-8")

    crunch_main([str(in_file), "-o", str(out_file)])
    assert out_file.exists()
    assert "Decompressing HTML..." in out_file.read_text(encoding="utf-8")


def test_dojo_cli_crunch_subcommand(tmp_path: Path):
    in_file = tmp_path / "input.html"
    out_file = tmp_path / "output.html"
    in_file.write_text("<h1>Hello from dojo crunch subcommand</h1>", encoding="utf-8")

    dojo_cli_main(["crunch", str(in_file), "-o", str(out_file)])
    assert out_file.exists()
    assert "Decompressing HTML..." in out_file.read_text(encoding="utf-8")
