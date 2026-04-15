# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-03-24

### Added

- Initial release of Dojo.
- Ninja build generator for static site generation.
- Pandoc integration for Markdown processing.
- Multi-stage pipeline: Compile (Markdown to AST), Render (AST to Output), and Assets (recursive
  dependency discovery).
- Pydantic-based configuration validation with cross-field checks.
- Plugin system for custom Ninja rules and build orchestration.
- Support for HTML and PDF (via Decktape) outputs.
- Post-processing pipeline steps (Ghostscript, Minification).
- Nix flake for reproducible development environments.
- Comprehensive test suite including end-to-end integration tests.
- Path security and sanitization.
