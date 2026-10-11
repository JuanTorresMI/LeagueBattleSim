"""
League of Legends DPS + duel engine — patch 16.20.1
===================================================
Compatibility layer: the engine lives in the `lolsim` package (stats, runes, enemies,
kits, effects, fight). This module re-exports the names spikes.py, lane.py and older
scripts use.

Game numbers live in data/wiki/*.json (source + patch per entry) and model choices in
config/*.json. Anything marked VERIFY is worth confirming in the Practice Tool.
"""
from lolsim.stats import (CHAMPS, ITEMS, CRIT_BASE, AS_CAP, AD_GROWTH_OVERRIDE, EXTRA_ITEM_STATS,
                          Stats, growth, lvl_scale, lvl_linear, build_stats, statline,
                          resist_mult, eff_resist, item_name, item_cost)
from lolsim.runes import RunePage, KEYSTONES, LEGENDS, COMBAT
from lolsim.enemies import (Dummy, DUMMY_KINDS, make_dummy, Ability, Threat, THREATS, ENEMY_ITEMS,
                            Enemy, threat_from_config)
from lolsim.kits import (KITS, Kit, Kalista, RANKS_BY_LEVEL, AA_AD_RATIO, Q_BASE, Q_RATIO, Q_CD, Q_CAST,
                         E_FIRST, E_FIRST_AD, E_FIRST_AP, E_ADD, E_ADD_AD, E_ADD_AP, rend_raw)
from lolsim.effects import REGISTRY as EFFECTS, HOOKS
from lolsim.fight import Opts, Fight, simulate

SPELLBLADE = {"3100", "2510"}
ENERGIZED = {"3087", "3095", "3094"}
