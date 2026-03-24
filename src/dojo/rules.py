"""Built-in Ninja build rule definitions.

Defines the standard set of rules for compilation, rendering,
asset processing, and tool invocation provided by default.
"""

from pathlib import Path
from typing import cast

from .config import Config, CustomRule
from .constants import RuleName
from .paths import shell_quote


def _get_tool_path_prefix(config: Config) -> str:
    """Generate the 'env PATH=...' prefix for shell commands.

    This ensures that tools resolved during configuration loading are available
    to subprocesses even if they are not in the system's global PATH.
    """
    tool_dirs = []
    tools_dict = cast("dict[str, str]", config.tools.model_dump())
    for tool_path_raw in tools_dict.values():
        tool_path = str(tool_path_raw)
        if tool_path and Path(tool_path).exists():
            parent_dir = str(Path(tool_path).parent)
            if parent_dir not in tool_dirs:
                tool_dirs.append(parent_dir)

    if not tool_dirs:
        return ""

    # Sort keys for determinism
    env_vars = {"PATH": f"{':'.join(tool_dirs)}:$$PATH"}
    env_parts = [f'{k}="{v}"' for k, v in sorted(env_vars.items())]
    return f"env {' '.join(env_parts)} "


def _get_pandoc_setup_vars(config: Config) -> str:
    """Generate shell variables used in pandoc commands.

    This setup script establishes absolute paths for inputs and outputs and
    calculates the relative path to the root reference directory to handle
    working directory shifts in the build process.
    """
    return (
        "in_abs=$$(realpath $in_shell) && "
        "out_abs=$$(realpath -m $out_shell) && "
        f"root_val=$$(realpath -m --relative-to=$$(dirname $in_shell) {shell_quote(config.root_ref_dir)})"
    )


def _get_typst_flags(config: Config, rel_src_dir_expr: str) -> list[str]:
    """Generate Typst-specific Pandoc flags.

    These flags address various compatibility issues with Pandoc's Typst writer,
    including CSL resolution, font discovery, and root directory mapping.
    """
    flags = [f"-M dojo-rel-src-dir={rel_src_dir_expr}"]
    abs_src = Path(config.src_dir).resolve()

    if config.pandoc_data_dir:
        abs_data = Path(config.pandoc_data_dir).resolve()
        try:
            rel_data = abs_data.relative_to(abs_src).as_posix()
        except ValueError:
            rel_data = abs_data.as_posix()
        flags.append(f"-M dojo-data-dir={shell_quote(rel_data)}")

    flags.append(f"--pdf-engine-opt=--root={shell_quote(abs_src.as_posix())}")

    if config.pandoc_data_dir:
        font_path = (Path(config.pandoc_data_dir).resolve() / "fonts").as_posix()
        flags.append(f"--pdf-engine-opt=--font-path={shell_quote(font_path)}")

    resources_dir = Path(__file__).parent / "resources"
    typst_csl_filter = resources_dir / "fix_typst_csl.lua"
    flags.append(f"--lua-filter {shell_quote(typst_csl_filter.as_posix())}")

    return flags


def get_builtin_rules(config: Config, config_path: Path) -> list[CustomRule]:
    """Generate the standard built-in Ninja rules based on configuration.

    Dojo Rules Convention:
    - Rules should use `$in_shell` and `$out_shell` for path safety.
    - `$args` is used for caller-provided tool flags.
    - `$defaults` is used for Pandoc defaults files.
    """
    path_prefix = _get_tool_path_prefix(config)
    setup_vars = _get_pandoc_setup_vars(config)
    abs_build_dir = Path(config.build_dir).resolve().as_posix()
    build_dir_cmd = f"mkdir -p {shell_quote(abs_build_dir)} && cd {shell_quote(abs_build_dir)}"
    pandoc_wrapper = f"{path_prefix}{config.tools.pandoc}"

    base_flags = "-V root=$$root_val"
    if config.pandoc_data_dir:
        base_flags += f" --data-dir={shell_quote(config.pandoc_data_dir)}"

    def get_pool(rule_name: str) -> str | None:
        return config.rule_pools.get(rule_name)

    rules = []

    # REGENERATE
    rules.append(
        CustomRule(
            name=RuleName.REGENERATE.value,
            command=f"{path_prefix}dojo build -c {config_path.as_posix()}",
            description="⚙️  REGENERATE build.ninja",
            generator=True,
        )
    )

    # COMPILE
    resources_dir = Path(__file__).parent / "resources"
    dep_filter = resources_dir / "dependencies.lua"
    compile_flags = base_flags
    if config.add_resource_path:
        compile_flags += " --resource-path=.:$$(dirname $$in_abs)"

    rules.append(
        CustomRule(
            name=RuleName.COMPILE.value,
            command=(
                f"{setup_vars} && {build_dir_cmd} && "
                f"{pandoc_wrapper} $$in_abs $defaults -t json -o $$out_abs "
                f"-M depfile=$$out_abs.d -M target=$$out_abs {compile_flags} "
                f"--lua-filter {dep_filter}"
            ),
            description="🧠 COMPILE $in",
            depfile="$out.d",
            deps="gcc",
            pool=get_pool(RuleName.COMPILE.value),
        )
    )

    # RENDER
    render_flags = [base_flags]
    abs_src = Path(config.src_dir).resolve().as_posix()
    abs_build = Path(config.build_dir).resolve().as_posix()
    rel_src_dir_expr = (
        f"$$(realpath -m --relative-to={shell_quote(abs_build)} $$(dirname $$in_abs))"
    )
    src_dir_val = f"$$(realpath -m {shell_quote(abs_src)}/{rel_src_dir_expr})"

    render_flags.extend(_get_typst_flags(config, rel_src_dir_expr))

    if config.add_resource_path:
        render_flags.append(f"--resource-path=.:$$(dirname $$in_abs):{src_dir_val}")

    rules.append(
        CustomRule(
            name=RuleName.RENDER.value,
            command=(
                f"{setup_vars} && {build_dir_cmd} && "
                f"{pandoc_wrapper} $$in_abs $defaults -o $$out_abs {' '.join(render_flags)}"
            ),
            description="🎨 RENDER $out",
            pool=get_pool(RuleName.RENDER.value),
        )
    )

    # Standard Tools
    rules.extend(
        [
            CustomRule(
                name=RuleName.COPY.value,
                command="cp $in_shell $out_shell",
                description="📂 COPY $out",
                pool=get_pool(RuleName.COPY.value),
            ),
            CustomRule(
                name=RuleName.MINIFY.value,
                command=f"{path_prefix}{config.tools.minify} $args -o $out_shell $in_shell",
                description="⚡ MINIFY $out",
                pool=get_pool(RuleName.MINIFY.value),
            ),
            CustomRule(
                name=RuleName.GHOSTSCRIPT.value,
                command=(
                    f"{path_prefix}{config.tools.ghostscript} -sDEVICE=pdfwrite "
                    "-dCompatibilityLevel=1.4 -dPDFSETTINGS=/ebook -dNOPAUSE -dQUIET "
                    "-dBATCH -dSAFER $args -sOutputFile=$out_shell $in_shell"
                ),
                description="🗜️  COMPRESS $out",
                pool=get_pool(RuleName.GHOSTSCRIPT.value),
            ),
            CustomRule(
                name=RuleName.DECKTAPE.value,
                command=f"{path_prefix}{config.tools.decktape} reveal $args $in_shell $out_shell",
                description="📸 DECKTAPE $out",
                pool=get_pool(RuleName.DECKTAPE.value),
            ),
        ]
    )

    return rules
