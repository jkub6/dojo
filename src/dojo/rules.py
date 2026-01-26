import sys
from pathlib import Path

from .config import Config, CustomRule
from .constants import PoolName, RuleName


def get_builtin_rules(config: Config, config_path: Path) -> list[CustomRule]:
    """
    Generate the standard built-in Ninja rules based on configuration.

    Args:
        config: The parsed configuration object
        config_path: Path to the configuration file (for regeneration rule)

    Returns:
        List of CustomRule objects defining the standard build rules
    """
    rules = []

    # REGENERATE Rule
    # We use sys.executable -m dojo to ensure we run the same package context
    cmd_parts = [
        sys.executable,
        "-m",
        "dojo",
        "build",  # Explicitly use build command
        "-c",
        config_path.as_posix(),
    ]

    rules.append(
        CustomRule(
            name=RuleName.REGENERATE.value,
            command=" ".join(cmd_parts),
            description="⚙️  REGENERATE build.ninja",
            generator=True,
        )
    )

    # COMPILE Rule (Markdown -> JSON AST)
    rules.append(
        CustomRule(
            name=RuleName.COMPILE.value,
            command=f"{config.tools.pandoc} $in -d $defaults -t json -o $out",
            description="🧠 COMPILE $in",
        )
    )

    # RENDER Rule (JSON AST -> Output Format)
    rules.append(
        CustomRule(
            name=RuleName.RENDER.value,
            command=f"{config.tools.pandoc} $in -d $defaults -o $out",
            description="🎨 RENDER $out",
        )
    )

    # MINIFY Rule
    rules.append(
        CustomRule(
            name=RuleName.MINIFY.value,
            command=f"{config.tools.minify} -o $out $in",
            description="⚡ MINIFY $out",
        )
    )

    # GHOSTSCRIPT Rule
    rules.append(
        CustomRule(
            name=RuleName.GHOSTSCRIPT.value,
            command=f"{config.tools.ghostscript} -sDEVICE=pdfwrite -dCompatibilityLevel=1.4 -dPDFSETTINGS=/ebook -dNOPAUSE -dQUIET -dBATCH -dSAFER -sOutputFile=$out $in",
            description="🗜️  COMPRESS $out",
            pool=PoolName.HEAVY_PROCESSING.value,
        )
    )

    # DECKTAPE Rule
    rules.append(
        CustomRule(
            name=RuleName.DECKTAPE.value,
            command=f"{config.tools.decktape} reveal $in $out",
            description="📸 DECKTAPE $out",
            pool=PoolName.HEAVY_PROCESSING.value,
        )
    )

    return rules
