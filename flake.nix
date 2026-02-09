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
    forAllSystems = nixpkgs.lib.genAttrs ["x86_64-linux" "aarch64-linux"];
    # forAllSystems = nixpkgs.lib.genAttrs ["x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin"];

    mkPandoc = pkgs: let
      version = "3.9";
      
      # Determine suffix based on system
      suffix = {
        "x86_64-linux"   = "linux-amd64.tar.gz";
        "aarch64-linux"  = "linux-arm64.tar.gz";
        "x86_64-darwin"  = "x86_64-macOS.zip";
        "aarch64-darwin" = "arm64-macOS.zip"; 
      }.${pkgs.system} or (throw "Unsupported system: ${pkgs.system}");

      url = "https://github.com/jgm/pandoc/releases/download/${version}/pandoc-${version}-${suffix}";
    in
    pkgs.stdenv.mkDerivation {
      pname = "pandoc-bin";
      inherit version;

      src = pkgs.fetchurl {
        inherit url;
        hash = "sha256-hyoQx+wp1SeIMdhVsRvUreDfTV7JoImjGXvGOjfrQAM="; 
      };

      nativeBuildInputs = [ pkgs.unzip pkgs.installShellFiles ];

      installPhase = ''
        mkdir -p $out/bin
        # Handle the different directory structures of zip vs tar.gz
        if [ -d bin ]; then
          cp bin/pandoc $out/bin/
        else
          # Fallback for flat archives or different layouts
          cp pandoc $out/bin/ || cp */bin/pandoc $out/bin/
        fi
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
          platforms = platforms.all; 
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
