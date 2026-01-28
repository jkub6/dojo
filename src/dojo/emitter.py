from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from .utils import ninja_escape


class NinjaEmitter:
    """
    Handles the low-level emission of Ninja build file syntax.
    """

    def __init__(self, fp: TextIO):
        self.fp = fp

    def comment(self, text: str) -> None:
        """Write a comment."""
        self.fp.write(f"# {text}\n")

    def newline(self) -> None:
        """Write a newline."""
        self.fp.write("\n")

    def variable(self, name: str, value: str, indent: int = 0) -> None:
        """Write a variable assignment."""
        padding = "  " * indent
        self.fp.write(f"{padding}{name} = {value}\n")

    def rule(
        self,
        name: str,
        command: str,
        description: str | None = None,
        pool: str | None = None,
        depfile: str | None = None,
        deps: str | None = None,
        generator: bool = False,
        variables: dict[str, str] | None = None,
    ) -> None:
        """Write a rule definition."""
        self.fp.write(f"rule {name}\n")
        self.variable("command", command, indent=1)
        if description:
            self.variable("description", description, indent=1)
        if pool:
            self.variable("pool", pool, indent=1)
        if depfile:
            self.variable("depfile", depfile, indent=1)
        if deps:
            self.variable("deps", deps, indent=1)
        if generator:
            self.variable("generator", "1", indent=1)
        if variables:
            for key, value in variables.items():
                self.variable(key, value, indent=1)
        self.newline()

    def build(
        self,
        outputs: Path | list[Path],
        rule: str,
        inputs: Path | list[Path] | None = None,
        implicit: Path | list[Path] | None = None,
        order_only: Path | list[Path] | None = None,
        variables: dict[str, str] | None = None,
    ) -> None:
        """Write a build edge."""

        def to_list(x: Path | list[Path] | str | None) -> Sequence[Path | str]:
            if x is None:
                return []
            return [x] if isinstance(x, (str, Path)) else x

        out_str = " ".join(ninja_escape(p) for p in to_list(outputs))
        in_str = " ".join(ninja_escape(p) for p in to_list(inputs))

        line = f"build {out_str}: {rule}"
        if in_str:
            line += f" {in_str}"

        impl_list = to_list(implicit)
        if impl_list:
            line += " | " + " ".join(ninja_escape(p) for p in impl_list)

        oo_list = to_list(order_only)
        if oo_list:
            line += " || " + " ".join(ninja_escape(p) for p in oo_list)

        self.fp.write(f"{line}\n")

        if variables:
            for name, value in variables.items():
                self.variable(name, value, indent=1)
