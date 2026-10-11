#!/usr/bin/env bash
# Runs the whole Kalista DPS checker pipeline in order (~80 s, Python 3, no packages).
set -euo pipefail
cd "$(dirname "$0")"
python3 spikes.py      # full-fight goals, duel calibration      -> spikes.json
python3 lane.py        # lane trades (reads spikes.json)          -> lane.json
python3 build_page.py  # results page                             -> kalista_spikes.html
echo "Done: open kalista_spikes.html"
