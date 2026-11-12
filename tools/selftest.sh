#!/usr/bin/env bash
# Check the whole toolchain end to end, in about a minute: start a throwaway
# project from the template, build it for one process (STL, STEP, check,
# renders), make a preview page from it, then delete it again.
#   tools/selftest.sh
# Prints "READY" and exits 0 when everything works; says what failed otherwise.
set -uo pipefail
cd "$(dirname "$0")/.."
. tools/env.sh

NAME=zz-selftest
DIR=projects/zz-selftest
OUT=$DIR/out/zz_selftest
TMP=$(mktemp -d "${TMPDIR:-/tmp}/selftest.XXXXXX")
cleanup () { rm -rf projects/zz-selftest "$TMP"; }
trap cleanup EXIT
rm -rf projects/zz-selftest

fail=0
ok   () { echo "  ok    $1"; }
bad  () { echo "  FAIL  $1"; fail=1; }

echo "OpenSCAD: $("$OPENSCAD" --version 2>&1 | tail -1)"
echo "Python:   $("$PY" --version)"

tools/newpart.sh "$NAME" >/dev/null || { echo "FAIL: could not create a project"; exit 1; }
tools/build_part.sh "$NAME" fdm_asa > "$TMP/build.log" 2>&1

[ -s "$OUT/zz_selftest_fdm_asa.stl" ]        && ok "model -> STL"        || bad "model -> STL (see the OpenSCAD lines below)"
[ -s "$OUT/zz_selftest_fdm_asa.check.md" ]   && ok "printability check"  || bad "printability check (Python packages: run tools/setup.sh)"
if "$PY" -c "import OCP" 2>/dev/null; then
  [ -s "$OUT/zz_selftest_fdm_asa.step" ]     && ok "STEP export"         || bad "STEP export"
else
  bad "STEP export (OCP missing: run tools/setup.sh)"
fi
[ -s "$OUT/zz_selftest_fdm_asa.png" ]        && ok "render"              || bad "render"
"$PY" tools/make_viewer.py --title "Self-test" --out "$TMP/view" --process fdm_asa \
    "$OUT/zz_selftest_fdm_asa.stl" >/dev/null 2>&1 \
  && [ -s "$TMP/view/index.html" ]           && ok "preview page"        || bad "preview page"

if [ $fail -ne 0 ]; then
  echo; echo "Build log:"; sed 's/^/  /' "$TMP/build.log"
  echo "NOT READY"
  exit 1
fi
echo "READY"
