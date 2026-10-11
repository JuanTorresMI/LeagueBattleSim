"""Headline summary of spikes.json + lane.json, the numbers HANDOFF.md reports.

    python3 tests/snapshot.py            # print the summary of the current outputs
    python3 tests/snapshot.py --update   # rewrite tests/snapshots/summary.json

Only update the snapshot when a change is meant to move the results."""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SNAPSHOT = os.path.join(HERE, "snapshots", "summary.json")


def summarize(spikes, lane):
    builds = {}
    for g, b in spikes["builds"].items():
        p = b["path"]
        builds[g] = {"page": b["page"], "boots": b["boots"], "items": [s["item"] for s in p],
                     "avg_kill_s": round(sum(s["kill"] for s in p) / len(p), 2),
                     "avg_duel": round(sum(s["duel"] for s in p) / len(p), 3),
                     "duel_wins": sum(s["wins"] for s in p)}
    ap = spikes["ap"]
    return {
        "patch": spikes["patch"],
        "duel_calibration": {k: v["mult"] for k, v in spikes["calibration"].items()},
        "builds": builds,
        "ap_build": {"page": ap["page"], "items": [s["item"] for s in ap["path"]],
                     "avg_duel": round(sum(s["ap_duel"] for s in ap["vs_best"]) / len(ap["vs_best"]), 3)},
        "lane_calibration": {k: v["mult"] for k, v in lane["calibration"].items()},
        "lane": {"page": lane["best_page"], "items": lane["lane_path"]["items"],
                 "boots": lane["lane_path"]["boots"],
                 "stages": [{k: s[k] for k in ("stage", "trade", "long", "pressure", "execs")}
                            for s in lane["lane_path"]["stages"]]},
    }


def load(root=ROOT):
    with open(os.path.join(root, "spikes.json"), encoding="utf-8") as f:
        spikes = json.load(f)
    with open(os.path.join(root, "lane.json"), encoding="utf-8") as f:
        lane = json.load(f)
    return summarize(spikes, lane)


if __name__ == "__main__":
    summary = load()
    text = json.dumps(summary, indent=1, ensure_ascii=False) + "\n"
    if "--update" in sys.argv:
        with open(SNAPSHOT, "w", encoding="utf-8") as f:
            f.write(text)
        print("wrote", SNAPSHOT)
    else:
        print(text, end="")
