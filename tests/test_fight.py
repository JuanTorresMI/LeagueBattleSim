"""Golden values for the fight simulator: one fixed trace, one duel per threat and
one lane trade per lane threat. These lock behavior for the refactor; if a change is
meant to move them, update the numbers and say why in the commit."""
import pytest

import lane, spikes
from engine import Opts, RunePage, THREATS, make_dummy, simulate

DUEL_MULTS = {"marksman": 1.675, "bruiser": 2.813, "tank": 4.554, "mage": 2.61}
LANE_MULTS = {"marksman": 1.85, "mage": 1.118, "tank": 2.227}


def test_kalista_fight_trace():
    """Doran's + BotRK at level 9 into a 1-item bruiser dummy: Q, autos, Rend kill."""
    d = make_dummy("bruiser", 9, 1)
    r = simulate(["3153", "1055"], 9, d, RunePage("Press the Attack", "Alacrity", 3, "Cut Down"),
                 Opts(), trace=True)
    assert r["ttk"] == pytest.approx(6.444469895849722)
    assert r["attacks"] == 8
    assert r["spears"] == 9                                        # 1 from Q + 8 autos
    times = [row[0] for row in r["trace"]]
    hps = [row[1] for row in r["trace"]]
    spears = [row[2] for row in r["trace"]]
    assert times == [0.25, 1.13, 2.02, 2.9, 3.79, 4.67, 5.56, 6.44]   # Q cast, then 1 / AS
    assert hps == [1453, 1320, 1138, 1006, 889, 776, 667, 562]
    assert spears == [2, 3, 4, 5, 6, 7, 8, 9]
    src = r["by_source"]
    assert set(src) == {"Pierce (Q)", "Auto attacks", "On-hit (physical)", "Press the Attack", "Rend (E)"}
    assert src["Rend (E)"] == pytest.approx(574.111, abs=1e-3)       # Rend finished it
    assert src["Pierce (Q)"] == pytest.approx(129.663, abs=1e-3)
    assert src["Auto attacks"] == pytest.approx(659.122, abs=1e-3)
    assert sum(src.values()) >= d.hp                               # one-way fights keep overkill


# kind -> (win, kill time, death time, Kalista HP left)
DUELS = {
    "marksman": (True, 1.3262, 1.8112, 0.2678),
    "bruiser": (True, 2.7643, 3.2177, 0.1409),
    "tank": (True, 4.0905, 5.6768, 0.2794),
    "mage": (True, 2.0881, 2.2985, 0.0916),
}


@pytest.mark.parametrize("kind", sorted(DUELS))
def test_duel_per_threat(kind, threat_mults):
    """Yun Tal, IE, LDR + Berserker's at level 13 vs a 3-item enemy."""
    threat_mults(DUEL_MULTS)
    inv = spikes.inventory(("3032", "3031", "3036"), "3006")
    r = simulate(inv, 13, make_dummy(kind, 13, 3), RunePage("Press the Attack", "Alacrity", 7, "Cut Down"),
                 Opts(), THREATS[kind], 3)
    win, tk, td, left = DUELS[kind]
    assert r["win"] is win
    assert r["tk"] == pytest.approx(tk, abs=1e-4)
    assert r["td"] == pytest.approx(td, abs=1e-4)
    assert r["kal_hp_left"] == pytest.approx(left, abs=1e-4)
    assert r["enemy_hp_left"] == 0.0


# kind -> (net, dealt, taken) as fractions of max HP
TRADES = {
    "marksman": (-0.015867, 0.349873, 0.365739),
    "mage": (-0.014373, 0.388595, 0.402968),
    "tank": (-0.003137, 0.314413, 0.31755),
}


@pytest.mark.parametrize("kind", sorted(TRADES))
def test_lane_trade_per_threat(kind, threat_mults):
    """Doran's Blade, Press the Attack / Alacrity / Cut Down at level 3, quick trades."""
    threat_mults(LANE_MULTS)
    t = lane.trade([spikes.DORANS], 3, kind, 0, lane.BASE_PAGE)
    net, dealt, taken = TRADES[kind]
    assert t["net"] == pytest.approx(net, abs=1e-6)
    assert t["dealt"] == pytest.approx(dealt, abs=1e-6)
    assert t["taken"] == pytest.approx(taken, abs=1e-6)


def test_trade_window_rips_rend_on_exit(threat_mults):
    threat_mults(LANE_MULTS)
    d = make_dummy("marksman", 6, 0)
    r = simulate([spikes.DORANS], 6, d, lane.BASE_PAGE, Opts(window=2.0, exit_e=True),
                 THREATS["marksman"], 0)
    assert not r["killed"]
    assert r["exit_rend"] > 0
    assert r["dealt_by"]["Rend (E)"] == round(r["exit_rend"])
