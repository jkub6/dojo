{
  description = "Dojo: Professional Ninja Build Generator";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-parts.url = "github:hercules-ci/flake-parts";
  };

  outputs = inputs @ {flake-parts, ...}:
    flake-parts.lib.mkFlake {inherit inputs;} {
      systems = ["x86_64-linux" "aarch64-linux" "aarch64-darwin" "x86_64-darwin"];

      perSystem = {
        config,
        self',
        inputs',
        system,
        ...
      }: let
        # Apply the Decktape overlay from the user's snippet
        overlay = final: prev: {
          decktape = prev.decktape.overrideAttrs (oldAttrs: rec {
            src = final.fetchFromGitHub {
              owner = "jkub6";
              repo = "decktape";
              rev = "fix-embedded-fonts";
              hash = "sha256-Vd/HKEh2w8aR6vQgO3t3TylNnJnmiOJIHJQ8Aatcp58=";
            };
            npmDepsHash = "sha256-7I4javLw9SG9sds7nhj78UIuOPrnKm6obUPezGtEDS0=";
            npmDeps = final.fetchNpmDeps {
              inherit src;
              hash = npmDepsHash;
            };
          });
        };

        pkgs = import inputs.nixpkgs {
          inherit system;
          config.allowUnfree = true;
          overlays = [overlay];
        };

        # ---------------------------------------------------------------------
        # Shared Dependencies
        # ---------------------------------------------------------------------

        # Tools required for the build pipeline (runtime)
        commonTools = with pkgs; [
          decktape
          chromium
          ghostscript
          minify
          ninja
          pandoc
        ];

        # Tools for testing
        testDeps = with pkgs.python3Packages; [
          pytest
          pytest-cov
        ];

        # Tools for development only (linters, formatters, utilities)
        devTools = with pkgs; [
          alejandra
          just
          ruff
          statix
          typos
        ];

        # Python environment with ALL dependencies (app + test + dev tools like mypy)
        pythonEnv = pkgs.python3.withPackages (ps: [
          # App dependencies
          ps.pyyaml
          ps.pydantic
          ps.tqdm
          ps.rich

          # Test dependencies
          ps.pytest
          ps.pytest-cov

          # Type checking (must be in the same env to see packages)
          ps.mypy
        ]);
      in {
        # Python package definition for Dojo
        packages.default = pkgs.python3Packages.buildPythonPackage {
          pname = "dojo";
          version = "0.1.0";
          pyproject = true;
          src = ./.;

          build-system = [pkgs.python3Packages.hatchling];

          propagatedBuildInputs = with pkgs.python3Packages; [
            pyyaml
            pydantic
            tqdm
            rich
          ];

          nativeBuildInputs = [pkgs.makeWrapper];

          # Wrap the binary with all necessary runtime tools
          postInstall = ''
            wrapProgram $out/bin/dojo \
              --prefix PATH : ${pkgs.lib.makeBinPath commonTools}
          '';

          nativeCheckInputs = testDeps;
        };

        # Development Environment
        devShells.default = pkgs.mkShell {
          # Inputs from package NOT used to avoid contaminating PYTHONPATH
          # inputsFrom = [self'.packages.default];

          packages =
            commonTools
            ++ [pythonEnv]
            ++ devTools;

          shellHook = ''
            export PYTHONPATH=$PWD/src:$PYTHONPATH
            alias dojo="python3 -m dojo"
            echo "🥷 Dojo Environment Loaded"
            echo "Tools available: dojo, ninja, pandoc, decktape, minify, ghostscript"
            echo "Development mode: Source code in ./src is added to PYTHONPATH"
          '';
        };

        formatter = pkgs.nixfmt-rfc-style;
      };
    };
}
