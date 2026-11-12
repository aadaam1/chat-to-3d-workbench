#!/usr/bin/env bash
# Start a new project, or add a part to an existing one, from the template.
#   tools/newpart.sh <project>            -> projects/<project>/<project>.scad (+ README.md)
#   tools/newpart.sh <project> <part>     -> projects/<project>/<part>.scad
# New work always goes in projects/ (ignored by git), never in examples/.
set -euo pipefail
cd "$(dirname "$0")/.."
project=${1:?usage: tools/newpart.sh <project> [part]   (lowercase; project may use -, part uses _)}
part=${2:-${project//-/_}}
[[ $project =~ ^[a-z0-9][a-z0-9_-]*$ ]] || { echo "project: lowercase letters, digits, - and _ only" >&2; exit 2; }
[[ $part =~ ^[a-z0-9_]+$ ]]             || { echo "part: lowercase letters, digits and _ only" >&2; exit 2; }

dir="projects/$project"
out="$dir/$part.scad"
[ -e "$out" ] && { echo "$out already exists" >&2; exit 1; }
mkdir -p "$dir"
sed -e "s/__NAME__/$part/g" -e "s/__PROJECT__/$project/g" templates/part.scad > "$out"
echo "created $out"

if [ ! -e "$dir/README.md" ]; then
  cat > "$dir/README.md" <<EOF
# $project

What it does, what it mates with, and where it lives (outdoors? water? load?).

## Measured
The mating part, measured with calipers -- not the listing. Diameters, thread
pitch *and length*, depths. How each number was measured.

## Parts
| Part | Source | Build |
|---|---|---|
| $part | \`$part.scad\` | \`tools/build_part.sh $project/$part resin_sla fdm_asa\` |

## Status
Nothing printed yet.
EOF
  echo "created $dir/README.md"
fi
echo "next: edit it, then  tools/build_part.sh $project/$part resin_sla fdm_asa"
