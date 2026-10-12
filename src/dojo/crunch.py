"""Self-extracting offline HTML compressor module.

Transforms UTF-8 HTML into self-extracting offline HTML using in-process Zstandard
compression and an embedded Web Worker decoder.
"""

from __future__ import annotations

import argparse
import base64
import codecs
import io
import json
import re
import sys
import tempfile
import zlib
from pathlib import Path
from typing import TYPE_CHECKING, cast

import zstandard as zstd

from .exceptions import (
    CrunchError,
    IncompleteUtf8HtmlError,
    InvalidUtf8HtmlError,
    SameInputOutputError,
    StreamSizeMismatchError,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from typing import BinaryIO

TRANSPORT_BYTES = 256 * 1024
BASE91_ALPHABET = (
    'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!#$%&()*+,./:;-=>?@[]^_`{|}~"'
)

_BASE91_THRESHOLD = 88
_BASE91_BITS_THRESHOLD = 13
_BASE91_COUNT_13 = 13
_BASE91_COUNT_14 = 14
_BASE91_MASK_8191 = 8191
_BASE91_MASK_16383 = 16383
_BASE91_TAIL_BITS = 7
_BASE91_TAIL_VALUE = 90

# =============================================================================
# Embedded Browser JavaScript
# =============================================================================

_RESOURCES = Path(__file__).parent / "resources"
FZSTD_DECODER_CODE = (
    "/*\n"
    + (_RESOURCES / "fzstd.LICENSE").read_text(encoding="utf-8")
    + "*/\n"
    + (_RESOURCES / "fzstd.js").read_text(encoding="utf-8")
)

JS_SHARED = """
function decodeBase91(encoded, expectedLength) {
  if (!Number.isSafeInteger(expectedLength) || expectedLength < 0) {
    throw new Error('Invalid decoded payload length');
  }
  if (encoded.length > Math.ceil(expectedLength * 16 / 13) + 1 ||
      (expectedLength && !encoded.length)) {
    throw new Error('Invalid Base91 payload length');
  }
  const alphabet = BASE91_ALPHABET;
  const table = new Int16Array(128);
  table.fill(-1);
  for (let index = 0; index < alphabet.length; ++index) {
    table[alphabet.charCodeAt(index)] = index;
  }
  const output = new Uint8Array(expectedLength);
  let accumulator = 0;
  let bits = 0;
  let pending = -1;
  let offset = 0;
  let lastValue = 0;
  let lastBits = 0;
  for (let index = 0; index < encoded.length; ++index) {
    const code = encoded.charCodeAt(index);
    const value = code < 128 ? table[code] : -1;
    if (value < 0) throw new Error('Invalid Base91 payload character');
    if (pending < 0) {
      pending = value;
      continue;
    }
    pending += value * 91;
    lastValue = pending;
    lastBits = (pending & 8191) > 88 ? 13 : 14;
    accumulator |= pending << bits;
    bits += lastBits;
    while (bits > 7) {
      if (offset === output.length) throw new Error('Base91 payload exceeds its declared length');
      output[offset++] = accumulator & 255;
      accumulator >>>= 8;
      bits -= 8;
    }
    pending = -1;
  }
  if (pending >= 0) {
    if (!bits || pending >= (1 << (8 - bits))) throw new Error('Invalid Base91 payload tail');
    if (offset === output.length) throw new Error('Base91 payload exceeds its declared length');
    output[offset++] = accumulator | (pending << bits);
  } else if (accumulator || (encoded.length && lastBits - bits <= 7 && lastValue <= 90)) {
    throw new Error('Invalid Base91 payload tail');
  }
  if (offset !== expectedLength) throw new Error('Base91 payload is truncated');
  return output;
}

function crc32(bytes) {
  const table = crc32.table || (crc32.table = Uint32Array.from({ length: 256 }, (_, value) => {
    for (let bit = 0; bit < 8; ++bit) value = (value >>> 1) ^ (0xedb88320 & -(value & 1));
    return value >>> 0;
  }));
  let crc = 0xffffffff;
  for (let index = 0; index < bytes.length; ++index) {
    crc = (crc >>> 8) ^ table[(crc ^ bytes[index]) & 255];
  }
  return (crc ^ 0xffffffff) >>> 0;
}
"""

JS_WORKER_MAIN = """
function workerMain() {
  let reply;
  const ask = (type, data = {}, transfer = []) => new Promise(resolve => {
    reply = resolve;
    self.postMessage({ type, ...data }, transfer);
  });
  self.onmessage = event => {
    if (reply) {
      const resolve = reply;
      reply = null;
      resolve(event.data);
    } else if (event.data.type === 'start') {
      run(event.data.meta).catch(error => self.postMessage({ type: 'error', message: error.message }));
    }
  };
  async function run(meta) {
    let input = new Uint8Array(0), offset = 0, received = 0, chunks = 0, decoded = 0;
    async function read(length) {
      const result = new Uint8Array(length);
      let filled = 0;
      while (filled < length) {
        if (offset === input.length) {
          const message = await ask('input');
          if (message.type !== 'input' || !message.text) throw new Error('Truncated compressed HTML.');
          const expected = Math.min(TRANSPORT_BYTES, meta.compressed - received);
          if (expected <= 0 || ++chunks > meta.chunks) throw new Error('Unexpected extra payload.');
          input = decodeBase91(message.text, expected);
          if (crc32(input) !== message.crc) throw new Error('Payload checksum mismatch. The file may be damaged.');
          offset = 0;
          received += input.length;
        }
        const count = Math.min(length - filled, input.length - offset);
        result.set(input.subarray(offset, offset + count), filled);
        filled += count;
        offset += count;
      }
      return result;
    }
    if (!self.fzstd || typeof self.fzstd.Decompress !== 'function') throw new Error('The embedded fzstd decoder is unavailable.');
    const header = await read(6);
    if (header[0] !== 40 || header[1] !== 181 || header[2] !== 47 || header[3] !== 253 ||
        (header[4] & ~4) !== 0) throw new Error('Unsupported Zstd frame header.');
    const windowBase = 2 ** (10 + (header[5] >>> 3));
    const windowSize = windowBase + windowBase / 8 * (header[5] & 7);
    if (windowSize > 2 ** meta.windowLog || windowSize > 2 ** 25) throw new Error('Zstd decoder window exceeds the configured limit.');
    let output = [];
    const decoder = new self.fzstd.Decompress(bytes => {
      if (bytes.length > 131072) throw new Error('Oversized Zstd block.');
      decoded += bytes.length;
      if (decoded > meta.size) throw new Error('Decoded HTML exceeds its declared size.');
      if (bytes.length) output.push(bytes.byteOffset === 0 && bytes.byteLength === bytes.buffer.byteLength ? bytes : bytes.slice());
    });
    async function drain() {
      if (!output.length) return;
      const batch = output;
      output = [];
      if (batch.length > 4) throw new Error('Unexpected decoder output batch.');
      const buffers = batch.map(bytes => bytes.buffer);
      const answer = await ask('output', { buffers }, buffers);
      if (answer.type !== 'ack') throw new Error('Invalid decoder acknowledgment.');
    }
    decoder.push(header, false);
    let last = false;
    while (!last) {
      const blockHeader = await read(3);
      const bits = blockHeader[0] | (blockHeader[1] << 8) | (blockHeader[2] << 16);
      last = !!(bits & 1);
      const type = (bits >>> 1) & 3;
      const size = bits >>> 3;
      if (type === 3 || size > Math.min(131072, windowSize)) throw new Error('Invalid Zstd block header.');
      const body = await read(type === 1 ? 1 : size);
      const block = new Uint8Array(3 + body.length);
      block.set(blockHeader);
      block.set(body, 3);
      decoder.push(block, false);
      await drain();
    }
    decoder.push(await read(header[4] & 4 ? 4 : 0), true);
    await drain();
    if (offset !== input.length || received !== meta.compressed || chunks !== meta.chunks || decoded !== meta.size) {
      throw new Error('Compressed HTML is truncated or has an incorrect length.');
    }
    self.postMessage({ type: 'done' });
  }
}
"""

JS_BROWSER_MAIN = """
function browserMain(meta, workerCode) {
  let worker, workerURL, finished = false, at = 0;
  let payload = Array.from(document.querySelectorAll('script[data-crunch]'));
  const decoder = new TextDecoder('utf-8', { fatal: true });
  const open = document.open.bind(document);
  const write = document.write.bind(document);
  const close = document.close.bind(document);
  const schedule = setTimeout.bind(globalThis);
  const later = globalThis.scheduler?.yield ? globalThis.scheduler.yield.bind(globalThis.scheduler) :
    () => new Promise(resolve => schedule(resolve, 0));

  const chunks = [];

  const release = () => {
    worker?.terminate();
    if (workerURL) URL.revokeObjectURL(workerURL);
    for (const element of payload) if (element) { element.textContent = ''; element.remove(); }
    payload = [];
  };

  const fail = error => {
    if (finished) return;
    finished = true;
    release();
    const message = document.createElement('pre');
    message.style.cssText = 'position:relative;z-index:999999;white-space:pre-wrap;padding:1rem;background:#fff;color:#a00';
    message.textContent = 'Unable to open compressed HTML: ' + error.message;
    (document.body || document.documentElement).append(message);
    const status = document.getElementById('crunch-status');
    if (status) status.textContent = 'Loading failed.';
    const spinner = document.querySelector('.spinner');
    if (spinner) spinner.style.display = 'none';
    console.error(error);
  };

  async function handle(message) {
    if (finished) return;

    if (message.type === 'input') {
      const element = payload[at];
      if (!element) throw new Error('Missing payload chunk.');
      const [index, checksum] = element.dataset.crunch.split(':');
      if (index !== at.toString(36)) throw new Error('Payload chunks are out of order.');
      const text = element.textContent;
      const crc = Number.parseInt(checksum, 16);
      payload[at++] = null;
      element.textContent = '';
      element.remove();
      worker.postMessage({ type: 'input', text, crc });

    } else if (message.type === 'output') {
      for (const buffer of message.buffers) {
        chunks.push(new Uint8Array(buffer));
      }
      worker.postMessage({ type: 'ack' });

    } else if (message.type === 'done') {
      if (at !== payload.length) throw new Error('Unconsumed payload chunks.');

      open();
      window.addEventListener('pagehide', release, { once: true });
      write('<!DOCTYPE html>');

      let chunkStart = performance.now();
      for (const bytes of chunks) {
        const text = decoder.decode(bytes, { stream: true });
        if (text) write(text);
        if (performance.now() - chunkStart > 16) {
          await later();
          chunkStart = performance.now();
        }
      }

      const tail = decoder.decode();
      if (tail) write(tail);

      finished = true;
      release();
      close();

    } else if (message.type === 'error') {
      throw new Error(message.message);
    }
  }

  try {
    if (payload.length !== meta.chunks) throw new Error('The compressed file is incomplete.');
    workerURL = URL.createObjectURL(new Blob([workerCode], { type: 'text/javascript' }));
    workerCode = null;
    worker = new Worker(workerURL);
    worker.onmessage = event => { handle(event.data).catch(fail); };
    worker.onerror = event => { event.preventDefault(); fail(new Error(event.message || 'Worker could not start.')); };
    worker.onmessageerror = () => fail(new Error('Could not receive decoder output.'));
    worker.postMessage({ type: 'start', meta });
  } catch (error) { fail(error); }
}
"""


def strip_js_formatting(js_code: str) -> str:
    """Remove leading whitespace and full-line comments for smaller payload injection."""
    code = re.sub(r"^\s*//[^\n]*\n", "", js_code, flags=re.MULTILINE)
    code = re.sub(r"^[ \t]+", "", code, flags=re.MULTILINE)
    return code.strip()


def encode_base91(data: bytes) -> str:
    """Encode binary bytes into chunked Base91 ASCII string."""
    alphabet = BASE91_ALPHABET
    output: list[str] = []
    append = output.append

    accumulator = 0
    bits = 0
    for byte in data:
        accumulator |= byte << bits
        bits += 8
        if bits > _BASE91_BITS_THRESHOLD:
            val = accumulator & _BASE91_MASK_8191
            count = _BASE91_COUNT_13
            if val <= _BASE91_THRESHOLD:
                val = accumulator & _BASE91_MASK_16383
                count = _BASE91_COUNT_14
            accumulator >>= count
            bits -= count
            append(alphabet[val % 91])
            append(alphabet[val // 91])

    if bits:
        append(alphabet[accumulator % 91])
        if bits > _BASE91_TAIL_BITS or accumulator > _BASE91_TAIL_VALUE:
            append(alphabet[accumulator // 91])

    return "".join(output)


def make_header() -> bytes:
    """Generate the initial HTML header displaying a lightweight loading spinner."""
    return (
        b'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        b"<title>Loading HTML...</title><style>"
        b"body{margin:0;background:#1a1a1a}"
        b"#crunch-loader{position:fixed;top:0;left:0;right:0;bottom:0;display:flex;align-items:center;justify-content:center;padding-top:80px;color:#eee;font:16px system-ui}"
        b".spinner{position:fixed;top:calc(50% - 40px);left:calc(50% - 20px);width:40px;height:40px;border:4px solid rgba(255,255,255,0.2);border-top-color:#fff;border-radius:50%;animation:spin 1s linear infinite}"
        b"@keyframes spin{to{transform:rotate(360deg)}}"
        b"</style></head><body>"
        b'<div id="crunch-loader"><div class="spinner"></div><p id="crunch-status">Decompressing HTML...</p>'
        b"<noscript><p>JavaScript is required to open this file.</p></noscript></div>\n"
    )


def make_footer(meta: dict[str, int]) -> bytes:
    """Generate the runtime script and self-extracting bootstrap footer."""
    worker_code = (
        f"{FZSTD_DECODER_CODE}\n"
        f"const BASE91_ALPHABET={json.dumps(BASE91_ALPHABET)},TRANSPORT_BYTES={TRANSPORT_BYTES};\n"
        f"{strip_js_formatting(JS_SHARED)}\n"
        f"{strip_js_formatting(JS_WORKER_MAIN)}\n"
        "workerMain();"
    )

    runtime_js = (
        f"({strip_js_formatting(JS_BROWSER_MAIN)})({json.dumps(meta)},{json.dumps(worker_code)});"
    )
    encoded = base64.b64encode(zlib.compress(runtime_js.encode("utf-8"), level=9)).decode("ascii")

    footer_text = (
        "<script>document.addEventListener('DOMContentLoaded',()=>setTimeout(async()=>{try{"
        "if(!globalThis.DecompressionStream||!globalThis.Worker)throw Error('This file requires a modern browser with Workers and DecompressionStream.');"
        f"const b=Uint8Array.from(atob('{encoded}'),c=>c.charCodeAt(0)),s=document.createElement('script');"
        "s.textContent=await new Response(new Blob([b]).stream().pipeThrough(new DecompressionStream('deflate'))).text();"
        "document.head.append(s);s.remove()"
        "}catch(e){document.getElementById('crunch-status').textContent='Unable to open compressed HTML: '+e.message;console.error(e)}},0),{once:true})</script></body></html>"
    )
    manifest = (
        '<script id="dojo-crunch-manifest" type="application/json">'
        + json.dumps(meta, sort_keys=True)
        + "</script>"
    )
    return (manifest + footer_text).encode("ascii")


def decode_base91(encoded: str) -> bytes:
    """Decode and reject noncanonical transport encoding."""
    table = {char: index for index, char in enumerate(BASE91_ALPHABET)}
    output = bytearray()
    accumulator = bits = 0
    pending = -1
    for char in encoded:
        if char not in table:
            message = "Invalid Base91 payload character"
            raise ValueError(message)
        value = table[char]
        if pending < 0:
            pending = value
            continue
        pending += value * 91
        accumulator |= pending << bits
        bits += 13 if (pending & _BASE91_MASK_8191) > _BASE91_THRESHOLD else 14
        while bits > _BASE91_TAIL_BITS:
            output.append(accumulator & 255)
            accumulator >>= 8
            bits -= 8
        pending = -1
    if pending >= 0:
        output.append((accumulator | pending << bits) & 255)
    result = bytes(output)
    if encode_base91(result) != encoded:
        message = "Noncanonical Base91 payload"
        raise ValueError(message)
    return result


def _crunch_manifest(value: str) -> dict[str, int]:
    """Validate the transport manifest before allocating a decoder."""
    raw: object = json.loads(value)
    keys = {"chunks", "compressed", "size", "windowLog"}
    if (
        not isinstance(raw, dict)
        or raw.keys() != keys
        or any(type(value) is not int for value in raw.values())
    ):
        message = "Invalid compressed output manifest"
        raise ValueError(message)
    return cast("dict[str, int]", raw)


def decode_html(text: str, *, max_size: int = 512 * 1024 * 1024) -> str:
    """Inspect the actual compressed document without executing its JavaScript."""
    chunks = re.findall(
        r'<script type="application/octet-stream" data-crunch="([^"]+)">(.*?)</script>',
        text,
        re.DOTALL,
    )
    if not chunks:
        if 'id="dojo-crunch-manifest"' in text:
            message = "Compressed output has no payload chunks"
            raise ValueError(message)
        return text
    manifest = re.search(
        r'<script id="dojo-crunch-manifest" type="application/json">(.*?)</script>', text
    )
    if manifest is None:
        message = "Compressed output lacks its validation manifest; rebuild it with current Dojo"
        raise ValueError(message)
    meta = _crunch_manifest(manifest[1])
    if meta["chunks"] != len(chunks) or not 0 <= meta["size"] <= max_size:
        message = "Invalid compressed document size or chunk count"
        raise ValueError(message)
    compressed = bytearray()
    for index, (identity, payload) in enumerate(chunks):
        ordinal, crc = identity.split(":")
        data = decode_base91(payload)
        if ordinal != base36_encode(index) or zlib.crc32(data) != int(crc, 16):
            message = "Corrupt or out-of-order compressed payload"
            raise ValueError(message)
        compressed.extend(data)
    if len(compressed) != meta["compressed"]:
        message = "Compressed payload length mismatch"
        raise ValueError(message)
    try:
        with zstd.ZstdDecompressor().stream_reader(io.BytesIO(compressed)) as stream:
            restored = stream.read(meta["size"] + 1)
    except zstd.ZstdError as error:
        message = f"Invalid Zstandard payload: {error}"
        raise ValueError(message) from error
    if len(restored) != meta["size"]:
        message = "Decompressed payload length mismatch"
        raise ValueError(message)
    return restored.decode("utf-8")


def chunked_reader(file_obj: BinaryIO, chunk_size: int = 65536) -> Iterator[bytes]:
    """Yield chunks from a binary stream."""
    while True:
        chunk = file_obj.read(chunk_size)
        if not chunk:
            break
        yield chunk


def base36_encode(number: int) -> str:
    """Format an integer as base36 string."""
    if number == 0:
        return "0"
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    base36 = ""
    while number:
        number, i = divmod(number, 36)
        base36 = alphabet[i] + base36
    return base36


class _ChunkBuffer:
    """Buffers compressed bytes into fixed TRANSPORT_BYTES chunks."""

    def __init__(self, emit_fn: Callable[[memoryview], bytes]) -> None:
        self.pending = bytearray(TRANSPORT_BYTES)
        self.length = 0
        self.emit_fn = emit_fn

    def feed(self, data: bytes) -> Iterator[bytes]:
        offset = 0
        while offset < len(data):
            count = min(TRANSPORT_BYTES - self.length, len(data) - offset)
            self.pending[self.length : self.length + count] = data[offset : offset + count]
            self.length += count
            offset += count
            if self.length == TRANSPORT_BYTES:
                yield self.emit_fn(memoryview(self.pending))
                self.length = 0

    def flush(self) -> Iterator[bytes]:
        if self.length > 0:
            yield self.emit_fn(memoryview(self.pending)[: self.length])
            self.length = 0


def generate_payloads(
    input_stream: BinaryIO,
    level: int = 22,
    window_log: int = 25,
    expected_size: int | None = None,
) -> Iterator[bytes]:
    """Yield compressed HTML byte chunks in streaming fashion.

    Args:
        input_stream: Binary input stream containing UTF-8 HTML.
        level: Zstandard compression level (1-22).
        window_log: Decoder window log size (10-25).
        expected_size: Optional expected byte count for integrity check.

    Yields:
        Byte chunks of the self-extracting HTML document.

    Raises:
        InvalidUtf8HtmlError: If input contains invalid UTF-8 data.
        IncompleteUtf8HtmlError: If input ends with incomplete UTF-8 bytes.
        StreamSizeMismatchError: If stream size differs from expected_size.

    """
    if not 10 <= window_log <= 25:  # noqa: PLR2004 - fzstd supports a maximum 32 MiB window
        message = "Browser decoder requires window_log between 10 and 25"
        raise ValueError(message)
    utf8_decoder = codecs.getincrementaldecoder("utf-8")("strict")

    params = zstd.ZstdCompressionParameters.from_level(
        level,
        window_log=window_log,
        threads=-1,
    )
    cctx = zstd.ZstdCompressor(compression_params=params)

    stats = {"size": 0, "compressed": 0, "chunks": 0, "windowLog": window_log}

    def emit_chunk(data: memoryview) -> bytes:
        index = stats["chunks"]
        stats["chunks"] += 1
        stats["compressed"] += len(data)
        crc = zlib.crc32(data) & 0xFFFFFFFF
        b91 = encode_base91(bytes(data))

        header = f'<script type="application/octet-stream" data-crunch="{base36_encode(index)}:{crc:x}">'.encode(
            "ascii"
        )
        return header + b91.encode("ascii") + b"</script>\n"

    buffer = _ChunkBuffer(emit_chunk)
    yield make_header()

    comp_obj = cctx.compressobj()

    for chunk in chunked_reader(input_stream):
        try:
            utf8_decoder.decode(chunk, final=False)
        except UnicodeDecodeError as err:
            raise InvalidUtf8HtmlError from err

        stats["size"] += len(chunk)
        compressed = comp_obj.compress(chunk)
        if compressed:
            yield from buffer.feed(compressed)

    try:
        utf8_decoder.decode(b"", final=True)
    except UnicodeDecodeError as err:
        raise IncompleteUtf8HtmlError from err

    final_compressed = comp_obj.flush()
    if final_compressed:
        yield from buffer.feed(final_compressed)

    yield from buffer.flush()

    if expected_size is not None and stats["size"] != expected_size:
        raise StreamSizeMismatchError

    yield make_footer(stats)


def _write_output_chunks(
    in_stream: BinaryIO,
    output_str: str,
    input_size: int | None,
    level: int,
    window_log: int,
) -> None:
    """Stream compressed payload chunks to stdout or atomically to a file."""
    if output_str == "-":
        for out_chunk in generate_payloads(
            in_stream, level=level, window_log=window_log, expected_size=input_size
        ):
            sys.stdout.buffer.write(out_chunk)
        sys.stdout.buffer.flush()
        return

    out_dir = Path(output_str).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=out_dir, prefix=".crunch-html-", suffix=".tmp", delete=False
        ) as tf:
            temp_path = Path(tf.name)
            for out_chunk in generate_payloads(
                in_stream, level=level, window_log=window_log, expected_size=input_size
            ):
                tf.write(out_chunk)
        temp_path.replace(output_str)
        temp_path = None
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def crunch_file(
    input_target: str | Path | None = None,
    output_target: str | Path | None = None,
    level: int = 22,
    window_log: int = 25,
) -> None:
    """Compress HTML file or stdin to self-extracting HTML file or stdout.

    Args:
        input_target: Path to input HTML file, or None / '-' for stdin.
        output_target: Path to output HTML file, or None / '-' for stdout.
        level: Zstandard compression level (1-22).
        window_log: Window log size (10-25).

    Raises:
        SameInputOutputError: If input and output refer to the same file.
        FileNotFoundError: If input file does not exist.

    """
    input_str = str(input_target) if input_target is not None else "-"
    output_str = str(output_target) if output_target is not None else "-"

    if (
        output_str != "-"
        and input_str != "-"
        and Path(output_str).resolve() == Path(input_str).resolve()
    ):
        raise SameInputOutputError

    if input_str != "-":
        input_path = Path(input_str).resolve()
        if not input_path.is_file():
            msg = f"Input '{input_str}' must be a regular file."
            raise FileNotFoundError(msg)
        input_size = input_path.stat().st_size
        with input_path.open("rb") as f:
            _write_output_chunks(f, output_str, input_size, level, window_log)
    else:
        _write_output_chunks(sys.stdin.buffer, output_str, None, level, window_log)


def main(argv: list[str] | None = None) -> None:
    """CLI entrypoint for standalone crunch execution or 'python -m dojo.crunch'."""
    parser = argparse.ArgumentParser(
        prog="crunch",
        description="Stream UTF-8 HTML into self-extracting offline HTML",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            'Input defaults to stdin; an explicit "-" is accepted. Output files are replaced\n'
            "atomically only after successful compression. Do not redirect stdout over input.\n\n"
            "The default is maximum compression (--level 22 --window-log 25) with multi-threading.\n"
            "Output includes its self-contained decoder and needs no external dependencies or CDN."
        ),
    )

    parser.add_argument("input", nargs="?", default="-", help='Input file ("-" for stdin)')
    parser.add_argument(
        "output_pos",
        nargs="?",
        default=argparse.SUPPRESS,
        help="Output file (positional backward compat)",
    )
    parser.add_argument(
        "-o", "--output", help='Output file (default: stdout; "-" also means stdout)'
    )
    parser.add_argument(
        "-l",
        "--level",
        type=int,
        default=22,
        choices=range(1, 23),
        metavar="1-22",
        help="Zstd level (default: 22)",
    )
    parser.add_argument(
        "--window-log",
        type=int,
        default=25,
        choices=range(10, 26),
        metavar="10-25",
        help="Decoder history: 2^N bytes (default: 25 = 32 MiB)",
    )

    args = parser.parse_args(argv)

    output_target = getattr(args, "output_pos", args.output) if args.output is None else args.output
    if output_target is None:
        output_target = "-"

    if args.input == "-" and sys.stdin.isatty():
        parser.error("Specify input HTML or pipe it on stdin. Run with --help for usage.")

    try:
        crunch_file(args.input, output_target, level=args.level, window_log=args.window_log)
    except (CrunchError, ValueError, OSError, RuntimeError) as e:
        sys.exit(f"Error: {e}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
