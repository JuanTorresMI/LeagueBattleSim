"""Game numbers and model settings, loaded from JSON.

data/wiki/*.json  game numbers Data Dragon leaves out; every entry carries a source
                  URL and the patch it was taken for, plus 'verify' when unconfirmed.
config/*.json     model choices: threat profiles, scoring weights, calibration targets.

A patch update edits these files, not code."""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))


def _read(*parts):
    with open(os.path.join(HERE, *parts), encoding="utf-8") as f:
        return json.load(f)


def wiki_table(name):
    """{key: values} for one data/wiki file, and {key: full entry} with its source."""
    raw = _read("data", "wiki", name + ".json")
    raw.pop("_meta", None)
    return {k: e["values"] for k, e in raw.items()}, raw


ITEM, ITEM_INFO = wiki_table("items")
RUNE, RUNE_INFO = wiki_table("runes")
MECH, MECH_INFO = wiki_table("mechanics")
CHAMP, CHAMP_INFO = wiki_table("champions")

THREAT_CFG = _read("config", "threats.json")
SCORING = _read("config", "scoring.json")
CALIBRATION = _read("config", "calibration.json")


def all_wiki_entries():
    """(file, key, entry) for every wiki value, for checks and reports."""
    for name, info in (("items", ITEM_INFO), ("runes", RUNE_INFO), ("mechanics", MECH_INFO),
                       ("champions", CHAMP_INFO)):
        for k, e in info.items():
            yield name, k, e
