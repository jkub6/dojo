# Justfile for Dojo — a static site and document generator
# Run 'just --list' to see available recipes

set shell := ["bash", "-uc", "-o", "pipefail"]
set dotenv-load

[doc('List available recipes')]
default:
    @just --list

# =============================================================================
# Quality
# =============================================================================

[doc('Apply automatic fixes (formatting and linting)')]
[group('Quality')]
fix: format
    ruff check --fix-only .
    statix fix .

[doc('Format code')]
[group('Quality')]
format:
    nix fmt

[doc('Run all static analysis checks')]
[group('Quality')]
check:
    ruff check .
    ruff format --check .
    mypy
    vulture
    statix check .
    typos --config .typos.toml .
    nix flake check .
    nix flake check . --all-systems --no-build

[doc('Run all tests')]
[group('Quality')]
test:
    pytest -n4 --cov=src --cov-report=term-missing --cov-report=xml

[doc('Run full CI pipeline: check, test, build')]
[group('Quality')]
ci: check test build

# =============================================================================
# Build
# =============================================================================

[doc('Build the Nix package')]
[group('Build')]
build:
    nix build

# =============================================================================
# Maintenance
# =============================================================================

[confirm('This will delete all build artifacts and caches. Continue?')]
[doc('Clean build artifacts and caches')]
[group('Maintenance')]
clean:
    rm -rf _build _site _cache .pytest_cache .ruff_cache .mypy_cache \
           .hypothesis .coverage coverage.xml htmlcov result node_modules
    find . -type d -name "__pycache__" -exec rm -rf {} +

[doc('Update flake inputs and show package version diffs')]
[group('Maintenance')]
update:
    #!/usr/bin/env bash
    set -euo pipefail

    # Determine the current system architecture
    SYS=$(nix eval --raw --impure --expr 'builtins.currentSystem')

    echo "=> Building current environment..."
    OLD_ENV=$(nix build .#devShells.$SYS.default --print-out-paths --no-link)

    echo "=> Updating flake inputs..."
    nix flake update

    echo "=> Building new environment..."
    NEW_ENV=$(nix build .#devShells.$SYS.default --print-out-paths --no-link)

    echo "=> Diffing packages..."
    nvd diff "$OLD_ENV" "$NEW_ENV"

    # Reload direnv if it's active
    if command -v direnv >/dev/null 2>&1; then
        echo "=> Reloading direnv..."
        direnv reload
    fi
