"""Cross-platform command execution wrapper for Ninja rules.

This module provides a standalone wrapper for executing commands in a portable way,
supporting path placeholder resolution and environment manipulation.
"""

from __future__ import annotations

import argparse
import contextlib
import functools
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import IO, overload

# Constants
MIN_COPY_ARGS = 2


@dataclass(frozen=True)
class PlaceholderContext:
    """Context for resolving `{placeholder}` variables in commands."""

    in_file: str | None = None
    out_file: str | None = None
    src_dir: str | None = None
    out_dir: str | None = None
    build_dir: str | None = None
    serve_dir: str | None = None
    serve_port: int | None = None
    publication_file: str | None = None


class WrapArgs(argparse.Namespace):
    """Typed arguments for dojo wrap."""

    ensure_dir: str | None = None
    cwd: str | None = None
    path_env: str | None = None
    in_file: str | None = None
    out_file: str | None = None
    src_dir: str | None = None
    out_dir: str | None = None
    build_dir: str | None = None
    serve_dir: str | None = None
    log_file: str | None = None
    command: list[str] | None = None
    copy: bool = False
    atomic: bool = False
    media_dir: str | None = None
    additional_in_file: list[str] | None = None
    publication_file: str | None = None


def _get_path_repls(ctx: PlaceholderContext) -> dict[str, str]:
    """Calculate path-based replacements."""
    in_abs = Path(ctx.in_file).resolve() if ctx.in_file else None
    out_abs = Path(ctx.out_file).resolve() if ctx.out_file else None
    in_abs_dir = in_abs.parent if in_abs else None
    out_abs_dir = out_abs.parent if out_abs else None

    repls: dict[str, str] = {}
    if in_abs and in_abs_dir:
        repls.update({"{in_abs}": in_abs.as_posix(), "{in_abs_dir}": in_abs_dir.as_posix()})
    if out_abs and out_abs_dir:
        repls.update({"{out_abs}": out_abs.as_posix(), "{out_abs_dir}": out_abs_dir.as_posix()})

    if ctx.publication_file:
        publication_dir = Path(ctx.publication_file).resolve().parent
        repls["{publication_dir}"] = str(publication_dir)
        repls["{root_val}"] = os.path.relpath(
            Path(ctx.out_dir or ".").resolve(), publication_dir
        ).replace("\\", "/")
        return repls
    if ctx.out_dir and out_abs_dir:
        base_dir = Path(ctx.out_dir).resolve()
        if ctx.build_dir:
            build_abs = Path(ctx.build_dir).resolve()
            try:
                out_abs_dir.relative_to(build_abs)
                base_dir = build_abs
            except ValueError:
                pass
        root_val = os.path.relpath(base_dir, out_abs_dir).replace("\\", "/")
        repls["{root_val}"] = root_val
    return repls


def _get_srv_repls(ctx: PlaceholderContext) -> dict[str, str]:
    """Calculate server-based replacements."""
    repls: dict[str, str] = {}
    if ctx.serve_dir and ctx.serve_port and ctx.in_file:
        serve_abs = Path(ctx.serve_dir).resolve()
        in_abs_val = Path(ctx.in_file).resolve()
        try:
            rel_path = os.path.relpath(in_abs_val, serve_abs).replace("\\", "/")
            repls["{url}"] = f"http://localhost:{ctx.serve_port}/{rel_path}"
        except ValueError:
            pass
    return repls


def _get_replacements(ctx: PlaceholderContext) -> dict[str, str]:
    """Calculate all available placeholder replacements."""
    repls: dict[str, str] = {}
    if ctx.src_dir:
        repls["{src_dir}"] = ctx.src_dir
    if ctx.out_dir:
        repls["{out_dir}"] = ctx.out_dir
    if ctx.build_dir:
        repls["{build_dir}"] = ctx.build_dir
    if ctx.serve_dir:
        repls["{serve_dir}"] = ctx.serve_dir

    repls.update(_get_path_repls(ctx))

    in_abs = Path(ctx.in_file).resolve() if ctx.in_file else None
    in_abs_dir = in_abs.parent if in_abs else None
    if ctx.build_dir and in_abs_dir:
        rel_src_dir = os.path.relpath(in_abs_dir, Path(ctx.build_dir).resolve()).replace("\\", "/")
        repls["{rel_src_dir}"] = rel_src_dir
        if ctx.src_dir:
            sv = (Path(ctx.src_dir).resolve() / rel_src_dir).resolve().as_posix()
            repls["{src_dir_val}"] = sv

    repls.update(_get_srv_repls(ctx))
    return repls


def resolve_placeholders(value: str, ctx: PlaceholderContext) -> str:
    """Replace `{placeholder}` variables based on resolved paths."""
    replacements = _get_replacements(ctx)
    v = value
    for placeholder, replacement in replacements.items():
        v = v.replace(placeholder, replacement)
    return v


def _create_parser() -> argparse.ArgumentParser:
    """Create the argument parser for dojo wrap."""
    parser = argparse.ArgumentParser(prog="dojo wrap", add_help=False)
    parser.add_argument(
        "--ensure-dir", help="Directory to create before running (supports placeholders)."
    )
    parser.add_argument(
        "--cwd", help="Directory to switch to before running (supports placeholders)."
    )
    parser.add_argument(
        "--path-env",
        help="Additional PATH entries to prepend (colon-separated, mapped to OS format).",
    )
    parser.add_argument("--in-file", help="Input file path for $in resolution.")
    parser.add_argument(
        "--media-dir", help="Owned relative extraction directory for this renderer."
    )
    parser.add_argument(
        "--additional-in-file",
        action="append",
        help="Additional input for tools accepting {in_all}.",
    )
    parser.add_argument(
        "--atomic", action="store_true", help="Replace output only on successful execution."
    )
    parser.add_argument("--publication-file", help="Final publication path for URL context.")
    parser.add_argument("--out-file", help="Output file path for $out resolution.")
    parser.add_argument("--src-dir", help="Absolute source directory.")
    parser.add_argument("--out-dir", help="Absolute output directory.")
    parser.add_argument("--build-dir", help="Absolute build directory.")
    parser.add_argument("--serve-dir", help="Directory to serve via HTTP during execution.")
    parser.add_argument("--log-file", help="Redirect stdout and stderr to this log file.")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="The command to run after --")
    parser.add_argument(
        "--copy", action="store_true", help="Perform a file copy instead of running a command."
    )
    return parser


def _setup_env(path_env: str | None) -> dict[str, str]:
    """Prepare the environment with modified PATH if requested."""
    env = os.environ.copy()
    if path_env:
        # Dojo convention: input path_env is ALWAYS colon-separated regardless of host OS.
        # It is merged into the system PATH using the OS-specific separator.
        paths = path_env.split(":")
        os_path_str = os.pathsep.join(paths)
        if "PATH" in env:
            env["PATH"] = f"{os_path_str}{os.pathsep}{env['PATH']}"
        else:
            env["PATH"] = os_path_str
    return env


def _handle_copy(src: str, dst: str) -> None:
    """Perform a file copy operation."""
    try:
        # Preserve permissions, but let a successful build establish a fresh mtime.
        # Copying the source timestamp leaves outputs older than rule dependencies
        # and makes Ninja rebuild old assets and all their consumers indefinitely.
        shutil.copy(src, dst)
        sys.exit(0)
    except OSError as e:
        sys.stderr.write(f"dojo wrap copy error: {e}\n")
        sys.exit(1)


def _handle_exec(
    cmd: list[str],
    env: dict[str, str],
    cwd: str | None,
    out_file: str | None = None,
    log_handler: IO[str] | None = None,
) -> None:
    """Execute the command using subprocess."""
    try:
        result = subprocess.run(  # noqa: S603
            cmd,
            env=env,
            cwd=cwd,
            check=False,
            stdout=log_handler or sys.stdout,
            stderr=subprocess.STDOUT if log_handler else sys.stderr,
        )

        if result.returncode != 0 and out_file:
            path = Path(out_file)
            if path.exists():
                path.unlink()

        sys.exit(result.returncode)
    except (OSError, subprocess.SubprocessError) as e:
        sys.stderr.write(f"dojo wrap error executing {cmd[0]}: {e}\n")
        if out_file:
            path = Path(out_file)
            if path.exists():
                path.unlink()
        sys.exit(1)


def _start_server(directory: str, log_handler: IO[str] | None) -> tuple[ThreadingHTTPServer, int]:
    """Start the ephemeral HTTP server."""

    class LoggingQuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, format_spec: str, *args: object) -> None:
            msg = f"HTTP: {format_spec % args}\n"
            if log_handler:
                log_handler.write(msg)
                log_handler.flush()
            else:
                sys.stderr.write(msg)

    handler = functools.partial(LoggingQuietHandler, directory=directory)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]

    msg = f"DOJO SERVER: Starting at 127.0.0.1:{port} serving {directory}\n"
    if log_handler:
        log_handler.write(msg)
        log_handler.flush()
    else:
        sys.stderr.write(msg)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


@overload
def _p(val: None, current_ctx: PlaceholderContext) -> None: ...


@overload
def _p(val: str, current_ctx: PlaceholderContext) -> str: ...


def _p(val: str | None, current_ctx: PlaceholderContext) -> str | None:
    return resolve_placeholders(val, current_ctx) if val is not None else None


def _inject_slide_level(cmd: list[str], meta: dict[str, object]) -> None:
    """Inject slide-level flag from metadata if present."""
    if "slide-level" not in meta:
        return
    val = meta["slide-level"]
    if not isinstance(val, dict):
        return
    if val.get("t") == "MetaString":
        cmd.insert(1, f"--slide-level={val['c']}")
    elif val.get("t") == "MetaInlines":
        text = "".join(i.get("c", "") for i in val.get("c", []) if i.get("t") == "Str")
        cmd.insert(1, f"--slide-level={text}")


def _inject_toc(cmd: list[str], meta: dict[str, object]) -> None:
    """Inject or remove toc flag from metadata if present."""
    if "toc" not in meta:
        return
    val = meta["toc"]
    if not isinstance(val, dict) or val.get("t") != "MetaBool":
        return
    if val.get("c"):
        if "--toc" not in cmd:
            cmd.insert(1, "--toc")
    elif "--toc" in cmd:
        cmd.remove("--toc")


def _inject_metadata_overrides(cmd: list[str], in_file: str | None) -> None:
    """Dynamically extract structural options from document AST metadata."""
    if not (cmd and "pandoc" in cmd[0] and in_file and in_file.endswith(".json")):
        return

    try:
        with Path(in_file).open(encoding="utf-8") as f:
            ast = json.load(f)
            meta = ast.get("meta", {})
            _inject_slide_level(cmd, meta)
            _inject_toc(cmd, meta)
    except (OSError, ValueError) as e:
        sys.stderr.write(f"dojo wrap warning: Failed to extract metadata from AST: {e}\n")


def _publish_media(source: Path, destination: Path) -> None:
    """Replace one renderer's private media tree, including obsolete derivatives."""
    source.mkdir(parents=True, exist_ok=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dojo-media-", dir=destination.parent) as directory:
        backup = Path(directory) / "previous"
        if destination.exists():
            destination.rename(backup)
        try:
            staged = Path(directory) / "next"
            shutil.copytree(source, staged)
            staged.rename(destination)
        except OSError:
            if backup.exists():
                backup.rename(destination)
            raise


def run_wrap(argv: list[str]) -> None:
    """Cross-platform command execution wrapper for Ninja rules."""
    parser = _create_parser()
    args, unknown = parser.parse_known_args(argv, namespace=WrapArgs())
    cmd: list[str] = args.command or unknown
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]

    if not cmd:
        sys.stderr.write("Error: No command provided to dojo wrap\n")
        sys.exit(1)

    _inject_metadata_overrides(cmd, args.in_file)

    ctx = PlaceholderContext(
        in_file=args.in_file,
        out_file=args.out_file,
        src_dir=args.src_dir,
        out_dir=args.out_dir,
        build_dir=args.build_dir,
        serve_dir=args.serve_dir,
        publication_file=args.publication_file,
    )

    with contextlib.ExitStack() as stack:
        log_handler: IO[str] | None = None
        if args.log_file:
            log_path = Path(_p(args.log_file, ctx))
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_handler = stack.enter_context(log_path.open("a", encoding="utf-8"))

        server: ThreadingHTTPServer | None = None
        if args.serve_dir:
            serve_path = _p(args.serve_dir, ctx)
            server, port = _start_server(serve_path, log_handler)
            stack.callback(server.shutdown)
            stack.callback(server.server_close)
            ctx = PlaceholderContext(
                in_file=args.in_file,
                out_file=args.out_file,
                src_dir=args.src_dir,
                out_dir=args.out_dir,
                build_dir=args.build_dir,
                serve_dir=serve_path,
                serve_port=port,
                publication_file=args.publication_file,
            )

        if args.ensure_dir:
            ed = _p(args.ensure_dir, ctx)
            if ed:
                Path(ed).mkdir(parents=True, exist_ok=True)

        if args.cwd:
            Path(_p(args.cwd, ctx)).mkdir(parents=True, exist_ok=True)

        _run_transaction(cmd, args, ctx, stack, log_handler)


def _command_arguments(
    cmd: list[str], args: WrapArgs, ctx: PlaceholderContext, temporary_output: Path | None
) -> list[str]:
    final_cmd: list[str] = []
    for raw_argument in cmd:
        argument = raw_argument
        if argument == "{in_all}":
            final_cmd.extend(
                str(Path(path).resolve())
                for path in [args.in_file, *(args.additional_in_file or [])]
                if path
            )
        else:
            if temporary_output:
                argument = argument.replace("{out_abs}", str(temporary_output.resolve()))
            final_cmd.append(_p(argument, ctx) or argument)
    return final_cmd


def _run_transaction(
    cmd: list[str],
    args: WrapArgs,
    ctx: PlaceholderContext,
    stack: contextlib.ExitStack,
    log_handler: IO[str] | None,
) -> None:
    media_work: Path | None = None
    if args.media_dir:
        media_work = Path(
            stack.enter_context(tempfile.TemporaryDirectory(prefix="media-", dir=args.build_dir))
        )
        args.cwd = str(media_work)
    final_output = Path(args.out_file) if args.atomic and args.out_file else None
    temporary_output: Path | None = None
    if final_output:
        temporary_dir = Path(
            stack.enter_context(
                tempfile.TemporaryDirectory(dir=final_output.parent, prefix=".dojo-")
            )
        )
        temporary_output = temporary_dir / final_output.name
    final_cmd = _command_arguments(cmd, args, ctx, temporary_output)
    try:
        if args.copy:
            if len(final_cmd) < MIN_COPY_ARGS:
                sys.stderr.write("Error: Copy requires source and destination\n")
                sys.exit(1)
            _handle_copy(final_cmd[0], final_cmd[1])
        else:
            _handle_exec(
                final_cmd,
                _setup_env(args.path_env),
                _p(args.cwd, ctx),
                str(temporary_output) if temporary_output else _p(args.out_file, ctx),
                log_handler=log_handler,
            )
    except SystemExit as result:
        if result.code == 0 and temporary_output and final_output:
            if args.media_dir and media_work and args.publication_file:
                _publish_media(
                    media_work / args.media_dir,
                    Path(args.publication_file).parent / args.media_dir,
                )
            temporary_output.replace(final_output)
        raise


if __name__ == "__main__":
    run_wrap(sys.argv[1:])
