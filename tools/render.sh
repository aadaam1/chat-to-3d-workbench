#!/usr/bin/env bash
# Render an STL to PNG, three-quarter view from above, for a quick look.
#   tools/render.sh <part.stl> <out.png> [WxH] [rot_x,rot_y,rot_z]
# Needs OpenSCAD (tools/setup.sh). Paths may be relative.
set -euo pipefail
. "$(dirname "$0")/env.sh"
abspath () { (cd "$(dirname "$1")" && echo "$(pwd)/$(basename "$1")"); }
stl=$(abspath "${1:?usage: tools/render.sh part.stl out.png [WxH] [rx,ry,rz]}")
mkdir -p "$(dirname "${2:?output png}")"
out=$(abspath "$2")
size=${3:-800,900}; size=${size/x/,}
rot=${4:-62,0,25}
tmpd=$(mktemp -d "${TMPDIR:-/tmp}/render.XXXXXX")
trap 'rm -rf "$tmpd"' EXIT
echo "import(\"$stl\");" > "$tmpd/view.scad"
headless scad_view --projection=p --camera=0,0,0,$rot,0 --viewall --autocenter \
  --imgsize="$size" --colorscheme=Tomorrow -o "$out" "$tmpd/view.scad" >/dev/null 2>&1
echo "$out"
