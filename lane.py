"""
Kalista laning: quick trades, executes and kill pressure (patch 16.20.1).

Scenarios (all vs an enemy that hits back):
  trade     - both full HP; ~2 s of Kalista autos + Q into the enemy's retaliation,
              then she rips Rend on the way out. Score: net HP lead
              (enemy % max HP lost minus Kalista % max HP lost).
  execute   - enemy at 25% HP, Kalista at 60%; the enemy escapes after 2 s.
              Did she kill, how fast, and how much HP did it cost?
  pressure  - the highest enemy HP % Kalista can kill inside a 2 s window
              (Kalista at 80% HP). Higher = the enemy has to respect more of the lane.

Lane threats: enemy marksman, poke-mage support, engage-tank support. Their damage
is calibrated so a standard Kalista (Doran's Blade, Press the Attack / Alacrity /
Cut Down) trades exactly even on average across levels 2, 3 and 6.
"""
import json, math, time
from engine import (simulate, make_dummy, Dummy, RunePage, KEYSTONES, Opts, THREATS,
                    item_name, item_cost, statline)
from spikes import (POOL, BOOTS, DORANS, LEGEND, ALL_PAGES, legal, inventory)
from params import SCORING, CALIBRATION

LN, CAL = SCORING["lane"], CALIBRATION["lane"]      # config/scoring.json, config/calibration.json
LANE_NAMES = dict(LN["threats"])
LANE = list(LANE_NAMES)
WINDOWS = LN["quick_windows"]        # quick trade
LONG_WINDOWS = LN["long_windows"]    # extended trade
STAGES = [tuple(s) for s in LN["stages"]]   # (label, level, our items as path length, enemy items)
BASE_PAGE = RunePage(CAL["reference_page"][0], CAL["reference_page"][1], CAL["reference_legend_stacks"],
                     CAL["reference_page"][2])
BASE_ITEMS = list(CAL["reference_items"])
CAL_STAGES = [s for s in STAGES if s[2] == 0 and s[1] in CAL["levels"]]
GUNBLADE_SHARE = LN["gunblade_trade_share"]
EX, PR = LN["execute"], LN["pressure"]

def stacks_for(n_items):
    return LEGEND[n_items]

def trade(inv, lvl, kind, ne, page, path_last=None, windows=WINDOWS):
    d = make_dummy(kind, lvl, ne)
    tot_net = tot_d = tot_t = 0.0
    last = None
    # Gunblade's active (60 s cooldown) is up for GUNBLADE_SHARE of lane trades
    actives = [True, False] if "3146" in inv and 0 < GUNBLADE_SHARE < 1 else [GUNBLADE_SHARE > 0]
    for w in windows:
        for act in actives:
            wt = (2 * GUNBLADE_SHARE if act else 2 * (1 - GUNBLADE_SHARE)) if len(actives) == 2 else 1.0
            r = simulate(inv, lvl, d, page, Opts(window=w, exit_e=True, gunblade_active=act,
                         yuntal_prestacked=path_last != "3032"), THREATS[kind], ne)
            tot_d += wt * r["dealt_frac"]; tot_t += wt * r["taken_frac"]
            tot_net += wt * (r["dealt_frac"] - r["taken_frac"])
            last = r if w == windows[1] else last
    n = len(windows) * len(actives)
    return {"net": tot_net / n, "dealt": tot_d / n, "taken": tot_t / n,
            "taken_by": last["taken_by"], "healed_by": last["healed_by"], "dealt_by": last["dealt_by"]}

def execute(inv, lvl, kind, ne, page, path_last=None):
    d = make_dummy(kind, lvl, ne)
    r = simulate(inv, lvl, d, page, Opts(window=EX["window"], enemy_start=EX["enemy_start"], kal_start=EX["kal_start"],
                 yuntal_prestacked=path_last != "3032"), THREATS[kind], ne)
    return {"killed": r["killed"] and not r["died"], "time": r["kill_time"],
            "cost": r["taken_frac"], "died": r["died"]}

def pressure(inv, lvl, kind, ne, page, path_last=None):
    d = make_dummy(kind, lvl, ne)
    def ok(f):
        r = simulate(inv, lvl, d, page, Opts(window=PR["window"], enemy_start=f, kal_start=PR["kal_start"],
                     yuntal_prestacked=path_last != "3032"), THREATS[kind], ne)
        return r["killed"] and not r["died"]
    if not ok(PR["lo"]): return 0.0
    lo, hi = PR["lo"], 1.0
    if ok(hi): return 1.0
    for _ in range(PR["steps"]):
        mid = (lo + hi) / 2
        if ok(mid): lo = mid
        else: hi = mid
    return lo

def evaluate(path, boots, lvl, ne, page):
    inv = inventory(path, boots)
    pg = page.at(stacks_for(len(path)))
    last = path[-1] if path else None
    per = {}
    for k in LANE:
        tr = trade(inv, lvl, k, ne, pg, last)
        lg = trade(inv, lvl, k, ne, pg, last, LONG_WINDOWS)
        per[k] = {"trade": round(tr["net"], 4), "long": round(lg["net"], 4), "dealt": round(tr["dealt"], 4), "taken": round(tr["taken"], 4),
                  "exec": execute(inv, lvl, k, ne, pg, last),
                  "pressure": round(pressure(inv, lvl, k, ne, pg, last), 3),
                  "taken_by": tr["taken_by"], "healed_by": tr["healed_by"], "dealt_by": tr["dealt_by"]}
    return {"per": per,
            "trade": sum(v["trade"] for v in per.values()) / len(per),
            "long": sum(v["long"] for v in per.values()) / len(per),
            "pressure": sum(v["pressure"] for v in per.values()) / len(per),
            "execs": sum(v["exec"]["killed"] for v in per.values()),
            "exec_cost": sum(v["exec"]["cost"] for v in per.values()) / len(per)}

def calibrate():
    """Scale each lane threat so the standard Kalista trades evenly at levels 2/3/6."""
    out = {}
    for k in LANE:
        th = THREATS[k]
        def avg_net(m):
            th.dmg_mult = m
            return sum(trade(BASE_ITEMS, lvl, k, 0, BASE_PAGE)["net"] for _, lvl, _, _ in CAL_STAGES) / len(CAL_STAGES)
        lo, hi, steps = CAL["bisect"]
        for _ in range(steps):
            mid = (lo + hi) / 2
            if avg_net(mid) > CAL["target"]: lo = mid
            else: hi = mid
        th.dmg_mult = round((lo + hi) / 2, 3)
        out[k] = {"mult": th.dmg_mult, "check": round(avg_net(th.dmg_mult), 4)}
    return out

def view(ev):
    return {"trade": round(ev["trade"], 4), "long": round(ev["long"], 4), "pressure": round(ev["pressure"], 3),
            "execs": ev["execs"], "exec_cost": round(ev["exec_cost"], 3),
            "per": {k: {"trade": v["trade"], "long": v["long"], "dealt": v["dealt"], "taken": v["taken"],
                        "pressure": v["pressure"], "exec": v["exec"]} for k, v in ev["per"].items()}}

QUICK_W, LONG_W, PRESSURE_W = LN["weights"]["quick"], LN["weights"]["long"], LN["weights"]["pressure"]

def lane_score(ev):
    """Net HP lead from trades (60% quick, 40% extended) plus a smaller kill-pressure term."""
    return QUICK_W * ev["trade"] + LONG_W * ev["long"] + PRESSURE_W * ev["pressure"]

if __name__ == "__main__":
    t0 = time.time()
    calib = calibrate()
    print("lane calibration", calib, flush=True)

    # 1. rune pages: pre-item stages on Doran's Blade
    rune_rows = []
    for pg in ALL_PAGES:
        stages = []
        for label, lvl, n, ne in STAGES[:3]:
            ev = evaluate((), None, lvl, ne, pg)
            stages.append({"stage": label, **view(ev)})
        rune_rows.append({"page": pg.label(),
                          "trade": round(sum(s["trade"] for s in stages) / 3, 4),
                          "long": round(sum(s["long"] for s in stages) / 3, 4),
                          "pressure": round(sum(s["pressure"] for s in stages) / 3, 3),
                          "stages": stages})
    for r in rune_rows: r["score"] = round(lane_score(r), 4)
    rune_rows.sort(key=lambda r: -r["score"])
    best_page = next(p for p in ALL_PAGES if p.label() == rune_rows[0]["page"])
    print("best lane page", best_page.label(), flush=True)

    # 2. first item (lvl 9) and second item + boots (lvl 11) for lane
    def rank(prefix, boots_opts, lvl, ne):
        base = evaluate(prefix, None, lvl, ne, best_page)
        rows = []
        for c in POOL:
            if c in prefix or not legal(prefix + (c,)): continue
            best = None
            for b in boots_opts:
                ev = evaluate(prefix + (c,), b, lvl, ne, best_page)
                if best is None or lane_score(ev) > lane_score(best[1]): best = (b, ev)
            b, ev = best
            rows.append({"item": item_name(c), "id": c, "cost": item_cost(c),
                         "boots": BOOTS.get(b) if b else None,
                         "score": round(lane_score(ev), 4),
                         "trade_gain": round((ev["trade"] - base["trade"]) * 100, 1), **view(ev)})
        rows.sort(key=lambda r: -r["score"])
        for i, r in enumerate(rows, 1): r["rank"] = i
        return {"base": view(base), "ranking": rows}

    first = rank((), [None], 9, 1)
    pick1 = first["ranking"][0]["id"]
    second = rank((pick1,), list(BOOTS), 11, 2)
    pick2 = second["ranking"][0]["id"]
    boots2 = next(k for k, v in BOOTS.items() if v == second["ranking"][0]["boots"])
    print("lane items", item_name(pick1), item_name(pick2), BOOTS[boots2], flush=True)

    # 3. lane path through all stages, and each goal build's early items in lane
    lane_path = (pick1, pick2)
    def stage_series(path, boots, page):
        out = []
        for label, lvl, n, ne in STAGES:
            ev = evaluate(path[:n], boots if n >= 2 else None, lvl, ne, page)
            out.append({"stage": label, **view(ev),
                        "breakdown": {k: {"taken_by": v["taken_by"], "healed_by": v["healed_by"],
                                          "dealt_by": v["dealt_by"]} for k, v in ev["per"].items()}})
        return out

    spikes = json.load(open("spikes.json"))
    goal_rows = []
    for g, b in spikes["builds"].items():
        names = [p["item"] for p in b["path"][:2]]
        ids = tuple(next(i for i in POOL if item_name(i) == n) for n in names)
        boots = next(k for k, v in BOOTS.items() if v == b["boots"])
        pg = next(p for p in ALL_PAGES if p.label() == b["page"])
        series = stage_series(ids, boots, pg)
        goal_rows.append({"goal": g, "name": spikes["goals"][g], "page": b["page"], "items": names,
                          "boots": b["boots"],
                          "stages": [{k: s[k] for k in ("stage", "trade", "long", "pressure", "execs")} for s in series]})

    report = {"calibration": calib, "weights": {"quick": QUICK_W, "long": LONG_W, "pressure": PRESSURE_W}, "threats": LANE_NAMES, "best_page": best_page.label(),
              "runes": rune_rows, "first": first, "second": second,
              "lane_path": {"items": [item_name(pick1), item_name(pick2)], "boots": BOOTS[boots2],
                            "page": best_page.label(),
                            "stages": stage_series(lane_path, boots2, best_page)},
              "goal_builds": goal_rows,
              "statlines": [statline("Kalista", lvl, inventory(lane_path[:n], boots2 if n >= 2 else None),
                                     best_page.at(stacks_for(n))) for _, lvl, n, _ in STAGES],
              "runtime_s": round(time.time() - t0, 1)}
    json.dump(report, open("lane.json", "w"), indent=1)
    print("done in", report["runtime_s"], "s")
