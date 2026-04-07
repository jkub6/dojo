# Dojo

[![CI](https://github.com/jkub6/dojo/actions/workflows/ci.yml/badge.svg)](https://github.com/jkub6/dojo/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Dojo** is a professional-grade static site and document generator powered by [Ninja](https://ninja-build.org/) and [Pandoc](https://pandoc.org/). It combines the flexibility of Pandoc's document conversion with the extreme speed of Ninja's incremental build system.

## Key Features

- **Blazing Fast**: Uses Ninja to track dependencies and perform minimal incremental rebuilds.
- **Format Agnostic**: Support for HTML, PDF (via Decktape/Typst), and any other format Pandoc supports.
- **Smart Assets**: Recursively discovers and copies CSS, images, and other dependencies.
- **Pipeline Processing**: Built-in support for Ghostscript optimization, minification, and multi-step post-processing.
- **Strict Configuration**: Pydantic-powered `dojo.yaml` with rigorous validation and ID discovery.
- **Extensible**: Fully featured Python-based plugin system to modify Ninja rules and build orchestration.
- **Reproducible**: Bundled with a Nix flake for consistent environments across development and CI.

## Why Dojo?

Traditional static site generators (SSGs) often struggle with complex document pipelines (like generating high-quality PDFs from HTML slides) or deep asset dependency trees. Dojo treats your website as a build graph, ensuring that changing a single CSS variable or a nested image only rebuilds what is strictly necessary, while providing the full power of Pandoc for document transformation.

## Quick Start

1. **Initialize a project**:
   ```bash
   dojo init
   ```

2. **Build your site**:
   ```bash
   dojo build
   ```

3. **Run Ninja**:
   Dojo generates a `_build/build.ninja` file. Run ninja to finalize the build:
   ```bash
   ninja -C _build
   ```

## Documentation

- [Architecture Guide](docs/ARCHITECTURE.md)
- [Plugin Development](docs/plugins.md)
- [Configuration Schema](docs/schema.md) — run `dojo schema` to generate

## Contributing

Dojo uses `just` for development tasks. See the `justfile` for available commands:

```bash
just check  # Run linting and type checking
just test   # Run the full test suite
```

## License

MIT © 2026 Jake
