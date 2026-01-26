# Justfile for Dojo

set shell := ["bash", "-c"]

# List available recipes
default:
    @just --list

# Run all static analysis checks
check:
    ruff check . && ruff format --check .
    mypy src

# Apply automatic fixes (formatting and linting)
fix:
    ruff check --fix .
    ruff format .

# Run tests with coverage
test:
    pytest --cov=src

# Build the project (requires config file)
build config="dojo.yaml":
    python3 -m dojo build -c {{config}} && ninja -f _build/build.ninja

# Clean build artifacts
clean:
    rm -rf _build _site .pytest_cache .coverage
    find . -type d -name "__pycache__" -exec rm -rf {} +
