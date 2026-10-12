{
  description = "Dojo - A static site and document generator powered by Ninja and Pandoc";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

    flake-parts.url = "github:hercules-ci/flake-parts";

    treefmt-nix = {
      url = "github:numtide/treefmt-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    treefmt-nix-config.url = "github:jkub6/treefmt-nix-config";
  };

  outputs = inputs @ {flake-parts, ...}:
    flake-parts.lib.mkFlake {inherit inputs;} {
      # 1. Broadened system support for maximum compatibility
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        # macOS support is untested; uncomment when CI covers Darwin:
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
                  pname = "dojo-ssg";
                  version = (builtins.fromTOML (builtins.readFile ./pyproject.toml)).project.version;
                  pyproject = true;

                  src = final.lib.cleanSource ./.;

                  propagatedBuildInputs = with python-final; [
                    pyyaml
                    pydantic
                    tqdm
                    rich
                    zstandard
                  ];

                  nativeBuildInputs = [
                    python-final.hatchling
                  ];

                  # Dojo spawns external tools (Ninja, Pandoc, Pandoc filters, Typst, ...)
                  # that resolve programs such as `python3` from PATH, so it must pass the
                  # caller's environment through untouched. The default wrapPythonPrograms
                  # launcher prepends the bare build interpreter and every dependency's
                  # bin/ directory to PATH and exports PYTHONNOUSERSITE; both leak into
                  # child processes and shadow the user's interpreter, e.g. Pandoc filters
                  # can no longer import panflute. Instead, bake the dependency search path
                  # into the entry point (as wrapPythonPrograms does internally) and pass
                  # `-s` on the shebang so user site-packages stay isolated for this process
                  # only. Covered by checks.environment-passthrough.
                  dontWrapPythonPrograms = true;
                  postFixup = ''
                    buildPythonPath "$out"
                    patchPythonScript "$out/bin/dojo"

                    if ! head -n 1 "$out/bin/dojo" | grep -q '^#!/nix/store/[^ ]*/bin/python[0-9.]*$'; then
                      echo "error: unexpected shebang in $out/bin/dojo: $(head -n 1 "$out/bin/dojo")" >&2
                      exit 1
                    fi
                    sed -i '1s/$/ -s/' "$out/bin/dojo"
                  '';

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
                    final.chromium
                    final.nodejs
                    final.ninja
                    final.pandoc
                    final.typst
                    final.decktape
                    final.minify
                    final.ghostscript
                  ];

                  dontUsePytestXdist = true; # Keep tool-heavy tests within a bounded worker count.
                  pytestFlags = ["-n4"];

                  # Browser tests need explicit fonts inside the isolated builder.
                  FONTCONFIG_FILE = final.makeFontsConf {
                    fontDirectories = [final.dejavu_fonts final.noto-fonts-cjk-sans];
                  };
                  DOJO_TEST_REVEALJS = final.callPackage ./nix/checks/revealjs.nix {};

                  preCheck = ''
                    export HOME=$(mktemp -d)
                    export XDG_CONFIG_HOME=$HOME/.config
                    export XDG_CACHE_HOME=$HOME/.cache
                    export XDG_DATA_HOME=$HOME/.local/share
                  '';

                  meta = with final.lib; {
                    description = "A static site and document generator powered by Ninja and Pandoc";
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
          environment-passthrough = localPkgs.callPackage ./nix/checks/environment-passthrough.nix {
            inherit python;
          };
        };

        # 5. Treefmt configuration mapped flawlessly via module system
        treefmt = {
          imports = [inputs.treefmt-nix-config.treefmtModule];
          settings.global.excludes = ["src/dojo/resources/fzstd.js"];
        };

        devShells.default = localPkgs.mkShell {
          # Pull in all build/check inputs declared on the package itself.
          inputsFrom = [python.pkgs.dojo];

          packages = with localPkgs; [
            just
            nvd
            chromium
            nodejs
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
              p.dojo
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

          env = {
            inherit (python.pkgs.dojo) FONTCONFIG_FILE DOJO_TEST_REVEALJS;
          };

          shellHook = ''
            # Bind the local src directory globally for transparent editable execution.
            export PYTHONPATH="$(pwd)/src:''${PYTHONPATH:-}"
          '';
        };
      };
    };
}
