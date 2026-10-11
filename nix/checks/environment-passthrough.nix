# Regression check: `dojo build` must hand the caller's PATH to the build steps it
# spawns, unmodified.
#
# Ninja, Pandoc and Pandoc filters resolve programs (most importantly `python3`
# for Python filters) from PATH. nixpkgs' default Python program wrapper prepends
# the package's bare interpreter to PATH, which shadowed the user's interpreter
# and broke filters that import third-party packages such as panflute.
#
# This check replaces `ninja` and `pandoc` with stubs where `ninja` records the PATH
# it receives and exercises both supported entry points: the standalone package
# (`nix run`, `nix profile install`) and a `python.withPackages` environment
# (the usual way dojo is consumed from a downstream flake).
{
  lib,
  runCommand,
  runtimeShell,
  python,
}: let
  launchers = {
    package = lib.getExe python.pkgs.dojo;
    python-env = lib.getExe' (python.withPackages (ps: [ps.dojo])) "dojo";
  };
in
  runCommand "dojo-environment-passthrough" {} ''
    set -euo pipefail

    export HOME="$TMPDIR"

    mkdir -p stub project/content
    cat > stub/ninja <<EOF
    #!${runtimeShell}
    printf '%s' "\$PATH" > "\$DOJO_CAPTURE"
    EOF
    chmod +x stub/ninja

    cat > stub/pandoc <<EOF
    #!${runtimeShell}
    exit 0
    EOF
    chmod +x stub/pandoc

    cat > project/dojo.yaml <<'EOF'
    src_dir: content
    output_dir: _site
    build_dir: _build
    default_type: page
    types:
      page:
        outputs: []
    EOF

    export PATH="$PWD/stub:$PATH"

    check() {
      local name="$1" exe="$2"
      local capture="$TMPDIR/$name.path"

      (cd project && DOJO_CAPTURE="$capture" "$exe" --quiet build)

      if [[ ! -f "$capture" ]]; then
        echo "FAIL ($name): stub ninja was never invoked" >&2
        exit 1
      fi
      if [[ "$(< "$capture")" != "$PATH" ]]; then
        echo "FAIL ($name): dojo modified PATH for build steps" >&2
        echo "  expected: $PATH" >&2
        echo "  received: $(< "$capture")" >&2
        exit 1
      fi
      echo "ok ($name): PATH passed through unchanged"
    }

    ${lib.concatStringsSep "\n" (lib.mapAttrsToList (name: exe: "check ${lib.escapeShellArg name} ${lib.escapeShellArg exe}") launchers)}

    touch "$out"
  ''
