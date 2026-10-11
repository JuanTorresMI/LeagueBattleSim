"""Mechanics settled against the wiki in roadmap step 6 (see docs/ASSUMPTIONS.md)."""
import pytest

from engine import Opts, RunePage, THREATS, make_dummy, simulate
from lolsim.stats import level_value
from params import ITEM, RUNE


def test_level_value_curves():
    lin = {"curve": "linear", "lo": 40, "hi": 160}
    assert level_value(lin, 1) == 40 and level_value(lin, 18) == pytest.approx(160)
    assert level_value({"curve": "linear", "lo": 175, "hi": 253, "levels": [1, 20]}, 20) == pytest.approx(253)
    steps = {"curve": "steps", "base": 165, "from_level": 9, "per_level": 15}
    assert [level_value(steps, l) for l in (1, 8, 9, 18)] == [165, 165, 180, 315]
    assert level_value({"curve": "growth", "lo": 9, "hi": 96}, 18) == pytest.approx(96)


def test_wiki_level_values():
    assert level_value(ITEM["6672"]["ranged"], 8) == 120 and level_value(ITEM["6672"]["ranged"], 18) == 160
    assert level_value(ITEM["6673"]["shield"], 18) == 560
    assert level_value(ITEM["3072"]["shield"], 18) == 315
    assert level_value(RUNE["Press the Attack"]["damage"], 18) == pytest.approx(160)
    assert level_value(RUNE["Lethal Tempo"]["damage"], 18) == pytest.approx(20.01)
    assert level_value(RUNE["Conqueror"]["ad"], 18) == pytest.approx(2.4)


def test_bloodletter_does_not_stack_from_on_hit():
    """Only champion-ability magic damage stacks it; Kalista's abilities are physical."""
    from lolsim.fight import Fight
    f = Fight(["8010", "3091", "3124"], 13, make_dummy("tank", 13, 3), RunePage("Lethal Tempo", "Alacrity", 7, "Cut Down"), Opts())
    f.run()
    bl = next(e for e in f.effects if type(e).__name__ == "Bloodletters")
    assert f.by_src["On-hit (magic)"] > 0 and bl.stacks == 0


def test_dusk_and_dawn_heals_on_empowered_hit(threat_mults):
    threat_mults({"bruiser": 2.813})
    r = simulate(["2510", "1055"], 11, make_dummy("bruiser", 11, 2), RunePage("Press the Attack", "Alacrity", 5, "Cut Down"),
                 Opts(kal_start=0.5), THREATS["bruiser"], 2)
    assert r["healed_by"].get("Dusk and Dawn", 0) > 0
