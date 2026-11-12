#!/usr/bin/env bash
# Build one part for one or more processes: STL, STEP, printability check, renders.
#
#   tools/build_part.sh <project>[/<part>] [process ...] [-- -D 'X=1' ...]
#
#   project   projects/<project>/ (else examples/<project>/)
#   part      <project folder>/<part>.scad   (default: <project>, with - as _)
#   process   resin_sla fdm_asa slm_316l slm_alsi10mg mjf_pa12  (default: resin_sla fdm_asa)
#   after --  extra OpenSCAD -D overrides, applied to every build
#
# Writes, all under <project folder>/out/<part>/ (not committed):
#   <part>_<process>.stl              binary STL
#   <part>_<process>.check.md|json    tools/partcheck.py report
#   <part>_<process>.step             editable solid (if OCP is installed)
#   <part>_<process>.png, _section.png
#   versions/v<N>/                    a new design version whenever the files changed
#                                     (NOTE="what changed" tools/build_part.sh ... labels it)
#
# Exits non-zero if any build fails the check, after building all of them.
set -uo pipefail
cd "$(dirname "$0")/.."
. tools/env.sh

spec=${1:?usage: tools/build_part.sh <project>[/<part>] [process ...] [-- -D X=1 ...]}; shift
project=${spec%%/*}
part=${spec#*/}; [ "$part" = "$spec" ] && part=${project//-/_}
procs=(); extra=()
while [ $# -gt 0 ]; do
  if [ "$1" = "--" ]; then shift; extra=("$@"); break; fi
  procs+=("$1"); shift
done
[ ${#procs[@]} -eq 0 ] && procs=(resin_sla fdm_asa)

dir=$(project_dir "$project") || { echo "no project $project in projects/ or examples/ (tools/newpart.sh $project makes one)" >&2; exit 2; }
src="$dir/$part.scad"
[ -f "$src" ] || { echo "no $src (tools/newpart.sh $project $part makes one)" >&2; exit 2; }
out="$dir/out/$part"
mkdir -p "$out"
have_ocp=$("$PY" -c "import OCP" 2>/dev/null && echo 1 || echo 0)
status=0

for p in "${procs[@]}"; do
  base="${part}_${p}"
  defs=(-D "PROCESS=\"$p\"" ${extra[@]+"${extra[@]}"})
  echo "== $project/$base"

  # STL, with OpenSCAD's own validity lines
  if ! scad --export-format binstl "${defs[@]}" -o "$out/$base.stl" "$src" 2>&1 \
       | grep -E "ERROR|WARNING|Simple:|Volumes:" | sed 's/^/   /'; then :; fi
  [ -s "$out/$base.stl" ] || { echo "   STL export failed"; status=1; continue; }

  # STEP
  if [ "$have_ocp" = 1 ]; then
    "$PY" tools/scad2step.py "$src" "$out/$base.step" "${defs[@]}" \
      | grep -E "solid|scad2step" | sed 's/^/   /' || true
  fi

  # check
  "$PY" tools/partcheck.py "$out/$base.stl" --process "$p" \
      --json "$out/$base.check.json" --md "$out/$base.check.md" > /dev/null
  rc=$?
  verdict=$("$PY" -c "import json,sys; r=json.load(open(sys.argv[1])); \
print(r['verdict'].upper(), '|', r['volume_cm3'], 'cm3 |', 'thinnest', r['thinnest_mm'], 'mm |', \
'cost', ('\$'+str(r['cost_usd'])) if r['cost_usd'] else 'n/a')" "$out/$base.check.json")
  echo "   check: $verdict   ($out/$base.check.md)"
  [ $rc -ne 0 ] && status=1

  # renders: outside, and cut in half
  tools/render.sh "$out/$base.stl" "$out/$base.png" >/dev/null 2>&1 || true
  headless scad_view "${defs[@]}" -D 'PART="section"' --colorscheme=Tomorrow \
      --camera=0,0,0,62,0,25,0 --viewall --autocenter --imgsize=800,800 \
      -o "$out/${base}_section.png" "$src" >/dev/null 2>&1 || true
done

# every build that changed the files becomes a new design version (local only)
"$PY" tools/versions.py snapshot "$out/versions" "$out"/*.stl --note "${NOTE:-}"

echo "done. Preview: $PY tools/make_viewer.py --title '$part' --out $dir/out/viewer --process ${procs[0]} --versions $out/versions"
exit $status
