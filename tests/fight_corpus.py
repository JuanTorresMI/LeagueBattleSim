"""A fixed corpus of 1,000 random fights (items, level, enemy, runes, options; one-way,
duel and trade windows) and their exact results, stored in tests/snapshots/fights.json.

    python3 tests/fight_corpus.py --update   # after a change meant to alter fight results

tests/test_corpus.py re-runs every fight and requires identical results, so a refactor
or speed-up cannot change behavior silently."""
import json, math, os, random, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import engine  # noqa: E402
from lolsim import spikes  # noqa: E402

CORPUS = os.path.join(HERE, "snapshots", "fights.json")
POOL = sorted(spikes.POOL) + sorted(spikes.BOOTS) + [spikes.DORANS]


def cases(n=1000, seed=7):
    rng = random.Random(seed)
    for _ in range(n):
        case = {"items": rng.sample(POOL, rng.randint(0, 6)), "level": rng.randint(1, 18),
                "kind": rng.choice(list(engine.THREATS)), "enemy_items": rng.randint(0, 5),
                "page": rng.choice(spikes.ALL_PAGES).label(), "stacks": rng.randint(0, 10),
                "duel": rng.random() < 0.7, "mult": rng.choice([1.0, 1.85, 2.8, 4.5]),
                "opts": {"yuntal_prestacked": rng.random() < 0.7, "kite_uptime": rng.choice([0.4, 0.65, 0.9]),
                         "gunblade_active": rng.random() < 0.7}}
        if rng.random() < 0.4:
            case["opts"].update(window=rng.choice([1.75, 2.0, 3.5]), exit_e=True,
                                enemy_start=rng.choice([1.0, 0.25, 0.6]), kal_start=rng.choice([1.0, 0.6, 0.8]))
        yield case


def clean(x):
    if isinstance(x, float):
        return "inf" if math.isinf(x) else round(x, 9)
    if isinstance(x, dict): return {k: clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)): return [clean(v) for v in x]
    return x


def run(case):
    th = engine.THREATS[case["kind"]]
    saved, th.dmg_mult = th.dmg_mult, case["mult"]
    try:
        page = engine.RunePage.parse(case["page"], case["stacks"])
        r = engine.simulate(case["items"], case["level"], engine.make_dummy(case["kind"], case["level"], case["enemy_items"]),
                            page, engine.Opts(**case["opts"]), th if case["duel"] else None, case["enemy_items"], trace=True)
    finally:
        th.dmg_mult = saved
    return clean(r)


if __name__ == "__main__":
    out = [{"case": c, "result": run(c)} for c in cases()]
    if "--update" in sys.argv:
        with open(CORPUS, "w", encoding="utf-8") as f:
            json.dump(out, f, separators=(",", ":"))
        print("wrote", CORPUS, len(out), "fights")
