"""Full-fight goals and item rankings: python3 spikes.py writes spikes.json (default config).

The code lives in lolsim/spikes.py; `./kalista run` runs the whole pipeline with flags."""
import json, os

from lolsim.config import Config
from lolsim.spikes import *            # noqa: F401,F403  (pools, Ranker, helpers)
from lolsim.spikes import Ranker, make_pool


def main(out="spikes.json", cfg=None):
    cfg = cfg or Config(jobs=os.cpu_count() or 1)
    pool = make_pool(cfg)
    try:
        report = Ranker(cfg, pool=pool).report(log=lambda *a: print(*a, flush=True))
    finally:
        if pool: pool.close(); pool.join()
    with open(out, "w") as f: json.dump(report, f, indent=1)
    print("done in", report["runtime_s"], "s")
    return report


if __name__ == "__main__":
    main()
