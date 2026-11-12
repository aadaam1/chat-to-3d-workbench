# Sourced by every build script. Works on Linux (cloud sessions) and macOS,
# and in bash 3.2, which is what macOS ships.
#
# Sets
#   PY        Python with the workshop's packages: .venv/bin/python when
#             tools/setup.sh made one (macOS), else python3
#   OPENSCAD  the OpenSCAD binary: $OPENSCAD if set, else PATH, else the macOS app
# Defines
#   scad ...      OpenSCAD, with the fast Manifold engine where the build has it
#   headless ...  run a command that draws a PNG: under xvfb on a Linux box
#                 without a display, directly everywhere else

WS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# A git worktree (.worktrees/<name>, one per parallel session) has no .venv of
# its own: use the main checkout's.
# (--git-common-dir is relative in a plain clone, hence the absolute form; the
# trailing || true keeps `set -e` scripts alive where there is no git.)
MAIN_ROOT="$(cd "$(git -C "$WS_ROOT" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || echo "$WS_ROOT/.git")/.." 2>/dev/null && pwd)" || MAIN_ROOT=""
if [ -x "$WS_ROOT/.venv/bin/python" ]; then
  PY="$WS_ROOT/.venv/bin/python"
elif [ -n "$MAIN_ROOT" ] && [ -x "$MAIN_ROOT/.venv/bin/python" ]; then
  PY="$MAIN_ROOT/.venv/bin/python"
else
  PY=python3
fi

[ "$(uname)" = Linux ] && PATH="$HOME/.local/bin:$PATH"   # where setup.sh puts OpenSCAD
if [ -z "${OPENSCAD:-}" ]; then
  OPENSCAD=$(command -v openscad || true)
  if [ -z "$OPENSCAD" ] && [ -x /Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD ]; then
    OPENSCAD=/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD
  fi
fi
if [ -z "$OPENSCAD" ]; then
  echo "OpenSCAD not found. Run tools/setup.sh, or set OPENSCAD=/path/to/openscad." >&2
  exit 1
fi
export PY OPENSCAD   # scad2step.py reads OPENSCAD too

# Geometry engines. OpenSCAD 2021.01 (apt, cloud) has only CGAL; snapshots
# (Homebrew openscad@snapshot) also have Manifold, which is many times faster.
#   Exports (STL/3MF) use CGAL: it is exact. Manifold leaves faces that merely
#   touch -- a bed chamfer meeting the body, a thread meeting its core -- as
#   edges shared by four faces, and print services reject those meshes as
#   non-manifold. (Seen on a click-on nozzle, Nov 2026; same volume, bad mesh.)
#   Renders (PNG) use Manifold where available: a picture can't be non-manifold.
# Override with SCAD_EXPORT_ENGINE=Manifold for a quick look at a slow model.
if "$OPENSCAD" --help 2>&1 | grep -q -- '--backend'; then
  SCAD_ENGINE="--backend=${SCAD_EXPORT_ENGINE:-CGAL}"
  SCAD_VIEW_ENGINE="--backend=Manifold"
else
  SCAD_ENGINE=""
  SCAD_VIEW_ENGINE=""
fi

scad () {       # exports and anything measured
  # the engine variables are deliberately unquoted: empty means no argument
  "$OPENSCAD" $SCAD_ENGINE "$@"
}

# project_dir <name-or-path>: where a project lives. A bare name is looked up
# in projects/ (your own designs, ignored by git) first, then examples/.
# A path (projects/x, examples/x) is used as given. Prints nothing and returns
# 1 when there is no such folder.
project_dir () {
  case "$1" in
    */*) [ -d "$1" ] && { echo "${1%/}"; return 0; } ;;
    *) for _d in projects examples; do
         [ -d "$_d/$1" ] && { echo "$_d/$1"; return 0; }
       done ;;
  esac
  return 1
}

scad_view () {  # PNG renders only
  "$OPENSCAD" $SCAD_VIEW_ENGINE "$@"
}

headless () {
  if [ "$(uname)" = Linux ] && [ -z "${DISPLAY:-}" ] && command -v xvfb-run >/dev/null; then
    # xvfb-run starts a program, not a shell function (scad_view), and its
    # sh drops exported functions: have bash source this file again under it
    OPENSCAD="$OPENSCAD" xvfb-run -a bash -c '. "$0/tools/env.sh"; "$@"' "$WS_ROOT" "$@"
  else
    "$@"
  fi
}
