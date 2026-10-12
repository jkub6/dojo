# Dojo

[![CI](https://github.com/jkub6/dojo/actions/workflows/ci.yml/badge.svg)](https://github.com/jkub6/dojo/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/dojo-ssg)](https://pypi.org/project/dojo-ssg/)
[![Python](https://img.shields.io/pypi/pyversions/dojo-ssg)](https://pypi.org/project/dojo-ssg/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Dojo** is an incremental static site and multi-format document generator powered by
[Ninja](https://ninja-build.org/) and [Pandoc](https://pandoc.org/). It merges the flexible markup
transformations of Pandoc with the minimal incremental rebuild times of Ninja's dependency graph.

Dojo models document workflows as a dependency graph: compile Markdown, render HTML or PDF, then
derive and post-process additional formats. Each build refreshes source discovery and plugin
preparation before Ninja reuses unchanged outputs. Embedded documents and browser exports use
conservative asset dependencies; ordinary linked HTML avoids unrelated asset rebuilds.

______________________________________________________________________

## Key Features

- **Incremental Builds**: Uses Ninja to track file modification times, AST caches, and compiler
  depfiles (`.d`) for incremental execution.
- **Format Agnostic**: Generate HTML websites, standalone articles, Reveal.js presentations, and
  high-quality PDFs (via Typst or Decktape).
- **Smart Asset Discovery**: Automatically discovers and copies assets referenced in frontmatter,
  recursively scans CSS `url()` references and HTML `src`/`href` links, and syncs static asset
  directories with timestamp stamps (`.static_assets.stamp`).
- **Flexible Post-Processing Pipelines**: Built-in support for chained post-processing tools,
  including HTML/CSS/JS minification (`minify`), PDF optimization (`ghostscript`), offline HTML
  compression (`crunch`), and custom commands.
- **Offline HTML Compression (`crunch`)**: In-process Zstandard compression bundled with an embedded
  Web Worker decoder that produces standalone, self-extracting offline HTML files with no CDN
  dependencies.
- **Cross-Format Sibling Links**: Automatically generates format-switcher navigation menus between
  sibling outputs (e.g., HTML \<-> PDF) via bundled Lua filters.
- **Resource Concurrency Pools**: Assign heavy processes (such as headless browser slide rendering
  or PDF generation) to named Ninja pools to prevent CPU and memory exhaustion.
- **Rigorous Configuration**: Type-safe `dojo.yaml` validated with Pydantic v2, featuring path
  sanitization, directory conflict detection, and JSON Schema export (`dojo schema`) for IDE
  support.
- **Extensible Plugin System**: Python-based plugin API (`PluginInterface`) with priority sorting to
  declare preparation inputs, metadata, assets, and provenance. See
  [the plugin contract](docs/plugins.md).
- **Reproducible Environments**: Packaged with a Nix flake for deterministic development, testing,
  and CI execution.

______________________________________________________________________

## Installation

### Prerequisites

- **Platform**: Linux/POSIX; x86_64 Linux is tested. The Nix flake also evaluates aarch64 Linux.
  Windows and macOS are not currently supported/tested build targets.
- **Python**: `>= 3.13`
- **[Ninja](https://ninja-build.org/)** (`>= 1.3`) — build executor
- **[Pandoc](https://pandoc.org/)** (`>= 3.0`) — markup conversion engine

Optional tools for specific workflows:

- **[Typst](https://typst.app/)** — native PDF generation
- **[Decktape](https://github.com/astefanutti/decktape)** — HTML/Reveal.js slide-to-PDF capture
- **[Ghostscript](https://www.ghostscript.com/)** (`gs`) — PDF compression and optimization
- **[minify](https://github.com/tdewolff/minify)** — HTML, CSS, and JavaScript minification

### Install via pip

```bash
pip install dojo-ssg
```

### Install via Nix

Install directly into your user profile:

```bash
nix profile install github:jkub6/dojo
```

Or enter a temporary development shell containing Python 3.14, Pandoc, Ninja, and all optional
tools:

```bash
nix develop github:jkub6/dojo
```

______________________________________________________________________

## Quick Start

### 1. Initialize a Starter Project

```bash
dojo init
```

This scaffolds a complete working project:

- `dojo.yaml`: Configuration defining content types and build directories.
- `content/index.md`: Starter homepage with YAML frontmatter.
- `defaults/html.yaml`: Pandoc defaults file for standalone HTML5 output.

### 2. Validate Configuration

```bash
dojo check
```

Verifies that `dojo.yaml` is valid, required directories exist, and tools are discoverable in
`$PATH`.

### 3. Build and Package

```bash
dojo build
```

The command discovers sources, refreshes plugin preparation, runs Ninja incrementally, and finalizes
publication ownership. Paths are relative to `dojo.yaml`, regardless of the caller's working
directory. Unknown fields, invalid pools, output collisions, and dependency cycles fail before
execution.

```bash
dojo build --dry-run        # Validate/discover without writes or preparation hooks
dojo build --generate-only  # Prepare inputs and write the graph, without executing tools
dojo check-output           # Validate resources and duplicate IDs
dojo check-output --links   # Also check authored local links and fragments
dojo package -o release.txz # Validate and archive the last successful full build
```

`_build` holds disposable private state; `_site` holds publication files. Hidden assets are allowed
when declared. Packaging selects files from `dojo-publication.json`, verifies checksums, and
validates the extracted archive. It does not build again or use hidden-file exclusions.

Use `dojo build` in watchers and CI. Raw Ninja commands are graph diagnostics and do not perform
source discovery, domain preparation, or publication finalization. See
[the architecture and dependency contract](docs/ARCHITECTURE.md).

______________________________________________________________________

## Command-Line Interface (CLI)

Dojo provides a structured command-line interface:

```
dojo [-h] [-v] [-q] [--version] [--json] <command> [options]
```

### Subcommands

| Command   | Usage                             | Description                                                                                     |
| --------- | --------------------------------- | ----------------------------------------------------------------------------------------------- |
| `build`   | `dojo build [-c CONFIG] [-n]`     | Refresh preparation and build incrementally. Use `-n / --dry-run` for discovery without writes. |
| `check`   | `dojo check [-c CONFIG]`          | Validate `dojo.yaml` schema, paths, and tool availability.                                      |
| `init`    | `dojo init`                       | Scaffold a new starter project in the current directory.                                        |
| `schema`  | `dojo schema [-o OUTPUT]`         | Print or export the JSON Schema definition for `dojo.yaml`.                                     |
| `version` | `dojo version`                    | Display installed version.                                                                      |
| `crunch`  | `dojo crunch [input] [-o OUTPUT]` | Compress HTML into a standalone self-extracting offline HTML file.                              |

### Global Flags

> [!NOTE]
> Global flags should precede the subcommand (for example: `dojo --verbose build`).

- `-v, --verbose`: Enable debug logging and full tracebacks on error.
- `-q, --quiet`: Suppress non-error console output and progress bars.
- `--json`: Output logs as structured JSON for CI/CD integrations.
- `--version`: Print version information and exit.

______________________________________________________________________

## Configuration Example (`dojo.yaml`)

```yaml
src_dir: content # Directory containing Markdown source files
output_dir: _site # Target directory for built site
build_dir: _build # Intermediate build artifacts directory
default_type: page # Default type when not specified in frontmatter
# Concurrency limits for resource-intensive jobs
pools:
  heavy: 2
rule_pools:
  decktape: heavy
types:
  page:
    outputs:
      - id: html
        extension: html
        defaults: defaults/page.yaml
        post_process:
          - tool: minify
  slides:
    outputs:
      - id: html
        extension: html
        defaults: defaults/slides.yaml
      - id: pdf
        extension: pdf
        source: html # Derived from the HTML output above
        tool: decktape
        args: ["--size", "1920x1080"]
        post_process:
          - tool: ghostscript
            args: ["-dPDFSETTINGS=/screen"]
# Verbatim static asset directories
static_dirs:
  - assets
# Auto-generate format switcher navigation links
format_links: true
# Optional plugin modules
plugins:
  - plugins/custom.py
```

______________________________________________________________________

## Offline HTML Compression (`crunch`)

Dojo includes built-in offline HTML compression using in-process Zstandard compression and an
embedded Web Worker decoder. The compressed file is an ordinary, self-contained HTML file that loads
instantly in any modern browser without external network access or CDNs.

### Using `crunch` in a Build Pipeline

Add `crunch` to any output's `post_process` pipeline in `dojo.yaml`:

```yaml
post_process:
  - tool: minify
  - tool: crunch
    args: ["-l", "22", "--window-log", "25"]
```

### Using `crunch` Standalone via CLI

Compress HTML documents directly from the terminal:

```bash
# Compress a file
dojo crunch input.html -o output.html

# Pipe through stdin/stdout
cat input.html | dojo crunch - >output.html
```

______________________________________________________________________

## Documentation

- **[Architecture Guide](docs/ARCHITECTURE.md)**: Deep dive into the multi-stage pipeline, `wrap.py`
  execution wrapper, Ninja variables, and internal AST caching.
- **[Plugin Development Guide](docs/plugins.md)**: Guide and reference for writing custom Python
  plugins using `PluginInterface`.
- **[Basic Site Example](examples/basic-site/)**: A minimal, functional example project
  demonstrating page compilation and Pandoc defaults.
- **[Contributing Guide](CONTRIBUTING.md)**: Development environment setup, coding standards, and
  testing procedures.
- **[Security Policy](SECURITY.md)**: Supported versions and vulnerability disclosure guidelines.
- **[Changelog](CHANGELOG.md)**: Release history and version migration notes.

______________________________________________________________________

## Development & Testing

Dojo uses [just](https://github.com/casey/just) to automate routine development tasks:

```bash
just check # Run Ruff linting, mypy type checking, vulture, and statix
just test  # Run pytest with 100% code coverage requirement
just ci    # Execute full quality gate, test suite, and Nix package build
just fix   # Automatically apply formatting and lint fixes
```

______________________________________________________________________

## License

MIT © 2026 Jake
