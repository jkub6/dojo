# Contributing to Dojo

Thank you for your interest in contributing to Dojo! We welcome contributions, bug reports, and
suggestions.

## Prerequisites

- **Python**: `>=3.13`
- **Ninja**: Build system for executing generated build graphs
- **Pandoc**: Document converter for markup processing

> [!NOTE]
> Using [Nix](https://nixos.org/) is recommended because it automatically manages all prerequisites
> and developer dependencies, but it is not required.

______________________________________________________________________

## Development Setup

### Option A: Nix (Recommended)

If you use Nix (with flakes enabled):

```bash
# Enter development shell with all tools and dependencies configured
nix develop

# Or automatically load the environment when entering the directory
direnv allow
```

### Option B: Manual Setup

If you prefer a manual setup without Nix:

1. Ensure Python 3.13+, Ninja, and Pandoc are installed via your system package manager.
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

Dojo uses [just](https://github.com/casey/just) to automate routine development tasks:

- `just check`: Run all static analysis checks (Ruff, mypy, vulture, statix, typos)
- `just test`: Run the full test suite
- `just fix`: Apply automatic code formatting and linting fixes
- `just ci`: Run the full CI pipeline (`check`, `test`, `build`)

______________________________________________________________________

## Code Standards

- **Formatting & Linting**: Managed by [Ruff](https://astral.sh/ruff). Ensure code conforms to repo
  formatting rules before submitting (`just fix` / `just check`).
- **Type Checking**: Strict type checking with [mypy](https://mypy-lang.org/). All functions,
  methods, and classes must have explicit type annotations.
- **Documentation**: All modules, classes, and public functions/methods must have clear, descriptive
  docstrings.

______________________________________________________________________

## Testing

- Testing is handled with [pytest](https://pytest.org/) and
  [Hypothesis](https://hypothesis.readthedocs.io/) for property-based testing.
- New features and bug fixes must include corresponding tests.
- Aim for high test coverage across all new and modified code.
- Run the test suite with `just test`.

______________________________________________________________________

## Pull Request Process

1. Fork the repository and create your branch from `main`.
2. Implement your changes adhering to the code and testing standards.
3. Ensure the full test and lint suite passes locally via `just ci`.
4. Write clear, concise commit messages.
5. Submit a pull request describing the changes and referencing any related issues.
