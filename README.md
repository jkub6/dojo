# Dojo 🥷

Ninja Build Generator for Static Site Generation.

## Quick Start (Nix — Recommended)

This project uses a `flake.nix` that provides all necessary tools (Python, Pandoc, Decktape, etc.) in a reproducible environment.

```bash
# Enter the development environment
nix develop

# Generate the build plan and execute it
dojo build -c dojo.yaml && ninja -f _build/build.ninja
```

## Installation (pip)

```bash
# Install the package in editable mode
pip install -e .

# Install development dependencies
pip install -e ".[dev]"
```

## Usage

### 1. Create Configuration
Create a `dojo.yaml` file to define your site structure, tools, and resource pools. Use `dojo init` to generate a starter config, or see the [Architecture Guide](docs/ARCHITECTURE.md) for the full schema.

### 2. Generate the Build Plan
```bash
dojo build -c dojo.yaml
```

### 3. Build the Site
```bash
ninja -f _build/build.ninja
```

## Development

Common tasks are defined in the `justfile`:

```bash
just check   # Run all static analysis (ruff, mypy, vulture, etc.)
just test    # Run tests with coverage
just fix     # Auto-format and fix linting issues
just clean   # Remove build artifacts
```
