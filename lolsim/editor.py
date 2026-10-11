"""One build, evaluated end to end: the results page's build editor (in the browser via
Pyodide) and `kalista build` both call evaluate_build()."""
import math
from dataclasses import replace

from .config import Config
from .enemies import make_dummy
from .fight import Opts, simulate
from .lane import LaneAnalysis
from .runes import RunePage
from .spikes import BOOTS, DORANS, EXCLUSIVE, Ranker
from .stats import item_name, statline


def evaluate_build(items, level, page="Press the Attack / Alacrity / Cut Down", stacks=10, enemy_items=None,
                   duel_mults=None, lane_mults=None, kite=None, cfg=None, champion=None, soul_mark=None,
                   secondary=None, threats=None, lane_threats=None):
    """Stat line, kill time and duel per full-fight threat, trades and pressure per lane threat."""
    cfg = (cfg or Config()).with_(kite_uptime=kite, champion=champion, soul_mark=soul_mark, secondary_targets=secondary,
                                  threats=tuple(threats) if threats else None, lane_threats=dict(lane_threats) if lane_threats else None)
    ch = cfg.champion
    rp = RunePage.parse(page, stacks)
    ne = enemy_items if enemy_items is not None else sum(i not in BOOTS and i != DORANS for i in items)
    from .enemies import KIT_THREATS
    r = Ranker(cfg, duel_mults)
    if cfg.calibrate_kits:                                   # real kits scaled like the class profiles
        r.set_mults({**r.mults, **{k: r.calibrate_one(k) for k in cfg.threats if k in KIT_THREATS}})
    opts = Opts(kite_uptime=cfg.kite_uptime, soul_mark=cfg.soul_mark)
    fights = {}
    for kind in cfg.threats:
        d = make_dummy(kind, level, ne)
        one = simulate(items, level, d, rp, replace(opts, secondary_targets=cfg.secondary_targets), champ=ch)
        ttk = one["ttk"]
        du = simulate(items, level, d, rp, opts, r.threats[kind], ne, champ=ch)
        fights[kind] = {"ttk": None if math.isinf(ttk) else round(ttk, 2), "win": du["win"],
                        "kal_hp_left": round(du["kal_hp_left"], 3), "enemy_hp_left": round(du["enemy_hp_left"], 3),
                        "tk": round(min(du["tk"], 99), 2), "td": round(min(du["td"], 99), 2),
                        "taken_by": du["taken_by"], "healed_by": du["healed_by"], "dealt_by": du["dealt_by"],
                        "splash": one.get("splash"), "splash_by": one.get("splash_by")}
    la = LaneAnalysis(cfg, lane_mults)
    if cfg.calibrate_kits:
        la.set_mults({**la.mults, **{k: la.calibrate_kind(k) for k in la.kinds if k in KIT_THREATS}})
    lane = {}
    for kind in la.kinds:
        q = la.trade(items, level, kind, ne, rp)
        l = la.trade(items, level, kind, ne, rp, windows=cfg.long_windows)
        lane[kind] = {"quick": round(q["net"], 4), "long": round(l["net"], 4),
                      "pressure": round(la.pressure(items, level, kind, ne, rp), 3)}
    from .teamfight import teamfight, SCENARIOS, TF
    team = {}
    tm_mults = {**{k: 1.0 for k in r.mults}, **r.mults}
    for sc in SCENARIOS:
        rs = [teamfight(items, level, rp, sc, ne, tm_mults, kite=cfg.kite_uptime, targeting=tg,
                        opts=opts, champ=ch) for tg in TF["kalista_targeting"]]
        team[sc] = {"label": SCENARIOS[sc]["label"], "score": round(sum(x["score"] for x in rs) / len(rs), 3),
                    "share": round(sum(x["kalista"]["share"] for x in rs) / len(rs), 3),
                    "alive": sum(x["kalista"]["alive"] for x in rs) / len(rs),
                    "kills": sum(x["kalista"]["kills"] for x in rs) / len(rs)}
    return {"champion": ch, "soul_mark": cfg.soul_mark, "secondary": cfg.secondary_targets, "team": team, "items": [item_name(i) for i in items], "warnings": warnings(items), "level": level, "page": rp.label(), "stacks": stacks,
            "enemy_items": ne, "calibrated": bool(duel_mults), "stats": statline(ch, level, items, rp),
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
