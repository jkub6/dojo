"""Cross-platform command execution wrapper for Ninja rules.

This module provides a standalone wrapper for executing commands in a portable way,
supporting path placeholder resolution and environment manipulation.
"""

from __future__ import annotations

import argparse
import functools
import os
import shutil
import socketserver
import subprocess
import sys
import threading
from dataclasses import dataclass
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

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


def resolve_placeholders(value: str, ctx: PlaceholderContext) -> str:
    """Replace `{placeholder}` variables based on resolved paths."""
    # Pre-resolve common paths used by multiple placeholders
    in_abs = Path(ctx.in_file).resolve() if ctx.in_file else None
    out_abs = Path(ctx.out_file).resolve() if ctx.out_file else None
    in_abs_dir = in_abs.parent if in_abs else None
    out_abs_dir = out_abs.parent if out_abs else None

    # Define available replacements
    replacements: dict[str, str] = {}
    if ctx.src_dir:
        replacements["{src_dir}"] = ctx.src_dir
    if ctx.out_dir:
        replacements["{out_dir}"] = ctx.out_dir
    if ctx.build_dir:
        replacements["{build_dir}"] = ctx.build_dir
    if ctx.serve_dir:
        replacements["{serve_dir}"] = ctx.serve_dir

    if in_abs and in_abs_dir:
        replacements["{in_abs}"] = in_abs.as_posix()
        replacements["{in_abs_dir}"] = in_abs_dir.as_posix()
    if out_abs and out_abs_dir:
        replacements["{out_abs}"] = out_abs.as_posix()
        replacements["{out_abs_dir}"] = out_abs_dir.as_posix()

    if ctx.out_dir and out_abs_dir:
        root_val = os.path.relpath(Path(ctx.out_dir).resolve(), out_abs_dir).replace("\\", "/")
        replacements["{root_val}"] = root_val

    if ctx.build_dir and in_abs_dir:
        rel_src_dir = os.path.relpath(in_abs_dir, Path(ctx.build_dir).resolve()).replace("\\", "/")
        replacements["{rel_src_dir}"] = rel_src_dir

        if ctx.src_dir:
            src_dir_val = (Path(ctx.src_dir).resolve() / rel_src_dir).resolve().as_posix()
            replacements["{src_dir_val}"] = src_dir_val

    if ctx.serve_dir and ctx.serve_port and ctx.in_file:
        serve_abs = Path(ctx.serve_dir).resolve()
        in_abs = Path(ctx.in_file).resolve()
        try:
            rel_path = os.path.relpath(in_abs, serve_abs).replace("\\", "/")
            replacements["{url}"] = f"http://localhost:{ctx.serve_port}/{rel_path}"
        except ValueError:
            # Fallback if paths are on different drives on Windows
            pass

    # Perform replacements
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
        shutil.copy2(src, dst)
        sys.exit(0)
    except OSError as e:
        sys.stderr.write(f"dojo wrap copy error: {e}\n")
        sys.exit(1)





def _handle_exec(
    cmd: list[str],
    env: dict[str, str],
    cwd: str | None,
    log_file: str | None,
    out_file: str | None = None,
    log_handler: Any = None,
) -> None:
    """Execute the command using subprocess."""
    try:
        if log_handler:
            result = subprocess.run(  # noqa: S603
                cmd,
                env=env,
                cwd=cwd,
                check=False,
                stdout=log_handler,
                stderr=subprocess.STDOUT,
            )
        elif log_file:
            with open(log_file, "a", encoding="utf-8") as lf:
                result = subprocess.run(  # noqa: S603
                    cmd,
                    env=env,
                    cwd=cwd,
                    check=False,
                    stdout=lf,
                    stderr=subprocess.STDOUT,
                )
        else:
            result = subprocess.run(cmd, env=env, cwd=cwd, check=False)  # noqa: S603

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


def run_wrap(argv: list[str]) -> None:
    """Cross-platform command execution wrapper for Ninja rules."""
    parser = _create_parser()
    args, unknown = parser.parse_known_args(argv, namespace=WrapArgs())

    cmd: list[str] = args.command or unknown
    # Remove -- separator if it's the first element of the command
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]

    if not cmd:
        sys.stderr.write("Error: No command provided to dojo wrap\n")
        sys.exit(1)

    ctx = PlaceholderContext(
        in_file=args.in_file,
        out_file=args.out_file,
        src_dir=args.src_dir,
        out_dir=args.out_dir,
        build_dir=args.build_dir,
        serve_dir=args.serve_dir,
    )

    def p(val: str | None) -> str | None:
        return resolve_placeholders(val, ctx) if val is not None else None

    log_handler = None
    if args.log_file:
        log_path = Path(p(args.log_file))
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handler = open(log_path, "a", encoding="utf-8")

    class LoggingQuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            msg = f"HTTP: {format % args}\n"
            if log_handler:
                log_handler.write(msg)
                log_handler.flush()
            else:
                sys.stderr.write(msg)

    server: socketserver.BaseServer | None = None
    if args.serve_dir:
        serve_path = p(args.serve_dir)
        # Port 0 lets the OS pick a random free port
        handler = functools.partial(LoggingQuietHandler, directory=serve_path)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        port = server.server_address[1]
        
        msg = f"DOJO SERVER: Starting at 127.0.0.1:{port} serving {serve_path}\n"
        if log_handler:
            log_handler.write(msg)
            log_handler.flush()
        else:
            sys.stderr.write(msg)

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        # Re-create context with the allocated port and RESOLVED serve_dir
        ctx = PlaceholderContext(
            in_file=args.in_file,
            out_file=args.out_file,
            src_dir=args.src_dir,
            out_dir=args.out_dir,
            build_dir=args.build_dir,
            serve_dir=serve_path,
            serve_port=port,
        )

    def p_final(val: str | None) -> str | None:
        return resolve_placeholders(val, ctx) if val is not None else None

    # Pre-flight
    if args.ensure_dir:
        ensure_dir = p(args.ensure_dir)
        if ensure_dir:
            Path(ensure_dir).mkdir(parents=True, exist_ok=True)

    cwd = p(args.cwd)
    final_cmd = [p(c) or c for c in cmd]

    if args.copy:
        if len(final_cmd) < MIN_COPY_ARGS:
            if log_handler:
                log_handler.write("Error: Copy requires source and destination\n")
            sys.stderr.write("Error: Copy requires source and destination\n")
            sys.exit(1)
        _handle_copy(final_cmd[0], final_cmd[1])

    env = _setup_env(args.path_env)
    try:
        _handle_exec(final_cmd, env, cwd, None, p(args.out_file), log_handler=log_handler)
    finally:
        if server:
            server.shutdown()
            server.server_close()
        if log_handler:
            log_handler.close()


if __name__ == "__main__":
    run_wrap(sys.argv[1:])
