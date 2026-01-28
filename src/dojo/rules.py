import sys
from pathlib import Path

from .config import Config, CustomRule
from .constants import PoolName, RuleName


def get_builtin_rules(config: Config, config_path: Path) -> list[CustomRule]:
    """Generate the standard built-in Ninja rules based on configuration.

    Args:
        config: The parsed configuration object
        config_path: Path to the configuration file (for regeneration rule)

    Returns:
        List of CustomRule objects defining the standard build rules

    """
    # Create a PATH environment variable string that includes all resolved tool directories
    # This ensures that tools invoked by other tools (e.g. pandoc calling typst) work correctly
    # even if they aren't in the global PATH but were resolved during config loading
    tool_dirs = set()
    for tool_path in config.tools.model_dump().values():
        if tool_path and Path(tool_path).exists():
            tool_dirs.add(str(Path(tool_path).parent))
    
    path_prefix = ""
    if tool_dirs:
        # Sort for determinism
        path_env = ":".join(sorted(tool_dirs))
        path_prefix = f"env PATH={path_env}:$PATH "

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
    # We attach the dependencies.lua filter at the end to track all assets
    resources_dir = Path(__file__).parent / "resources"
    dep_filter = resources_dir / "dependencies.lua"

    # Note: We use $in_shell and $out_shell which are safe to use in the shell command
    # The normal $in and $out are reserved for Ninja containment/dependency tracking
    compile_cmd = (
        f"{path_prefix}{config.tools.pandoc} $in_shell $defaults -t json -o $out_shell "
        f"-M depfile=$out_shell.d -M target=$out_shell "
        f"--lua-filter {dep_filter}"
    )

    rules.append(
        CustomRule(
            name=RuleName.COMPILE.value,
            command=compile_cmd,
            description="🧠 COMPILE $in",
            depfile="$out.d",
            deps="gcc",
        )
    )

    # RENDER Rule (JSON AST -> Output Format)
    rules.append(
        CustomRule(
            name=RuleName.RENDER.value,
            command=f"{path_prefix}{config.tools.pandoc} $in_shell $defaults -o $out_shell",
            description="🎨 RENDER $out",
        )
    )

    # MINIFY Rule
    rules.append(
        CustomRule(
            name=RuleName.MINIFY.value,
            command=f"{path_prefix}{config.tools.minify} $args -o $out_shell $in_shell",
            description="⚡ MINIFY $out",
        )
    )

    # GHOSTSCRIPT Rule
    rules.append(
        CustomRule(
            name=RuleName.GHOSTSCRIPT.value,
            command=f"{path_prefix}{config.tools.ghostscript} -sDEVICE=pdfwrite -dCompatibilityLevel=1.4 -dPDFSETTINGS=/ebook -dNOPAUSE -dQUIET -dBATCH -dSAFER $args -sOutputFile=$out_shell $in_shell",
            description="🗜️  COMPRESS $out",
            pool=PoolName.HEAVY_PROCESSING.value,
        )
    )

    # DECKTAPE Rule
    rules.append(
        CustomRule(
            name=RuleName.DECKTAPE.value,
            command=f"{path_prefix}{config.tools.decktape} reveal $args $in_shell $out_shell",
            description="📸 DECKTAPE $out",
            pool=PoolName.HEAVY_PROCESSING.value,
        )
    )

    return rules
