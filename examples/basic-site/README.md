# Basic Site Example

This is a minimal Dojo project demonstrating basic usage.

## Prerequisites

Ensure you have the following tools installed:

- `dojo`
- `ninja`
- `pandoc`

## Usage

1. Navigate into this directory:

   ```bash
   cd examples/basic-site
   ```

2. Run Dojo to generate the Ninja build file:

   ```bash
   dojo build
   ```

3. Build the site using Ninja:

   ```bash
   ninja -C _build
   ```

The compiled output will be generated in `_site/`.
