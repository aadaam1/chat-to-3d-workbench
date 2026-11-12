#!/usr/bin/env bash
# Build the tap aerator: printable parts, thread gauges, STEP, CFD fluid domain,
# the doc renders, and the handover folder for whoever prints it.
#   examples/tap-aerator/build.sh          full quality (slow)
#   examples/tap-aerator/build.sh fast     coarse facets, for a quick look
#
# Writes (out/ is not committed -- rebuild it, don't edit it):
#   out/stl/       every part and gauge
#   out/step/      the same parts as editable CAD solids (needs cadquery-ocp)
#   out/handover/  the folder to zip and hand over, with PRINT-ME.txt
#   img/           renders used by README.md (committed; a full build refreshes
#                  them, a fast one writes to out/img/ instead)
set -euo pipefail

cd "$(dirname "$0")"
. ../../tools/env.sh
TOOLS=../../tools
SRC=aerator.scad
OUT=out/stl
STEP=out/step
FAST=${1:-}
# fast renders are coarse: keep them out of the README images
IMG=$([ "$FAST" = fast ] && echo out/img || echo img)
Q=$([ "$FAST" = fast ] && echo true || echo false)

mkdir -p "$OUT" "$STEP" "$IMG"
rm -f "$OUT"/*.stl

stl () { # stl <outfile> <extra -D args...>
  local out="$OUT/$1.stl"; shift
  echo "  -> $out"
  scad --export-format binstl -D "FAST=$Q" "$@" -o "$out" "$SRC" 2>&1 \
    | grep -E "WARNING|ERROR|Simple:|Volumes:" | sed 's/^/     /' || true
}

echo "== the part =="
stl aerator_G1            -D 'PART="aerator"'
stl aerator_G34           -D 'PART="aerator"' -D 'TAP_THREAD="G3/4"'
# Shorter: less open bore under the blades, channels at L/D 5. Print it next to
# the standard one and keep it only if the stream stays as even.
COMPACT=(-D 'GAP_H=5' -D 'EXIT_H=10')
stl aerator_G1_compact    -D 'PART="aerator"' "${COMPACT[@]}"
# For metal printing (SLM 316L): thin walls instead of plastic's thick ones,
# flutes that stop below the washer seat, no rim notches, a looser thread to chase with
# a G1 tap afterwards, and holes at nominal size (HOLE_COMP is an FDM fix).
METAL=(-D 'BODY_OD=38.5' -D 'NOSE_OD=29.5' -D 'GRIP_STYLE="flutes_low"' -D 'DRAIN_N=0'
       -D 'HOLE_COMP=0' -D 'TAP_FIT=0.45' -D 'TOP_SLOPE=0.8')
stl aerator_G1_metal         -D 'PART="aerator"' "${METAL[@]}"
stl aerator_G1_metal_compact -D 'PART="aerator"' "${METAL[@]}" "${COMPACT[@]}"

echo "== thread gauges -- print one of these FIRST =="
for c in 0.20 0.25 0.30 0.35 0.40; do
  stl "gauge_G1_${c}"     -D 'PART="gauge"' -D "TAP_FIT=$c"
done
for c in 0.25 0.30 0.35; do
  stl "gauge_G34_${c}"    -D 'PART="gauge"' -D 'TAP_THREAD="G3/4"' -D "TAP_FIT=$c"
done

echo "== STEP, for Fusion and other CAD =="
if "$PY" -c "import OCP" 2>/dev/null; then
  for v in G1 G34; do
    t=$([ $v = G1 ] && echo G1 || echo G3/4)
    "$PY" "$TOOLS/scad2step.py" "$SRC" "$STEP/aerator_$v.step" -D "TAP_THREAD=\"$t\"" \
      | grep -E "solid|scad2step" || true
  done
  "$PY" "$TOOLS/scad2step.py" "$SRC" "$STEP/aerator_G1_compact.step" "${COMPACT[@]}" \
    | grep -E "solid|scad2step" || true
  "$PY" "$TOOLS/scad2step.py" "$SRC" "$STEP/aerator_G1_metal.step" "${METAL[@]}" \
    | grep -E "solid|scad2step" || true
  "$PY" "$TOOLS/scad2step.py" "$SRC" "$STEP/aerator_G1_metal_compact.step" "${METAL[@]}" "${COMPACT[@]}" \
    | grep -E "solid|scad2step" || true
else
  echo "  skipped: pip install cadquery-ocp to export STEP"
fi

echo "== CFD fluid domain =="
stl fluid_domain          -D 'PART="fluid"'

echo "== renders =="
png () { # png <name> <part> <camera> <size>
  echo "  -> $IMG/$1.png"
  headless scad_view -D "FAST=$Q" -D "PART=\"$2\"" --projection=o \
      --camera="$3" --imgsize="$4" --colorscheme=Tomorrow \
      -o "$IMG/$1.png" "$SRC" >/dev/null 2>&1
}
png aerator  aerator  0,0,26,62,0,35,130  800,900
png section  section  0,0,26,72,0,25,175  900,1000
png outlet   aerator  0,0,26,180,0,0,110  800,800
png fluid    fluid    0,0,22,70,0,30,190  800,950

echo "== handover folder =="
# What the person with the printer gets. PRINT-ME.txt names these exact files;
# change both together.
H=out/handover
rm -rf "$H"; mkdir -p "$H/1-gauges-print-these-first" "$H/2-the-part"
cp PRINT-ME.txt "$H/"
for c in 0.25 0.30 0.35; do cp "$OUT/gauge_G1_$c.stl" "$H/1-gauges-print-these-first/gauge_$c.stl"; done
cp "$OUT/aerator_G1.stl"         "$H/2-the-part/aerator_G1_fit0.30.stl"
cp "$OUT/aerator_G1_compact.stl" "$H/2-the-part/aerator_G1_fit0.30_COMPACT.stl"
[ -f "$STEP/aerator_G1.step" ]         && cp "$STEP/aerator_G1.step"         "$H/2-the-part/aerator_G1_fit0.30.step"
[ -f "$STEP/aerator_G1_compact.step" ] && cp "$STEP/aerator_G1_compact.step" "$H/2-the-part/aerator_G1_fit0.30_COMPACT.step"
echo "  -> $H/"

echo "== design version (for the preview's version switcher) =="
# The two ASA parts someone actually prints; a new version only when they changed.
"$PY" ../../tools/versions.py snapshot out/versions \
  "$OUT/aerator_G1.stl" "$OUT/aerator_G1_compact.stl" --note "${NOTE:-}"

echo "done. Preview: $PY ../../tools/make_viewer.py --title 'Garden tap aerator' --out out/viewer --process fdm_asa --versions out/versions"
