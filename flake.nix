{
  description = "Dojo: Professional Ninja Build Generator";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

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
    pyproject-nix,
    uv2nix,
    pyproject-build-systems,
  }: let
    forAllSystems = nixpkgs.lib.genAttrs ["x86_64-linux" "aarch64-linux"];

    workspace = uv2nix.lib.workspace.loadWorkspace {workspaceRoot = ./.;};

    mkPythonSet = pkgs:
      (pkgs.callPackage pyproject-nix.build.packages {python = pkgs.python314;}).overrideScope (
        pkgs.lib.composeManyExtensions [
          pyproject-build-systems.overlays.default
          (workspace.mkPyprojectOverlay {sourcePreference = "wheel";})
        ]
      );

    pandoc-bin = pkgs: let
      version = "3.8.3";
      inherit (pkgs.stdenv.hostPlatform) system;
      sources = {
        "x86_64-linux" = {
          url = "https://github.com/jgm/pandoc/releases/download/${version}/pandoc-${version}-linux-amd64.tar.gz";
          hash = "sha256-wiT6uJ+CfTYjOA7LfBB4wWPHachJoUrCfo07+7kUybQ=";
        };
        "aarch64-linux" = {
          url = "https://github.com/jgm/pandoc/releases/download/${version}/pandoc-${version}-linux-arm64.tar.gz";
          hash = "sha256-FmpaNzh+sQvUxPJCqBCb7vdVrB6NTrA5xrXr0dkY2Nc=";
        };
      };
      source = sources.${system} or (throw "Unsupported system: ${system}");
    in
      pkgs.stdenv.mkDerivation {
        pname = "pandoc-bin";
        inherit version;
        src = pkgs.fetchurl source;
        installPhase = ''
          mkdir -p $out/bin $out/share/man/man1
          cp bin/pandoc $out/bin/
          cp share/man/man1/pandoc.1.gz $out/share/man/man1/
        '';
      };

    runtimeDeps = pkgs:
      with pkgs; [
        chromium
        decktape
        ghostscript
        typst
        minify
        ninja
        # pandoc
        (pandoc-bin pkgs)
      ];
  in {
    packages = forAllSystems (system: let
      pkgs = nixpkgs.legacyPackages.${system};
      pythonSet = mkPythonSet pkgs;
      venv = pythonSet.mkVirtualEnv "dojo-venv" workspace.deps.default;
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
            --prefix PATH : ${pkgs.lib.makeBinPath (runtimeDeps pkgs)}
        '';

        meta = with pkgs.lib; {
          description = "Professional Ninja Build Generator";
          homepage = "https://github.com/jkub6/dojo";
          license = licenses.mit;
          platforms = platforms.unix;
          mainProgram = "dojo";
        };
      };
    });

    devShells = forAllSystems (system: let
      pkgs = nixpkgs.legacyPackages.${system};
      pythonSet = mkPythonSet pkgs;
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
        packages = (runtimeDeps pkgs) ++ devTools ++ [venv];

        shellHook = ''
          unset PYTHONPATH
          echo "🥷 Dojo Development Environment"
        '';
      };
    });

    formatter = forAllSystems (system: nixpkgs.legacyPackages.${system}.alejandra);
  };
}
