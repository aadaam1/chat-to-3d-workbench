#!/usr/bin/env bash
# Build a timber structure from its description: the frame, the checks, the
# shopping list, a saved version, and the command for the preview.
#   tools/build_frame.sh <project> [spec.json]
#       <project>   a folder under projects/ (or examples/) holding the description
#                   (default structure.json; an older shed.json still works)
#   NOTE="taller door" tools/build_frame.sh garden-shed     labels the version
#   PRICES=hu tools/build_frame.sh garden-shed               price the list from the newest hu-* snapshot
#   TITLE="Bike shed"                                        the preview's title (default: the project name)
# Output goes to <project folder>/out/ (never committed):
#   frame.json  checks.json  bom.json  bom.md  cutlist.csv  versions/v<N>/
set -uo pipefail
cd "$(dirname "$0")/.."
. tools/env.sh

proj=${1:?usage: tools/build_frame.sh <project> [spec.json]}
dir=$(project_dir "$proj") || { echo "no spec: no project $proj in projects/ or examples/" >&2; exit 1; }
if [ -n "${2:-}" ]; then
  spec="$dir/$2"
elif [ -f "$dir/structure.json" ]; then
  spec="$dir/structure.json"
else
  spec="$dir/shed.json"
fi
[ -f "$spec" ] || { echo "no spec at $spec" >&2; exit 1; }
out="$dir/out"
mkdir -p "$out"

"$PY" tools/frame.py "$spec" --out "$out/frame.json" || exit 1

"$PY" tools/framecheck.py "$out/frame.json" --out "$out/checks.json" || exit 1

# prices: the newest snapshot for the region named by PRICES
region=${PRICES:-}
snap=""
if [ -n "$region" ]; then
  snap=$(ls data/timber/prices/"$region"-*.csv 2>/dev/null | sort | tail -1)
  [ -n "$snap" ] || echo "   no price snapshot for '$region' in data/timber/prices/: the list has no prices"
fi
if [ -n "$snap" ]; then
  "$PY" tools/bom.py "$out/frame.json" --snapshot "$snap" --out "$out" || exit 1
else
  "$PY" tools/bom.py "$out/frame.json" --out "$out" || exit 1
fi

# a build whose files changed becomes a new version (local only)
"$PY" tools/versions.py snapshot "$out/versions" "$out/frame.json" "$out/checks.json" "$out/bom.json" \
    "$out/bom.md" "$out/cutlist.csv" --note "${NOTE:-}"

# the preview's title: TITLE, else the description's name, else the project folder's name (never the path)
title=${TITLE:-$("$PY" -c "
import json, os, sys
name = ''
try:
    name = json.load(open(sys.argv[1], encoding='utf-8')).get('name', '')
except Exception:
    pass
name = name if isinstance(name, str) and name.strip() else os.path.basename(os.path.abspath(sys.argv[2]))
print(name.replace('-', ' ').capitalize())" "$spec" "$dir")}
echo "done. Shopping list: $out/bom.md"
echo "Preview: $PY tools/make_viewer.py --title '$title' --build $out/versions --out $out/viewer"
