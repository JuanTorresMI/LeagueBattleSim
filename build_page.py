"""Render spikes.json + lane.json into a self-contained HTML page (kalista_spikes.html).

The page is templates/page.html with three placeholders: __DATA__ (the results),
__EDITOR__ (lists for the build editor) and __ENGINE__ (the simulator's Python source and
trimmed data files, which the build editor loads into Pyodide in the browser)."""
import glob, json, html, os

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "templates", "page.html")
ENGINE_MODULES = ["params.py"] + [f"lolsim/{m}.py" for m in
                  ("__init__", "stats", "runes", "enemies", "kits", "effects", "fight", "config", "spikes", "lane", "editor")]


def _read(rel):
    with open(os.path.join(HERE, rel), encoding="utf-8") as f: return f.read()


def engine_files():
    """Source and data the build editor needs, with Data Dragon trimmed to what it reads."""
    from lolsim import spikes
    from lolsim.stats import ITEMS, CHAMPS, PATCH
    from params import ITEM, THREAT_CFG
    files = {m: _read(m) for m in ENGINE_MODULES}
    for p in sorted(glob.glob(os.path.join(HERE, "data", "wiki", "*.json")) + glob.glob(os.path.join(HERE, "config", "*.json"))):
        files[os.path.relpath(p, HERE).replace(os.sep, "/")] = _read(os.path.relpath(p, HERE))
    keep = set(spikes.POOL) | set(spikes.BOOTS) | {spikes.DORANS} | set(ITEM)
    items = {i: {k: ITEMS[i][k] for k in ("name", "stats", "gold")} for i in sorted(keep) if i in ITEMS}
    champs = {"Kalista"} | {d["champion"] for k, d in THREAT_CFG["dummies"].items() if not k.startswith("_")}
    files["data/item.json"] = json.dumps({"version": PATCH, "data": items}, separators=(",", ":"))
    files["data/champion.json"] = json.dumps({"version": PATCH, "data": {c: {"name": CHAMPS[c]["name"], "stats": CHAMPS[c]["stats"]}
                                                                         for c in sorted(champs)}}, separators=(",", ":"))
    return files


def editor_data():
    from lolsim import spikes
    from lolsim.config import Config
    from lolsim.runes import KEYSTONES, LEGENDS, COMBAT
    from lolsim.stats import item_name
    from lolsim.kits import KITS
    cfg = Config()
    ids = list(spikes.POOL) + list(spikes.BOOTS) + [spikes.DORANS]
    return {"items": {i: item_name(i) for i in ids}, "starter": spikes.DORANS, "legend": cfg.legend,
            "keystones": KEYSTONES, "legends": LEGENDS, "combat": COMBAT, "kite": cfg.kite_uptime,
            "champions": list(KITS),
            "lane_stages": [list(s) for s in cfg.lane_stages]}


def _script_json(obj):
    """JSON safe to embed in a <script> element."""
    return json.dumps(obj, separators=(",", ":")).replace("</", "<\\/")


def render(spikes, lane):
    r = dict(spikes, lane=lane)
    with open(TEMPLATE, encoding="utf-8") as f: page = f.read()
    return (page.replace("__ENGINE__", _script_json(engine_files()))
                .replace("__EDITOR__", _script_json(editor_data()))
                .replace("__DATA__", _script_json(r))
                .replace("__PATCH__", html.escape(r["patch"])))


def main(spikes_path="spikes.json", lane_path="lane.json", out_path="kalista_spikes.html"):
    with open(spikes_path, encoding="utf-8") as f: spikes = json.load(f)
    with open(lane_path, encoding="utf-8") as f: lane = json.load(f)
    out = render(spikes, lane)
    with open(out_path, "w", encoding="utf-8") as f: f.write(out)
    print("wrote", len(out), "bytes")


if __name__ == "__main__":
    main()
