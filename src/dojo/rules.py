import sys
from pathlib import Path

from .config import Config, CustomRule
from .constants import PoolName, RuleName
from .utils import shell_quote


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

    # Pandoc Command Construction Helpers
    # We resolve inputs/outputs to absolute paths to support changing working directory
    # root_val: The path of the root reference directory relative to the input file input directory
    # Note: We use $$ for shell variables/substitution because Ninja uses $ for its own variables
    setup_vars = (
        "in_abs=$$(realpath $in_shell) && "
        "out_abs=$$(realpath -m $out_shell) && "
        f"root_val=$$(realpath -m --relative-to=$$(dirname $in_shell) {shell_quote(config.root_ref_dir)})"
    )

    cd_cmd = f" && cd {shell_quote(config.pandoc_working_dir)}" if config.pandoc_working_dir else ""

    common_flags = "-V root=$$root_val"
    if config.add_resource_path:
        common_flags += " --resource-path=.:$$(dirname $$in_abs)"

    # COMPILE Rule (Markdown -> JSON AST)
    # We attach the dependencies.lua filter at the end to track all assets
    resources_dir = Path(__file__).parent / "resources"
    dep_filter = resources_dir / "dependencies.lua"

    # Note: We use $in_abs and $out_abs which are established in the setup_vars
    compile_cmd = (
        f"{setup_vars}{cd_cmd} && "
        f"{path_prefix}{config.tools.pandoc} $$in_abs $defaults -t json -o $$out_abs "
        f"-M depfile=$$out_abs.d -M target=$$out_abs "
        f"{common_flags} "
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
    render_cmd = (
        f"{setup_vars}{cd_cmd} && "
        f"{path_prefix}{config.tools.pandoc} $$in_abs $defaults -o $$out_abs "
        f"{common_flags}"
    )

    rules.append(
        CustomRule(
            name=RuleName.RENDER.value,
            command=render_cmd,
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
