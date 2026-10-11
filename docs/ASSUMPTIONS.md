# The eight assumptions (roadmap step 6)

HANDOFF.md listed eight unconfirmed numbers. Each was checked against the League Wiki as
of patch 16.20.1 (wiki versions V26.16–V26.20): the item, rune and champion data modules,
the rune data templates and Kalista's patch history. Five are settled by the wiki
(two confirmed as they were, three corrected), and the rune/item level-scaling
assumption was corrected wherever it applied. Three details still need a Practice Tool
measurement; they keep a `verify` flag in `data/wiki/`.

| # | Assumption (v4) | Wiki says | Status | Change |
|---|---|---|---|---|
| 1 | 200% default crit damage; IE +30% | 200% (reverted from 175% in V26.01); IE `critdamage = 30` | Confirmed | none |
| 2 | Kalista autos at 100% AD | 100% since V13.11 (was 90%) | Confirmed | none |
| 3 | Kraken Slayer ranged 120→168 linear, +0–75% by missing HP | 80% of (150 + 5 per level from 9): 120 to level 8, 160 at 18; +0–75% by missing HP | Corrected | `curve: steps` 120, +4 per level from 9 |
| 4 | Dusk and Dawn repeat adds a Rend spear | "applies on-hit effects to the target again"; Rend spears come from "basic attacks on-hit". The empowered hit also heals 10% AP + 3% bonus HP | Spear still open; heal added | heal added; spear **verify** |
| 5 | Fleet Footwork heal 9–96 + 6% bonus AD (109.64?) | Ranged 60% of 15–160 on the growth curve = 9–96, + 6% bonus AD + 3% AP. 109.64 is the level-20 value | Confirmed | none |
| 6 | Conqueror: 2 stacks per Pierce | Ranged: 1 per on-hit attack; 2 for ability damage once per 4 s per cast instance (Pierce: new cast, 9 s cooldown) | Confirmed | per-stack value corrected (see 8) |
| 7 | Bloodletter's Curse stacks from item on-hit magic | Stacks only from magic damage "with a champion ability" | Corrected | never stacks for Kalista (her abilities are physical) |
| 8 | Rune and item level values on the growth curve between level 1 and 18 | Mixed, and several v4 "level 18" values were the wiki's level-20 values | Corrected | see below |

Level scaling now follows each page (`level_value` in `lolsim/stats.py`, spec per entry):

| Effect | v4 | Now (level 1 → 18) |
|---|---|---|
| Press the Attack | 40 → 174.12, growth curve | 40 → 160, linear |
| Lethal Tempo (ranged) | 6 → 21.66, growth curve | 6.0 → 20.0, linear |
| Conqueror per stack | 1.08 → 2.56 AD, growth curve | 1.08 → 2.4 AD (1.8 → 4.0 AP), linear |
| Fleet Footwork heal | 9 → 96, growth curve | unchanged |
| Bloodthirster shield | 165 → 345, growth curve | 165 to level 8, +15 per level (315) |
| Immortal Shieldbow (ranged) | 320 → 560, growth curve | 320 to level 8, +24 per level (560) |
| Kraken Slayer (ranged) | 120 → 168, linear | 120 to level 8, +4 per level (160) |
| Hextech Gunblade active | 175 → 253, linear | 175 → 253 over levels 1–20, linear (244.8 at 18), **verify** |

Calibration was re-run with the same targets. The multipliers did not move at three
decimals (marksman ×1.675, bruiser ×2.813, tank ×4.554, mage ×2.61; lane ×1.85, ×1.118,
×2.227).

## Still to measure in the Practice Tool

Use a level-18 target dummy with known armor/MR (set in the tool), Kalista with the
items below, and the damage-dealt recap (Tab → damage breakdown) or the floating text.

1. **Dusk and Dawn spear.** Kalista level 13+, Dusk and Dawn only. Cast Pierce, then
   one empowered auto, then Rend. Repeat with one plain auto instead. If the empowered
   case's Rend matches a 3-spear Rend (Q + auto + repeat), the repeat adds a spear.
   Compare with the Rend formula: first spear 5–45 + 70% AD + 65% AP, each extra 7–35 +
   20–50% AD + 50% AP. If not, set `extra_on_hit` to 0 in `data/wiki/items.json`
   (2510) and remove `times +=` from `DuskAndDawn.on_attack`.
2. **Gunblade active at level 18.** Fire the active on a 0-MR dummy at level 18 with no
   AP besides Gunblade's 80. Expected 244.8 + 24 = 268.8 (linear over 1–20) or 253 + 24 =
   277 (linear over 1–18). Set `active.levels` to `[1, 20]` or `[1, 18]`.
3. **Kraken missing-health bonus.** Hit dummies at 100%, 50% and 10% health with the
   third (Kraken) attack at level 18 and 0 armor. Linear predicts 160, 220, 268; the wiki's
   "0 to 75 by 5" could mean 5% steps. If stepped, change the formula in
   `Kraken.on_attack_bonus`.

After any change: `./run_all.sh`, then `python3 tests/fight_corpus.py --update`,
`python3 tests/snapshot.py --update`, and update the golden numbers in
`tests/test_fight.py` if they moved.
