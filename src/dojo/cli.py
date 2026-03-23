"""Command-line interface for the Dojo build generator.

This module defines the CLI entry points, argument parsing, and command
dispatching for build configuration, validation, and initialization.
"""

import argparse
import logging
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as get_pkg_version
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler

from .config import load_config
from .core import NinjaGenerator
from .logging import setup_logging as setup_json_logging
from .schema import print_schema, write_schema


console = Console()

logger = logging.getLogger("dojo")


class DojoArgs(argparse.Namespace):
    """Typed arguments for dojo CLI.

    All attributes have default values to ensure they are always present,
    even when the corresponding argument is not parsed (e.g., subcommand-specific args).
    """

    command: str | None = None
    config: str | None = None
    verbose: bool = False
    quiet: bool = False
    version: bool = False
    dry_run: bool = False
    json_output: bool = False
    output: str | None = None


def get_version() -> str:
    """Get the current version of dojo.

    Uses importlib.metadata to read version from package metadata,
    with fallback for development installs.
    """
    try:
        return get_pkg_version("dojo")
    except PackageNotFoundError:
        return "0.1.0-dev"


def setup_cli_logging(*, verbose: bool, quiet: bool, json_output: bool = False) -> None:
    """Set up logging configuration."""
    if quiet:
        level = logging.ERROR
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO

    # Use JSON formatter for machine-parseable output
    if json_output:
        setup_json_logging(level=level, json_output=True)
        return

    # Use Rich for human-readable output
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
        force=True,
    )


def cmd_build(
    args: DojoArgs,
    parser: argparse.ArgumentParser | None = None,
    *,
    print_help_on_fail: bool = False,
) -> None:
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

        if print_help_on_fail and parser:
            sys.stdout.write("\n")
            parser.print_help()

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

    # Create a simple default config
    content = """src_dir: content
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
    with open(target, "w") as f:
        f.write(content)

    msg = f"Created sample configuration at {target}"
    console.print(f"[bold green]{msg}[/bold green]")


def cmd_version(_args: DojoArgs) -> None:
    """Handle the version command."""
    v = get_version()
    console.print(f"[bold]dojo[/bold] version [cyan]{v}[/cyan]")


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

    # Check command
    check_parser = subparsers.add_parser("check", help="Validate configuration")
    check_parser.add_argument("-c", "--config", help="Path to configuration file")

    # Init command
    subparsers.add_parser("init", help="Create a sample configuration")

    # Schema command
    schema_parser = subparsers.add_parser("schema", help="Output JSON Schema for configuration")
    schema_parser.add_argument(
        "-o",
        "--output",
        help="Write schema to file instead of stdout",
    )

    # Version command (as subcommand)
    subparsers.add_parser("version", help="Show version info")

    args = parser.parse_args(argv, namespace=DojoArgs())

    try:
        setup_cli_logging(
            verbose=args.verbose,
            quiet=args.quiet,
            json_output=args.json_output,
        )

        if args.version or args.command == "version":
            cmd_version(args)
            return

        # Default to help if no command specified
        command = args.command
        if command is None:
            parser.print_help()
            sys.exit(0)
        elif command == "build":
            cmd_build(args, parser=parser)
        elif command == "check":
            cmd_check(args)
        elif command == "init":
            cmd_init(args)
        elif command == "schema":
            cmd_schema(args)
        else:
            parser.print_help()
            sys.exit(1)
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
