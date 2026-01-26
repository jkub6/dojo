# Contributing to Dojo

We love your input! We want to make contributing to Dojo as easy and transparent as possible, whether it's:

- Reporting a bug
- Discussing the current state of the code
- Submitting a fix
- Proposing new features

## Development Process

We use Github to host code, to track issues and feature requests, and to accept pull requests.

### 1. Fork the repo and create your branch from `main`
```bash
git checkout -b my-new-feature
```

### 2. Set up the environment
We use **Nix** to ensure a reproducible development environment.
```bash
nix develop
```

### 3. Make your changes
Make sure to follow our coding standards.

### 4. Run Tests & Lints
Ensure everything is green before submitting.
```bash
nix develop --command bash -c "ruff check ."
nix develop --command bash -c "mypy src"
nix develop --command bash -c "pytest"
```

### 5. Submit a Pull Request
Prerequisites:
- [ ] Tests pass
- [ ] Code is linted
- [ ] Type checks pass

## License
By contributing, you agree that your contributions will be licensed under its MIT License.
