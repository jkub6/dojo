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
fix:
	ruff format .
	ruff check --fix-only .
	alejandra .
	statix fix .

[group('Quality')]
[doc('Alias for fix')]
format: fix

[group('Quality')]
[doc('Run all static analysis checks')]
check:
	ruff format --check .
	ruff check .
	mypy src
	vulture src --min-confidence 80
	typos --config .typos.toml .
	alejandra --check .
	statix check .
	nix flake check --all-systems .

[group('Quality')]
[doc('Alias for check')]
lint: check

[group('Quality')]
[doc('Run tests (with coverage via pyproject.toml addopts)')]
test:
	pytest


# =============================================================================
# Build
# =============================================================================

[group('Build')]
[doc('Build the Nix package')]
build:
	nix build

# =============================================================================
# CI
# =============================================================================

[group('CI')]
[doc('Run full CI pipeline: check, test, build')]
ci: check test build

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
