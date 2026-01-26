# Dojo 🥷

Professional Ninja Build Generator for Static Site Generation.

## Installation

```bash
# Install dependencies and the package execution mode
pip install -e .

# Install development dependencies (optional, for running tests)
pip install pytest
```

## Usage

### 1. Create Configuration
Create a `config.yaml` file (see `sample_config.yaml` for an example) to define your site structure.

### 2. Run the Builder
Run `dojo` to generate the Ninja build plan:

```bash
dojo config.yaml
```

### 3. Build the Site
Use `ninja` to execute the build plan:

```bash
ninja -f _build/build.ninja
```

### Nix Usage (Recommended)
This project includes a `flake.nix` that provides all necessary tools (python, pandoc, decktape, etc.) in a reproducible environment.

```bash
# Enter the environment
nix develop

# Run the build
dojo config.yaml && ninja -f _build/build.ninja
```
