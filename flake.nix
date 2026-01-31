{
  description = "Dojo: Professional Ninja Build Generator";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

    citeproc-src = {
      url = "github:jgm/citeproc";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
    };

    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.nixpkgs.follows = "nixpkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
    };
  };

  outputs = {
    self,
    nixpkgs,
    citeproc-src,
    pyproject-nix,
    uv2nix,
    pyproject-build-systems,
  }: let
    # forAllSystems = nixpkgs.lib.genAttrs ["x86_64-linux" "aarch64-linux"];
    forAllSystems = nixpkgs.lib.genAttrs ["x86_64-linux"];

    # Helper to build the custom Pandoc binary package
    mkPandoc = pkgs: let
      version = "3.8.3-jake";
      inherit (pkgs.stdenv.hostPlatform) system;
      sources = {
        "x86_64-linux" = {
          url = "https://github.com/jkub6/pandoc/releases/download/jake-test/nightly-linux.zip";
          hash = "sha256-l34bkcPDV09vDab4qRt8oEZdxaFD8NUFpsEf6ys82Dk=";
        };
      };
      source = sources.${system} or (throw "Unsupported system: ${system}");
    in
      pkgs.stdenv.mkDerivation {
        pname = "pandoc-bin";
        inherit version;
        src = pkgs.fetchurl source;

        # 1. Add autoPatchelfHook to fix the binary
        nativeBuildInputs = [
          pkgs.unzip
          pkgs.autoPatchelfHook
        ];

        # 2. Add dependencies the binary likely needs to link against
        # Pandoc (Haskell) usually needs gmp, zlib, and standard C++ libs
        buildInputs = [
          pkgs.gmp
          pkgs.zlib
          pkgs.stdenv.cc.cc.lib
        ];

        setSourceRoot = "sourceRoot=$(echo pandoc-nightly-linux-*)";

        installPhase = ''
          runHook preInstall
          mkdir -p $out/bin
          cp pandoc $out/bin/pandoc
          chmod +x $out/bin/pandoc

          if [ -d "share" ]; then
            mkdir -p $out/share/man/man1
            cp -r share/man/man1/* $out/share/man/man1/
          fi
          runHook postInstall
        '';
      };

    mkPythonSet = pkgs: workspace:
      (pkgs.callPackage pyproject-nix.build.packages {python = pkgs.python314;}).overrideScope (
        pkgs.lib.composeManyExtensions [
          pyproject-build-systems.overlays.default
          (workspace.mkPyprojectOverlay {sourcePreference = "wheel";})
        ]
      );

    getRuntimeDeps = pkgs:
      with pkgs; [
        chromium
        decktape
        ghostscript
        typst
        minify
        ninja
        (mkPandoc pkgs)
      ];
  in {
    packages = forAllSystems (system: let
      pkgs = nixpkgs.legacyPackages.${system};
      workspace = uv2nix.lib.workspace.loadWorkspace {workspaceRoot = ./.;};
      pythonSet = mkPythonSet pkgs workspace;
      venv = pythonSet.mkVirtualEnv "dojo-venv" workspace.deps.default;
      pandoc = mkPandoc pkgs;
    in {
      default = pkgs.stdenvNoCC.mkDerivation {
        pname = "dojo";
        version = "0.1.0";
        src = ./.;

        nativeBuildInputs = [pkgs.makeWrapper];

        installPhase = ''
          mkdir -p $out/bin
          makeWrapper ${venv}/bin/dojo $out/bin/dojo \
            --unset PYTHONPATH \
            --prefix PATH : ${pkgs.lib.makeBinPath (getRuntimeDeps pkgs)} \
            --set DOJO_PANDOC "${pandoc}/bin/pandoc" \
            --set DOJO_TYPST "${pkgs.typst}/bin/typst" \
            --set DOJO_MINIFY "${pkgs.minify}/bin/minify" \
            --set DOJO_GHOSTSCRIPT "${pkgs.ghostscript}/bin/gs" \
            --set DOJO_DECKTAPE "${pkgs.decktape}/bin/decktape"
        '';

        meta = with pkgs.lib; {
          description = "Professional Ninja Build Generator";
          homepage = "https://github.com/jkub6/dojo";
          license = licenses.mit;
          platforms = platforms.linux; # Adjusted based on your binary targets
          mainProgram = "dojo";
        };
      };
    });

    devShells = forAllSystems (system: let
      pkgs = nixpkgs.legacyPackages.${system};
      workspace = uv2nix.lib.workspace.loadWorkspace {workspaceRoot = ./.;};
      pythonSet = mkPythonSet pkgs workspace;
      venv = pythonSet.mkVirtualEnv "dojo-dev-venv" workspace.deps.all;

      devTools = with pkgs; [
        alejandra
        just
        uv
        ruff
        statix
        typos
      ];
    in {
      default = pkgs.mkShell {
        packages = (getRuntimeDeps pkgs) ++ devTools ++ [venv];

        shellHook = ''
          unset PYTHONPATH
          export UV_PYTHON_DOWNLOADS=never
          echo "🥷 Dojo Development Environment"
        '';
      };
    });

    formatter = forAllSystems (system: nixpkgs.legacyPackages.${system}.alejandra);
  };
}
