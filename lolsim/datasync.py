"""Data updates: Data Dragon files, AD growth from the wiki, and change warnings.

    python3 -m lolsim.datasync                 # report only: latest version, what would change
    python3 -m lolsim.datasync --apply         # download and write data/ + AD growth
    python3 -m lolsim.datasync --version 16.19.1 --apply

What it does
  1. Finds the latest Data Dragon version (Riot's versions.json; falls back to the
     InFinity54/LoL_DDragon GitHub mirror where Riot's CDN is blocked).
  2. Downloads champion.json, item.json and champion/Kalista.json.
  3. Warns when an item the model uses changes its description, stats or cost, so the
     matching data/wiki entry can be re-checked.
  4. Reads every champion's stats from the wiki (Module:ChampionData/data): fills AD
     growth for all champions (Data Dragon reports 0) and flags base stats that disagree
     with Data Dragon.
  5. Lists data/wiki entries last checked on an older patch.
  It writes data/update_report.md either way."""
import argparse, json, os, re, sys, urllib.request

from params import HERE, ITEM_INFO, CHAMP_INFO, all_wiki_entries

DATA = os.path.join(HERE, "data")
DDRAGON = "https://ddragon.leagueoflegends.com"
MIRROR = "https://raw.githubusercontent.com/InFinity54/LoL_DDragon/master/latest"
WIKI_CHAMPS = "https://wiki.leagueoflegends.com/en-us/Module:ChampionData/data?action=raw"
FILES = {"champion.json": "data/en_US/champion.json", "item.json": "data/en_US/item.json",
         "Kalista.json": "data/en_US/champion/Kalista.json"}
# wiki stat key -> Data Dragon stat key, for the base-stat cross-check
STAT_KEYS = {"hp_base": "hp", "hp_lvl": "hpperlevel", "arm_base": "armor", "arm_lvl": "armorperlevel",
             "mr_base": "spellblock", "mr_lvl": "spellblockperlevel", "dam_base": "attackdamage",
             "as_base": "attackspeed", "as_lvl": "attackspeedperlevel", "ms": "movespeed"}


def fetch(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "lolsim-datasync/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def latest_version():
    try:
        return json.loads(fetch(DDRAGON + "/api/versions.json"))[0], "ddragon"
    except Exception as e:                                    # CDN blocked: use the mirror
        print(f"Riot CDN unavailable ({e}); using the GitHub mirror", file=sys.stderr)
        return json.loads(fetch(MIRROR + "/" + FILES["champion.json"]))["version"], "mirror"


def download(version, source):
    out = {}
    for name, path in FILES.items():
        url = (f"{DDRAGON}/cdn/{version}/{path}" if source == "ddragon" else f"{MIRROR}/{path}")
        out[name] = fetch(url)
    return out


def parse_champion_module(lua):
    """{apiname: {wiki stat: value}} from Module:ChampionData/data (first stats block only;
    nested alternate forms are skipped)."""
    out = {}
    blocks = re.split(r'\n  \["[^"]+"\] = \{', lua)
    for b in blocks[1:]:
        api = re.search(r'\["apiname"\]\s*=\s*"([^"]+)"', b)
        st = re.search(r'\["stats"\]\s*=\s*\{(.*?)\n    \}', b, re.S)
        if not api or not st: continue
        stats = {}
        for line in st.group(1).split("\n"):
            m = re.match(r'      \["(\w+)"\]\s*=\s*(-?[\d.]+)', line)        # 6-space indent: top-level form
            if m: stats[m.group(1)] = float(m.group(2))
        out[api.group(1)] = stats
    return out


def item_changes(old_items, new_items, ids):
    """Human-readable changes for the given item ids between two item.json 'data' dicts."""
    rows = []
    for iid in sorted(ids):
        o, n = old_items.get(iid), new_items.get(iid)
        name = (n or o or {}).get("name", iid)
        if o is None or n is None:
            rows.append(f"{iid} {name}: {'added' if o is None else 'removed'}"); continue
        if o.get("description") != n.get("description"): rows.append(f"{iid} {name}: description changed")
        if o.get("stats") != n.get("stats"): rows.append(f"{iid} {name}: stats {o.get('stats')} -> {n.get('stats')}")
        if o.get("gold", {}).get("total") != n.get("gold", {}).get("total"):
            rows.append(f"{iid} {name}: cost {o['gold']['total']} -> {n['gold']['total']}")
    return rows


def stat_mismatches(wiki, champs):
    rows = []
    for cid, c in sorted(champs.items()):
        w = wiki.get(cid)
        if w is None: rows.append(f"{cid}: not in the wiki module"); continue
        for wk, dk in STAT_KEYS.items():
            if wk in w and abs(w[wk] - c["stats"].get(dk, 0)) > 1e-6:
                rows.append(f"{cid}: {dk} Data Dragon {c['stats'].get(dk)} vs wiki {w[wk]:g}")
    return rows


def model_item_ids():
    from . import spikes
    return set(ITEM_INFO) | set(spikes.POOL) | set(spikes.BOOTS) | {spikes.DORANS}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--version", help="Data Dragon version (default: latest)")
    ap.add_argument("--apply", action="store_true", help="write the downloaded files and AD growth")
    a = ap.parse_args(argv)

    with open(os.path.join(DATA, "champion.json"), encoding="utf-8") as f:
        cur_version = json.load(f)["version"]
    version, source = (a.version, "ddragon") if a.version else latest_version()
    print(f"current {cur_version}, target {version} ({source})")
    new = download(version, source)
    with open(os.path.join(DATA, "item.json"), encoding="utf-8") as f:
        old_items = json.load(f)["data"]
    new_items = json.loads(new["item.json"])["data"]
    new_champs = json.loads(new["champion.json"])["data"]
    changes = item_changes(old_items, new_items, model_item_ids())

    wiki = parse_champion_module(fetch(WIKI_CHAMPS).decode("utf-8"))
    growth = {cid: wiki[cid]["dam_lvl"] for cid in sorted(new_champs) if cid in wiki and "dam_lvl" in wiki[cid]}
    mismatches = stat_mismatches(wiki, new_champs)
    stale = [f"{name}/{key} (patch {e['patch']})" for name, key, e in all_wiki_entries() if e["patch"] != version]
    changed_growth = {k: (CHAMP_INFO["ad_growth"]["values"].get(k), v) for k, v in growth.items()
                      if CHAMP_INFO["ad_growth"]["values"].get(k) != v}

    lines = [f"# Data update report", "", f"Data Dragon: {cur_version} -> {version} (from {source})", "",
             f"## Model items changed ({len(changes)})", *([f"- {r}" for r in changes] or ["- none"]), "",
             f"## AD growth from the wiki ({len(growth)} champions, {len(changed_growth)} new or changed)",
             *[f"- {k}: {o} -> {n}" for k, (o, n) in list(changed_growth.items())[:20]],
             *(["- ..."] if len(changed_growth) > 20 else []), "",
             f"## Base stats where Data Dragon and the wiki disagree ({len(mismatches)})",
             *([f"- {r}" for r in mismatches] or ["- none"]), "",
             f"## data/wiki entries last checked on another patch ({len(stale)})",
             *([f"- {s}" for s in stale] or ["- none"]), ""]
    if a.apply:
        for name, blob in new.items():
            with open(os.path.join(DATA, name), "wb") as f: f.write(blob)
        path = os.path.join(DATA, "wiki", "champions.json")
        with open(path, encoding="utf-8") as f: raw = json.load(f)
        raw["ad_growth"]["values"] = growth
        raw["ad_growth"]["patch"] = version
        raw["ad_growth"]["note"] = ("Data Dragon reports 0 AD growth for every champion; filled from the wiki "
                                    "module by lolsim/datasync.py.")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(raw, f, indent=1, ensure_ascii=False); f.write("\n")
        lines.insert(3, "Applied: data files and AD growth written. Re-run the pipeline and the tests.\n")
    else:
        lines.insert(3, "Report only (run with --apply to write).\n")
    with open(os.path.join(DATA, "update_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
