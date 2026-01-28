{
  description = "Dojo: Professional Ninja Build Generator";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-parts.url = "github:hercules-ci/flake-parts";
    pyproject-nix.url = "github:pyproject-nix/pyproject.nix";
    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.nixpkgs.follows = "nixpkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
    };
    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
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
        # uv2nix Logic
        # ---------------------------------------------------------------------

        # Load workspace from pyproject.toml/uv.lock
        workspace = inputs.uv2nix.lib.workspace.loadWorkspace {workspaceRoot = ./.;};

        # Create a Python package set
        pythonSet = pkgs.callPackage inputs.pyproject-nix.build.packages {
          python = pkgs.python311;
        };

        # Overlay that provides build systems (like hatchling)
        # and the project itself
        pkgs-overlay = workspace.mkPyprojectOverlay {
          sourcePreference = "wheel";
        };

        # Base overlay for common build systems
        base-overlay = inputs.pyproject-build-systems.overlays.default;

        # The final Python set with our overlays
        python = pythonSet.overrideScope (
          pkgs.lib.composeManyExtensions [
            base-overlay
            pkgs-overlay
          ]
        );

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

        # Tools for development only (linters, formatters, utilities)
        devTools = with pkgs; [
          alejandra
          just
          uv
          ruff
          statix
          typos
        ];
      in {
        # Python package definition for Dojo
        packages.default = let
          # Create a virtualenv containing the project and its runtime dependencies
          venv = python.mkVirtualEnv "dojo-venv" workspace.deps.default;
        in
          pkgs.stdenvNoCC.mkDerivation {
            pname = "dojo";
            version = "0.1.0";
            src = ./.;

            nativeBuildInputs = [pkgs.makeWrapper];

            installPhase = ''
              mkdir -p $out/bin
              makeWrapper ${venv}/bin/dojo $out/bin/dojo \
                --prefix PATH : ${pkgs.lib.makeBinPath commonTools}
            '';
          };

        # Development Environment
        devShells.default = pkgs.mkShell {
          packages =
            commonTools
            ++ devTools
            ++ [
              (python.mkVirtualEnv "dojo-dev-env" workspace.deps.all)
            ];

          env = {
            # Required for many python wheels to link correctly on NixOS
            LD_LIBRARY_PATH = "${pkgs.stdenv.cc.cc.lib}/lib";
          };

          shellHook = ''
            echo "🥷 Dojo Environment Loaded (uv2nix Enabled)"
            echo "Project dependencies are managed by pyproject.toml and uv.lock"

            # Unset PYTHONPATH so it doesn't conflict with our virtualenv
            unset PYTHONPATH
          '';
        };

        formatter = pkgs.nixfmt-rfc-style;
      };
    };
}
