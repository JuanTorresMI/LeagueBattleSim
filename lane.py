"""Lane trades: python3 lane.py writes lane.json (reads spikes.json; default config).

The code lives in lolsim/lane.py; `./kalista run` runs the whole pipeline with flags."""
import json

from lolsim.config import Config
from lolsim.lane import LaneAnalysis


def main(spikes_path="spikes.json", out="lane.json", cfg=None):
    with open(spikes_path) as f: spikes = json.load(f)
    report = LaneAnalysis(cfg or Config()).report(spikes, log=lambda *a: print(*a, flush=True))
    with open(out, "w") as f: json.dump(report, f, indent=1)
    print("done in", report["runtime_s"], "s")
    return report


if __name__ == "__main__":
    main()
