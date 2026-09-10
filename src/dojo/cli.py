"""Command-line interface for the Dojo build generator.

This module defines the CLI entry points, argument parsing, and command
dispatching for build configuration, validation, and initialization.
"""

import argparse
import logging
import sys
from collections.abc import Callable
from pathlib import Path

from rich.console import Console

from . import __version__
from .config import load_config
from .core import NinjaGenerator
from .log_config import setup_logging
from .schema import print_schema, write_schema

console = Console()

logger = logging.getLogger("dojo")


class DojoArgs(argparse.Namespace):
    """Typed arguments for dojo CLI.

    All attributes have default values to ensure they are always present,
    even when the corresponding argument is not parsed (e.g., subcommand-specific args).
    """

    command: str | None = None
    func: Callable[["DojoArgs"], None] | None = None
    config: str | None = None
    verbose: bool = False
    quiet: bool = False
    version: bool = False
    dry_run: bool = False
    json_output: bool = False
    output: str | None = None


def setup_cli_logging(*, verbose: bool, quiet: bool, json_output: bool = False) -> None:
    """Set up logging configuration."""
    if quiet:
        level = logging.ERROR
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO

    # Setup logging scoped to 'dojo'
    setup_logging(level=level, json_output=json_output)


def cmd_build(args: DojoArgs) -> None:
    """Handle the build command."""
    try:
        config, config_path = load_config(args.config)

        if not args.quiet:
            console.print(f"[bold green]Using configuration:[/bold green] {config_path}")

        generator = NinjaGenerator(config, config_path, quiet=args.quiet, dry_run=args.dry_run)

        generator.generate()

        if not args.quiet:
            if args.dry_run:
                console.print("[bold cyan]🔍 Dry-run complete. No files written.[/bold cyan]")
            else:
                console.print(
                    "[bold green]✨ Build configuration generated successfully![/bold green]"
                )

    except FileNotFoundError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        console.print("[yellow]Tip:[/yellow] Run 'dojo init' to create a configuration file.")
        sys.exit(1)

    except Exception as e:
        if args.verbose:
            logger.exception("Unexpected error during build")
        else:
            console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)


def cmd_check(args: DojoArgs) -> None:
    """Handle the check command."""
    try:
        config, config_path = load_config(args.config)
        console.print(f"[bold green]✓ Configuration valid:[/bold green] {config_path}")
        console.print(f"  Src: {config.src_dir}")
        console.print(f"  Dst: {config.output_dir}")
        console.print(f"  Types: {', '.join(config.types.keys())}")
    except Exception as e:
        if args.verbose:
            logger.exception("Unexpected error during configuration check")
        else:
            console.print(f"[bold red]Configuration invalid:[/bold red] {e}")
        sys.exit(1)


def cmd_init(_args: DojoArgs) -> None:
    """Handle the init command."""
    target = Path("dojo.yaml")
    if target.exists():
        msg = f"Configuration file {target} already exists."
        console.print(f"[bold red]{msg}[/bold red]")
        sys.exit(1)

    # Create a working starter project
    config_content = """\
src_dir: content
output_dir: _site
build_dir: _build
default_type: page

tools:
  python: python3
  pandoc: pandoc
  # minify: minify # Optional: install 'minify' tool

# pools:
#   heavy: 2 # Limit concurrent heavy tasks

# rule_pools:
#   decktape: heavy # Assign decktape rule to the heavy pool

types:
  page:
    outputs:
      - extension: html
        defaults: defaults/html.yaml
        # Example of a multi-step post-processing pipeline
        # post_process:
        #   - tool: minify
        #   - tool: custom_tool
        #     args: ["--param", "value"]
"""

    defaults_content = """\
# Pandoc defaults for HTML output
# See: https://pandoc.org/MANUAL.html#defaults-files
writer: html5
standalone: true
metadata:
  lang: en
"""

    index_content = """\
---
title: Home
---

# Welcome to Dojo

Your site is ready. Edit this file or add more Markdown files to `content/`.
"""

    # Write configuration
    target.write_text(config_content, encoding="utf-8")

    # Create content directory with sample page
    content_dir = Path("content")
    content_dir.mkdir(exist_ok=True)
    index_path = content_dir / "index.md"
    if not index_path.exists():
        index_path.write_text(index_content, encoding="utf-8")

    # Create defaults directory with Pandoc defaults
    defaults_dir = Path("defaults")
    defaults_dir.mkdir(exist_ok=True)
    defaults_path = defaults_dir / "html.yaml"
    if not defaults_path.exists():
        defaults_path.write_text(defaults_content, encoding="utf-8")

    console.print("[bold green]✨ Created starter project:[/bold green]")
    console.print(f"  {target}")
    console.print(f"  {index_path}")
    console.print(f"  {defaults_path}")
    console.print("\n[yellow]Next steps:[/yellow] Run 'dojo build' then 'ninja -C _build'")


def cmd_version(_args: DojoArgs) -> None:
    """Handle the version command."""
    console.print(f"[bold]dojo[/bold] version [cyan]{__version__}[/cyan]")


def cmd_schema(args: DojoArgs) -> None:
    """Handle the schema command."""
    if args.output:
        output_path = Path(args.output)
        write_schema(output_path)
        console.print(f"[bold green]✓ Schema written to:[/bold green] {output_path}")
    else:
        print_schema()


def main(argv: list[str] | None = None) -> None:
    """CLI entry point for dojo."""
    parser = argparse.ArgumentParser(
        prog="dojo",
        description="Ninja Build Generator (Dojo)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Global arguments
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress all output except errors",
    )
    parser.add_argument("--version", action="store_true", help="Show version info and exit")
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output logs as JSON for CI/tooling integration",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Build command
    build_parser = subparsers.add_parser("build", help="Generate Ninja build file (default)")
    build_parser.add_argument("-c", "--config", help="Path to configuration file")
    build_parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Show what would be built without generating files",
    )
    build_parser.set_defaults(func=cmd_build)

    # Check command
    check_parser = subparsers.add_parser("check", help="Validate configuration")
    check_parser.add_argument("-c", "--config", help="Path to configuration file")
    check_parser.set_defaults(func=cmd_check)

    # Init command
    init_parser = subparsers.add_parser("init", help="Create a sample configuration")
    init_parser.set_defaults(func=cmd_init)

    # Schema command
    schema_parser = subparsers.add_parser("schema", help="Output JSON Schema for configuration")
    schema_parser.add_argument(
        "-o",
        "--output",
        help="Write schema to file instead of stdout",
    )
    schema_parser.set_defaults(func=cmd_schema)

    # Version command (as subcommand)
    version_parser = subparsers.add_parser("version", help="Show version info")
    version_parser.set_defaults(func=cmd_version)

    args = parser.parse_args(argv, namespace=DojoArgs())

    try:
        setup_cli_logging(
            verbose=args.verbose,
            quiet=args.quiet,
            json_output=args.json_output,
        )

        if args.version:
            cmd_version(args)
            return

        if args.func is not None:
            args.func(args)
        else:
            parser.print_help()
            sys.exit(0)

    except Exception as e:
        if args.verbose:
            logger.exception("Unexpected error")
        else:
            console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)


def entry_point() -> None:
    """Provide the main binary entry point for the dojo command.

    This function wraps main() with a global exception handler for
    KeyboardInterrupt to provide clean exit behavior.
    """
    try:
        main()
    except KeyboardInterrupt:
        sys.stderr.write("\nInterrupted by user\n")
        sys.exit(130)


if __name__ == "__main__":
    entry_point()
