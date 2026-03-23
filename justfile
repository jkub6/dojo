# Justfile for Dojo

set shell := ["bash", "-c"]

# List available recipes
default:
    @just --list

# Apply automatic fixes (formatting and linting)
fix:
    ruff format .
    ruff check --fix-only .

# Run all static analysis checks
check:
    ruff check .
    ruff format --check .
    mypy src
    vulture
    typos .

# Run tests with coverage
test:
    pytest

# Build the project (requires config file)
build config="dojo.yaml":
    python -m dojo build -c {{config}} && ninja -f _build/build.ninja

# Clean build artifacts
clean:
    rm -rf _build _site .pytest_cache .coverage
    find . -type d -name "__pycache__" -exec rm -rf {} +
