"""Command line for the Kalista DPS checker.

  kalista run                         whole pipeline -> spikes.json, lane.json, kalista_spikes.html
  kalista optimize --goal practical   one goal's best build (beam search + rune search)
  kalista build IE BotRK LDR --level 13          one build: stats, kill times, duels, trades
  kalista items                       item ids, names and nicknames the tool understands
  kalista update-data [--apply]       refresh Data Dragon files and AD growth

Scenario flags (run, optimize, build): --threat, --kite, --weights, --quick-windows,
--long-windows, --lane-weights, --lane-threat, --gunblade-share, --beam-width, --jobs.
Calibration stays tied to config/calibration.json, so a flag shows how results move
against the same baseline."""
import argparse, json, os, sys, time

from params import HERE
from .config import Config
from .enemies import THREATS, make_dummy
from .fight import Opts, simulate
from .runes import RunePage
from .stats import ITEMS, PATCH, item_name, statline
from . import spikes as SPK
from .lane import LaneAnalysis

ALIASES = {"ie": "3031", "yuntal": "3032", "yun": "3032", "ldr": "3036", "lord": "3036", "mr": "3033",
           "mortal": "3033", "serylda": "6694", "pd": "3046", "rfc": "3094", "storm": "3095",
           "stormrazor": "3095", "navori": "6675", "runaans": "3085", "botrk": "3153", "bork": "3153",
           "kraken": "6672", "bc": "3071", "cleaver": "3071", "bt": "3072", "hexoptics": "2523",
           "collector": "6676", "shieldbow": "6673", "bow": "6673", "youmuu": "3142", "ga": "3026",
           "dd": "6333", "maw": "3156", "qss": "3139", "merc": "3139", "guinsoo": "3124", "rageblade": "3124",
           "wits": "3091", "terminus": "3302", "statikk": "3087", "rift": "4633", "riftmaker": "4633",
           "nashor": "3115", "rabadon": "3089", "cap": "3089", "void": "3135", "shadowflame": "4645",
           "lich": "3100", "dusk": "2510", "liandry": "6653", "stormsurge": "4646", "gunblade": "3146",
           "bloodletter": "8010", "berserker": "3006", "zerks": "3006", "steelcaps": "3047", "tabis": "3047",
           "mercs": "3111", "dblade": "1055", "dorans": "1055"}
KNOWN = {**SPK.POOL, **SPK.BOOTS, SPK.DORANS: "Doran's Blade"}
SHORT = {"marksman": "M", "bruiser": "B", "tank": "T", "mage": "Mg"}


def find_item(text):
    t = text.strip().lower().replace("'", "").replace(" ", "")
    if t in ALIASES: return ALIASES[t]
    if text in ITEMS: return text
    hits = [i for i in KNOWN if t in item_name(i).lower().replace("'", "").replace(" ", "")]
    if len(hits) == 1: return hits[0]
    raise SystemExit(f"item {text!r}: " + ("ambiguous: " + ", ".join(item_name(i) for i in hits) if hits
                                            else "not found (see `kalista items`)"))


def floats(s): return tuple(float(x) for x in s.split(","))


def add_scenario(p, lane=True):
    g = p.add_argument_group("scenario")
    g.add_argument("--threat", help="full-fight enemies, comma list (marksman,bruiser,tank,mage)")
    g.add_argument("--kite", type=float, help="share of melee damage that lands while Kalista kites (default 0.65)")
    g.add_argument("--weights", help="spike weights, 5 numbers (default 0.30,0.25,0.20,0.15,0.10)")
    g.add_argument("--beam-width", type=int, help="beam search width (default 8)")
    if lane:
        g.add_argument("--lane-threat", help="lane enemies, comma list (marksman,mage,tank)")
        g.add_argument("--quick-windows", help="quick trade lengths in s (default 1.75,2,2.25)")
        g.add_argument("--long-windows", help="extended trade lengths in s (default 3.25,3.5,3.75)")
        g.add_argument("--lane-weights", help="quick,extended,pressure (default 0.6,0.4,0.25)")
        g.add_argument("--gunblade-share", type=float, help="share of trades with Gunblade's active up (default 0.5)")
    g.add_argument("--jobs", type=int, default=os.cpu_count() or 1, help="worker processes (default: all cores)")


def config_from(a):
    d = Config()
    kw = {"jobs": a.jobs, "kite_uptime": getattr(a, "kite", None), "beam_width": getattr(a, "beam_width", None),
          "gunblade_share": getattr(a, "gunblade_share", None)}
    if getattr(a, "threat", None):
        kw["threats"] = tuple(t.strip() for t in a.threat.split(","))
        bad = set(kw["threats"]) - set(THREATS)
        if bad: raise SystemExit(f"unknown threat {bad}; choose from {list(THREATS)}")
    if getattr(a, "weights", None):
        w = floats(a.weights)
        if len(w) != len(d.slots): raise SystemExit(f"--weights needs {len(d.slots)} numbers")
        kw["weights"] = {s[0]: x for s, x in zip(d.slots, w)}
    if getattr(a, "lane_threat", None):
        names = {k.strip(): d.lane_threats.get(k.strip(), THREATS[k.strip()].name) for k in a.lane_threat.split(",")}
        kw["lane_threats"] = names
    for flag, field in (("quick_windows", "quick_windows"), ("long_windows", "long_windows")):
        if getattr(a, flag, None): kw[field] = floats(getattr(a, flag))
    if getattr(a, "lane_weights", None):
        q, l, p = floats(a.lane_weights)
        kw["lane_weights"] = {"quick": q, "long": l, "pressure": p}
    return d.with_(**kw)


def saved_mults(name, key="calibration"):
    """Calibration multipliers from the last run's spikes.json / lane.json, if present."""
    path = os.path.join(HERE, name)
    if not os.path.exists(path): return None
    with open(path) as f: return json.load(f)[key]


def pct(x): return f"{x * 100:+.0f}%"


# ------------------------------------------------------------------ commands
def cmd_run(a):
    import build_page
    cfg = config_from(a)
    out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    t0 = time.time()
    pool = SPK.make_pool(cfg)
    try:
        sp = SPK.Ranker(cfg, pool=pool).report(log=lambda *x: print(*x, flush=True))
    finally:
        if pool: pool.close(); pool.join()
    with open(os.path.join(out, "spikes.json"), "w") as f: json.dump(sp, f, indent=1)
    sp = json.load(open(os.path.join(out, "spikes.json")))           # lane reads the saved, rounded file
    ln = LaneAnalysis(cfg).report(sp, log=lambda *x: print(*x, flush=True))
    with open(os.path.join(out, "lane.json"), "w") as f: json.dump(ln, f, indent=1)
    html = build_page.render(sp, ln)
    with open(os.path.join(out, "kalista_spikes.html"), "w", encoding="utf-8") as f: f.write(html)
    print(f"wrote {out}/spikes.json, lane.json, kalista_spikes.html in {time.time() - t0:.1f} s")


def cmd_optimize(a):
    cfg = config_from(a)
    pool = SPK.make_pool(cfg)
    try:
        r = SPK.Ranker(cfg, pool=pool)
        mults = None if a.recalibrate else saved_mults("spikes.json")
        if mults: r.set_mults(mults)
        else: print("calibration", r.calibrate(), file=sys.stderr)
        page = None if a.runes == "auto" else RunePage.parse(a.runes)
        pool_items = SPK.AP_ONHIT_POOL if a.ap else SPK.GOAL_POOL[a.goal]
        res = r.optimize(a.goal, pool_items, page)
    finally:
        if pool: pool.close(); pool.join()
    view = r.path_view(res)
    if a.json:
        print(json.dumps({"goal": a.goal, "page": res["page"].label(), "boots": SPK.BOOTS[res["boots"]],
                          "path": view, "config": {k: str(v) for k, v in cfg.changed().items()}}, indent=1))
        return
    print(f"{SPK.GOALS[a.goal]} · {res['page'].label()} · {SPK.BOOTS[res['boots']]} at item 2")
    if cfg.changed(): print("scenario:", ", ".join(f"{k}={v}" for k, v in cfg.changed().items()))
    th = list(cfg.threats)
    print(f"{'item':4s} {'lvl':>3s}  {'buy':26s} {'kill':>6s} {'duel':>6s} {'alive':>6s} wins  " + " ".join(f"{SHORT.get(t, t):>5s}" for t in th))
    for p in view:
        print(f"{p['slot']:4d} {p['level']:3d}  {p['item']:26s} {p['kill']:5.2f}s {pct(p['duel']):>6s} {p['safe']:5.2f}s "
              f"{p['wins']}/{len(th)}  " + " ".join(f"{pct(p['per'][t]['duel']):>5s}" for t in th))
    n = len(view)
    print(f"average: kill {sum(p['kill'] for p in view) / n:.2f}s, duel {pct(sum(p['duel'] for p in view) / n)}, "
          f"{sum(p['wins'] for p in view)}/{n * len(th)} duel wins")


def cmd_build(a):
    cfg = config_from(a)
    items = [find_item(x) for x in a.items]
    page = RunePage.parse(a.runes, a.stacks)
    ne = a.enemy_items if a.enemy_items is not None else sum(i not in SPK.BOOTS and i != SPK.DORANS for i in items)
    print(f"Kalista level {a.level}: {', '.join(item_name(i) for i in items) or 'no items'} · {page.label()} "
          f"(legend {a.stacks}) · enemies own {ne} items")
    print("  " + "  ".join(f"{k} {v}" for k, v in statline("Kalista", a.level, items, page).items() if k != "level"))
    duel_m = saved_mults("spikes.json") or {}
    lane_m = saved_mults("lane.json") or {}
    r = SPK.Ranker(cfg, duel_m or None)
    opts = Opts(kite_uptime=cfg.kite_uptime)
    print(f"\n{'enemy':10s} {'kill time':>9s}   duel")
    for kind in cfg.threats:
        d = make_dummy(kind, a.level, ne)
        ttk = simulate(items, a.level, d, page, opts)["ttk"]
        du = simulate(items, a.level, d, page, opts, r.threats[kind], ne)
        res = f"won, {du['kal_hp_left'] * 100:.0f}% HP left" if du["win"] else f"lost, enemy on {du['enemy_hp_left'] * 100:.0f}%"
        print(f"{kind:10s} {ttk:8.2f}s   {res} (kill {du['tk']:.2f}s, death {min(du['td'], 99):.2f}s)")
    la = LaneAnalysis(cfg, lane_m or None)
    print(f"\n{'lane enemy':10s} {'quick':>7s} {'extended':>9s} {'pressure':>9s}")
    for kind in la.kinds:
        q = la.trade(items, a.level, kind, ne, page)["net"]
        l = la.trade(items, a.level, kind, ne, page, windows=cfg.long_windows)["net"]
        p = la.pressure(items, a.level, kind, ne, page)
        print(f"{kind:10s} {q * 100:+6.1f}% {l * 100:+8.1f}% {p * 100:8.0f}%")
    if not duel_m: print("\n(no spikes.json yet: enemy damage is uncalibrated; run `kalista run` first)")


def cmd_items(a):
    rev = {}
    for k, v in ALIASES.items(): rev.setdefault(v, []).append(k)
    for i in sorted(KNOWN, key=item_name):
        print(f"{i}  {item_name(i):28s} {', '.join(rev.get(i, []))}")


def cmd_update(a):
    from .datasync import main
    return main((["--apply"] if a.apply else []) + (["--version", a.version] if a.version else []))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kalista", description=f"Kalista DPS checker (patch {PATCH}).",
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run", help="whole pipeline: spikes.json, lane.json, kalista_spikes.html")
    p.add_argument("--out", default=HERE, help="output folder (default: the repo)")
    add_scenario(p); p.set_defaults(fn=cmd_run)
    p = sub.add_parser("optimize", help="best build for one goal")
    p.add_argument("--goal", choices=list(SPK.GOALS), default="practical")
    p.add_argument("--runes", default="auto", help="'auto' (search 24 pages) or a page like 'Press the Attack / Alacrity / Cut Down'")
    p.add_argument("--ap", action="store_true", help="AP and on-hit items only")
    p.add_argument("--recalibrate", action="store_true", help="recompute enemy damage instead of reading spikes.json")
    p.add_argument("--json", action="store_true")
    add_scenario(p, lane=False); p.set_defaults(fn=cmd_optimize)
    p = sub.add_parser("build", help="one build: stats, kill times, duels, lane trades")
    p.add_argument("items", nargs="*", help="item names, ids or nicknames (see `kalista items`)")
    p.add_argument("--level", type=int, default=13)
    p.add_argument("--runes", default="Press the Attack / Alacrity / Cut Down")
    p.add_argument("--stacks", type=int, default=10, help="Legend stacks, 0-10")
    p.add_argument("--enemy-items", type=int, help="enemy item count (default: same as yours)")
    add_scenario(p); p.set_defaults(fn=cmd_build)
    p = sub.add_parser("items", help="items the tool understands"); p.set_defaults(fn=cmd_items)
    p = sub.add_parser("update-data", help="refresh Data Dragon files and AD growth")
    p.add_argument("--apply", action="store_true"); p.add_argument("--version")
    p.set_defaults(fn=cmd_update)
    a = ap.parse_args(argv)
    return a.fn(a) or 0
