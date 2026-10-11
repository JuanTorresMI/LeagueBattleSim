"""One build, evaluated end to end: the results page's build editor (in the browser via
Pyodide) and `kalista build` both call evaluate_build()."""
import math

from .config import Config
from .enemies import make_dummy
from .fight import Opts, simulate
from .lane import LaneAnalysis
from .runes import RunePage
from .spikes import BOOTS, DORANS, EXCLUSIVE, Ranker
from .stats import item_name, statline


def evaluate_build(items, level, page="Press the Attack / Alacrity / Cut Down", stacks=10, enemy_items=None,
                   duel_mults=None, lane_mults=None, kite=None, cfg=None):
    """Stat line, kill time and duel per full-fight threat, trades and pressure per lane threat."""
    cfg = (cfg or Config()).with_(kite_uptime=kite)
    rp = RunePage.parse(page, stacks)
    ne = enemy_items if enemy_items is not None else sum(i not in BOOTS and i != DORANS for i in items)
    r = Ranker(cfg, duel_mults)
    opts = Opts(kite_uptime=cfg.kite_uptime)
    fights = {}
    for kind in cfg.threats:
        d = make_dummy(kind, level, ne)
        ttk = simulate(items, level, d, rp, opts)["ttk"]
        du = simulate(items, level, d, rp, opts, r.threats[kind], ne)
        fights[kind] = {"ttk": None if math.isinf(ttk) else round(ttk, 2), "win": du["win"],
                        "kal_hp_left": round(du["kal_hp_left"], 3), "enemy_hp_left": round(du["enemy_hp_left"], 3),
                        "tk": round(min(du["tk"], 99), 2), "td": round(min(du["td"], 99), 2),
                        "taken_by": du["taken_by"], "healed_by": du["healed_by"], "dealt_by": du["dealt_by"]}
    la = LaneAnalysis(cfg, lane_mults)
    lane = {}
    for kind in la.kinds:
        q = la.trade(items, level, kind, ne, rp)
        l = la.trade(items, level, kind, ne, rp, windows=cfg.long_windows)
        lane[kind] = {"quick": round(q["net"], 4), "long": round(l["net"], 4),
                      "pressure": round(la.pressure(items, level, kind, ne, rp), 3)}
    return {"items": [item_name(i) for i in items], "warnings": warnings(items), "level": level, "page": rp.label(), "stacks": stacks,
            "enemy_items": ne, "calibrated": bool(duel_mults), "stats": statline("Kalista", level, items, rp),
            "fights": fights, "lane": lane}


def warnings(items):
    """Inventory rules the game enforces (the simulator itself does not)."""
    out = []
    if len(items) > 6: out.append("More than 6 items.")
    dup = sorted({item_name(i) for i in items if items.count(i) > 1})
    if dup: out.append("Duplicate: " + ", ".join(dup) + ".")
    if sum(i in BOOTS for i in items) > 1: out.append("Only one pair of boots.")
    for g in EXCLUSIVE:
        own = [i for i in dict.fromkeys(items) if i in g]
        if len(own) > 1: out.append("Only one of " + ", ".join(item_name(i) for i in own) + ".")
    return out
