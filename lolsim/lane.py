"""Laning: quick and extended trades, executes and kill pressure.

Scenarios (all vs an enemy that hits back):
  trade     both full HP; ~2 s of Kalista autos + Q into the enemy's retaliation, then
            she rips Rend on the way out. Score: enemy % max HP lost minus Kalista's.
  extended  the same over ~3.5 s.
  execute   enemy at 25% HP, Kalista at 60%; the enemy escapes after 2 s.
  pressure  the highest enemy HP % Kalista can kill inside a 2 s window (Kalista at 80%).

Lane threats are calibrated separately so the reference Kalista (Doran's Blade, Press the
Attack / Alacrity / Cut Down) trades exactly even across levels 2, 3 and 6."""
import time
from dataclasses import replace

from .config import Config
from .enemies import THREATS, make_dummy
from .fight import Opts, simulate
from .runes import RunePage
from .stats import item_name, item_cost, statline
from .spikes import POOL, BOOTS, ALL_PAGES, legal, inventory


class LaneAnalysis:
    def __init__(self, cfg=None, mults=None):
        self.cfg = cfg = cfg or Config()
        self.kinds = list(cfg.lane_threats)
        cal = cfg.lane_cal
        rp = cal["reference_page"]
        self.base_page = RunePage(rp[0], rp[1], cal["reference_legend_stacks"], rp[2])
        self.base_items = list(cal["reference_items"])
        self.cal_stages = [s for s in cfg.lane_stages if s[2] == 0 and s[1] in cal["levels"]]
        self.set_mults(mults or {k: 1.0 for k in self.kinds})

    def set_mults(self, mults):
        self.mults = {k: (m["mult"] if isinstance(m, dict) else m) for k, m in mults.items()}
        self.threats = {k: replace(THREATS[k], dmg_mult=self.mults.get(k, 1.0)) for k in self.kinds}

    def stacks_for(self, n_items):
        return self.cfg.legend[n_items]

    # -------------------------------------------------------------- scenarios
    def _champ(self, ref):
        """Calibration always uses the reference (Kalista, no Soul-Mark)."""
        return ("Kalista", False) if ref else (self.cfg.champion, self.cfg.soul_mark)

    def trade(self, inv, lvl, kind, ne, page, path_last=None, windows=None, ref=False):
        windows = self.cfg.quick_windows if windows is None else windows
        ch, soul = self._champ(ref)
        share = self.cfg.gunblade_share
        d = make_dummy(kind, lvl, ne)
        tot_net = tot_d = tot_t = 0.0
        last = None
        # Gunblade's active (60 s cooldown) is up for `share` of lane trades
        actives = [True, False] if "3146" in inv and 0 < share < 1 else [share > 0]
        for w in windows:
            for act in actives:
                wt = (2 * share if act else 2 * (1 - share)) if len(actives) == 2 else 1.0
                r = simulate(inv, lvl, d, page, Opts(window=w, exit_e=True, gunblade_active=act, soul_mark=soul,
                             yuntal_prestacked=path_last != "3032"), self.threats[kind], ne, champ=ch)
                tot_d += wt * r["dealt_frac"]; tot_t += wt * r["taken_frac"]
                tot_net += wt * (r["dealt_frac"] - r["taken_frac"])
                last = r if w == windows[len(windows) // 2] else last
        n = len(windows) * len(actives)
        return {"net": tot_net / n, "dealt": tot_d / n, "taken": tot_t / n,
                "taken_by": last["taken_by"], "healed_by": last["healed_by"], "dealt_by": last["dealt_by"]}

    def execute(self, inv, lvl, kind, ne, page, path_last=None):
        ex = self.cfg.execute
        r = simulate(inv, lvl, make_dummy(kind, lvl, ne), page,
                     Opts(window=ex["window"], enemy_start=ex["enemy_start"], kal_start=ex["kal_start"],
                          soul_mark=self.cfg.soul_mark, yuntal_prestacked=path_last != "3032"),
                     self.threats[kind], ne, champ=self.cfg.champion)
        return {"killed": r["killed"] and not r["died"], "time": r["kill_time"],
                "cost": r["taken_frac"], "died": r["died"]}

    def pressure(self, inv, lvl, kind, ne, page, path_last=None):
        pr = self.cfg.pressure
        d = make_dummy(kind, lvl, ne)

        def ok(f):
            r = simulate(inv, lvl, d, page, Opts(window=pr["window"], enemy_start=f, kal_start=pr["kal_start"],
                         soul_mark=self.cfg.soul_mark, yuntal_prestacked=path_last != "3032"),
                         self.threats[kind], ne, champ=self.cfg.champion)
            return r["killed"] and not r["died"]
        if not ok(pr["lo"]): return 0.0
        lo, hi = pr["lo"], 1.0
        if ok(hi): return 1.0
        for _ in range(pr["steps"]):
            mid = (lo + hi) / 2
            if ok(mid): lo = mid
            else: hi = mid
        return lo

    def evaluate(self, path, boots, lvl, ne, page):
        inv = inventory(path, boots)
        pg = page.at(self.stacks_for(len(path)))
        last = path[-1] if path else None
        per = {}
        for k in self.kinds:
            tr = self.trade(inv, lvl, k, ne, pg, last)
            lg = self.trade(inv, lvl, k, ne, pg, last, self.cfg.long_windows)
            per[k] = {"trade": round(tr["net"], 4), "long": round(lg["net"], 4), "dealt": round(tr["dealt"], 4),
                      "taken": round(tr["taken"], 4), "exec": self.execute(inv, lvl, k, ne, pg, last),
                      "pressure": round(self.pressure(inv, lvl, k, ne, pg, last), 3),
                      "taken_by": tr["taken_by"], "healed_by": tr["healed_by"], "dealt_by": tr["dealt_by"]}
        return {"per": per,
                "trade": sum(v["trade"] for v in per.values()) / len(per),
                "long": sum(v["long"] for v in per.values()) / len(per),
                "pressure": sum(v["pressure"] for v in per.values()) / len(per),
                "execs": sum(v["exec"]["killed"] for v in per.values()),
                "exec_cost": sum(v["exec"]["cost"] for v in per.values()) / len(per)}

    def calibrate(self):
        """Scale each lane threat so the reference Kalista trades evenly at the calibration levels."""
        cal, out = self.cfg.lane_cal, {}
        for k in self.kinds:
            base = THREATS[k]

            def avg_net(m):
                self.threats[k] = replace(base, dmg_mult=m)
                return sum(self.trade(self.base_items, lvl, k, 0, self.base_page, ref=True)["net"]
                           for _, lvl, _, _ in self.cal_stages) / len(self.cal_stages)
            lo, hi, steps = cal["bisect"]
            for _ in range(steps):
                mid = (lo + hi) / 2
                if avg_net(mid) > cal["target"]: lo = mid
                else: hi = mid
            m = round((lo + hi) / 2, 3)
            out[k] = {"mult": m, "check": round(avg_net(m), 4)}
        self.set_mults(out)
        return out

    @staticmethod
    def view(ev):
        return {"trade": round(ev["trade"], 4), "long": round(ev["long"], 4), "pressure": round(ev["pressure"], 3),
                "execs": ev["execs"], "exec_cost": round(ev["exec_cost"], 3),
                "per": {k: {"trade": v["trade"], "long": v["long"], "dealt": v["dealt"], "taken": v["taken"],
                            "pressure": v["pressure"], "exec": v["exec"]} for k, v in ev["per"].items()}}

    def lane_score(self, ev):
        """Net HP lead from trades (quick and extended) plus a smaller kill-pressure term."""
        w = self.cfg.lane_weights
        return w["quick"] * ev["trade"] + w["long"] * ev["long"] + w["pressure"] * ev["pressure"]

    # -------------------------------------------------------------- whole report
    def report(self, spikes_report, log=print):
        t0 = time.time()
        cfg, stages = self.cfg, self.cfg.lane_stages
        calib = self.calibrate()
        log("lane calibration", calib)
        pre = [s for s in stages if s[2] == 0]
        rune_rows = []
        for pg in ALL_PAGES:
            st = [{"stage": label, **self.view(self.evaluate((), None, lvl, ne, pg))} for label, lvl, n, ne in pre]
            rune_rows.append({"page": pg.label(),
                              "trade": round(sum(s["trade"] for s in st) / len(st), 4),
                              "long": round(sum(s["long"] for s in st) / len(st), 4),
                              "pressure": round(sum(s["pressure"] for s in st) / len(st), 3),
                              "stages": st})
        for r in rune_rows: r["score"] = round(self.lane_score(r), 4)
        rune_rows.sort(key=lambda r: -r["score"])
        best_page = next(p for p in ALL_PAGES if p.label() == rune_rows[0]["page"])
        log("best lane page", best_page.label())

        def rank(prefix, boots_opts, lvl, ne):
            base = self.evaluate(prefix, None, lvl, ne, best_page)
            rows = []
            for c in POOL:
                if c in prefix or not legal(prefix + (c,)): continue
                best = None
                for b in boots_opts:
                    ev = self.evaluate(prefix + (c,), b, lvl, ne, best_page)
                    if best is None or self.lane_score(ev) > self.lane_score(best[1]): best = (b, ev)
                b, ev = best
                rows.append({"item": item_name(c), "id": c, "cost": item_cost(c),
                             "boots": BOOTS.get(b) if b else None, "score": round(self.lane_score(ev), 4),
                             "trade_gain": round((ev["trade"] - base["trade"]) * 100, 1), **self.view(ev)})
            rows.sort(key=lambda r: -r["score"])
            for i, r in enumerate(rows, 1): r["rank"] = i
            return {"base": self.view(base), "ranking": rows}

        s1 = next(s for s in stages if s[2] == 1)
        s2 = next(s for s in stages if s[2] == 2)
        first = rank((), [None], s1[1], s1[3])
        pick1 = first["ranking"][0]["id"]
        second = rank((pick1,), list(BOOTS), s2[1], s2[3])
        pick2 = second["ranking"][0]["id"]
        boots2 = next(k for k, v in BOOTS.items() if v == second["ranking"][0]["boots"])
        log("lane items", item_name(pick1), item_name(pick2), BOOTS[boots2])

        def stage_series(path, boots, page):
            out = []
            for label, lvl, n, ne in stages:
                ev = self.evaluate(path[:n], boots if n >= 2 else None, lvl, ne, page)
                out.append({"stage": label, **self.view(ev),
                            "breakdown": {k: {"taken_by": v["taken_by"], "healed_by": v["healed_by"],
                                              "dealt_by": v["dealt_by"]} for k, v in ev["per"].items()}})
            return out

        goal_rows = []
        for g, b in spikes_report["builds"].items():
            names = [p["item"] for p in b["path"][:2]]
            ids = tuple(next(i for i in POOL if item_name(i) == n) for n in names)
            boots = next(k for k, v in BOOTS.items() if v == b["boots"])
            pg = next(p for p in ALL_PAGES if p.label() == b["page"])
            series = stage_series(ids, boots, pg)
            goal_rows.append({"goal": g, "name": spikes_report["goals"][g], "page": b["page"], "items": names,
                              "boots": b["boots"],
                              "stages": [{k: s[k] for k in ("stage", "trade", "long", "pressure", "execs")} for s in series]})
        lane_path = (pick1, pick2)
        report = {"calibration": calib, "weights": dict(cfg.lane_weights), "threats": dict(cfg.lane_threats),
                  "best_page": best_page.label(), "runes": rune_rows, "first": first, "second": second,
                  "lane_path": {"items": [item_name(pick1), item_name(pick2)], "boots": BOOTS[boots2],
                                "page": best_page.label(), "stages": stage_series(lane_path, boots2, best_page)},
                  "goal_builds": goal_rows,
                  "statlines": [statline(cfg.champion, lvl, inventory(lane_path[:n], boots2 if n >= 2 else None),
                                         best_page.at(self.stacks_for(n))) for _, lvl, n, _ in stages],
                  "runtime_s": round(time.time() - t0, 1)}
        return report
