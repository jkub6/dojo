{
  description = "Dojo - A static site and document generator built on Pandoc and Typst";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = {
    self,
    nixpkgs,
    flake-utils,
  }: let
    # Export a Nixpkgs overlay so consumers can compile Dojo transparently
    # against whatever custom Python derivation they require.
    overlay = final: prev: {
      pythonPackagesExtensions =
        prev.pythonPackagesExtensions
        ++ [
          (python-final: _python-prev: {
            dojo = python-final.buildPythonPackage {
              pname = "dojo";
              version = "0.1.0";
              pyproject = true;

              src = final.lib.cleanSource ./.;

              propagatedBuildInputs = with python-final; [
                pyyaml
                pydantic
                tqdm
                rich
              ];

              nativeBuildInputs = [
                python-final.hatchling
              ];

              nativeCheckInputs = with python-final; [
                pytestCheckHook
                pytest-cov
                pytest-xdist
                pytest-randomly
                pytest-timeout
                pytest-mock
                pytest-regressions
                hypothesis
                jsonschema
                final.ninja
                final.pandoc
                final.typst
                final.decktape
                final.minify
                final.ghostscript
              ];

              meta = with final.lib; {
                description = "A static site and document generator built on Pandoc and Typst";
                homepage = "https://github.com/jkub6/dojo";
                license = licenses.mit;
                maintainers = [];
                platforms = platforms.linux;
              };
            };
          })
        ];
    };
  in
    flake-utils.lib.eachSystem [
      "x86_64-linux"
      "aarch64-linux"
    ] (system: let
      pkgs = import nixpkgs {
        inherit system;
        overlays = [overlay];
      };

      # Single source of truth for the Python version used across both the
      # package and the dev shell, so a one-line change upgrades everything.
      python = pkgs.python313;

      inherit (python.pkgs) dojo;
    in {
      packages.default = dojo;

      devShells.default = pkgs.mkShell {
        # Pull in all build/check inputs declared on the package itself.
        inputsFrom = [dojo];

        packages = with pkgs; [
          just
          ninja
          pandoc
          typst
          decktape
          minify
          ghostscript
          typos
          alejandra
          statix
          (python.withPackages (p: [
            # Runtime
            p.pyyaml
            p.pydantic
            p.tqdm
            p.rich
            # Test
            p.pytest
            p.pytest-cov
            p.pytest-xdist
            p.pytest-randomly
            p.pytest-timeout
            p.pytest-mock
            p.pytest-regressions
            p.hypothesis
            p.jsonschema
            # Type-checking & linting
            p.mypy
            p.types-pyyaml
            p.ruff
            p.vulture
          ]))
        ];

        shellHook = ''
          # Bind the local src directory globally for transparent editable execution.
          export PYTHONPATH="$(pwd)/src:''${PYTHONPATH:-}"
        '';
      };
    })
    // {
      overlays.default = overlay;
    };
}
