# Dojo

[![CI](https://github.com/jkub6/dojo/actions/workflows/ci.yml/badge.svg)](https://github.com/jkub6/dojo/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/dojo-ssg)](https://pypi.org/project/dojo-ssg/)
[![Python](https://img.shields.io/pypi/pyversions/dojo-ssg)](https://pypi.org/project/dojo-ssg/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Dojo** is a static site and document generator powered by [Ninja](https://ninja-build.org/) and
[Pandoc](https://pandoc.org/). It combines the flexibility of Pandoc's document conversion with the
extreme speed of Ninja's incremental build system.

## Key Features

- **Blazing Fast**: Uses Ninja to track dependencies and perform minimal incremental rebuilds.
- **Format Agnostic**: Support for HTML, PDF (via Decktape/Typst), and any other format Pandoc
  supports.
- **Smart Assets**: Recursively discovers and copies CSS, images, and other dependencies.
- **Pipeline Processing**: Built-in support for Ghostscript optimization, minification, and
  multi-step post-processing.
- **Strict Configuration**: Pydantic-powered `dojo.yaml` with rigorous validation and ID discovery.
- **Extensible**: Fully featured Python-based plugin system to modify Ninja rules and build
  orchestration.
- **Reproducible**: Bundled with a Nix flake for consistent environments across development and CI.

## Installation

### Prerequisites

Dojo requires the following tools to be installed on your system:

- **[Ninja](https://ninja-build.org/)** (≥1.3) — the build executor
- **[Pandoc](https://pandoc.org/)** (≥3.0) — the document converter

Optional tools for specific output formats:

- **[Typst](https://typst.app/)** — PDF generation via Typst
- **[Decktape](https://github.com/astefanutti/decktape)** — HTML-to-PDF slide conversion
- **[Ghostscript](https://www.ghostscript.com/)** — PDF optimization
- **[minify](https://github.com/tdewolff/minify)** — HTML/CSS/JS minification

### Install via pip

```bash
pip install dojo-ssg
```

### Install via Nix

```bash
nix profile install github:jkub6/dojo
```

Or use the flake in a development shell:

```bash
nix develop github:jkub6/dojo
```

## Quick Start

1. **Initialize a project:**

   ```bash
   dojo init
   ```

   This creates a starter project with a `dojo.yaml` configuration, a `content/` directory with a
   sample page, and `defaults/` with a Pandoc defaults file.

2. **Generate the build file:**

   ```bash
   dojo build
   ```

3. **Run Ninja** to execute the build:

   ```bash
   ninja -C _build
   ```

Your generated site will be in `_site/`.

## Why Dojo?

Traditional static site generators often struggle with complex document pipelines (like generating
high-quality PDFs from HTML slides) or deep asset dependency trees. Dojo treats your website as a
build graph, ensuring that changing a single CSS variable or a nested image only rebuilds what is
strictly necessary, while providing the full power of Pandoc for document transformation.

## Documentation

- [Architecture Guide](docs/ARCHITECTURE.md) — how the pipeline works
- [Plugin Development](docs/plugins.md) — writing custom plugins
- [Example Project](examples/basic-site/) — a minimal working site
- Run `dojo schema` to export the full JSON Schema for IDE integration

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, coding standards, and PR guidelines.

```bash
just check # Run linting and type checking
just test  # Run the full test suite
just ci    # Run everything
```

## License

MIT © 2026 Jake
