#!/usr/bin/env bash
# Make the printable site pack (shopping list and each side drawn) for a built structure.
#   tools/site_pack.sh <project> [--html-only]
# Needs the project's out/ from tools/build_frame.sh. Writes out/site-pack.html and
# out/<project>-site-pack-v<N>.pdf (the PDF needs Google Chrome or Chromium; CHROME=/path to point at it).
set -uo pipefail
cd "$(dirname "$0")/.."
. tools/env.sh

proj=${1:?usage: tools/site_pack.sh <project> [--html-only]}
dir=$(project_dir "$proj") || { echo "no project $proj in projects/ or examples/" >&2; exit 1; }
[ -f "$dir/out/frame.json" ] || { echo "no build in $dir/out: run tools/build_frame.sh $proj first" >&2; exit 1; }
shift
exec "$PY" tools/site_pack.py "$dir/out" "$@"
