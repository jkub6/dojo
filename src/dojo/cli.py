import argparse
import logging
import sys
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler

from .config import load_config
from .core import NinjaGenerator

console = Console()

logger = logging.getLogger("dojo")


def get_version() -> str:
    """Get the current version of dojo."""
    # In a real package, use importlib.metadata
    return "0.1.0"


def setup_cli_logging(verbose: bool, quiet: bool) -> None:
    """Set up logging configuration."""
    if quiet:
        level = logging.ERROR
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO

    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
        force=True,
    )


def cmd_build(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser | None = None,
    print_help_on_fail: bool = False,
) -> None:
    """Handle the build command."""
    try:
        config, config_path = load_config(args.config)
        if not args.quiet:
            console.print(f"[bold green]Using configuration:[/bold green] {config_path}")

        generator = NinjaGenerator(config, config_path, quiet=args.quiet)

        generator.generate()

        if not args.quiet:
            console.print("[bold green]✨ Build configuration generated successfully![/bold green]")

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


def cmd_check(args: argparse.Namespace) -> None:
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


def cmd_init(_args: argparse.Namespace) -> None:
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
default_type: markdown

tools:
  python: python3
  pandoc: pandoc

types:
  markdown:
    outputs:
      - extension: html
        defaults: defaults/html.yaml
"""
    with open(target, "w") as f:
        f.write(content)

    msg = f"Created sample configuration at {target}"
    console.print(f"[bold green]{msg}[/bold green]")


def cmd_version(_args: argparse.Namespace) -> None:
    """Handle the version command."""
    v = get_version()
    console.print(f"[bold]dojo[/bold] version [cyan]{v}[/cyan]")


def main(argv: list[str] | None = None) -> None:
    """CLI entry point for dojo."""
    parser = argparse.ArgumentParser(
        prog="dojo",
        description="Professional Ninja Build Generator (Dojo)",
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

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Build command
    # Build command
    build_parser = subparsers.add_parser("build", help="Generate Ninja build file (default)")
    build_parser.add_argument("-c", "--config", help="Path to configuration file")

    # Check command
    check_parser = subparsers.add_parser("check", help="Validate configuration")
    check_parser.add_argument("-c", "--config", help="Path to configuration file")

    # Init command
    # Init command
    subparsers.add_parser("init", help="Create a sample configuration")

    # Version command (as subcommand)
    subparsers.add_parser("version", help="Show version info")

    args = parser.parse_args(argv)

    setup_cli_logging(args.verbose, args.quiet)

    if args.version or args.command == "version":
        cmd_version(args)
        return

    # Default to help if no command specified
    if args.command is None:
        parser.print_help()
        sys.exit(0)
    elif args.command == "build":
        cmd_build(args, parser=parser)
    elif args.command == "check":
        cmd_check(args)
    elif args.command == "init":
        cmd_init(args)
    else:
        parser.print_help()
        sys.exit(1)


def entry_point() -> None:
    try:
        main()
    except KeyboardInterrupt:
        sys.stderr.write("\nInterrupted by user\n")
        sys.exit(130)


if __name__ == "__main__":
    entry_point()
