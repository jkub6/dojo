# Justfile for Dojo - A static site and document generator
# Use 'just --list' to see available recipes

set shell := ["bash", "-c", "-u", "-o", "pipefail"]

# --- Default ---

# List available recipes
default:
    @just --list

# --- Linting & Formatting ---

# Apply automatic fixes (formatting and linting)
fix:
    ruff format .
    ruff check --fix-only .

# Alias for fix
fmt: fix

# Run all static analysis checks
check:
    ruff check .
    ruff format --check .
    mypy src
    vulture
    typos .

# Alias for check
lint: check

# --- Testing ---

# Run tests with coverage and parallel execution
test:
    pytest

# Run tests continuously on file changes
watch:
    watchexec -e py,yaml,toml -- just test

# --- Building ---

# Build the project (requires config file)
build config="dojo.yaml":
    python -m dojo build -c {{config}} && ninja -f _build/build.ninja

# --- Maintenance ---

# Clean build artifacts and temporary files
clean:
    rm -rf _build _site .pytest_cache .coverage .hypothesis .mypy_cache .ruff_cache
    find . -type d -name "__pycache__" -exec rm -rf {} +
