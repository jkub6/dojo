# Basic Site Example

This directory contains a minimal, working static website built with **Dojo**, demonstrating the
core features of the build pipeline with zero external dependencies beyond Pandoc and Ninja.

## Project Structure

```
examples/basic-site/
├── dojo.yaml              # Project build configuration
├── content/               # Source Markdown files
│   ├── index.md           # Homepage
│   └── about.md           # Secondary page
└── defaults/              # Pandoc defaults configuration
    └── html.yaml          # HTML5 rendering options
```

### Key Configuration Files

- **`dojo.yaml`**: Specifies that source files live in `content/`, build artifacts in `_build/`, and
  compiled web pages in `_site/`. It defines the `page` content type with an `html` output targeting
  `defaults/html.yaml`.
- **`defaults/html.yaml`**: Standard Pandoc YAML defaults file that enables HTML5 output, standalone
  document generation, and default metadata.
- **`content/*.md`**: Markdown files with optional YAML frontmatter (`title`, `author`, `date`,
  etc.) that are compiled to HTML.

______________________________________________________________________

## Prerequisites

Before building this example, ensure the following tools are available on your system:

- **Python**: `>= 3.13` with `dojo-ssg` installed (or run from a repository checkout with
  `python -m dojo`)
- **[Ninja](https://ninja-build.org/)** (`>= 1.3`)
- **[Pandoc](https://pandoc.org/)** (`>= 3.0`)

> [!TIP]
> If using Nix, run `nix develop` at the repository root to enter an environment with all tools
> pre-installed.

______________________________________________________________________

## Step-by-Step Usage

### 1. Validate Configuration

Verify that the project structure and configuration are valid:

```bash
dojo check
```

Output:

```text
✓ Configuration valid: .../examples/basic-site/dojo.yaml
  Src: content
  Dst: _site
  Types: page
```

### 2. Generate the Ninja Build Graph

Generate the `_build/build.ninja` file from your Markdown files:

```bash
dojo build
```

This compiles `content/index.md` and `content/about.md` into Pandoc JSON AST files in `_build/` and
writes the corresponding Ninja build edges.

### 3. Execute the Build

Run Ninja to execute the build plan:

```bash
ninja -C _build
```

Output:

```text
ninja: Entering directory `_build'
[1/4] 🧠 COMPILE .../content/about.md
[2/4] 🧠 COMPILE .../content/index.md
[3/4] 🎨 RENDER .../_site/about.html
[4/4] 🎨 RENDER .../_site/index.html
```

Your compiled website is now available in `_site/`:

- `_site/index.html`
- `_site/about.html`

### 4. Preview the Site Locally

Serve the generated site using Python's built-in HTTP server:

```bash
python3 -m http.server -d _site 8000
```

Open [http://localhost:8000](http://localhost:8000) in your web browser.

______________________________________________________________________

## Observing Incremental Builds

To see Ninja's incremental build speed:

1. Edit a single file (for example, `content/about.md`):

   ```bash
   echo "\nUpdated content!" >>content/about.md
   ```

2. Re-run Ninja:

   ```bash
   ninja -C _build
   ```

Notice that Ninja only recompiles and re-renders `about.md` — `index.md` is untouched and skipped
entirely.
