"""Champion kits beyond Kalista's defaults (roadmap step 9): skill order helper, a plain
auto-attacker, Vayne, and Kalista's opt-in Soul-Mark."""
import pytest

from engine import Opts, RunePage, make_dummy, simulate
from lolsim.kits import Kit, kit_for, skill_ranks
from params import CHAMP

PAGE = RunePage("Lethal Tempo", "Alacrity", 7, "Cut Down")


def test_skill_ranks():
    assert skill_ranks(1) == (1, 0, 0)
    assert skill_ranks(3) == (1, 1, 1)
    assert skill_ranks(9, priority=("Q", "W", "E")) == (5, 2, 1)
    assert skill_ranks(18) == (5, 5, 5)
    assert sum(skill_ranks(11)) == 11 - 2          # levels 6 and 11 go to the ultimate


def test_unknown_champion_auto_attacks_only():
    assert kit_for("Jinx") is Kit
    r = simulate(["3031"], 11, make_dummy("tank", 11, 2), PAGE, Opts(), champ="Jinx")
    assert set(r["by_source"]) <= {"Auto attacks", "On-hit (physical)", "On-hit (magic)", "Lethal Tempo"}


def count_procs(items, level, kind, source, champ="Kalista", **opts):
    """Run a fight and count how many times `source` dealt damage."""
    from lolsim.fight import Fight
    f = Fight(items, level, make_dummy(kind, level, 3), PAGE, Opts(**opts), champ=champ)
    calls, deal = [], f.deal
    def counting(src, raw, kind_, is_attack=False):
        if src == source and raw > 0: calls.append(f.t)
        return deal(src, raw, kind_, is_attack)
    f.deal = counting
    return f, f.run(), calls


def test_vayne_silver_bolts_every_third_hit():
    f, r, procs = count_procs(["3031"], 13, "tank", "Silver Bolts (W)", champ="Vayne")
    assert len(procs) == r["attacks"] // 3
    assert r["by_source"]["Tumble (Q)"] > 0


def test_soul_mark_is_opt_in_and_once_per_ten_seconds():
    _, off, none = count_procs(["3031", "3006"], 13, "tank", "Soul-Marked (W)")
    _, on, procs = count_procs(["3031", "3006"], 13, "tank", "Soul-Marked (W)", soul_mark=True, max_time=25.0)
    assert none == [] and "Soul-Marked (W)" not in off["by_source"]
    assert procs[0] == 0.0                                   # Pierce at t=0 consumes the first marks
    assert all(b - a >= 10 for a, b in zip(procs, procs[1:]))
    assert on["ttk"] < off["ttk"]


def test_no_soul_mark_before_w():
    r = simulate([], 2, make_dummy("tank", 2, 0), PAGE, Opts(soul_mark=True))   # W unlocks at level 3
    assert "Soul-Marked (W)" not in r["by_source"]
