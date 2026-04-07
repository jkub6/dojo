"""Cross-platform command execution wrapper for Ninja rules.

This module provides a standalone wrapper for executing commands in a portable way,
supporting path placeholder resolution and environment manipulation.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

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
    log_file: str | None = None
    command: list[str] | None = None
    copy: bool = False


def resolve_placeholders(value: str, ctx: PlaceholderContext) -> str:
    """Replace `{placeholder}` variables based on resolved paths."""
    v = value

    in_abs = Path(ctx.in_file).resolve() if ctx.in_file else None
    out_abs = Path(ctx.out_file).resolve() if ctx.out_file else None

    in_abs_dir = in_abs.parent if in_abs else None
    out_abs_dir = out_abs.parent if out_abs else None

    if "{in_abs}" in v and in_abs:
        v = v.replace("{in_abs}", in_abs.as_posix())
    if "{in_abs_dir}" in v and in_abs_dir:
        v = v.replace("{in_abs_dir}", in_abs_dir.as_posix())
    if "{out_abs}" in v and out_abs:
        v = v.replace("{out_abs}", out_abs.as_posix())
    if "{out_abs_dir}" in v and out_abs_dir:
        v = v.replace("{out_abs_dir}", out_abs_dir.as_posix())

    if "{root_val}" in v and ctx.out_dir and out_abs_dir:
        root_val = os.path.relpath(Path(ctx.out_dir).resolve(), out_abs_dir).replace("\\", "/")
        v = v.replace("{root_val}", root_val)

    if "{rel_src_dir}" in v and ctx.build_dir and in_abs_dir:
        rel_src_dir = os.path.relpath(in_abs_dir, Path(ctx.build_dir).resolve()).replace("\\", "/")
        v = v.replace("{rel_src_dir}", rel_src_dir)

    if "{src_dir_val}" in v and ctx.build_dir and ctx.src_dir and in_abs_dir:
        rel_src_dir = os.path.relpath(in_abs_dir, Path(ctx.build_dir).resolve()).replace("\\", "/")
        src_dir_val = (Path(ctx.src_dir).resolve() / rel_src_dir).resolve().as_posix()
        v = v.replace("{src_dir_val}", src_dir_val)

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
        # Convert colon-separated to OS specific (e.g. semicolon on Windows)
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
) -> None:
    """Execute the command using subprocess."""
    try:
        if log_file:
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
        sys.exit(result.returncode)
    except (OSError, subprocess.SubprocessError) as e:
        sys.stderr.write(f"dojo wrap error executing {cmd[0]}: {e}\n")
        sys.exit(1)


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

    ctx = PlaceholderContext(
        in_file=args.in_file,
        out_file=args.out_file,
        src_dir=args.src_dir,
        out_dir=args.out_dir,
        build_dir=args.build_dir,
    )

    def p(val: str | None) -> str | None:
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
            sys.stderr.write("Error: Copy requires source and destination\n")
            sys.exit(1)
        _handle_copy(final_cmd[0], final_cmd[1])

    env = _setup_env(args.path_env)
    _handle_exec(final_cmd, env, cwd, p(args.log_file))


if __name__ == "__main__":
    run_wrap(sys.argv[1:])
