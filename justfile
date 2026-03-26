# Justfile for Dojo - A static site and document generator
# Use 'just --list' to see available recipes

set shell := ["bash", "-c", "-u", "-o", "pipefail"]

# --- Default ---

# List available recipes
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
  vulture --min-confidence 80
  typos --config .typos.toml .
  alejandra --check .
  statix check .
  nix flake check --all-systems .

[group('Quality')]
[doc('Alias for check')]
lint: check

[group('Quality')]
[doc('Run all tests')]
test:
  pytest

[group('Quality')]
[doc('Run full CI pipeline: check, test')]
ci: check test

# =============================================================================
# Maintenance
# =============================================================================

[group('Maintenance')]
[doc('Clean build artifacts and caches')]
clean:
    rm -rf _build _site _cache .pytest_cache .ruff_cache .mypy_cache .hypothesis .coverage coverage.xml htmlcov result node_modules
    find . -type d -name "__pycache__" -exec rm -rf {} +
