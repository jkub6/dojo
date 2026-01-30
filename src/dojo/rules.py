import sys
from pathlib import Path
from typing import cast

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
    # Cast to dict[str, str] to avoid Any in values()
    tools_dict = cast("dict[str, str]", config.tools.model_dump())
    for tool_path_raw in tools_dict.values():
        tool_path = str(tool_path_raw)
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
        ),
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

    # Resolve build directory to absolute path
    abs_build_dir = Path(config.build_dir).resolve().as_posix()
    # Command prefix to run inside build directory
    # We use mkdir -p to ensure it exists (though NinjaGenerator also creates it)
    build_dir_cmd = f"mkdir -p {shell_quote(abs_build_dir)} && cd {shell_quote(abs_build_dir)}"

    # Combine with path prefix
    # path_prefix already ends with a space if not empty
    # We prepend data_dir_env to the pandoc command execution
    pandoc_wrapper = f"{path_prefix}{config.tools.pandoc}"

    base_flags = "-V root=$$root_val"
    if config.pandoc_data_dir:
        # We assume the path is already resolved by the config validator
        base_flags += f" --data-dir={shell_quote(config.pandoc_data_dir)}"

    # COMPILE Rule (Markdown -> JSON AST)
    # We attach the dependencies.lua filter at the end to track all assets
    resources_dir = Path(__file__).parent / "resources"
    dep_filter = resources_dir / "dependencies.lua"

    # Compile Flags: Input is source file, so dirname is source dir
    compile_flags = base_flags
    if config.add_resource_path:
        compile_rp = ".:$$(dirname $$in_abs)"
        compile_flags += f" --resource-path={compile_rp}"

    # Note: We use $in_abs and $out_abs which are established in the setup_vars
    # We change directory to build_dir BEFORE executing pandoc
    compile_cmd = (
        f"{setup_vars} && {build_dir_cmd} && "
        f"{pandoc_wrapper} $$in_abs $defaults -t json -o $$out_abs "
        f"-M depfile=$$out_abs.d -M target=$$out_abs "
        f"{compile_flags} "
        f"--lua-filter {dep_filter}"
    )

    rules.append(
        CustomRule(
            name=RuleName.COMPILE.value,
            command=compile_cmd,
            description="🧠 COMPILE $in",
            depfile="$out.d",
            deps="gcc",
        ),
    )

    # RENDER Rule (JSON AST -> Output Format)
    # Render Flags: Input is build file (JSON), need to map back to source dir
    render_flags = base_flags
    if config.add_resource_path:
        render_rp = "."
        abs_src = Path(config.src_dir).resolve().as_posix()
        abs_build = Path(config.build_dir).resolve().as_posix()
        # Calculate source path relative to build path mapping
        src_dir_val = f"$$(realpath -m {shell_quote(abs_src)}/$$(realpath -m --relative-to={shell_quote(abs_build)} $$(dirname $$in_abs)))"
        render_rp += f":$$(dirname $$in_abs):{src_dir_val}"
        render_flags += f" --resource-path={render_rp}"

    render_cmd = f"{setup_vars} && {build_dir_cmd} && {pandoc_wrapper} $$in_abs $defaults -o $$out_abs {render_flags}"

    rules.append(
        CustomRule(
            name=RuleName.RENDER.value,
            command=render_cmd,
            description="🎨 RENDER $out",
        ),
    )

    # MINIFY Rule
    rules.append(
        CustomRule(
            name=RuleName.MINIFY.value,
            command=f"{path_prefix}{config.tools.minify} $args -o $out_shell $in_shell",
            description="⚡ MINIFY $out",
        ),
    )

    # GHOSTSCRIPT Rule
    rules.append(
        CustomRule(
            name=RuleName.GHOSTSCRIPT.value,
            command=f"{path_prefix}{config.tools.ghostscript} -sDEVICE=pdfwrite -dCompatibilityLevel=1.4 -dPDFSETTINGS=/ebook -dNOPAUSE -dQUIET -dBATCH -dSAFER $args -sOutputFile=$out_shell $in_shell",
            description="🗜️  COMPRESS $out",
            pool=PoolName.HEAVY_PROCESSING.value,
        ),
    )

    # DECKTAPE Rule
    rules.append(
        CustomRule(
            name=RuleName.DECKTAPE.value,
            command=f"{path_prefix}{config.tools.decktape} reveal $args $in_shell $out_shell",
            description="📸 DECKTAPE $out",
            pool=PoolName.HEAVY_PROCESSING.value,
        ),
    )

    return rules
