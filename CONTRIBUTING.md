# Contributing to Dojo

Thank you for contributing to Dojo! We welcome contributions, bug reports, feature requests, and
documentation enhancements.

This document outlines the development workflow, coding guidelines, testing requirements, and pull
request process for the project.

______________________________________________________________________

## Prerequisites

To develop Dojo locally, you will need:

- **Python**: `>= 3.13` (Python 3.14 supported and tested in CI)
- **[Ninja](https://ninja-build.org/)** (`>= 1.3`)
- **[Pandoc](https://pandoc.org/)** (`>= 3.0`)
- **[just](https://github.com/casey/just)** (command runner for quality checks and tests)

Optional tools for full integration testing:

- **Typst**
- **Decktape**
- **Ghostscript** (`gs`)
- **Minify**

> [!TIP]
> Using [Nix](https://nixos.org/) is the easiest and most reliable way to set up the development
> environment, as all runtime dependencies, test tools, and linters are provided automatically.

______________________________________________________________________

## Development Setup

### Option A: Nix Development Shell (Recommended)

With Nix and flakes enabled:

```bash
# Spawn a shell with Python 3.14, Pandoc, Ninja, and all tooling installed
nix develop

# Or automatically enter the environment via direnv
direnv allow
```

### Option B: Manual Setup

If you prefer using your system's package manager:

1. Install Python 3.13+, Ninja, Pandoc, and `just`.
2. Create and activate a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. Install Dojo in editable mode with development dependencies:
   ```bash
   pip install -e . --dependency-groups dev
   ```

______________________________________________________________________

## Development Workflow

All routine maintenance, linting, and testing tasks are orchestrated with `just`:

| Command       | Description                                                                            |
| ------------- | -------------------------------------------------------------------------------------- |
| `just check`  | Run all static analysis checks (Ruff, mypy, Vulture, Statix, Typos, Nix flake checks). |
| `just test`   | Run the full pytest test suite with test coverage verification.                        |
| `just fix`    | Automatically apply code formatting and linting fixes via Ruff and Statix.             |
| `just format` | Format code using `nix fmt`.                                                           |
| `just ci`     | Run the complete CI pipeline locally (`check`, `test`, `build`).                       |
| `just clean`  | Remove build artifacts, cache files, and virtual environment temporary directories.    |

______________________________________________________________________

## Code Quality Standards

Contributions must adhere to strict quality standards:

### 1. Code Style and Formatting

- Formatting and linting are strictly enforced by [Ruff](https://astral.sh/ruff).
- Maximum line length is **100 characters**.
- Run `just fix` before committing code to automatically apply standard formatting.

### 2. Static Typing

- Dojo enforces strict type annotations across all source modules using
  [mypy](https://mypy-lang.org/) and the Pydantic plugin.
- All functions, methods, class attributes, and module-level variables must have explicit type
  annotations.
- Avoid using `Any` or unannotated helper functions.

### 3. Documentation and Docstrings

- All modules, public classes, methods, and functions must include descriptive docstrings adhering
  to Google / PEP 257 conventions (enforced by Ruff `D` rules).
- Keep docstring summaries on a single line where possible.
- Document arguments (`Args:`), return values (`Returns:`), and exceptions (`Raises:`).

______________________________________________________________________

## Testing Guidelines

- **Test Framework**: Tests are written with [pytest](https://pytest.org/) and
  [Hypothesis](https://hypothesis.readthedocs.io/) for property-based testing.
- **Coverage Requirement**: The repository requires **100% branch test coverage**
  (`fail_under = 100` in `pyproject.toml`). Any added or modified code in `src/dojo/` must include
  corresponding unit or integration tests that cover all execution branches.
- **Test Organization**:
  - `tests/test_*.py`: Unit tests for individual components (CLI, config, crunch, rules, wrap,
    etc.).
  - `tests/test_e2e*.py`: End-to-end integration tests verifying complete build generation and Ninja
    execution.
- Run tests with:
  ```bash
  just test
  ```

______________________________________________________________________

## Pull Request Process

1. **Create a branch**: Fork the repository and create a feature branch off `main`:
   ```bash
   git checkout -b feature/my-new-feature
   ```
2. **Implement changes**: Write clean, modular code following the style standards.
3. **Add tests**: Ensure all new logic is covered with unit tests and existing tests pass.
4. **Run local CI**: Run `just ci` and confirm that all checks, tests, and builds succeed.
5. **Commit cleanly**: Write concise, informative commit messages explaining the rationale behind
   changes.
6. **Submit PR**: Open a pull request against `main` using the provided PR template. Link any relevant
   issues or discussion threads.
