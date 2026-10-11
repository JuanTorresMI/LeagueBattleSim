"""Snapshots of the pipeline outputs.

* The committed spikes.json / lane.json must match tests/snapshots/summary.json
  (the numbers HANDOFF.md reports).
* The engine must still reproduce the committed numbers: calibration, every goal
  build at every spike, and the lane path at every stage (a few seconds).
* With --runslow, the whole pipeline runs in a temp dir and must reproduce
  spikes.json and lane.json exactly (except runtime)."""
import json, os, shutil, subprocess, sys

import pytest

import lane, spikes
from tests.conftest import ROOT
from tests.snapshot import SNAPSHOT, summarize


def page_from_label(label):
    return next(p for p in spikes.ALL_PAGES if p.label() == label)


def item_id(name):
    return next(i for i in spikes.POOL if spikes.item_name(i) == name)


def boots_id(name):
    return next(k for k, v in spikes.BOOTS.items() if v == name)


def test_outputs_match_summary_snapshot(spikes_json, lane_json):
    with open(SNAPSHOT, encoding="utf-8") as f:
        expected = json.load(f)
    assert summarize(spikes_json, lane_json) == expected


def test_duel_calibration_reproduces(threat_mults, spikes_json):
    threat_mults({k: 1.0 for k in spikes.KINDS})
    got = spikes.calibrate()
    assert got == spikes_json["calibration"]


def test_lane_calibration_reproduces(threat_mults, lane_json):
    threat_mults({k: 1.0 for k in spikes.KINDS})
    got = lane.calibrate()
    assert got == lane_json["calibration"]


@pytest.mark.parametrize("goal", list(spikes.GOALS))
def test_goal_build_spikes_reproduce(goal, threat_mults, spikes_json):
    threat_mults(spikes_json["calibration"])
    spikes._cache.clear()
    b = spikes_json["builds"][goal]
    path = tuple(item_id(p["item"]) for p in b["path"])
    boots, page = boots_id(b["boots"]), page_from_label(b["page"])
    for (s, lvl, ne), want in zip(spikes.SLOTS, b["path"]):
        view = spikes.metric_view(spikes.evaluate(path[:s], boots, lvl, ne, page))
        assert view == {k: want[k] for k in view}, f"{goal} slot {s}"
    spikes._cache.clear()


def test_lane_path_reproduces(threat_mults, spikes_json, lane_json):
    threat_mults({**spikes_json["calibration"], **lane_json["calibration"]})
    lp = lane_json["lane_path"]
    path = tuple(item_id(n) for n in lp["items"])
    boots, page = boots_id(lp["boots"]), page_from_label(lp["page"])
    for (label, lvl, n, ne), want in zip(lane.STAGES, lp["stages"]):
        view = lane.view(lane.evaluate(path[:n], boots if n >= 2 else None, lvl, ne, page))
        assert view == {k: want[k] for k in view}, label


@pytest.mark.slow
def test_full_pipeline_reproduces(tmp_path, spikes_json, lane_json):
    for name in ("spikes.py", "lane.py", "build_page.py"):
        subprocess.run([sys.executable, os.path.join(ROOT, name)], cwd=tmp_path, check=True,
                       capture_output=True)
    for name, committed in (("spikes.json", spikes_json), ("lane.json", lane_json)):
        with open(tmp_path / name, encoding="utf-8") as f:
            got = json.load(f)
        got.pop("runtime_s"); committed = dict(committed); committed.pop("runtime_s")
        assert got == committed, name
    assert (tmp_path / "kalista_spikes.html").stat().st_size > 100_000
