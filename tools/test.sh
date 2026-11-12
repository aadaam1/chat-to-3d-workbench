#!/usr/bin/env bash
# Run every regression check and print PASS, or name what failed.
#   tools/test.sh                    everything (a few minutes: it rebuilds the aerator)
#   tools/test.sh --update-baseline  rewrite tests/baseline/*.json from a fresh
#                                    build, on purpose (say why in the commit)
# Nothing here calls an AI model.
set -uo pipefail
cd "$(dirname "$0")/.."
. tools/env.sh

UPDATE=0
case "${1:-}" in
  "") ;;
  --update-baseline) UPDATE=1 ;;
  *) echo "usage: tools/test.sh [--update-baseline]" >&2; exit 2 ;;
esac

if ! "$PY" -c "import pytest, trimesh" 2>/dev/null; then
  echo "pytest or trimesh missing: run tools/setup.sh" >&2
  exit 1
fi

START=$(date +%s)
failed=""

echo "== pytest (aerator baseline, tools) =="
if [ $UPDATE = 1 ]; then
  UPDATE_BASELINE=1 "$PY" -m pytest -q tests/test_aerator.py || failed="$failed pytest"
  echo "baseline rewritten: review 'git diff tests/baseline' before committing"
else
  "$PY" -m pytest -q tests || failed="$failed pytest"
fi

if [ $UPDATE = 0 ]; then
  echo "== selftest =="
  tools/selftest.sh > /tmp/test-selftest.$$ 2>&1
  if tail -1 /tmp/test-selftest.$$ | grep -qx READY; then
    echo "READY"
  else
    cat /tmp/test-selftest.$$; failed="$failed selftest"
  fi
  rm -f /tmp/test-selftest.$$
fi

echo "($(( $(date +%s) - START )) s)"
if [ -n "$failed" ]; then
  echo "FAILED:$failed"
  exit 1
fi
[ $UPDATE = 1 ] || echo PASS
