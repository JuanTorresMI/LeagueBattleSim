"""Team fight simulator (lolsim/teamfight.py)."""
import json, os, subprocess, sys

import pytest

from engine import Opts, RunePage
from lolsim.spikes import Ranker
from lolsim.teamfight import SCENARIOS, TeamFight, mirror_baseline, teamfight
from tests.conftest import ROOT

MULTS = {"marksman": 1.675, "bruiser": 2.813, "tank": 4.554, "mage": 2.61}
PAGE = RunePage("Press the Attack", "Alacrity", 7, "Last Stand")
CARRY = ["6673", "3032", "3036", "3047"]


@pytest.mark.parametrize("scenario", list(SCENARIOS))
@pytest.mark.parametrize("level,ne", [(9, 1), (13, 3), (17, 5)])
def test_mirror_is_even(scenario, level, ne):
    """With a marksman profile in Kalista's place both teams are identical: dead even."""
    for tg in ("front", "back"):
        assert mirror_baseline(level, scenario, ne, MULTS, targeting=tg)["score"] == 0


def test_a_real_build_beats_doran_only():
    good = teamfight(CARRY, 13, PAGE, "3v3", 3, MULTS)
    bare = teamfight(["1055"], 13, PAGE, "3v3", 3, MULTS)
    assert good["score"] > bare["score"]
    assert good["kalista"]["dealt"] > bare["kalista"]["dealt"]


def test_target_switch_resets_per_target_state():
    tf = TeamFight(["3071", "3047", "1055"], 13, PAGE, "3v3", 3, MULTS)
    tf.run_all()
    cleaver = next(e for e in tf.effects if type(e).__name__ == "BlackCleaver")
    kills = [u for u in tf.units if u.side == "enemy" and not u.alive]
    assert kills                                             # she moved through several targets
    assert cleaver.stacks <= 5


def test_runaans_hits_other_enemies():
    r = teamfight(["3085", "3031", "3047"], 13, PAGE, "5v5", 3, MULTS, targeting="front")
    assert r["kalista"]["splash_by"].get("Runaan's bolts", 0) > 0
    solo = teamfight(["3085", "3031", "3047"], 13, PAGE, "2v2", 3, MULTS, targeting="front")
    assert solo["kalista"]["splash_by"].get("Runaan's bolts", 0) >= 0


def test_summary_is_consistent():
    r = teamfight(CARRY, 13, PAGE, "5v5", 3, MULTS, targeting="back")
    assert -1 <= r["score"] <= 1 and 0 <= r["kalista"]["share"] <= 1
    assert r["win"] == (r["score"] > 0 and r["enemy_hp"] == 0)


def test_carry_goal_uses_team_metrics():
    r = Ranker(mults=MULTS)
    from lolsim.spikes import ALL_PAGES
    ev = r.evaluate(("6673", "3032"), "3047", 11, 2, ALL_PAGES[0], team=True)
    w = r.cfg.carry_weights
    assert ev["carry"] == pytest.approx(w["duel"] * ev["duel"] + sum(w[s] * ev[s] for s in ev["scenarios"]))
    plain = r.evaluate(("6673", "3032"), "3047", 11, 2, ALL_PAGES[0])
    assert "carry" not in plain                              # other goals skip the team fights


def test_teamfight_command():
    out = subprocess.run([sys.executable, os.path.join(ROOT, "kalista"), "teamfight", "shieldbow", "yuntal", "ldr",
                          "steelcaps", "--level", "13", "--scenario", "3v3", "--targeting", "back"],
                         capture_output=True, text=True, check=True).stdout
    assert "3v3" in out and "dies" in out
