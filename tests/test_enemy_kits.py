"""Real champion kits as opponents (roadmap step 9)."""
import pytest

from engine import Opts, RunePage, make_dummy, simulate
from lolsim.config import Config
from lolsim.enemies import KIT_THREATS, Enemy, THREATS
from lolsim.lane import LaneAnalysis
from lolsim.spikes import Ranker

PAGE = RunePage("Press the Attack", "Alacrity", 7, "Cut Down")


def duel(kind, level=11, n=2, items=("3032", "3031", "3006")):
    return simulate(list(items), level, make_dummy(kind, level, n), PAGE, Opts(), KIT_THREATS[kind], n)


def test_kit_dummy_uses_real_base_stats():
    d = make_dummy("Nautilus", 1, 0)
    assert d.hp == 646 and d.armor == 39 and d.kind == "Nautilus"


def test_kit_abilities_show_by_name():
    r = duel("Caitlyn")
    assert "Piltover Peacemaker (Q)" in r["taken_by"]
    assert "Mystic Shot (Q)" in duel("Ezreal")["taken_by"]


def test_ranks_follow_skill_order():
    e = Enemy(KIT_THREATS["Lux"], 1, 0, 0.65)               # level 1: Q only
    assert [a[-1] for a in e.abil] == ["Light Binding (Q)"]
    e = Enemy(KIT_THREATS["Lux"], 2, 0, 0.65)
    assert [a[-1] for a in e.abil] == ["Light Binding (Q)", "Lucent Singularity (E)"]


def test_nautilus_stun_on_every_hook():
    e = Enemy(KIT_THREATS["Nautilus"], 9, 1, 0.65)
    q = next(a for a in e.abil if a[-1] == "Dredge Line (Q)")
    assert q[4] == 1.0 and q[5] is True


class StubFight:
    """Records what an enemy does over a long fight that nobody wins."""
    class Side: dead_at, revive_until, cc_until = None, -1.0, 0.0
    class St: tenacity = 0.0

    def __init__(self):
        self.hp, self.t, self.kal, self.st, self.log = 1e9, 0.0, self.Side(), self.St(), []

    def take(self, src, raw, kind, is_attack=False):
        self.log.append((round(self.t, 3), src))


def enemy_log(kind, level=11, n=2, until=20.0):
    f = StubFight()
    Enemy(KIT_THREATS[kind], level, n, 0.65).run_until(f, until)
    return f.log


def test_caitlyn_headshot_every_sixth_auto():
    log = enemy_log("Caitlyn")
    autos = [x for x in log if x[1] == "Enemy autos"]
    heads = [x for x in log if x[1] == "Headshot"]
    assert len(heads) == len(autos) // 6 and heads[0][0] == autos[5][0]


def test_nautilus_passive_every_six_seconds():
    hits = [t for t, src in enemy_log("Nautilus") if src == "Staggering Blow"]
    assert hits and all(b - a >= 6 for a, b in zip(hits, hits[1:]))


def test_lux_illumination_after_ability():
    log = enemy_log("Lux")
    for i, (t, src) in enumerate(log):
        if src == "Illumination":
            prior = [s for _, s in log[:i - 1] if s != "Enemy autos"]
            assert prior and prior[-1] != "Illumination"


def test_class_profiles_unchanged_by_kits():
    assert set(THREATS) == {"marksman", "bruiser", "tank", "mage"}


def test_kits_uncalibrated_by_default_and_calibratable():
    r = Ranker(Config(threats=("Nautilus",)))
    assert r.threats["Nautilus"].dmg_mult == 1.0
    m = Ranker(Config(threats=("Nautilus",), calibrate_kits=True)).calibrate_one("Nautilus")["mult"]
    assert 1.0 < m < 8.0
    la = LaneAnalysis(Config(lane_threats={"Lux": "Lux"}))
    assert la.calibrate()["Lux"] == {"mult": 1.0, "check": None}
