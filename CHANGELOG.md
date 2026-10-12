# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## 0.2.0 — coordinated authoring and publication API

- Add declarative plugin preparation, shared discovery, explicit inputs/assets/provenance, unique
  module loading, and configuration mutation diagnostics.
- Resolve execution defaults and dependencies together; track filters, template partials, citation
  inputs, relative images, tool implementations, and configured fonts.
- Validate unknown fields, pools, output graphs, collisions, and config-relative paths.
- Keep intermediates under `_build`, replace managed outputs atomically, repair extracted media,
  reconcile owned deletions, and serialize builds and packaging.
- Add publication inventories and deterministic, validated `dojo package` archives.
- Inspect hidden files, srcset, embedded resources, Reveal routes, and decoded Crunch payloads.
- Bound Crunch history to the bundled decoder's supported window, record vendor provenance, and add
  real browser round-trip tests.
- Add end-to-end incremental, failure-recovery, and archive tests with subprocess coverage.

Migration: configuration typos and config-mutating plugins now fail. Consumers of the new
preparation contract must require Dojo 0.2. Use `dojo build` as the build entry point.

## [0.1.0] - 2026-03-24

### Added

- **Ninja Build Generator**: Incremental static site and document build orchestration powered by
  Ninja.
- **Pandoc Markdown Compilation**: Decoupled multi-stage pipeline compiling Markdown into Pandoc
  JSON AST with automatic Makefile-style depfile generation (`dependencies.lua`).
- **Multi-Format Rendering**: Support for standalone HTML, Reveal.js slides, and PDF outputs (via
  Decktape and Typst).
- **Post-Processing Pipelines**: Multi-step chained post-processing steps (`PipelineStep`),
  including HTML/CSS/JS minification (`minify`), PDF optimization (`ghostscript`), and offline HTML
  compression (`crunch`).
- **Offline HTML Compression (`crunch`)**: In-process Zstandard compression and embedded Web Worker
  decoder generating self-extracting offline HTML with no CDN or external dependencies.
- **Cross-Format Sibling Links**: Automatic generation of format-switcher navigation menus
  (`format_links`) via injected defaults and bundled Lua filter (`format_links.lua`).
- **Smart Asset Discovery**: Automatic tracking and deduplication of frontmatter assets, recursive
  CSS `url()` references, recursive HTML `src`/`href` links, and static asset directory
  synchronization with `.static_assets.stamp`.
- **Subprocess Execution Wrapper (`wrap.py`)**: Portable execution wrapper providing path
  placeholder resolution, directory pre-creation, failure cleanup, ephemeral localhost HTTP serving
  for Decktape, and dynamic AST metadata overrides (`slide-level`, `toc`).
- **Concurrency Resource Pools**: Named concurrency limits (`pools` and `rule_pools`) to throttle
  resource-intensive jobs in Ninja.
- **Strict Configuration Schema**: Pydantic v2-backed `dojo.yaml` validation with path traversal
  prevention, directory collision checks, and JSON Schema export (`dojo schema`).
- **Extensible Plugin System**: Python plugin API (`PluginInterface`) supporting custom Ninja rules,
  dynamic output configuration modifications, and Ninja file post-processing with priority ordering.
- **Logging & Diagnostics**: Human-readable Rich console logging and single-line structured JSON
  logging for CI integration.
- **Reproducible Nix Environment**: Complete Nix flake providing dev shells, package derivations,
  checks, and treefmt formatting.
- **Comprehensive Quality Assurance**: 100% branch test coverage enforcement with pytest and
  Hypothesis.

[0.1.0]: https://github.com/jkub6/dojo/releases/tag/v0.1.0
[unreleased]: https://github.com/jkub6/dojo/compare/v0.1.0...HEAD
