"""
Kalista spike ranker v3 (patch 16.20.1): damage AND survival.

Three build goals, each optimized slot by slot with a beam search:
  * kill  - fastest kill: geometric-mean time-to-kill vs 4 dummies that don't fight back
  * duel  - best duelist: mean HP left at the end of a two-way duel vs 4 threats
            (+0.60 = won with 60% HP left, -0.30 = lost with the enemy on 30%)
  * safe  - hardest to kill: geometric-mean time-to-die in those duels

Spikes: start Doran's Blade; item 1 at lvl 9; item 2 + boots at lvl 11 (Berserker's,
Plated Steelcaps or Mercury's Treads, chosen by the search); items 3/4/5 at lvl 13/15/17.
Enemies have the same number of items as you. Early spikes are weighted more.
"""
import json, math, time, itertools
from engine import (simulate, statline, item_name, item_cost, make_dummy, Dummy,
                    RunePage, KEYSTONES, Opts, THREATS)
from params import SCORING, CALIBRATION

SP = SCORING["spikes"]
DORANS = SP["starter"]
BOOTS = dict(SP["boots"])
AD_POOL = {
    "3031": "Infinity Edge", "3032": "Yun Tal Wildarrows", "3036": "Lord Dominik's Regards",
    "3033": "Mortal Reminder", "6694": "Serylda's Grudge", "3046": "Phantom Dancer",
    "3094": "Rapid Firecannon", "3095": "Stormrazor", "6675": "Navori Flickerblade",
    "3085": "Runaan's Hurricane", "3153": "Blade of the Ruined King", "6672": "Kraken Slayer",
    "3071": "Black Cleaver", "3072": "Bloodthirster", "2523": "Hexoptics C44",
    "6676": "The Collector", "6673": "Immortal Shieldbow", "3142": "Youmuu's Ghostblade",
}
DEF_POOL = {"3026": "Guardian Angel", "6333": "Death's Dance", "3156": "Maw of Malmortius",
            "3139": "Mercurial Scimitar"}
ONHIT_POOL = {"3124": "Guinsoo's Rageblade", "3091": "Wit's End", "3302": "Terminus",
              "3087": "Statikk Shiv"}
AP_POOL = {
    "4633": "Riftmaker", "3115": "Nashor's Tooth", "3089": "Rabadon's Deathcap",
    "3135": "Void Staff", "4645": "Shadowflame", "3100": "Lich Bane", "2510": "Dusk and Dawn",
    "6653": "Liandry's Torment", "4646": "Stormsurge", "3146": "Hextech Gunblade",
    "8010": "Bloodletter's Curse",
}
POOL = {**AD_POOL, **DEF_POOL, **ONHIT_POOL, **AP_POOL}
AP_ONHIT_POOL = {**ONHIT_POOL, **AP_POOL}
EXCLUSIVE = [{"3036", "3033", "6694"},             # Last Whisper
             {"3087", "3095", "3094"},             # Energized
             {"3100", "2510"},                     # Spellblade
             {"3135", "3137"},                     # Blight
             {"6673", "3156"}]                     # Lifeline

# config/scoring.json
SLOTS = [tuple(s) for s in SP["slots"]]          # (item number, level, enemy items)
WEIGHTS = {int(k): v for k, v in SP["weights"].items()}
LEGEND = {int(k): v for k, v in SP["legend_stacks"].items()}
KILL_GRID = SP["kill_hp_grid"]
DUEL_GRID = SP["duel_hp_grid"]
KINDS = list(THREATS)                     # marksman, bruiser, tank, mage
TD_CAP = SP["td_cap"]
BEAM_WIDTH = SP["beam_width"]
KITE_UPTIME = SCORING["fight"]["kite_uptime"]
GOALS = {"kill": "Fastest kill", "duel": "Best duelist", "practical": "Best duelist, no GA",
         "safe": "Hardest to kill"}
# Guardian Angel is a second life in a 1v1, which a one-fight duel overvalues
# (300 s cooldown, teamfights). "practical" is the duel goal without it.
NO_GA_POOL = {k: v for k, v in POOL.items() if k != "3026"}
GOAL_POOL = {"kill": POOL, "duel": POOL, "practical": NO_GA_POOL, "safe": POOL}

def legal(items):
    s = set(items)
    return all(len(g & s) <= 1 for g in EXCLUSIVE)

def inventory(path, boots):
    inv = list(path)
    if len(path) >= 2 and boots: inv.append(boots)
    if len(path) <= 4: inv.append(DORANS)
    return inv

_cache = {}
def evaluate(path, boots, level, ne, page, uptime=KITE_UPTIME):
    """All metrics for one inventory at one spike."""
    key = (tuple(sorted(path)), path[-1] if path else None, boots, level, ne, page.label(), uptime)
    if key in _cache: return _cache[key]
    inv = inventory(path, boots)
    rp = page.at(LEGEND[len(path)])
    opts = Opts(yuntal_prestacked=not (path and path[-1] == "3032"), kite_uptime=uptime)
    per = {}
    for kind in KINDS:
        d = make_dummy(kind, level, ne)
        ttk = sum(simulate(inv, level, replace_hp(d, m), rp, opts)["ttk"] / m for m in KILL_GRID) / len(KILL_GRID)
        duels = [simulate(inv, level, replace_hp(d, m), rp, opts, THREATS[kind], ne) for m in DUEL_GRID]
        mid = duels[1]
        score = sum((r["kal_hp_left"] if r["win"] else -r["enemy_hp_left"]) for r in duels) / len(duels)
        td = min(TD_CAP, sum(min(TD_CAP, r["td"]) for r in duels) / len(duels))
        per[kind] = {"ttk": round(ttk, 3), "duel": round(score, 3), "td": round(td, 2),
                     "win": mid["win"], "tk": round(min(mid["tk"], 99), 2),
                     "margin": round(mid["margin"], 2),
                     "taken_by": mid["taken_by"], "healed_by": mid["healed_by"],
                     "dealt_by": mid["dealt_by"], "ga_used": mid["ga_used"]}
    out = {"per": per,
           "kill": math.exp(sum(math.log(v["ttk"]) for v in per.values()) / len(per)),
           "duel": sum(v["duel"] for v in per.values()) / len(per),
           "safe": math.exp(sum(math.log(v["td"]) for v in per.values()) / len(per)),
           "wins": sum(v["win"] for v in per.values())}
    _cache[key] = out
    return out

def replace_hp(d, m):
    return Dummy(d.name, d.hp * m, d.armor, d.mr, d.bonus_hp, d.kind)

def cost(goal, ev):
    """Lower is better for every goal."""
    if goal == "kill": return ev["kill"]
    if goal in ("duel", "practical"): return -ev["duel"]
    return -ev["safe"]

def beam(goal, page, pool, width=BEAM_WIDTH):
    states = [((), None, 0.0, [])]
    for slot, lvl, ne in SLOTS:
        nxt = {}
        for path, boots, score, hist in states:
            boot_opts = list(BOOTS) if slot == 2 else [boots]
            for c in pool:
                if c in path or not legal(path + (c,)): continue
                for b in boot_opts:
                    p = path + (c,)
                    ev = evaluate(p, b, lvl, ne, page)
                    cand = (p, b, score + WEIGHTS[slot] * cost(goal, ev), hist + [ev])
                    key = (tuple(sorted(p)), b)
                    if key not in nxt or cand[2] < nxt[key][2]: nxt[key] = cand
        states = sorted(nxt.values(), key=lambda x: x[2])[:width]
    return states[0]

ALL_PAGES = [RunePage(ks, lg, 10, cb) for ks in KEYSTONES for lg in ("Alacrity", "Bloodline")
             for cb in ("Coup de Grace", "Cut Down", "Last Stand")]

def page_scores(goal, path, boots):
    rows = []
    for pg in ALL_PAGES:
        tot = sum(WEIGHTS[s] * cost(goal, evaluate(path[:s], boots, l, ne, pg)) for s, l, ne in SLOTS)
        rows.append((tot, pg))
    rows.sort(key=lambda x: x[0])
    return rows

def optimize(goal, pool=POOL):
    pool = dict(pool)
    page = RunePage("Press the Attack", "Alacrity", 10, "Cut Down")
    path, boots, _, _ = beam(goal, page, pool)
    ranked = page_scores(goal, path, boots)
    page = ranked[0][1]
    path, boots, score, hist = beam(goal, page, pool)
    ranked = page_scores(goal, path, boots)
    if ranked[0][1] != page:
        page = ranked[0][1]
        path, boots, score, hist = beam(goal, page, pool)
        ranked = page_scores(goal, path, boots)
    return {"goal": goal, "page": page, "path": path, "boots": boots, "score": score,
            "hist": hist, "pages": ranked}

def metric_view(ev):
    return {"kill": round(ev["kill"], 3), "duel": round(ev["duel"], 3),
            "safe": round(ev["safe"], 2), "wins": ev["wins"],
            "per": {k: {x: v[x] for x in ("ttk", "duel", "td", "win", "tk", "margin")}
                    for k, v in ev["per"].items()}}

def rank_slot(goal, res, slot, lvl, ne, pool):
    prefix, boots, page = res["path"][:slot - 1], res["boots"], res["page"]
    base = evaluate(prefix, boots if slot > 2 else None, lvl, ne, page)
    rows = []
    for c in pool:
        if c in prefix or not legal(prefix + (c,)): continue
        ev = evaluate(prefix + (c,), boots, lvl, ne, page)
        rows.append({"item": item_name(c), "id": c, "cost": item_cost(c),
                     "faster_pct": round((base["kill"] / ev["kill"] - 1) * 100, 1),
                     "duel_gain": round((ev["duel"] - base["duel"]) * 100, 1),
                     "safer_pct": round((ev["safe"] / base["safe"] - 1) * 100, 1),
                     **metric_view(ev)})
    rows.sort(key=lambda r: cost(goal, {"kill": r["kill"], "duel": r["duel"], "safe": r["safe"]}))
    for i, r in enumerate(rows, 1): r["rank"] = i
    return {"slot": slot, "level": lvl, "enemy_items": ne,
            "owned": [item_name(i) for i in inventory(prefix, boots if slot > 2 else None)],
            "base": metric_view(base), "ranking": rows}

def path_view(res):
    out = []
    for (s, l, ne), i, ev in zip(SLOTS, res["path"], res["hist"]):
        e = {"slot": s, "level": l, "item": item_name(i), **metric_view(ev),
             "breakdown": {k: {"taken_by": v["taken_by"], "healed_by": v["healed_by"],
                               "dealt_by": v["dealt_by"], "ga_used": v["ga_used"]}
                           for k, v in ev["per"].items()}}
        out.append(e)
    return out

def kite_sensitivity(res):
    rows = []
    for up in SP["kite_check"]:
        for s, l, ne in SLOTS:
            ev = evaluate(res["path"][:s], res["boots"], l, ne, res["page"], up)
            rows.append({"uptime": up, "slot": s, "duel": round(ev["duel"], 3), "wins": ev["wins"],
                         "per": {k: v["duel"] for k, v in ev["per"].items()}})
    return rows

def cross_table(results):
    """Each goal's final path scored on every goal (at every spike)."""
    out = {}
    for g, res in results.items():
        out[g] = [{"slot": s, **{m: round(evaluate(res["path"][:s], res["boots"], l, ne, res["page"])[m], 3)
                               for m in ("kill", "duel", "safe")}}
                  for s, l, ne in SLOTS]
    return out

def early_runes():
    out = []
    for lvl in SP["early_rune_levels"]:
        for pg in ALL_PAGES:
            ev = evaluate((), None, lvl, 0, pg)
            out.append({"level": lvl, "page": pg.label(), "kill": round(ev["kill"], 2),
                        "duel": round(ev["duel"], 3), "safe": round(ev["safe"], 2)})
    return out

CAL = CALIBRATION["duel"]                                         # config/calibration.json
REFERENCE = (tuple(CAL["reference_items"]), CAL["reference_boots"])   # standard crit Kalista
TARGET = CAL["target"]                                            # a narrow win on average

def calibrate():
    """Scale each threat's damage so the reference build narrowly wins on average.
    One multiplier per threat, constant across the game, so power curves still show."""
    page = RunePage(CAL["reference_page"][0], CAL["reference_page"][1], 10, CAL["reference_page"][2])
    path, boots = REFERENCE
    mults = {}
    for kind, th in THREATS.items():
        def score(m):
            th.dmg_mult = m
            tot = 0.0
            for s, l, ne in SLOTS:
                inv = inventory(path[:s], boots)
                d = make_dummy(kind, l, ne)
                opts = Opts(yuntal_prestacked=s > 1)
                rs = [simulate(inv, l, replace_hp(d, m2), page.at(LEGEND[s]), opts, th, ne) for m2 in DUEL_GRID]
                tot += sum((r["kal_hp_left"] if r["win"] else -r["enemy_hp_left"]) for r in rs) / len(rs)
            return tot / len(SLOTS)
        lo, hi, steps = CAL["bisect"]
        for _ in range(steps):
            mid = (lo + hi) / 2
            if score(mid) > TARGET: lo = mid
            else: hi = mid
        th.dmg_mult = round((lo + hi) / 2, 3)
        mults[kind] = {"mult": th.dmg_mult, "ref_score": round(score(th.dmg_mult), 3)}
    _cache.clear()
    return mults

if __name__ == "__main__":
    t0 = time.time()
    calib = calibrate()
    print("calibration", calib, flush=True)
    results = {}
    for g in GOALS:
        results[g] = optimize(g, GOAL_POOL[g])
        r = results[g]
        print(f"{GOALS[g]:16s} {r['page'].label():40s} {BOOTS[r['boots']]:20s} {[item_name(i) for i in r['path']]}  ({time.time()-t0:.0f}s)", flush=True)
    ap = optimize("practical", AP_ONHIT_POOL)
    print("AP duel", ap["page"].label(), [item_name(i) for i in ap["path"]], flush=True)

    report = {"patch": "16.20.1", "goals": GOALS, "threats": {k: t.name for k, t in THREATS.items()},
              "calibration": calib,
              "builds": {}, "cross": cross_table(results), "early_runes": early_runes()}
    for g, res in results.items():
        report["builds"][g] = {
            "page": res["page"].label(), "boots": BOOTS[res["boots"]],
            "path": path_view(res),
            "pages": [{"page": pg.label(), "score": round(s, 4)} for s, pg in res["pages"]],
            "spikes": [rank_slot(g, res, s, l, ne, GOAL_POOL[g]) for s, l, ne in SLOTS],
            "kite": kite_sensitivity(res),
            "statlines": [statline("Kalista", l, inventory(res["path"][:s], res["boots"]),
                                   res["page"].at(LEGEND[s])) for s, l, _ in SLOTS],
        }
    report["ap"] = {"page": ap["page"].label(), "boots": BOOTS[ap["boots"]], "path": path_view(ap),
                    "vs_best": [{"slot": s,
                                 "ap_duel": round(e["duel"], 3),
                                 "best_duel": round(b["duel"], 3)}
                                for (s, _, _), e, b in zip(SLOTS, ap["hist"], results["practical"]["hist"])]}
    rift = []
    for g in GOALS:
        for sp in report["builds"][g]["spikes"]:
            rf = next((x for x in sp["ranking"] if x["item"] == "Riftmaker"), None)
            if rf is None:
                rift.append({"goal": g, "slot": sp["slot"], "rank": None, "of": len(sp["ranking"]), "owned": True})
            else:
                rift.append({"goal": g, "slot": sp["slot"], "rank": rf["rank"], "of": len(sp["ranking"])})
    report["riftmaker"] = rift
    report["runtime_s"] = round(time.time() - t0, 1)
    json.dump(report, open("spikes.json", "w"), indent=1)
    print("done in", report["runtime_s"], "s")
