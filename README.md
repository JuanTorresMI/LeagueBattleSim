# LoL DPS Checker v4 (patch 16.20.1)

Run: `./run_all.sh` (~80 s): spikes.py → spikes.json, lane.py → lane.json, build_page.py → kalista_spikes.html. See HANDOFF.md for the full write-up.

Tests: `pytest` (about 1 s; pytest is the only dev dependency). `pytest --runslow` also reruns
the whole pipeline in a temp dir and checks it reproduces spikes.json and lane.json exactly.
After a change that is meant to move the results, rerun the pipeline, then
`python3 tests/snapshot.py --update` and update the golden numbers in tests/test_fight.py.

## Files
- `engine.py`: stat engine (any champion, level, items), damage math, Kalista kit,
  item passives, Precision runes, scaling target dummies, fight simulator.
- `spikes.py`: slot-by-slot item spike ranking + rune page comparison + AP-only search.
- `build_page.py`: renders the results page.
- `data/`: Riot Data Dragon 16.20.1.

## Spike schedule
Start Doran's Blade. Item 1 at lvl 9, item 2 + Berserker's Greaves at lvl 11,
item 3 at lvl 13, item 4 at lvl 15, item 5 at lvl 17 (Doran's sold).
Enemy dummies have the same number of items as you.

## Scoring
Geometric-mean time-to-kill over squishy / bruiser / tank dummies, averaged over
target HP x0.85-1.15 to remove whole-attack ties. Slot weights 0.30 / 0.25 /
0.20 / 0.15 / 0.10 (early spikes count most). Beam search keeps the 10 best paths.

## Dummies (`DUMMY_KINDS` in engine.py)
Jinx / Darius / Ornn base stats at the fight's level, plus per enemy item:
squishy +80 HP; bruiser +300 HP, +12 armor, +8 MR; tank +400 HP, +35 armor, +20 MR.

## Runes
Keystones: Press the Attack, Lethal Tempo, Conqueror, Fleet Footwork.
Legend: Alacrity always (legend stacks grow 1 -> 10 across the game).
Combat row: Coup de Grace or Cut Down (Last Stand needs your own missing HP).

## Items modeled
AD/crit: IE, Yun Tal (unstacked the slot you buy it), LDR, Mortal Reminder, Serylda's,
Phantom Dancer, RFC, Stormrazor, Navori, Runaan's, BotRK, Kraken, Black Cleaver,
Bloodthirster, Hexoptics, Collector, Shieldbow, Youmuu's.
On-hit: Guinsoo's, Wit's End, Terminus, Statikk Shiv.
AP: Riftmaker, Nashor's, Rabadon's, Void Staff, Shadowflame, Lich Bane,
Dusk and Dawn, Liandry's, Stormsurge, Hextech Gunblade, Bloodletter's Curse.

## VERIFY in Practice Tool
200% default crit damage; Kalista autos at 100% AD; Kraken ranged scaling (linear
assumed); Dusk and Dawn repeat on-hit adding a Rend spear; Bloodletter's stacking
from item on-hit magic; Conqueror stacks from Q (2 assumed); rune level scaling
(growth curve assumed).

## Not valued
Multi-target damage, W Soul-Mark, mana, summoner spells, positioning and teammates,
gold timing beyond the fixed spike levels. (Survivability is covered by the v3 duel.)

## v3: two-way duels
- `THREATS` in engine.py: marksman, bruiser, tank, mage. Each has auto attacks, an
  opener ability with crowd control that repeats on cooldown, item-based armor/magic
  pen and Grievous Wounds, all scaling with level and enemy item count.
- Calibration (`calibrate()` in spikes.py): one damage multiplier per threat, fixed for
  the whole game, set so a standard crit Kalista (Yun Tal, IE, LDR, Stormrazor, BotRK)
  narrowly wins on average (target +5% HP left).
- Kalista survival: lifesteal, omnivamp (Gunblade, Riftmaker at full strength, Maw),
  Conqueror and Fleet Footwork heals, Bloodthirster Ichorshield, Shieldbow and Maw
  lifelines, Death's Dance (10% ranged), Guardian Angel revive, Plated Steelcaps,
  tenacity (Mercury's, Wit's End), Legend: Bloodline, Last Stand.
- Kiting: melee threats land 65% of their damage by default (`kite_uptime`).
- Duel score: Kalista's HP left when the fight ends (negative = enemy HP left on a loss),
  averaged over enemy HP x0.9/1.0/1.1.
- Goals: fastest kill, best duelist, best duelist without Guardian Angel, hardest to kill.
  Each runs its own beam search, boots choice and 24-page rune search.

## v4: laning (`lane.py`, ~2 s; run after spikes.py)
- Quick trade: ~2 s (1.75/2.0/2.25) of Q + autos into the enemy's retaliation, then
  Rend on the way out. Extended trade: ~3.5 s. Score = enemy % max HP lost minus
  Kalista % max HP lost (damage still stored in Death's Dance counts as taken).
- Execute: enemy at 25% HP, Kalista at 60%, enemy escapes after 2 s.
- Kill pressure: highest enemy HP % Kalista can kill within 2 s (Kalista at 80%).
- Lane threats: enemy marksman, poke mage support, engage tank support, calibrated so
  Doran's Blade + Press the Attack / Alacrity / Cut Down trades exactly even across
  levels 2, 3 and 6.
- Lane score = 0.6 quick + 0.4 extended + 0.25 kill pressure.
- Gunblade's active (60 s cooldown) counts in half of trades, always in all-ins.
- Ranks all 24 rune pages (lvl 2/3/6), the first item (lvl 9) and the second item
  + boots (lvl 11), and scores each full-fight build's first two items in lane.

## v4.1: tests (roadmap steps 1-2)
- Reproduced: `./run_all.sh` matches the committed spikes.json and lane.json exactly
  (except `runtime_s`); about 55 s on this machine.
- `tests/test_stats.py`: Kalista level 1 / 18 base stats against the wiki
  (Module:ChampionData), growth curve, AS cap, description-only item stats.
- `tests/test_damage.py`: resistance multiplier; reduction → % pen → flat pen order,
  floor at 0, no pen on negative resists; Rend scaling.
- `tests/test_fight.py`: a fixed Kalista fight trace (attack times, spears, Rend kill),
  one duel per threat, one lane trade per lane threat, exit Rend.
- `tests/test_snapshots.py`: headline results vs `tests/snapshots/summary.json`; calibration,
  every goal build at every spike, and the lane path recomputed from the engine and
  compared with the committed JSON; `--runslow` full pipeline run.
- Duel tests set `THREATS[*].dmg_mult` explicitly through a fixture, because both
  `calibrate()` functions mutate these globals.

## v4.2: numbers in data files (roadmap step 3)
- `data/wiki/*.json`: every game number Data Dragon leaves out (item passives and
  description-only stats, runes, crit/AS/growth/Energized rules, Kalista's kit, AD growth
  overrides), one entry per item / rune / rule with `source` (wiki URL), `patch`,
  `values` and, where unconfirmed, `verify`.
- `config/*.json`: model choices: `threats.json` (threat profiles and fastest-kill
  dummies), `scoring.json` (spike schedule, grids, weights, trade windows, lane scenarios),
  `calibration.json` (reference builds and targets).
- `params.py` loads both; `tests/test_data.py` checks every wiki entry has a source and patch.
- Results unchanged (the full pipeline reproduces the JSON outputs exactly).

## v4.3: restructured engine (roadmap step 4)
- `lolsim/` package: `stats.py` (stat engine, damage math), `runes.py`, `enemies.py`
  (dummies, threat profiles, the enemy's event queue), `kits.py` (`Kit` base class and
  `Kalista`), `effects.py` (34 item and rune effects registered by hook), `fight.py`
  (`Fight` state and loop, `simulate()`).
- Hooks: `damage_amp`, `on_damage`, `omnivamp`, `on_ability`, `attack_speed`, `on_attack`,
  `on_hit`, `on_attack_bonus`, `on_rune`, `after_attack`, `on_tick`, `on_take_damage`,
  `on_low_hp`, `on_lethal` and a few more (listed in `effects.py`). Handlers of one hook run
  in class-definition order, which keeps the v3 order wherever it changes a result.
- `engine.py` is now a re-export layer, so `spikes.py`, `lane.py` and old scripts are unchanged.
- `tests/reference/engine_v3.py` is a frozen copy of the old simulator;
  `tests/test_equivalence.py` checks 1,000 random fights match it exactly. The full
  pipeline also reproduces the JSON outputs exactly.

## v4.4: data updates (roadmap step 5)
- `python3 -m lolsim.datasync` reports, `--apply` writes: latest Data Dragon version
  (GitHub mirror fallback when Riot's CDN is blocked), champion/item/Kalista files, AD growth
  for every champion from the wiki's Module:ChampionData, warnings when a model item's
  description, stats or cost changes, base stats where Data Dragon and the wiki disagree,
  and data/wiki entries last checked on an older patch. Writes `data/update_report.md`.
- Applied for 16.20.1: Data Dragon files unchanged; AD growth now covers all 173 champions
  (Kalista, Jinx and Caitlyn unchanged). Known disagreements: Jhin AS growth, Kled HP (mount).
