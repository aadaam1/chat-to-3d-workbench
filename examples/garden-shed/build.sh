#!/usr/bin/env bash
# The example shed: frame, checks, shopping list priced from the Hungarian
# snapshot, and a saved version. See tools/build_frame.sh.
cd "$(dirname "$0")/../.."
PRICES=${PRICES:-hu} exec tools/build_frame.sh garden-shed
