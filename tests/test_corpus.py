"""Every fight in tests/snapshots/fights.json must reproduce exactly (see fight_corpus.py)."""
import json

import pytest

from tests.fight_corpus import CORPUS, run

with open(CORPUS, encoding="utf-8") as f:
    FIGHTS = json.load(f)


@pytest.mark.parametrize("chunk", range(0, len(FIGHTS), 50))
def test_corpus(chunk):
    for i, fx in enumerate(FIGHTS[chunk:chunk + 50], chunk):
        assert run(fx["case"]) == fx["result"], f"fight {i}: {fx['case']}"
