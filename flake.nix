{
  description = "Dojo - A static site and document generator built on Pandoc and Typst";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

    flake-parts.url = "github:hercules-ci/flake-parts";

    treefmt-nix = {
      url = "github:numtide/treefmt-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    treefmt-nix-config.url = "git+ssh://git@github.com/jkub6/treefmt-nix-config";
  };

  outputs = inputs @ {flake-parts, ...}:
    flake-parts.lib.mkFlake {inherit inputs;} {
      # 1. Broadened system support for maximum compatibility
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        # "x86_64-darwin"
        # "aarch64-darwin"
      ];

      # 2. Global flake module imports
      imports = [
        inputs.treefmt-nix.flakeModule
      ];

      # 3. System-agnostic outputs (Overlay)
      flake = {
        overlays.default = final: prev: {
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

                  pytestFlagsArray = [
                    "--deselect=tests/test_e2e_tools.py::TestOptionalToolsPipeline::test_generates_and_executes_tools"
                  ];

                  preCheck = ''
                    export HOME=$(mktemp -d)
                    export XDG_CONFIG_HOME=$HOME/.config
                    export XDG_CACHE_HOME=$HOME/.cache
                    export XDG_DATA_HOME=$HOME/.local/share
                  '';

                  meta = with final.lib; {
                    description = "A static site and document generator built on Pandoc and Typst";
                    homepage = "https://github.com/jkub6/dojo";
                    license = licenses.mit;
                    mainProgram = "dojo"; # Explicit mainProgram mapping
                  };
                };
              })
            ];
        };
      };

      # 4. System-specific outputs (Packages, Checks, Shells, Formatting)
      perSystem = {
        config,
        pkgs,
        system,
        ...
      }: let
        # Apply the overlay locally so `pkgs` includes `python3.pkgs.dojo`
        localPkgs = pkgs.extend inputs.self.overlays.default;
        python = localPkgs.python3;
      in {
        # Default package output
        packages.default = python.pkgs.dojo;

        # CI Checks
        checks = {
          build = python.pkgs.dojo;
        };

        # 5. Treefmt configuration mapped flawlessly via module system
        treefmt = {
          imports = [inputs.treefmt-nix-config.treefmtModule];
        };

        devShells.default = localPkgs.mkShell {
          # Pull in all build/check inputs declared on the package itself.
          inputsFrom = [python.pkgs.dojo];

          packages = with localPkgs; [
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

            # Treefmt exposed as an executable wrapper in your shell
            config.treefmt.build.wrapper

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
      };
    };
}
