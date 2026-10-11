"""The restructured engine (lolsim) must match the frozen v3 simulator exactly on random
fights: random items, level, enemy, runes and options, one-way, duel and trade windows."""
import random

import pytest

import engine
import spikes
from tests.reference import engine_v3 as v3

POOL = list(spikes.POOL) + list(spikes.BOOTS) + [spikes.DORANS]
PAGES = spikes.ALL_PAGES


def random_case(rng):
    items = rng.sample(POOL, rng.randint(0, 6))
    level = rng.randint(1, 18)
    kind = rng.choice(spikes.KINDS)
    ne = rng.randint(0, 5)
    page = rng.choice(PAGES).at(rng.randint(0, 10))
    kw = dict(yuntal_prestacked=rng.random() < 0.7, kite_uptime=rng.choice([0.4, 0.65, 0.9]),
              gunblade_active=rng.random() < 0.7)
    if rng.random() < 0.4:
        kw.update(window=rng.choice([1.75, 2.0, 3.5]), exit_e=True,
                  enemy_start=rng.choice([1.0, 0.25, 0.6]), kal_start=rng.choice([1.0, 0.6, 0.8]))
    duel = rng.random() < 0.7
    mult = rng.choice([1.0, 1.85, 2.813, 4.554])
    return items, level, kind, ne, page, kw, duel, mult


@pytest.mark.parametrize("seed", range(40))
def test_matches_v3(seed):
    rng = random.Random(seed)
    for _ in range(25):
        items, level, kind, ne, page, kw, duel, mult = random_case(rng)
        d_new, d_old = engine.make_dummy(kind, level, ne), v3.make_dummy(kind, level, ne)
        th_new, th_old = engine.THREATS[kind], v3.THREATS[kind]
        saved = th_new.dmg_mult, th_old.dmg_mult
        th_new.dmg_mult = th_old.dmg_mult = mult
        try:
            pg_old = v3.RunePage(page.keystone, page.legend, page.legend_stacks, page.combat)
            new = engine.simulate(items, level, d_new, page, engine.Opts(**kw),
                                  th_new if duel else None, ne, trace=True)
            old = v3.simulate(items, level, d_old, pg_old, v3.Opts(**kw),
                              th_old if duel else None, ne, trace=True)
        finally:
            th_new.dmg_mult, th_old.dmg_mult = saved
        assert new == old, (items, level, kind, ne, page, kw, duel)
