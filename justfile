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

[group('Quality')]
[doc('Apply automatic fixes (formatting and linting)')]
fix: format
	ruff check --fix-only .
	statix fix .

[group('Quality')]
[doc('Format code')]
format:
	nix fmt

[group('Quality')]
[doc('Run all static analysis checks')]
check:
	ruff check .
	ruff format --check .
	mypy
	vulture
	statix check .
	typos --config .typos.toml .
	nix flake check .
	nix flake check . --all-systems --no-build

[group('Quality')]
[doc('Run all tests')]
test:
	pytest -n4 --cov=src --cov-report=term-missing --cov-report=xml

[group('Quality')]
[doc('Run full CI pipeline: check, test, build')]
ci: check test build

# =============================================================================
# Build
# =============================================================================

[group('Build')]
[doc('Build the Nix package')]
build:
	nix build

# =============================================================================
# Maintenance
# =============================================================================

[group('Maintenance')]
[doc('Clean build artifacts and caches')]
[confirm('This will delete all build artifacts and caches. Continue?')]
clean:
	rm -rf _build _site _cache .pytest_cache .ruff_cache .mypy_cache \
	       .hypothesis .coverage coverage.xml htmlcov result node_modules
	find . -type d -name "__pycache__" -exec rm -rf {} +

[group('Maintenance')]
[doc('Update flake inputs and show package version diffs')]
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
