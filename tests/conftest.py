"""Shared fixtures. Tests import the pipeline modules straight from the repo root."""
import json, os, sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine import THREATS  # noqa: E402


def pytest_addoption(parser):
    parser.addoption("--runslow", action="store_true",
                     help="also run the full pipeline (~1 min) and compare its outputs")


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: runs the full pipeline; needs --runslow")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--runslow"):
        return
    skip = pytest.mark.skip(reason="needs --runslow")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip)


def load_output(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def threat_mults():
    """Set THREATS[*].dmg_mult for one test and restore it afterwards.

    calibrate() in spikes.py and lane.py mutates these module globals, so every
    test that runs a duel sets them explicitly instead of relying on run order."""
    saved = {k: t.dmg_mult for k, t in THREATS.items()}

    def apply(mults):
        for k, m in mults.items():
            THREATS[k].dmg_mult = m["mult"] if isinstance(m, dict) else m

    yield apply
    for k, m in saved.items():
        THREATS[k].dmg_mult = m


@pytest.fixture
def spikes_json():
    return load_output("spikes.json")


@pytest.fixture
def lane_json():
    return load_output("lane.json")
