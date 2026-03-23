{
  description = "Dojo - A static site and document generator built on Pandoc and Typst";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    let
      # Export a Nixpkgs Overlay so consumers can compile Dojo
      # transparently against whatever custom Python derivation they require.
      overlay = final: prev: {
        pythonPackagesExtensions = prev.pythonPackagesExtensions ++ [
          (python-final: python-prev: {
            dojo = python-final.buildPythonPackage {
              pname = "dojo";
              version = "0.1.0";
              format = "pyproject";
              src = ./.;

              propagatedBuildInputs = with python-final; [
                pyyaml
                pydantic
                tqdm
                rich
              ];
              nativeBuildInputs = [ python-final.hatchling ];
              nativeCheckInputs = with python-final; [
                pytest
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
            };
          })
        ];
      };
    in
    flake-utils.lib.eachDefaultSystem (system:
      let
        # Apply the overlay locally to construct the isolated development shell
        pkgs = import nixpkgs {
          inherit system;
          overlays = [ overlay ];
        };
        python-to-use = pkgs.python313;
      in {
        packages.default = pkgs.python313Packages.dojo;

        devShells.default = pkgs.mkShell {
          inputsFrom = [ pkgs.python313Packages.dojo ];
          packages = with pkgs; [
            just
            ninja
            pandoc
            typst
            decktape
            minify
            ghostscript
            typos
            (python-to-use.withPackages (p: [
               p.pyyaml
               p.pydantic
               p.tqdm
               p.rich
               p.pytest
               p.pytest-cov
               p.pytest-xdist
               p.pytest-randomly
               p.pytest-timeout
               p.pytest-mock
               p.pytest-regressions
               p.hypothesis
               p.mypy
               p.types-pyyaml
               p.vulture
               p.jsonschema
               p.ruff
            ]))
          ];
          shellHook = ''
            # Bind the local src directory globally for transparent editable execution
            export PYTHONPATH="$(pwd)/src:$PYTHONPATH"
          '';
        };
      }
    ) // {
      overlays.default = overlay;
    };
}
