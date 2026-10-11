#!/usr/bin/env bash
# Runs the whole Kalista DPS checker pipeline (Python 3, no packages):
# spikes.json (full-fight goals) -> lane.json (lane trades) -> kalista_spikes.html.
# Same as ./kalista run; pass scenario flags there (./kalista run --help).
set -euo pipefail
cd "$(dirname "$0")"
python3 kalista run "$@"
echo "Done: open kalista_spikes.html"
