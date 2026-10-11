"""Every game number is traceable: each data/wiki entry names a source page and the
patch it was taken for, and the engine reads the same values."""
import re

import pytest

import engine
from params import ITEM, ITEM_INFO, CALIBRATION, SCORING, THREAT_CFG, all_wiki_entries

ENTRIES = list(all_wiki_entries())


@pytest.mark.parametrize("name,key,entry", ENTRIES, ids=[f"{n}:{k}" for n, k, _ in ENTRIES])
def test_wiki_entry_is_traceable(name, key, entry):
    assert re.match(r"https://wiki\.leagueoflegends\.com/en-us/\S+$", entry["source"]), entry
    assert re.match(r"^\d+\.\d+\.\d+$", entry["patch"]), entry
    assert isinstance(entry["values"], dict) and entry["values"]


def test_item_ids_exist_in_data_dragon():
    for iid, e in ITEM_INFO.items():
        assert iid in engine.ITEMS, iid
        assert engine.ITEMS[iid]["name"].lower() == e["name"].lower(), iid


def test_handoff_assumptions_are_settled_or_flagged():
    """The eight assumptions from HANDOFF.md: each entry either says how the wiki settled
    it (note) or still carries a verify flag."""
    info = {k: e for _, k, e in ENTRIES}
    for key in ("crit", "Kalista", "6672", "2510", "Fleet Footwork", "Conqueror", "8010", "Press the Attack"):
        assert "note" in info[key] or "verify" in info[key], key
    still_open = {k for k, e in info.items() if "verify" in e}
    assert still_open == {"2510", "6672", "3146"}


def test_engine_reads_the_data():
    assert engine.CRIT_BASE == 2.0
    assert engine.EXTRA_ITEM_STATS["3031"] == ITEM["3031"]["stats"]
    assert engine.THREATS["bruiser"].abilities[0].cc == THREAT_CFG["threats"]["bruiser"]["abilities"][0]["cc"]


def test_config_has_scoring_and_calibration():
    assert sum(SCORING["spikes"]["weights"].values()) == pytest.approx(1.0)
    assert CALIBRATION["duel"]["target"] == 0.05
    assert CALIBRATION["lane"]["target"] == 0.0
