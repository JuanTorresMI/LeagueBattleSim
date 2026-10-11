"""Full-fight build optimizer: four goals, beam search slot by slot, boots, 24 rune pages,
duel calibration and per-spike item rankings.

Goals (lower cost is better for each):
  kill       fastest kill: geometric-mean time to kill vs dummies that don't fight back
  duel       best duelist: mean HP left after two-way duels (+0.60 won on 60%, -0.30 lost
             with the enemy on 30%)
  practical  best duelist without Guardian Angel (a 1v1 overvalues a second life)
  safe       hardest to kill: geometric-mean time to die in those duels

Spikes: start Doran's Blade; item 1, item 2 + boots, items 3-5 at the levels in
config/scoring.json; enemies own the same number of items. Early spikes weigh more."""
import math, os, time
from dataclasses import replace

from params import SCORING
from .config import Config
from .enemies import THREATS, ALL_THREATS, Dummy, make_dummy
from .fight import Opts, simulate
from .runes import RunePage, KEYSTONES, LEGENDS, COMBAT
from .stats import PATCH, item_name, item_cost, statline

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
GOALS = {"kill": "Fastest kill", "duel": "Best duelist", "practical": "Best duelist, no GA",
         "safe": "Hardest to kill"}
NO_GA_POOL = {k: v for k, v in POOL.items() if k != "3026"}
GOAL_POOL = {"kill": POOL, "duel": POOL, "practical": NO_GA_POOL, "safe": POOL}
ALL_PAGES = [RunePage(ks, lg, 10, cb) for ks in KEYSTONES for lg in LEGENDS for cb in COMBAT]
START_PAGE = RunePage("Press the Attack", "Alacrity", 10, "Cut Down")


def legal(items):
    s = set(items)
    return all(len(g & s) <= 1 for g in EXCLUSIVE)


def inventory(path, boots):
    inv = list(path)
    if len(path) >= 2 and boots: inv.append(boots)
    if len(path) <= 4: inv.append(DORANS)
    return inv


def replace_hp(d, m):
    return Dummy(d.name, d.hp * m, d.armor, d.mr, d.bonus_hp, d.kind)


def cost(goal, ev):
    """Lower is better for every goal."""
    if goal == "kill": return ev["kill"]
    if goal in ("duel", "practical"): return -ev["duel"]
    return -ev["safe"]


def duel_score(rs):
    return sum((r["kal_hp_left"] if r["win"] else -r["enemy_hp_left"]) for r in rs) / len(rs)


# ------------------------------------------------------------------ worker processes
_WORKER = {}


def _worker_init(cfg):
    _WORKER["cfg"] = cfg


def _worker_eval(task):
    mults, args = task
    key = tuple(sorted(mults.items()))
    r = _WORKER.get(key)
    if r is None:
        r = _WORKER[key] = Ranker(_WORKER["cfg"], mults)
    return r.evaluate(*args)


def _worker_calibrate(kind):
    return Ranker(_WORKER["cfg"]).calibrate_one(kind)


class Ranker:
    def __init__(self, cfg=None, mults=None, pool=None):
        self.cfg = cfg or Config()
        self.pool = pool
        self.cache = {}
        self.set_mults(mults or {k: 1.0 for k in THREATS})

    def set_mults(self, mults):
        self.mults = {k: (m["mult"] if isinstance(m, dict) else m) for k, m in mults.items()}
        self.threats = {k: replace(ALL_THREATS[k], dmg_mult=self.mults.get(k, 1.0)) for k in ALL_THREATS}
        self.cache.clear()

    # -------------------------------------------------------------- one inventory
    def _key(self, path, boots, level, ne, page, uptime):
        return (tuple(sorted(path)), path[-1] if path else None, boots, level, ne, page.label(), uptime)

    def evaluate(self, path, boots, level, ne, page, uptime=None):
        """All metrics for one inventory at one spike."""
        cfg = self.cfg
        uptime = cfg.kite_uptime if uptime is None else uptime
        key = self._key(path, boots, level, ne, page, uptime)
        if key in self.cache: return self.cache[key]
        inv = inventory(path, boots)
        rp = page.at(cfg.legend[len(path)])
        opts = Opts(yuntal_prestacked=not (path and path[-1] == "3032"), kite_uptime=uptime, soul_mark=cfg.soul_mark)
        ch = cfg.champion
        per = {}
        for kind in cfg.threats:
            d = make_dummy(kind, level, ne)
            ttk = sum(simulate(inv, level, replace_hp(d, m), rp, opts, champ=ch)["ttk"] / m for m in cfg.kill_grid) / len(cfg.kill_grid)
            duels = [simulate(inv, level, replace_hp(d, m), rp, opts, self.threats[kind], ne, champ=ch) for m in cfg.duel_grid]
            mid = duels[len(duels) // 2]
            td = min(cfg.td_cap, sum(min(cfg.td_cap, r["td"]) for r in duels) / len(duels))
            per[kind] = {"ttk": round(ttk, 3), "duel": round(duel_score(duels), 3), "td": round(td, 2),
                         "win": mid["win"], "tk": round(min(mid["tk"], 99), 2),
                         "margin": round(mid["margin"], 2),
                         "taken_by": mid["taken_by"], "healed_by": mid["healed_by"],
                         "dealt_by": mid["dealt_by"], "ga_used": mid["ga_used"]}
        out = {"per": per,
               "kill": math.exp(sum(math.log(v["ttk"]) for v in per.values()) / len(per)),
               "duel": sum(v["duel"] for v in per.values()) / len(per),
               "safe": math.exp(sum(math.log(v["td"]) for v in per.values()) / len(per)),
               "wins": sum(v["win"] for v in per.values())}
        self.cache[key] = out
        return out

    def prefetch(self, calls):
        """Evaluate many (path, boots, level, ne, page[, uptime]) in worker processes."""
        if not self.pool: return
        todo, seen = [], set()
        for c in calls:
            args = tuple(c) + ((None,) if len(c) == 5 else ())
            key = self._key(*args[:5], self.cfg.kite_uptime if args[5] is None else args[5])
            if key in self.cache or key in seen: continue
            seen.add(key); todo.append((key, args))
        if len(todo) < 8:
            return
        res = self.pool.map(_worker_eval, [(self.mults, a) for _, a in todo], chunksize=max(1, len(todo) // (8 * self.cfg.jobs)))
        for (key, _), r in zip(todo, res): self.cache[key] = r

    # -------------------------------------------------------------- search
    def beam(self, goal, page, pool, width=None):
        cfg = self.cfg
        width = width or cfg.beam_width
        states = [((), None, 0.0, [])]
        for slot, lvl, ne in cfg.slots:
            calls, cands = [], []
            for path, boots, score, hist in states:
                boot_opts = list(BOOTS) if slot == 2 else [boots]
                for c in pool:
                    if c in path or not legal(path + (c,)): continue
                    for b in boot_opts:
                        calls.append((path + (c,), b, lvl, ne, page))
                        cands.append((path, boots, score, hist, c, b))
            self.prefetch(calls)
            nxt = {}
            for path, boots, score, hist, c, b in cands:
                p = path + (c,)
                ev = self.evaluate(p, b, lvl, ne, page)
                cand = (p, b, score + cfg.weights[slot] * cost(goal, ev), hist + [ev])
                key = (tuple(sorted(p)), b)
                if key not in nxt or cand[2] < nxt[key][2]: nxt[key] = cand
            states = sorted(nxt.values(), key=lambda x: x[2])[:width]
        return states[0]

    def page_scores(self, goal, path, boots, pages=ALL_PAGES):
        cfg = self.cfg
        self.prefetch([(path[:s], boots, l, ne, pg) for pg in pages for s, l, ne in cfg.slots])
        rows = []
        for pg in pages:
            tot = sum(cfg.weights[s] * cost(goal, self.evaluate(path[:s], boots, l, ne, pg)) for s, l, ne in cfg.slots)
            rows.append((tot, pg))
        rows.sort(key=lambda x: x[0])
        return rows

    def optimize(self, goal, pool=None, page=None):
        """Beam search, then the best rune page, repeated until the page is stable.
        A fixed `page` skips the rune search."""
        pool = dict(pool or GOAL_POOL[goal])
        fixed = page is not None
        page = page or START_PAGE
        path, boots, score, hist = self.beam(goal, page, pool)
        if not fixed:
            ranked = self.page_scores(goal, path, boots)
            page = ranked[0][1]
            path, boots, score, hist = self.beam(goal, page, pool)
            ranked = self.page_scores(goal, path, boots)
            if ranked[0][1] != page:
                page = ranked[0][1]
                path, boots, score, hist = self.beam(goal, page, pool)
                ranked = self.page_scores(goal, path, boots)
        else:
            ranked = self.page_scores(goal, path, boots, [page])
        return {"goal": goal, "page": page, "path": path, "boots": boots, "score": score,
                "hist": hist, "pages": ranked}

    # -------------------------------------------------------------- reports
    @staticmethod
    def metric_view(ev):
        return {"kill": round(ev["kill"], 3), "duel": round(ev["duel"], 3),
                "safe": round(ev["safe"], 2), "wins": ev["wins"],
                "per": {k: {x: v[x] for x in ("ttk", "duel", "td", "win", "tk", "margin")}
                        for k, v in ev["per"].items()}}

    def rank_slot(self, goal, res, slot, lvl, ne, pool):
        prefix, boots, page = res["path"][:slot - 1], res["boots"], res["page"]
        cands = [c for c in pool if c not in prefix and legal(prefix + (c,))]
        self.prefetch([(prefix, boots if slot > 2 else None, lvl, ne, page)] +
                      [(prefix + (c,), boots, lvl, ne, page) for c in cands])
        base = self.evaluate(prefix, boots if slot > 2 else None, lvl, ne, page)
        rows = []
        for c in cands:
            ev = self.evaluate(prefix + (c,), boots, lvl, ne, page)
            rows.append({"item": item_name(c), "id": c, "cost": item_cost(c),
                         "faster_pct": round((base["kill"] / ev["kill"] - 1) * 100, 1),
                         "duel_gain": round((ev["duel"] - base["duel"]) * 100, 1),
                         "safer_pct": round((ev["safe"] / base["safe"] - 1) * 100, 1),
                         **self.metric_view(ev)})
        rows.sort(key=lambda r: cost(goal, {"kill": r["kill"], "duel": r["duel"], "safe": r["safe"]}))
        for i, r in enumerate(rows, 1): r["rank"] = i
        return {"slot": slot, "level": lvl, "enemy_items": ne,
                "owned": [item_name(i) for i in inventory(prefix, boots if slot > 2 else None)],
                "base": self.metric_view(base), "ranking": rows}

    def path_view(self, res):
        out = []
        for (s, l, ne), i, ev in zip(self.cfg.slots, res["path"], res["hist"]):
            out.append({"slot": s, "level": l, "item": item_name(i), **self.metric_view(ev),
                        "breakdown": {k: {"taken_by": v["taken_by"], "healed_by": v["healed_by"],
                                          "dealt_by": v["dealt_by"], "ga_used": v["ga_used"]}
                                      for k, v in ev["per"].items()}})
        return out

    def kite_sensitivity(self, res):
        cfg = self.cfg
        self.prefetch([(res["path"][:s], res["boots"], l, ne, res["page"], up)
                       for up in cfg.kite_check for s, l, ne in cfg.slots])
        rows = []
        for up in cfg.kite_check:
            for s, l, ne in cfg.slots:
                ev = self.evaluate(res["path"][:s], res["boots"], l, ne, res["page"], up)
                rows.append({"uptime": up, "slot": s, "duel": round(ev["duel"], 3), "wins": ev["wins"],
                             "per": {k: v["duel"] for k, v in ev["per"].items()}})
        return rows

    def cross_table(self, results):
        """Each goal's final path scored on every goal (at every spike)."""
        return {g: [{"slot": s, **{m: round(self.evaluate(res["path"][:s], res["boots"], l, ne, res["page"])[m], 3)
                                  for m in ("kill", "duel", "safe")}}
                    for s, l, ne in self.cfg.slots]
                for g, res in results.items()}

    def early_runes(self):
        self.prefetch([((), None, lvl, 0, pg) for lvl in self.cfg.early_rune_levels for pg in ALL_PAGES])
        out = []
        for lvl in self.cfg.early_rune_levels:
            for pg in ALL_PAGES:
                ev = self.evaluate((), None, lvl, 0, pg)
                out.append({"level": lvl, "page": pg.label(), "kill": round(ev["kill"], 2),
                            "duel": round(ev["duel"], 3), "safe": round(ev["safe"], 2)})
        return out

    # -------------------------------------------------------------- calibration
    def calibrate_one(self, kind):
        """Bisect one threat's damage multiplier so the reference build hits the target."""
        cal, cfg = self.cfg.duel_cal, self.cfg
        rp = cal["reference_page"]
        page = RunePage(rp[0], rp[1], 10, rp[2])
        path, boots = tuple(cal["reference_items"]), cal["reference_boots"]
        base = ALL_THREATS[kind]

        def score(m):
            th = replace(base, dmg_mult=m)
            tot = 0.0
            for s, l, ne in cfg.slots:
                inv = inventory(path[:s], boots)
                d = make_dummy(kind, l, ne)
                opts = Opts(yuntal_prestacked=s > 1)
                tot += duel_score([simulate(inv, l, replace_hp(d, m2), page.at(cfg.legend[s]), opts, th, ne)
                                   for m2 in cfg.duel_grid])
            return tot / len(cfg.slots)

        lo, hi, steps = cal["bisect"]
        for _ in range(steps):
            mid = (lo + hi) / 2
            if score(mid) > cal["target"]: lo = mid
            else: hi = mid
        m = round((lo + hi) / 2, 3)
        return {"mult": m, "ref_score": round(score(m), 3)}

    def calibrate(self):
        kinds = list(THREATS) + ([k for k in self.cfg.threats if k not in THREATS] if self.cfg.calibrate_kits else [])
        res = self.pool.map(_worker_calibrate, kinds) if self.pool else [self.calibrate_one(k) for k in kinds]
        out = dict(zip(kinds, res))
        self.set_mults(out)
        return out

    # -------------------------------------------------------------- whole report
    def report(self, log=print):
        """Calibrate, optimize every goal and the AP path, and build spikes.json."""
        t0 = time.time()
        cfg = self.cfg
        calib = self.calibrate()
        log("calibration", calib)
        results = {}
        for g in GOALS:
            results[g] = r = self.optimize(g, GOAL_POOL[g])
            log(f"{GOALS[g]:16s} {r['page'].label():40s} {BOOTS[r['boots']]:20s} "
                f"{[item_name(i) for i in r['path']]}  ({time.time()-t0:.0f}s)")
        ap = self.optimize("practical", AP_ONHIT_POOL)
        log("AP duel", ap["page"].label(), [item_name(i) for i in ap["path"]])
        report = {"patch": PATCH, "champion": cfg.champion, "goals": GOALS,
                  "threats": {k: ALL_THREATS[k].name for k in cfg.threats},
                  "calibration": calib, "builds": {}, "cross": self.cross_table(results),
                  "early_runes": self.early_runes()}
        if cfg.changed(): report["config"] = {k: (list(v) if isinstance(v, tuple) else v) for k, v in cfg.changed().items()}
        for g, res in results.items():
            report["builds"][g] = {
                "page": res["page"].label(), "boots": BOOTS[res["boots"]],
                "path": self.path_view(res),
                "pages": [{"page": pg.label(), "score": round(s, 4)} for s, pg in res["pages"]],
                "spikes": [self.rank_slot(g, res, s, l, ne, GOAL_POOL[g]) for s, l, ne in cfg.slots],
                "kite": self.kite_sensitivity(res),
                "statlines": [statline(cfg.champion, l, inventory(res["path"][:s], res["boots"]),
                                       res["page"].at(cfg.legend[s])) for s, l, _ in cfg.slots],
            }
        report["ap"] = {"page": ap["page"].label(), "boots": BOOTS[ap["boots"]], "path": self.path_view(ap),
                        "vs_best": [{"slot": s, "ap_duel": round(e["duel"], 3), "best_duel": round(b["duel"], 3)}
                                    for (s, _, _), e, b in zip(cfg.slots, ap["hist"], results["practical"]["hist"])]}
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
        return report


def make_pool(cfg):
    """A worker pool for cfg.jobs > 1 (None otherwise). Use as a context manager."""
    if cfg.jobs <= 1: return None
    import multiprocessing as mp
    return mp.get_context("fork" if os.name == "posix" else "spawn").Pool(cfg.jobs, _worker_init, (cfg,))


metric_view = Ranker.metric_view
