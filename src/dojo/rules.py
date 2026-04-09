"""Built-in Ninja build rule definitions.

Defines the standard set of rules for compilation, rendering,
asset processing, and tool invocation provided by default.
"""

import sys
from pathlib import Path
from typing import cast

from .config import Config, CustomRule
from .constants import RuleName
from .paths import shell_quote


def _get_tool_path_prefix(config: Config) -> str:
    """Generate the '--path-env' argument for dojo wrap.

    This ensures that tools resolved during configuration loading are available
    to subprocesses.
    """
    tool_dirs = []
    tools_dict = cast("dict[str, str]", config.tools.model_dump())
    for tool_path_raw in tools_dict.values():
        tool_path = str(tool_path_raw)
        if tool_path and Path(tool_path).exists():
            parent_dir = str(Path(tool_path).parent.resolve())
            if parent_dir not in tool_dirs:
                tool_dirs.append(parent_dir)

    if not tool_dirs:
        return ""

    return f"--path-env {shell_quote(':'.join(tool_dirs))} "


def _get_typst_flags(config: Config) -> list[str]:
    """Generate Typst-specific Pandoc flags."""
    flags = ["-M dojo-rel-src-dir={rel_src_dir}"]
    abs_src = Path(config.src_dir).resolve().as_posix()

    if config.pandoc_data_dir:
        abs_data = Path(config.pandoc_data_dir).resolve().as_posix()
        flags.append(f"-M dojo-data-dir={shell_quote(abs_data)}")

    flags.append(f"--pdf-engine-opt=--root={shell_quote(abs_src)}")

    if config.font_paths:
        for font_dir in config.font_paths:
            font_path = Path(font_dir).resolve().as_posix()
            flags.append(f"--pdf-engine-opt=--font-path={shell_quote(font_path)}")
    elif config.pandoc_data_dir:
        font_path = (Path(config.pandoc_data_dir).resolve() / "fonts").as_posix()
        if Path(font_path).exists():
            flags.append(f"--pdf-engine-opt=--font-path={shell_quote(font_path)}")

    resources_dir = Path(__file__).parent.resolve() / "resources"
    typst_csl_filter = resources_dir / "fix_typst_csl.lua"
    flags.append(f"--lua-filter {shell_quote(typst_csl_filter.as_posix())}")

    return flags


def get_builtin_rules(config: Config, config_path: Path) -> list[CustomRule]:
    """Generate the standard built-in Ninja rules based on configuration."""
    path_prefix = _get_tool_path_prefix(config)
    abs_build_dir = Path(config.build_dir).resolve().as_posix()
    abs_src = Path(config.src_dir).resolve().as_posix()
    abs_out = Path(config.output_dir).resolve().as_posix()

    # Path to the standalone wrap.py script
    wrap_script = (Path(__file__).parent.resolve() / "wrap.py").as_posix()

    # We use the absolute path to wrap.py to avoid dependency on PYTHONPATH or dojo module
    dojo_wrap_base = (
        f"{shell_quote(sys.executable)} {shell_quote(wrap_script)} {path_prefix}"
        f"--in-file $in_shell --out-file $out_shell "
        f"--src-dir {shell_quote(abs_src)} "
        f"--out-dir {shell_quote(abs_out)} "
        f"--build-dir {shell_quote(abs_build_dir)} "
    )

    pandoc_wrapper = shell_quote(config.tools.pandoc)

    # REGENERATE rule uses the full dojo CLI
    dojo_src = Path(__file__).parent.parent.resolve().as_posix()
    python_env = f"PYTHONPATH={shell_quote(dojo_src)}"
    regen_cmd = (
        f"{python_env} {shell_quote(sys.executable)} -m dojo build -c {config_path.as_posix()}"
    )

    base_flags = "-V root={root_val} -M root={root_val}"
    if config.pandoc_data_dir:
        base_flags += f" --data-dir={shell_quote(config.pandoc_data_dir)}"

    def get_pool(rule_name: str) -> str | None:
        return config.rule_pools.get(rule_name)

    rules = []

    # REGENERATE
    rules.append(
        CustomRule(
            name=RuleName.REGENERATE.value,
            command=regen_cmd,
            description="⚙️  REGENERATE build.ninja",
            generator=True,
        )
    )

    # COMPILE
    resources_dir = Path(__file__).parent.resolve() / "resources"
    dep_filter = resources_dir / "dependencies.lua"
    compile_flags = base_flags
    if config.add_resource_path:
        compile_flags += " --resource-path=.:{in_abs_dir}"

    rules.append(
        CustomRule(
            name=RuleName.COMPILE.value,
            command=(
                f"{dojo_wrap_base} --ensure-dir {shell_quote(abs_build_dir)} --cwd {shell_quote(abs_build_dir)} -- "
                f"{pandoc_wrapper} {{in_abs}} $defaults -t json -o {{out_abs}} "
                f"-M depfile={{out_abs}}.d -M target={{out_abs}} {compile_flags} "
                f"--lua-filter {shell_quote(dep_filter.as_posix())}"
            ),
            description="🧠 COMPILE $in",
            depfile="$out.d",
            deps="gcc",
            pool=get_pool(RuleName.COMPILE.value),
        )
    )

    # RENDER
    render_flags = [base_flags]
    render_flags.extend(_get_typst_flags(config))

    if config.add_resource_path:
        render_flags.append("--resource-path=.:{in_abs_dir}:{src_dir_val}")

    # Media Extraction for generated diagrams (diagram.lua)
    render_flags.append("--extract-media=media")

    rules.append(
        CustomRule(
            name=RuleName.RENDER.value,
            command=(
                f"{dojo_wrap_base} --ensure-dir {{out_abs_dir}} --cwd {{out_abs_dir}} -- "
                f"{pandoc_wrapper} {{in_abs}} $defaults -o {{out_abs}} {' '.join(render_flags)} "
                "-M dojo-document-stem=$dojo_stem"
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
                command=(
                    f"{dojo_wrap_base} --ensure-dir {{out_abs_dir}} --copy -- "
                    "{in_abs} {out_abs}"
                ),
                description="📂 COPY $out",
                pool=get_pool(RuleName.COPY.value),
            ),
            CustomRule(
                name=RuleName.MINIFY.value,
                command=(
                    f"{dojo_wrap_base} --ensure-dir {{out_abs_dir}} -- "
                    f"{shell_quote(config.tools.minify)} "
                    "--html-keep-document-tags --html-keep-end-tags -q "
                    "$args -o {out_abs} {in_abs}"
                ),
                description="⚡ MINIFY $out",
                pool=get_pool(RuleName.MINIFY.value),
            ),
            CustomRule(
                name=RuleName.GHOSTSCRIPT.value,
                command=(
                    f"{dojo_wrap_base} --ensure-dir {{out_abs_dir}} -- "
                    f"{shell_quote(config.tools.ghostscript)} -sDEVICE=pdfwrite "
                    "-dCompatibilityLevel=1.4 -dPDFSETTINGS=/ebook -dNOPAUSE -dQUIET "
                    "-dBATCH -dSAFER $args -sOutputFile={out_abs} {in_abs}"
                ),
                description="🗜️  COMPRESS $out",
                pool=get_pool(RuleName.GHOSTSCRIPT.value),
            ),
        ]
    )

    decktape_cmd = f"{dojo_wrap_base} --ensure-dir {{out_abs_dir}} "
    if config.log_file:
        log_path = Path(config.log_file).resolve().as_posix()
        decktape_cmd += f"--log-file {shell_quote(log_path)} "

    decktape_cmd += f"-- {shell_quote(config.tools.decktape)} reveal $args {{in_abs}} {{out_abs}}"

    rules.append(
        CustomRule(
            name=RuleName.DECKTAPE.value,
            command=decktape_cmd,
            description="📸 DECKTAPE $out",
            pool=get_pool(RuleName.DECKTAPE.value),
        )
    )

    return rules
