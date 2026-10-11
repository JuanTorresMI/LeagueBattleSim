# Kalista DPS Checker Handoff

Oct 11, 2026 · Juan (Markdown copy of the "Kalista DPS Checker Handoff" doc)

## How to use this handoff

This doc and the code bundle (kalista-dps-handoff.zip) are everything Fable needs to take the Kalista DPS checker from a working prototype to a polished tool. Upload the zip, point Fable at this file, then paste the prompt below.

```text
You are taking over a working Python prototype: a League of Legends damage and duel simulator for Kalista (patch 16.20.1). The attached zip has the code, data and results; HANDOFF.md explains how it works, what is assumed, and what to polish.

First: run ./run_all.sh and confirm the outputs match the results in HANDOFF.md. Then work through the polish roadmap in order. Keep every game-mechanic number traceable to its source (Data Dragon or the League Wiki), keep the three scenario families (fastest kill, two-way duel, lane trades) and their scoring, and add tests before refactoring. Ask me before changing any scoring weight or calibration target.
```

The roadmap at the end is ordered so each step leaves the tool working: verify, test, restructure, then extend.

## What the tool does today

The tool simulates Kalista fights attack by attack and ranks every item, rune page and build for three jobs: killing fastest, winning duels, and winning lane trades. It runs in about 80 seconds on plain Python 3 with no packages, and writes a single self-contained results page.

| File | What it is |
| --- | --- |
| engine.py | Stat engine for any champion, level and items; damage math; Kalista kit; item passives; Precision runes; enemy threat profiles; the fight simulator (one-way, two-way duel, short trade windows) |
| spikes.py | Full-fight optimizer: four build goals, beam search slot by slot, boots choice, 24 rune pages, duel calibration, per-spike item rankings |
| lane.py | Lane trades: quick and extended trades, executes, kill pressure; lane calibration; rune, first-item and second-item rankings |
| build_page.py | Renders spikes.json + lane.json into kalista_spikes.html |
| data/ | Riot Data Dragon 16.20.1: champion.json, item.json, Kalista.json |
| spikes.json, lane.json | Results from the last run |
| kalista_spikes.html | The results page (open in any browser) |
| run_all.sh | Runs the whole pipeline in order |
| README.md, HANDOFF.md | Change log by version, and this handoff |

Run order: `python3 spikes.py`, then `python3 lane.py`, then `python3 build_page.py` (or `./run_all.sh`). The page check used Playwright for screenshots, which is optional.

## Architecture and data flow

All analysis goes through one function, `simulate()` in engine.py, which spikes.py and lane.py call with different options. lane.py also imports the item pool and inventory rules from spikes.py and reads the goal builds from spikes.json, so spikes.py must run first.

```text
 Data Dragon 16.20.1                 League Wiki values (typed in)
 (base stats, item stats, gold)      (item passives, runes, Kalista kit, AD growth)
            \                                   /
             v                                 v
   engine.py  -- build_stats + simulate: one-way kill, two-way duel, short trade window
              -- Kalista kit, item passives, Precision runes, dummies, threat profiles
            /                                   \
           v                                     v
 spikes.py -> spikes.json  ---- goal builds ---->  lane.py -> lane.json
 (calibrates duel threats;                        (calibrates lane threats;
  4 goals, beam search, boots, 24 rune pages)      quick/extended trades, executes, kill pressure)
            \                                   /
             v                                 v
        build_page.py -> kalista_spikes.html (lane section, goal switcher, charts, rankings)
```

Data Dragon numbers are read from data/ at import time; every wiki value is a typed constant in engine.py (EXTRA_ITEM_STATS, the Kalista kit constants, rune numbers inside simulate). Data Dragon 16.20.1 reports 0 AD growth for every champion, so AD_GROWTH_OVERRIDE supplies the wiki values.

## Game mechanics modeled

Stats, damage and Kalista's kit follow League's own formulas; item and rune effects are hand-coded one by one. Level 18 base stats match the wiki exactly (2,498 HP, 137.75 AD).

**Stat growth** (n = level): `stat(n) = base + g * (n-1) * (0.7025 + 0.0175 * (n-1))`

**Attack speed:** base AS + AS ratio × (bonus AS from growth, items, runes, buffs), capped at 2.5. **Resistances:** damage × 100 / (100 + armor), or 2 − 100 / (100 − armor) below zero; order is % reduction, then % pen, then flat pen, floored at 0. **Crit:** expected value, 200% base crit damage plus Infinity Edge's 30%. Level-scaled rune and item values follow the growth curve between their level 1 and level 18 values.

**Kalista:** autos at 100% AD; skill order E max, then Q, then W. Pierce (Q): 10–270 + 105% AD, 9 s, 0.25 s cast, adds a spear. Rend (E): first spear 5–45 + 70% AD + 65% AP, each extra spear 7–35 + 20–50% AD + 50% AP; held until it kills, or ripped at the end of a trade. Every on-hit adds a spear, including Guinsoo's phantom hit and (assumed) Dusk and Dawn's repeat.

| Group | Items and what is modeled |
| --- | --- |
| Crit and pen | Infinity Edge (+30% crit damage), Yun Tal (25% crit, unstacked the slot it is bought; Flurry), Lord Dominik's (35% pen, Giant Slayer), Mortal Reminder, Serylda's, Collector (execute 5%), Hexoptics (+10% at range), Youmuu's, Black Cleaver (6% shred × 5) |
| On-hit | BotRK (6% current HP), Kraken (every 3rd, missing-HP amp), Guinsoo's (phantom hit), Wit's End, Terminus (Dark pen stacks), Nashor's, Statikk, Stormrazor, Rapid Firecannon (Energized) |
| AP | Riftmaker (ramp + omnivamp + HP→AP), Rabadon's, Void Staff, Shadowflame, Lich Bane, Dusk and Dawn, Liandry's, Stormsurge, Gunblade (active + omnivamp), Bloodletter's |
| Defense | Bloodthirster (lifesteal + Ichorshield), Shieldbow, Maw, Death's Dance (10% stored), Guardian Angel, Mercurial, Plated Steelcaps (−10% attack damage), Mercury's (tenacity) |
| Stats only | Phantom Dancer, Runaan's, Navori (also cuts Q cooldown); Runaan's bolts are not counted (single target) |

**Runes:** keystones Press the Attack, Lethal Tempo, Conqueror, Fleet Footwork; Legend: Alacrity or Bloodline (stacks grow over the game); Coup de Grace, Cut Down or Last Stand. That makes 24 pages, all searched.

## Scenarios, calibration and scoring

Three scenario families share the simulator; each has its own calibration so results are relative to a fixed, fair baseline rather than invented absolute enemy damage.

| Scenario | Setup | Score | Calibration |
| --- | --- | --- | --- |
| Fastest kill | Dummy with Jinx, Darius, Ornn or Lux base stats + defensive stats per enemy item; it does not fight back | Geometric-mean time to kill over 4 dummies, averaged over target HP ×0.85–1.15 | None |
| Two-way duel | Enemy autos + an opener with crowd control on cooldown; armor/magic pen and 40% Grievous Wounds at set item counts; melee lands 65% of damage (kiting) | Kalista HP left at the end (negative = enemy HP left on a loss), averaged over enemy HP ×0.9/1.0/1.1 | One damage multiplier per threat for the whole game: marksman ×1.675, bruiser ×2.813, tank ×4.554, mage ×2.61, so Yun Tal → IE → LDR → Stormrazor → BotRK wins by +5% on average |
| Lane trades | Quick (~2 s) and extended (~3.5 s) trades with Rend ripped on exit; execute (25% target, Kalista 60%, 2 s to escape); kill pressure (highest enemy HP % killable in 2 s) | Lane score = 0.6 quick + 0.4 extended + 0.25 kill pressure (net HP lead in % of max HP) | Separate multipliers: marksman ×1.85, poke mage support ×1.118, engage tank support ×2.227, so Doran's Blade + Press the Attack / Alacrity / Cut Down trades even at levels 2, 3 and 6 |

**Spike schedule:** start Doran's Blade; item 1 at level 9, item 2 + boots at 11, items 3–5 at 13, 15 and 17 (Doran's sold at item 5). Enemies own the same number of items.

**Search:** for each goal, a beam search (width 8) adds one item per spike from 37 candidates with exclusivity groups (Last Whisper, Energized, Spellblade, Blight, Lifeline). It picks boots at item 2 from Berserker's, Steelcaps or Mercury's, and weights spikes 0.30 / 0.25 / 0.20 / 0.15 / 0.10 to favor Kalista's early game. It then picks the best of 24 rune pages and repeats until the page is stable.

**Goals:** fastest kill; best duelist; best duelist without Guardian Angel (a 1v1 overvalues a second life); hardest to kill (geometric-mean time to die). Gunblade's 60 s active counts in half of lane trades and in every all-in or duel.

## Key results so far

The realistic all-round build is Shieldbow → BotRK → LDR → Gunblade → Kraken, which wins all 20 duel matchups; the pure crit build kills fastest but wins only 15. Averages below are over the five item spikes.

| Goal | Runes | Boots | Items in order | Kill time | Duel score | Duel wins |
| --- | --- | --- | --- | --- | --- | --- |
| Fastest kill | Press the Attack / Alacrity / Cut Down | Berserker's | Yun Tal, Infinity Edge, Lord Dominik's, Stormrazor, Youmuu's | 2.61 s | +3% | 15/20 |
| Best duelist, no GA | Press the Attack / Alacrity / Last Stand | Steelcaps | Shieldbow, BotRK, Lord Dominik's, Gunblade, Kraken | 4.05 s | +37% | 20/20 |
| Best duelist | Press the Attack / Bloodline / Coup de Grace | Steelcaps | Guardian Angel, Gunblade, Wit's End, Shieldbow, BotRK | 5.63 s | +39% | 20/20 |
| Hardest to kill | Fleet Footwork / Bloodline / Coup de Grace | Steelcaps | Guardian Angel, Shieldbow, Death's Dance, Mercurial, Riftmaker | 7.42 s | +28% | 20/20 |
| Lane | Press the Attack / Bloodline / Cut Down | Berserker's | Gunblade, Lord Dominik's | — | — | — |

- **Lane:** trades are even through level 6 by construction; the lane build then wins quick trades by +14.8% at item 1 and +21.0% at item 2, and kill pressure rises from 30% to 68% enemy HP.
- **Runes in lane:** Kalista fits only two autos into a 2 s trade early, so Press the Attack rarely fires there; it still wins overall because extended trades favor it (+8% vs +4%).
- **Power curve:** the crit build loses to bruiser and tank at item 1, wins everything at item 3, then starts losing to marksman and mage at items 4–5.
- **Kiting:** if melee enemies land 90% of their damage instead of 65%, the no-GA build loses to bruiser and tank until item 3.
- **AP and Riftmaker:** the best AP path (Gunblade, Terminus, Dusk and Dawn, Riftmaker, Rabadon's) averages a +15% duel score against +37% for the no-GA build. Riftmaker ranks 1st–6th only when the goal is survival and 27th–28th in lane.

## Assumptions to verify and known limits

Eight numbers are unconfirmed and could move rankings; each should be checked in the Practice Tool before anything else is polished.

| Assumption | Current value | Where |
| --- | --- | --- |
| Default crit damage | 200% (wiki); Infinity Edge +30% | CRIT_BASE, EXTRA_ITEM_STATS |
| Kalista auto damage | 100% AD (older patches: 90%) | AA_AD_RATIO |
| Kraken Slayer, ranged | 120→168 linear by level, +0–75% by missing HP | simulate, on-hit block |
| Dusk and Dawn repeat on-hit | Adds a Rend spear | simulate, spellblade block |
| Fleet Footwork heal | 9–96 + 6% bonus AD (wiki pages disagree: 109.64) | simulate, Fleet block |
| Conqueror stacks from Q | 2 per cast | simulate, Pierce block |
| Bloodletter's shred | Triggers from item on-hit magic damage | deal() |
| Rune and item level scaling | Growth curve between level 1 and 18 values | lvl_scale |

**Modeling limits:**

- Threat profiles are estimates of a typical enemy of each class, not real champion kits. The calibrations make results relative, so absolute win rates mean nothing.
- Not modeled: positioning, missed skillshots, teammates, summoner spells, mana, W Soul-Mark, attack windup and missile travel, and multi-target value (Runaan's, Statikk bounces).
- One-fight scoring overvalues long-cooldown effects: Guardian Angel, Gunblade active, Shieldbow and Maw lifelines.
- Gold is not a constraint: spikes are fixed levels, and gold efficiency is reported but not optimized.
- Data Dragon 16.20.1 has 0 AD growth for all champions; only Kalista, Jinx and Caitlyn have wiki overrides.

## Polish roadmap for Fable

Work top to bottom; each step should leave ./run_all.sh producing the same results unless the step is meant to change them.

1. **Reproduce.** Run the pipeline and confirm the builds and averages in Key results match.
2. **Lock it with tests.** Add pytest checks:
    - level 1 and 18 base stats against the wiki table
    - the resistance and penetration order
    - a fixed Kalista fight trace (attack times, spears, Rend kill)
    - one duel and one lane trade per threat
    - snapshot tests of spikes.json and lane.json summaries
3. **Move numbers into data files.** Put wiki values (item passives, runes, Kalista kit, threat profiles, calibration targets, scoring weights) in YAML or JSON with a source URL and patch per entry, so a patch update edits data, not code.
4. **Restructure the code.**
    - Break simulate() (about 400 lines) into a fight state, an event queue, and item and rune effect handlers registered by hook (on_attack, on_hit, on_damage, on_take_damage).
    - Keep behavior identical (the tests from step 2 guard this).
5. **Automate data updates.** Fetch the latest Data Dragon version (the GitHub mirror InFinity54/LoL_DDragon works where Riot's CDN is blocked). Fill AD growth from the wiki or CommunityDragon for every champion, and warn when an item's description text changes between patches.
6. **Settle the eight assumptions** from the table above with Practice Tool measurements, then re-run calibration.
7. **Add a command-line interface.** For example `kalista --goal practical --threat bruiser --kite 0.8 --runes auto`. Make threats, kiting share, trade windows and weights flags instead of constants.
8. **Improve the results page.**
    - Build it from a template file instead of a Python string.
    - Add a build editor: pick items, see the statline, duel and trade numbers live, by running the engine in the browser via Pyodide or a small API.
    - Keep the current sections and the phone layout.
9. **Extend the model.**
    - Gold-constrained timing (completed items at real gold totals, components bought on back).
    - W Soul-Mark with a support.
    - Multi-target value.
    - Real champion kits for common bot-lane matchups.
    - Generalize the champion kit so other marksmen can be added.
10. **Speed.** Profile it. Cache build_stats and use multiprocessing across goals. The full run is about 80 s now; target under 20 s.

## Sources

- Riot Data Dragon 16.20.1 via GitHub mirror: https://github.com/InFinity54/LoL_DDragon
- League Wiki (all passive, rune and kit values): https://wiki.leagueoflegends.com/en-us/
  Kalista, Champion statistics, Critical strike, and each item and rune page named in engine.py.
