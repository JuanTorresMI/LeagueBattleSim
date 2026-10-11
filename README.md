# LoL DPS Checker v6 (patch 16.20.1)

## Quick start
Plain Python 3, no packages (pytest only for tests).
- `./run_all.sh` (or `./kalista run`): about 15 s on 4 cores; writes spikes.json, lane.json and
  **kalista_spikes.html** (open it in a browser; its build editor runs the simulator in-page).
- `./kalista optimize --goal practical`: best build for one goal (`kill`, `duel`, `practical`, `safe`).
- `./kalista build yuntal ie ldr zerks --level 13`: check any build (`./kalista items` lists names).
- `./kalista teamfight shieldbow yuntal ldr steelcaps --level 13`: the build in 2v2, 3v3 and 5v5 fights
  (`--scenario 5v5 --targeting back` prints the fight's timeline).
- `./kalista optimize --goal carry`: best build for solo queue skirmishes *and* teamfights.
  `--start bc,shieldbow`, `--exclude statikk`, `--boots steelcaps` steer the search.
- `./kalista --help` for scenario flags (threats, kiting, weights, real enemy kits, Vayne, Soul-Mark).
- `pytest` (about 2 s), `pytest --runslow` (adds a full pipeline run).
- Assumptions and their wiki status: `docs/ASSUMPTIONS.md`. Change log by version below.

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

## v5.0: assumptions settled against the wiki (roadmap step 6)
See `docs/ASSUMPTIONS.md`. Confirmed: 200% crit, Kalista autos at 100% AD, Fleet Footwork
9–96, Conqueror 2 stacks per Pierce. Corrected: Kraken Slayer (120 to level 8, +4 per level),
Bloodletter's Curse (never stacks for Kalista), and level scaling for Press the Attack,
Lethal Tempo, Conqueror, Bloodthirster, Shieldbow and Gunblade (several v4 level-18 values
were the wiki's level-20 values). Dusk and Dawn now heals on the empowered hit. Still to
measure: Dusk and Dawn's spear, Gunblade at 18, Kraken's missing-health curve.
- Results: calibration multipliers unchanged; fastest-kill, hardest-to-kill and lane
  builds unchanged. Best duelist, no GA is now Black Cleaver → Shieldbow → BotRK → Dusk and
  Dawn → Mortal Reminder (the v4 path scores within 0.2%); best duelist now takes
  Mercury's Treads with GA → Shieldbow → Gunblade → Youmuu's → Navori.
- `tests/fight_corpus.py` + `tests/test_corpus.py`: 1,000 stored random fights must
  reproduce exactly (replaces the v3 code oracle, which no longer matches by design).

## v5.1: command line (roadmap step 7)
`./kalista --help` (or `python3 -m lolsim`):
- `./kalista run [flags]`: whole pipeline (also `./run_all.sh`), parallel on all cores.
- `./kalista optimize --goal practical --threat bruiser --kite 0.8 --runes auto`: one goal.
  `--runes` takes `auto` (search 24 pages) or a page label; `--ap` limits to AP/on-hit items.
- `./kalista build yuntal ie ldr zerks --level 13`: stat line, kill time and duel per threat,
  quick/extended trades and kill pressure per lane threat. Items by name, id or nickname
  (`./kalista items`).
- `./kalista update-data [--apply]`: Data Dragon and AD growth refresh.
- Scenario flags: `--threat`, `--kite`, `--weights`, `--beam-width`, `--lane-threat`,
  `--quick-windows`, `--long-windows`, `--lane-weights`, `--gunblade-share`, `--jobs`.
  Defaults come from `config/*.json`; calibration stays on config/calibration.json.
- Analysis code moved into `lolsim/spikes.py` (`Ranker`) and `lolsim/lane.py`
  (`LaneAnalysis`); each holds its own threat multipliers, so nothing mutates globals.
  `spikes.py`, `lane.py` and `build_page.py` remain as thin scripts.

## v5.2: results page (roadmap step 8)
- The page is `templates/page.html` (HTML, CSS and JS) with placeholders `__DATA__`,
  `__EDITOR__`, `__ENGINE__`, `__PATCH__`; `build_page.py` fills them. Same sections and
  phone layout as before.
- New **build editor** section: pick items (6 slots), level, enemy items, keystone / legend /
  combat rune, legend stacks and kiting share, or start from any goal or lane build at any
  spike; it shows the stat line, kill time and duel per threat (with damage taken) and
  quick/extended trades and kill pressure per lane threat, with inventory warnings
  (exclusive items, boots, duplicates). It runs the real `lolsim` engine in the browser via
  Pyodide 0.26.4 (loaded from jsDelivr on demand); the engine source and trimmed data
  (~140 KB) are embedded in the page. `lolsim/editor.py` is shared with `kalista build`.
- Checks: `tests/test_page.py` (template filled, script parses under node, embedded engine
  runs standalone and matches); `tools/check_page.js` (Playwright: no errors, no horizontal
  scroll at 1100 px and 390 px, editor loads and fills its tables).

## v5.3: champion kits and Soul-Mark (roadmap step 9, part 1)
- Any champion can be simulated: `kit_for(champ)` returns its kit or a plain auto-attacker
  (`--champion Jinx`). `Vayne` is a second full kit (Tumble empowers the next auto, Silver
  Bolts every third hit), from data/wiki/champions.json. `skill_ranks()` derives skill
  points from a start order and a max order.
- Calibration always uses Kalista without Soul-Mark, so other champions and options are
  scored against the same enemies.
- `--soul-mark` (or `Opts(soul_mark=True)`, `Config(soul_mark=True)`): Kalista's Oathsworn
  support keeps the target marked; her hits then deal 10–18% max health magic damage
  (by W rank) once per 10 s. Off by default.
- Ability hooks now pass `damaging`: Conqueror and Liandry's react only to ability damage
  (Vayne's Tumble is basic-attack damage).

## v5.4: multi-target value (roadmap step 9, part 2)
- `Opts(secondary_targets=N)` / `--secondary N`: N other enemies with the main target's
  stats stand in reach. Runaan's bolts (2 × 60% AD, crit, on-hit), Statikk's chain (60 magic,
  4–8 targets by level, on-hit) and Rend on the spears those hits leave are tracked as
  `splash` / `splash_by` in the result. Reported, never scored; fight results are identical.
- `./kalista multitarget [owned items] --level 13`: items ranked by damage per second they add
  to the other enemies. `kalista build --secondary 2` and the page editor show it per fight.
- Simplifications: secondaries stay at full HP (BotRK uses their max health), take base
  resistances and no damage amplifiers.
- spikes.json now records `champion`.

## v5.5: real champion kits (roadmap step 9, part 3)
- `data/wiki/enemy_kits.json`: Caitlyn, Ezreal, Lux and Nautilus from the wiki's ability data
  (rank tables, ratios, cooldowns), real base stats from Data Dragon, ranks from a skill order,
  and per-item stats copied from the matching class profile. Modeled: Piltover Peacemaker +
  Headshot every 6th auto; Mystic Shot (with its 1.5 s refund) + Essence Flux; Light Binding +
  Lucent Singularity + Illumination; Dredge Line (1 s stun) + Riptide + Staggering Blow.
  Not modeled: ultimates, shields, slows, roots (Kalista can still attack), missed skillshots.
- Use them anywhere a threat goes: `--threat Caitlyn,Nautilus`, `--lane-threat Caitlyn,Lux`
  (`kalista build`, `optimize`, `run`, the page editor). Kits deal their real numbers
  (uncalibrated) unless `--calibrate-kits` scales them to the same targets as the class
  profiles (e.g. Caitlyn ×1.24, Nautilus ×2.51 for the duel target).
- The class profiles and default results are unchanged.

## v6.0: team fights and the solo queue carry goal
- `lolsim/teamfight.py`: Kalista (the full engine) with allies against an enemy team. Every
  other unit, on both sides, is a class profile or real kit on its own event queue with the
  same targeting rules (`config/teamfight.json`): tanks, carries and mages hit what is in
  front, bruisers dive the carries, units arrive with role-based engage delays, stuns delay
  their targets. Teams mirror each other except that Kalista replaces the enemy marksman, so
  with a marksman profile in her place every fight is exactly even (tested at every spike):
  the score is what her build adds.
- Kalista hits one target at a time and moves on when it dies: spears, Black Cleaver, Giant
  Slayer and Press the Attack stacks reset per target, her own buffs carry over. Runaan's
  bolts, Statikk's chain and Rend on their spears land on the other enemies.
- Scenarios: 2v2 bot lane, 3v3 with junglers, 5v5 (supports own half the items). Score like
  the duel score (team HP left on a win, minus enemy HP left on a loss), averaged over
  Kalista hitting the frontline first and the backline first.
- New goal `carry` ("Solo queue carry"): 20% duel + 30% 2v2 + 30% 3v3 + 20% 5v5
  (`carry_weights` in config/teamfight.json). Result: Lethal Tempo / Bloodline / Last Stand,
  Steelcaps, Shieldbow → Yun Tal → LDR → Runaan's → BotRK: best 3v3 and 5v5 of all builds,
  +28% duel, 19/20 duel wins, 42% of the team's damage in 5v5.
- `kalista teamfight`, team rows in `kalista build`'s page editor, and a Team fights section
  plus a carry column on the results page. Pipeline: about 30 s on 4 cores.
