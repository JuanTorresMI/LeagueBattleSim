"""
League of Legends DPS + duel engine v3 (prototype) — patch 16.20.1
==================================================================
* Generic stat engine: any champion, any level, any items (Riot Data Dragon).
* Fight simulator with Kalista's kit, item passives (AD / crit / on-hit / AP),
  Precision runes, and an optional enemy that fights back (two-way duel).

Data Dragon blanks most passive numbers and reports 0 AD growth for every
champion this patch, so passive / rune / growth values come from the League
Wiki. Threat profiles (how hard each enemy hits) are estimates: edit THREATS.
Anything marked VERIFY is worth confirming in the Practice Tool.
"""
import json, os, math
from dataclasses import dataclass, replace

HERE = os.path.dirname(os.path.abspath(__file__))

def _load(name):
    with open(os.path.join(HERE, "data", name), encoding="utf-8") as f:
        return json.load(f)["data"]

CHAMPS = _load("champion.json")
ITEMS = _load("item.json")

# ------------------------------------------------------------------ constants
CRIT_BASE = 2.00     # VERIFY: wiki lists 200% default crit damage
AS_CAP = 2.5
AD_GROWTH_OVERRIDE = {"Kalista": 4.75, "Jinx": 3.25, "Caitlyn": 3.8}

EXTRA_ITEM_STATS = {           # stats that only exist in description text
    "3031": {"crit_damage": 0.30},          # Infinity Edge
    "3036": {"armor_pen": 0.35},            # Lord Dominik's
    "3033": {"armor_pen": 0.30},            # Mortal Reminder
    "6694": {"armor_pen": 0.35},            # Serylda's
    "6676": {"lethality": 10},              # Collector
    "3142": {"lethality": 18},              # Youmuu's
    "3135": {"magic_pen_pct": 0.40},        # Void Staff
    "3137": {"magic_pen_pct": 0.30},        # Cryptbloom
    "4645": {"magic_pen": 15},              # Shadowflame
    "4646": {"magic_pen": 15},              # Stormsurge
    "3146": {"omnivamp": 0.10},             # Hextech Gunblade
    "3111": {"tenacity": 0.30},             # Mercury's Treads
    "3091": {"tenacity": 0.20},             # Wit's End
}

def growth(level):
    n = level - 1
    return n * (0.7025 + 0.0175 * n)

def lvl_scale(lo, hi, level):
    """Level-based value on League's growth curve (lo at 1, hi at 18)."""
    return lo + (hi - lo) * growth(level) / growth(18)

def lvl_linear(lo, hi, level):
    return lo + (hi - lo) * (level - 1) / 17

# ------------------------------------------------------------------ stats
@dataclass
class Stats:
    level: int
    hp: float; base_hp: float; armor: float; mr: float
    base_ad: float; bonus_ad: float; ap: float
    base_as: float; as_ratio: float; bonus_as: float
    crit: float; crit_damage: float
    armor_pen: float; lethality: float
    magic_pen_pct: float; magic_pen: float
    lifesteal: float; omnivamp: float; tenacity: float
    ms: float

    @property
    def ad(self): return self.base_ad + self.bonus_ad
    @property
    def bonus_hp(self): return self.hp - self.base_hp
    def attack_speed(self, extra=0.0):
        return min(AS_CAP, self.base_as + self.as_ratio * (self.bonus_as + extra))

def build_stats(champ, level, item_ids, runes=None):
    runes = runes or RunePage()
    s = CHAMPS[champ]["stats"]
    g = growth(level)
    base_hp = s["hp"] + s["hpperlevel"] * g
    st = Stats(level=level, hp=base_hp, base_hp=base_hp,
               armor=s["armor"] + s["armorperlevel"] * g,
               mr=s["spellblock"] + s["spellblockperlevel"] * g,
               base_ad=s["attackdamage"] + AD_GROWTH_OVERRIDE.get(champ, s["attackdamageperlevel"]) * g,
               bonus_ad=0.0, ap=0.0,
               base_as=s["attackspeed"], as_ratio=s["attackspeed"],
               bonus_as=s["attackspeedperlevel"] / 100 * g + runes.alacrity_as(),
               crit=0.0, crit_damage=CRIT_BASE, armor_pen=0.0, lethality=0.0,
               magic_pen_pct=0.0, magic_pen=0.0,
               lifesteal=runes.bloodline_ls(), omnivamp=0.0, tenacity=0.0,
               ms=s["movespeed"])
    st.hp += runes.bloodline_hp()
    apens, mpens, tens = [], [], []
    for iid in item_ids:
        it = ITEMS[iid]["stats"]
        st.hp += it.get("FlatHPPoolMod", 0)
        st.armor += it.get("FlatArmorMod", 0)
        st.mr += it.get("FlatSpellBlockMod", 0)
        st.bonus_ad += it.get("FlatPhysicalDamageMod", 0)
        st.ap += it.get("FlatMagicDamageMod", 0)
        st.bonus_as += it.get("PercentAttackSpeedMod", 0)
        st.crit += it.get("FlatCritChanceMod", 0)
        st.lifesteal += it.get("PercentLifeStealMod", 0)
        st.ms += it.get("FlatMovementSpeedMod", 0)
        ex = EXTRA_ITEM_STATS.get(iid, {})
        st.crit_damage += ex.get("crit_damage", 0)
        st.lethality += ex.get("lethality", 0)
        st.magic_pen += ex.get("magic_pen", 0)
        st.omnivamp += ex.get("omnivamp", 0)
        if ex.get("armor_pen"): apens.append(ex["armor_pen"])
        if ex.get("magic_pen_pct"): mpens.append(ex["magic_pen_pct"])
        if ex.get("tenacity"): tens.append(ex["tenacity"])
    if "4633" in item_ids: st.ap += 0.02 * st.bonus_hp          # Riftmaker Void Infusion
    if "3089" in item_ids: st.ap *= 1.30                         # Rabadon's
    st.crit = min(1.0, st.crit)
    for p in apens: st.armor_pen = 1 - (1 - st.armor_pen) * (1 - p)
    for p in mpens: st.magic_pen_pct = 1 - (1 - st.magic_pen_pct) * (1 - p)
    for p in tens: st.tenacity = 1 - (1 - st.tenacity) * (1 - p)
    return st

def statline(champ, level, item_ids, runes=None):
    st = build_stats(champ, level, item_ids, runes)
    return {"level": level, "HP": round(st.hp), "AD": round(st.ad, 1),
            "AP": round(st.ap, 1), "AS": round(st.attack_speed(), 3),
            "crit %": round(st.crit * 100), "crit dmg %": round(st.crit_damage * 100),
            "armor": round(st.armor, 1), "MR": round(st.mr, 1),
            "armor pen %": round(st.armor_pen * 100, 1), "lethality": st.lethality,
            "lifesteal %": round(st.lifesteal * 100, 2), "omnivamp %": round(st.omnivamp * 100, 1),
            "tenacity %": round(st.tenacity * 100)}

def resist_mult(r):
    return 100 / (100 + r) if r >= 0 else 2 - 100 / (100 - r)

def eff_resist(resist, reduction_pct, pen_pct, flat_pen):
    r = resist * (1 - reduction_pct)
    if r <= 0: return r
    return max(0.0, r * (1 - pen_pct) - flat_pen)

# ------------------------------------------------------------------ dummies (defense side)
@dataclass
class Dummy:
    name: str
    hp: float
    armor: float
    mr: float
    bonus_hp: float = 0.0
    kind: str = ""

# kind -> (champion whose base stats are used, per-item HP, armor, MR)
DUMMY_KINDS = {
    "marksman": ("Jinx",   80,  0,  0),
    "bruiser":  ("Darius", 300, 12, 8),
    "tank":     ("Ornn",   400, 35, 20),
    "mage":     ("Lux",    60,  0,  0),
}

def make_dummy(kind, level, n_items):
    champ, hp_i, ar_i, mr_i = DUMMY_KINDS[kind]
    s = CHAMPS[champ]["stats"]; g = growth(level)
    bonus = hp_i * n_items
    return Dummy(f"{kind} (lvl {level}, {n_items} items)",
                 s["hp"] + s["hpperlevel"] * g + bonus,
                 s["armor"] + s["armorperlevel"] * g + ar_i * n_items,
                 s["spellblock"] + s["spellblockperlevel"] * g + mr_i * n_items,
                 bonus, kind)

# ------------------------------------------------------------------ threats (attack side)
@dataclass
class Ability:
    first: float          # seconds into the fight
    cd: float
    kind: str             # physical / magic
    base_lo: float; base_hi: float
    bonus_ad_ratio: float = 0.0
    ap_ratio: float = 0.0
    cc: float = 0.0       # seconds Kalista can't act (before tenacity)
    repeat_scale: float = 1.0   # later casts deal this fraction of the opener

@dataclass
class Threat:
    name: str
    melee: bool
    ad_lo: float; ad_hi: float; ad_per_item: float
    as_base: float; as_per_lvl: float; as_per_item: float
    crit_per_item: float = 0.0
    armor_pen_at: tuple = (99, 0.0)        # (items needed, % pen)
    magic_pen_at: tuple = (99, 0.0, 0)     # (items needed, % pen, flat)
    ap_per_item: float = 0.0
    wounds_at: int = 99                    # items needed for 40% Grievous Wounds
    abilities: tuple = ()
    dmg_mult: float = 1.0                  # calibration multiplier on all damage dealt

# Estimates of a typical enemy of each class. Edit freely.
THREATS = {
    "marksman": Threat("Marksman", False, 60, 115, 45, 0.66, 0.03, 0.30, crit_per_item=0.25,
                       armor_pen_at=(3, 0.35), wounds_at=3,
                       abilities=(Ability(1.0, 8, "physical", 60, 300, bonus_ad_ratio=1.0),)),
    "bruiser":  Threat("Bruiser", True, 64, 145, 45, 0.625, 0.02, 0.15,
                       armor_pen_at=(2, 0.30), wounds_at=2,
                       abilities=(Ability(0.4, 6, "physical", 90, 320, bonus_ad_ratio=1.3, cc=0.75,
                                          repeat_scale=0.75),)),
    "tank":     Threat("Tank", True, 60, 120, 15, 0.625, 0.015, 0.05, wounds_at=2,
                       abilities=(Ability(0.4, 9, "magic", 80, 280, cc=1.0, repeat_scale=0.7),)),
    "mage":     Threat("Mage", False, 52, 95, 0, 0.625, 0.02, 0.0, ap_per_item=85,
                       magic_pen_at=(2, 0.0, 15), wounds_at=3,
                       abilities=(Ability(0.3, 7, "magic", 240, 680, ap_ratio=0.85, cc=1.25,
                                          repeat_scale=0.55),)),
}

# ------------------------------------------------------------------ runes
KEYSTONES = ["Press the Attack", "Lethal Tempo", "Conqueror", "Fleet Footwork"]

@dataclass
class RunePage:
    keystone: str = "Lethal Tempo"
    legend: str = "Alacrity"          # "Alacrity" / "Bloodline"
    legend_stacks: int = 10           # 0-10 on this scale (Bloodline maps to 0-15)
    combat: str = "Coup de Grace"     # "Coup de Grace" / "Cut Down" / "Last Stand"
    def alacrity_as(self):
        return (0.03 + 0.015 * self.legend_stacks) if self.legend == "Alacrity" else 0.0
    def _bl(self): return min(15, round(self.legend_stacks * 1.5))
    def bloodline_ls(self):
        return 0.0045 * self._bl() if self.legend == "Bloodline" else 0.0
    def bloodline_hp(self):
        return 85 if self.legend == "Bloodline" and self._bl() >= 15 else 0
    def label(self):
        return f"{self.keystone} / {self.legend} / {self.combat}"
    def at(self, stacks):
        return replace(self, legend_stacks=stacks)

# ------------------------------------------------------------------ Kalista kit
RANKS_BY_LEVEL = {  # level -> (Q, W, E); E max, Q second
    1:(0,0,1), 2:(1,0,1), 3:(1,1,1), 4:(1,1,2), 5:(1,1,3), 6:(1,1,3), 7:(1,1,4),
    8:(2,1,4), 9:(2,1,5), 10:(3,1,5), 11:(3,1,5), 12:(4,1,5), 13:(5,1,5),
    14:(5,2,5), 15:(5,3,5), 16:(5,3,5), 17:(5,4,5), 18:(5,5,5)}
AA_AD_RATIO = 1.0   # VERIFY
Q_BASE = [10, 75, 140, 205, 270]; Q_RATIO = 1.05; Q_CD = 9.0; Q_CAST = 0.25
E_FIRST = [5, 15, 25, 35, 45];    E_FIRST_AD = 0.70; E_FIRST_AP = 0.65
E_ADD = [7, 14, 21, 28, 35];      E_ADD_AD = [0.20, 0.275, 0.35, 0.425, 0.50]; E_ADD_AP = 0.50

def rend_raw(ad, ap, rank, spears):
    if spears <= 0 or rank == 0: return 0.0
    r = rank - 1
    first = E_FIRST[r] + E_FIRST_AD * ad + E_FIRST_AP * ap
    each = E_ADD[r] + E_ADD_AD[r] * ad + E_ADD_AP * ap
    return first + (spears - 1) * each

# ------------------------------------------------------------------ simulator
@dataclass
class Opts:
    use_q: bool = True
    energized_full_at_start: bool = True
    hop_units_per_attack: float = 200.0
    yuntal_prestacked: bool = True
    kite_uptime: float = 0.65      # share of melee damage that lands while Kalista kites
    max_time: float = 40.0
    window: float = 0.0            # >0: a short trade that ends after this many seconds
    exit_e: bool = False           # rip Rend at the end of the trade window
    enemy_start: float = 1.0       # enemy's starting HP fraction
    kal_start: float = 1.0         # Kalista's starting HP fraction
    gunblade_active: bool = True   # Hextech Gunblade's active is off cooldown
    margin_cap: float = 5.0

SPELLBLADE = {"3100", "2510"}
ENERGIZED = {"3087", "3095", "3094"}

def simulate(item_ids, level, dummy, runes=None, opts=None, threat=None, enemy_items=0, trace=False):
    """Fight `dummy`. With `threat`, the dummy fights back (two-way duel).

    Returns kill time, (duel) death time, margin = death time / kill time,
    HP left on both sides, and damage / healing breakdowns."""
    runes = runes or RunePage(); opts = opts or Opts()
    st = build_stats("Kalista", level, item_ids, runes)
    has = set(item_ids)
    qr, wr, er = RANKS_BY_LEVEL[level]
    duel = threat is not None
    hp = dummy.hp * opts.enemy_start
    hp0 = hp
    by_src, log = {}, []
    t = 0.0
    S = dict(cleaver=0, dark=0, attacks=0, spears=0, guinsoo=0, phantom=0,
             energized=100 if opts.energized_full_at_start else 0, fleet=100,
             flurry_until=-1.0, flurry_cd=0.0, q_cd=0.0,
             lt=0, pta=0, pta_cd=0.0, pta_amp=False, conq=0,
             blood=0, spellblade=False, liandry_until=-1.0, liandry_last=0.0,
             storm_window=[], storm_at=None, storm_used=False)
    giant = 1 + (0.15 * min(dummy.bonus_hp / 1500, 1) if "3036" in has else 0)
    crit = min(1.0, st.crit + (0.25 if "3032" in has and opts.yuntal_prestacked else 0))
    crit_factor = 1 + crit * (st.crit_damage - 1)
    energize_per_attack = (15 if "3087" in has else 6) + opts.hop_units_per_attack / 24
    adaptive_magic = st.ap > st.bonus_ad

    # ---------------- Kalista's defensive state (duel only)
    K = dict(hp=st.hp * opts.kal_start, max=st.hp, shields=[], ichor=0.0, cc_until=0.0, dead_at=None,
             ga=("3026" in has), revive_until=-1.0, dd=[], maw_used=False, maw_vamp=False,
             bow_used=False, taken=0.0, healed=0.0, taken_by={}, healed_by={},
             wounds=False)
    E = None
    if duel:
        n = enemy_items
        th = threat
        e_bonus_ad = th.ad_per_item * n
        e_ad = lvl_scale(th.ad_lo, th.ad_hi, level) + e_bonus_ad
        e_as = min(AS_CAP, th.as_base * (1 + th.as_per_lvl * (level - 1) + th.as_per_item * n))
        e_crit = min(1.0, th.crit_per_item * n)
        e_ap = th.ap_per_item * n * (1.3 if n >= 4 and th.ap_per_item else 1)
        E = dict(next_auto=0.5 if th.melee else 0.0, ad=e_ad, bonus_ad=e_bonus_ad, ap=e_ap,
                 as_=e_as, crit_f=1 + e_crit * (CRIT_BASE + (0.3 if n >= 2 and e_crit else 0) - 1),
                 apen=th.armor_pen_at[1] if n >= th.armor_pen_at[0] else 0.0,
                 mpen=(th.magic_pen_at[1], th.magic_pen_at[2]) if n >= th.magic_pen_at[0] else (0.0, 0),
                 abil=[[a, a.first, 0] for a in th.abilities], dealt=0.0)
        K["wounds"] = n >= th.wounds_at
        uptime = opts.kite_uptime if th.melee else 1.0

    def conq_bonus():
        if runes.keystone != "Conqueror": return 0.0, 0.0
        if adaptive_magic: return 0.0, S["conq"] * lvl_scale(1.8, 4.26, level)
        return S["conq"] * lvl_scale(1.08, 2.56, level), 0.0
    def cur_ad():  return st.ad + conq_bonus()[0]
    def cur_bad(): return st.bonus_ad + conq_bonus()[0]
    def cur_ap():  return st.ap + conq_bonus()[1]

    def k_frac(): return K["hp"] / K["max"]

    def amp(kind, is_attack=False):
        m = giant
        if S["pta_amp"] and kind != "true": m *= 1.08
        if "4633" in has: m *= 1 + min(0.08, 0.02 * math.floor(t))
        if "6653" in has: m *= 1 + min(0.06, 0.02 * math.floor(t))
        frac = hp / dummy.hp
        if runes.combat == "Coup de Grace" and frac < 0.40: m *= 1.08
        if runes.combat == "Cut Down" and frac > 0.60: m *= 1.08
        if runes.combat == "Last Stand" and duel:
            kf = k_frac()
            if kf < 0.60: m *= 1 + 0.05 + 0.06 * min(1.0, (0.60 - kf) / 0.30)
        if "4645" in has and kind in ("magic", "true") and frac < 0.40: m *= 1.20
        if is_attack and "2523" in has: m *= 1.10
        return m

    def mitig(kind):
        if kind == "physical":
            red = 0.06 * S["cleaver"] if "3071" in has else 0
            pen = 1 - (1 - st.armor_pen) * (1 - (0.10 * S["dark"] if "3302" in has else 0))
            return resist_mult(eff_resist(dummy.armor, red, pen, st.lethality))
        if kind == "magic":
            red = 0.075 * S["blood"] if "8010" in has else 0
            return resist_mult(eff_resist(dummy.mr, red, st.magic_pen_pct, st.magic_pen))
        return 1.0

    # ---------------- healing / shields for Kalista
    def heal(src, amount):
        if not duel or amount <= 0 or K["dead_at"] is not None or t < K["revive_until"]: return
        amount *= 0.6 if K["wounds"] else 1.0
        room = K["max"] - K["hp"]
        h = min(room, amount)
        K["hp"] += h
        if h > 0:
            K["healed"] += h; K["healed_by"][src] = K["healed_by"].get(src, 0) + h
        over = amount - h
        if over > 0 and "3072" in has and src in ("Lifesteal",):         # Bloodthirster Ichorshield
            cap = lvl_scale(165, 345, level)
            add = min(over, cap - K["ichor"])
            if add > 0:
                K["ichor"] += add
                K["healed_by"]["Ichorshield"] = K["healed_by"].get("Ichorshield", 0) + add

    def deal(src, raw, kind, is_attack=False):
        nonlocal hp
        if raw <= 0 or hp <= 0: return 0.0
        dmg = raw * mitig(kind) * amp(kind, is_attack)
        dmg = min(dmg, hp) if duel else dmg
        hp -= dmg
        by_src[src] = by_src.get(src, 0) + dmg
        if kind == "physical" and "3071" in has: S["cleaver"] = min(5, S["cleaver"] + 1)
        if kind == "magic" and "8010" in has: S["blood"] = min(4, S["blood"] + 1)   # VERIFY
        if "4646" in has and not S["storm_used"]:
            S["storm_window"].append((t, dmg))
            S["storm_window"] = [(a, b) for a, b in S["storm_window"] if t - a <= 2.5]
            if sum(b for _, b in S["storm_window"]) >= 0.25 * dummy.hp:
                S["storm_used"] = True; S["storm_at"] = t + 2.0
        if duel:
            vamp = st.omnivamp
            if "4633" in has and t >= 4: vamp += 0.06                       # Riftmaker max strength, ranged
            if K["maw_vamp"]: vamp += 0.10
            heal("Omnivamp", vamp * dmg)
            if is_attack: heal("Lifesteal", st.lifesteal * dmg)
            if runes.keystone == "Conqueror" and S["conq"] >= 12: heal("Conqueror", 0.05 * dmg)
        return dmg

    def take(src, raw, kind, is_attack=False):
        """Enemy damage to Kalista."""
        if K["dead_at"] is not None or t < K["revive_until"]: return
        raw *= threat.dmg_mult
        if kind == "physical":
            dmg = raw * resist_mult(eff_resist(st.armor, 0, E["apen"], 0))
            if is_attack and "3047" in has: dmg *= 0.90                       # Plated Steelcaps
        elif kind == "magic":
            dmg = raw * resist_mult(eff_resist(st.mr, 0, E["mpen"][0], E["mpen"][1]))
        else:
            dmg = raw
        E["dealt"] += dmg
        K["taken_by"][src] = K["taken_by"].get(src, 0) + dmg
        if "6333" in has and kind != "true":                                   # Death's Dance (ranged 10%)
            stored = 0.10 * dmg; dmg -= stored
            K["dd"].append([t, stored])
        # lifeline shields trigger on damage that would drop below 30%
        after = K["hp"] - dmg
        if kind == "magic" and "3156" in has and not K["maw_used"] and after < 0.30 * K["max"]:
            K["maw_used"] = True; K["maw_vamp"] = True
            K["shields"].append(["Maw shield", 150 + 1.125 * cur_bad(), t + 3, "magic"])
        if "6673" in has and not K["bow_used"] and after < 0.30 * K["max"]:
            K["bow_used"] = True
            K["shields"].append(["Shieldbow", lvl_scale(320, 560, level), t + 3, "any"])
        apply_to_hp(dmg, kind)

    def apply_to_hp(dmg, kind):
        for sh in K["shields"]:
            if sh[2] < t or sh[1] <= 0: continue
            if sh[3] == "magic" and kind != "magic": continue
            a = min(sh[1], dmg); sh[1] -= a; dmg -= a
            K["healed_by"][sh[0]] = K["healed_by"].get(sh[0], 0) + a
        if dmg > 0 and K["ichor"] > 0:
            a = min(K["ichor"], dmg); K["ichor"] -= a; dmg -= a
        K["taken"] += dmg
        K["hp"] -= dmg
        if K["hp"] <= 0:
            if K["ga"]:
                K["ga"] = False; K["revive_until"] = t + 4.0; K["hp"] = 0.5 * st.base_hp
                K["dd"].clear()
                K["healed_by"]["Guardian Angel"] = 0.5 * st.base_hp
            else:
                K["hp"] = 0; K["dead_at"] = t

    def enemy_until(until):
        """Run enemy actions (and Death's Dance bleed) up to `until`."""
        nonlocal t
        if not duel: return
        saved = t
        while hp > 0 and K["dead_at"] is None:
            nxt, what = E["next_auto"], ("auto", None)
            for ab in E["abil"]:
                if ab[1] < nxt: nxt, what = ab[1], ("abil", ab)
            if nxt > until: break
            t = nxt
            if what[0] == "auto":
                take("Enemy autos", E["ad"] * E["crit_f"] * uptime, "physical", True)
                E["next_auto"] += 1 / E["as_"]
            else:
                ab = what[1]; a = ab[0]
                scale = 1.0 if ab[2] == 0 else a.repeat_scale * (uptime if threat.melee else 1.0)
                raw = (lvl_scale(a.base_lo, a.base_hi, level) + a.bonus_ad_ratio * E["bonus_ad"]
                       + a.ap_ratio * E["ap"]) * scale
                take("Enemy abilities", raw, a.kind)
                if a.cc and ab[2] == 0 and t >= K["revive_until"]:
                    K["cc_until"] = max(K["cc_until"], t + a.cc * (1 - st.tenacity))
                ab[2] += 1; ab[1] += a.cd
        # Death's Dance bleed: stored damage dealt as true damage over 3 s
        if K["dead_at"] is None:
            for d in K["dd"]:
                start, amt = d
                due = amt * min(1.0, (until - start) / 3.0)
                if due > 0:
                    d[1] -= due; d[0] = until
                    t = until
                    K["taken_by"]["Death's Dance bleed"] = K["taken_by"].get("Death's Dance bleed", 0) + due
                    apply_to_hp(due, "true")
            K["dd"] = [d for d in K["dd"] if d[1] > 1e-6]
        t = saved

    def adaptive_kind(): return "magic" if adaptive_magic else "physical"

    def try_finish():
        if hp <= 0: return True
        if duel and K["dead_at"] is not None: return True
        if "6676" in has and hp < 0.05 * dummy.hp:
            deal("Collector execute", hp, "true"); return True
        if er and S["spears"] > 0:
            raw = rend_raw(cur_ad(), cur_ap(), er, S["spears"])
            if raw * mitig("physical") * amp("physical") >= hp:
                deal("Rend (E)", raw, "physical"); return True
        return False

    def tick(now):
        """Advance DoTs and enemy actions to `now`."""
        nonlocal t
        enemy_until(now)
        saved = t
        if "6653" in has and S["liandry_until"] > S["liandry_last"]:
            end = min(now, S["liandry_until"])
            if end > S["liandry_last"]:
                t = end
                deal("Liandry's burn", 0.02 * dummy.hp * (end - S["liandry_last"]), "magic")
                S["liandry_last"] = end
        if S["storm_at"] is not None and S["storm_at"] <= now:
            t = S["storm_at"]; S["storm_at"] = None
            deal("Stormsurge", 125 + 0.10 * cur_ap(), "magic")
        t = saved

    def wait_for_control():
        """Kalista can't act while crowd-controlled or reviving."""
        nonlocal t
        if not duel: return
        while True:
            free = max(K["cc_until"], K["revive_until"])
            if free <= t: return
            tick(free); t = free

    if "3146" in has and opts.gunblade_active:
        deal("Gunblade active", lvl_linear(175, 253, level) + 0.30 * cur_ap(), "magic")

    limit = opts.window if opts.window > 0 else opts.max_time
    while t <= limit:
        tick(t); wait_for_control()
        if try_finish(): break
        # ---- Pierce
        if opts.use_q and qr and S["q_cd"] <= t:
            deal("Pierce (Q)", Q_BASE[qr - 1] + Q_RATIO * cur_ad(), "physical")
            S["spears"] += 1; S["q_cd"] = t + Q_CD
            if runes.keystone == "Conqueror": S["conq"] = min(12, S["conq"] + 2)
            if has & SPELLBLADE: S["spellblade"] = True
            if "6653" in has:
                if S["liandry_until"] < t: S["liandry_last"] = t
                S["liandry_until"] = t + 3
            if try_finish(): break
            tick(min(t + Q_CAST, limit)); t += Q_CAST
            wait_for_control()
            if try_finish(): break

        extra = 0.0
        if "3124" in has: extra += 0.08 * S["guinsoo"]
        if runes.keystone == "Lethal Tempo": extra += 0.048 * S["lt"]
        if "3032" in has:
            if S["flurry_cd"] <= t and S["flurry_until"] < t:
                S["flurry_until"] = t + 6; S["flurry_cd"] = t + 30
            if t < S["flurry_until"]: extra += 0.30
        if S["spellblade"] and "3100" in has: extra += 0.50
        aspd = st.attack_speed(extra)
        S["attacks"] += 1
        ad, bad, ap = cur_ad(), cur_bad(), cur_ap()

        def on_hit_once():
            ph = mg = 0.0
            if "3153" in has: ph += 0.06 * max(hp, 0)
            if "3124" in has: mg += 30
            if "3091" in has: mg += 45
            if "3302" in has: mg += 30 + 0.10 * bad + 0.10 * ap
            if "3115" in has: mg += 15 + 0.15 * ap
            return ph, mg
        times = 1
        if "3124" in has and S["guinsoo"] == 4:
            if S["phantom"] == 2: times, S["phantom"] = 2, 0
            else: S["phantom"] += 1
        ph = mg = 0.0
        if S["spellblade"]:
            S["spellblade"] = False
            if "3100" in has: mg += 0.75 * st.base_ad + 0.45 * ap
            if "2510" in has: mg += 0.75 * st.base_ad + 0.10 * ap; times += 1   # VERIFY extra spear
        for _ in range(times):
            a, b = on_hit_once(); ph += a; mg += b
        S["spears"] += times
        if "6672" in has and S["attacks"] % 3 == 0:
            ph += lvl_linear(120, 168, level) * (1 + 0.75 * (1 - max(hp, 0) / dummy.hp))   # VERIFY
        if S["energized"] >= 100 and has & ENERGIZED:
            S["energized"] = 0
            mg += 60 * ("3087" in has) + 100 * ("3095" in has) + 40 * ("3094" in has)
        else:
            S["energized"] = min(100, S["energized"] + energize_per_attack)

        rune_dmg, pta_now = 0.0, False
        if runes.keystone == "Press the Attack":
            S["pta"] += 1
            if S["pta"] >= 3 and S["pta_cd"] <= t:
                rune_dmg += lvl_scale(40, 174.12, level); S["pta"] = 0; S["pta_cd"] = t + 6
                pta_now = True
        if runes.keystone == "Lethal Tempo":
            S["lt"] = min(6, S["lt"] + 1)
            if S["lt"] == 6:
                rune_dmg += lvl_scale(6, 21.66, level) * (1 + st.bonus_as + extra)

        deal("Auto attacks", ad * AA_AD_RATIO * crit_factor, "physical", True)
        deal("On-hit (physical)", ph, "physical", True)
        deal("On-hit (magic)", mg, "magic", True)
        deal(runes.keystone, rune_dmg, adaptive_kind())
        if runes.keystone == "Fleet Footwork" and duel:                          # Fleet heal
            if S["fleet"] >= 100:
                S["fleet"] = 0
                heal("Fleet Footwork", lvl_scale(9, 96, level) + 0.06 * bad + 0.03 * ap)  # VERIFY
            else:
                S["fleet"] = min(100, S["fleet"] + 6 + opts.hop_units_per_attack / 24)
        if pta_now: S["pta_amp"] = True
        if runes.keystone == "Conqueror": S["conq"] = min(12, S["conq"] + 1)
        if "3302" in has and S["attacks"] % 2 == 0: S["dark"] = min(3, S["dark"] + 1)
        if "3124" in has: S["guinsoo"] = min(4, S["guinsoo"] + 1)
        if "3032" in has: S["flurry_cd"] -= 1 + crit
        if "6675" in has and S["q_cd"] > t: S["q_cd"] = t + (S["q_cd"] - t) * 0.85
        if trace: log.append((round(t, 2), round(hp), S["spears"], round(K["hp"])))
        if try_finish(): break
        nxt = t + 1 / aspd
        tick(min(nxt, limit)); t = nxt
        if try_finish(): break

    # ---------------- results
    if opts.window > 0:
        end = min(t, limit)
        exit_rend = 0.0
        if opts.exit_e and hp > 0 and S["spears"] > 0 and er and (not duel or K["dead_at"] is None):
            t = limit
            exit_rend = deal("Rend (E)", rend_raw(cur_ad(), cur_ap(), er, S["spears"]), "physical")
        killed = hp <= 0
        return {"killed": killed, "kill_time": end if killed else None,
                "died": duel and K["dead_at"] is not None,
                "dealt_frac": (hp0 - max(hp, 0)) / dummy.hp,
                # damage still stored in Death's Dance lands after the trade, so it counts
                "taken_frac": ((st.hp * opts.kal_start - K["hp"] + sum(d[1] for d in K["dd"])) / K["max"]) if duel else 0.0,
                "exit_rend": exit_rend, "spears": S["spears"],
                "taken_by": {k: round(v) for k, v in K["taken_by"].items()},
                "healed_by": {k: round(v) for k, v in K["healed_by"].items()},
                "dealt_by": {k: round(v) for k, v in by_src.items()}}
    killed = hp <= 0
    if not duel:
        ttk = t if killed else math.inf
        return {"ttk": ttk, "dps": dummy.hp / ttk if ttk < math.inf else 0,
                "attacks": S["attacks"], "spears": S["spears"], "by_source": by_src, "trace": log}

    died = K["dead_at"] is not None
    k_eff = K["hp"] + K["ichor"] + sum(sh[1] for sh in K["shields"] if sh[2] >= t)
    if killed:
        tk = t
        net = (K["taken"] - K["healed"]) / max(tk, 1e-6)      # HP lost per second, net of healing
        td = tk + (k_eff / net if net > 1e-6 else math.inf)
        if K["ga"]: td += 4 + 0.5 * st.base_hp / max(net, 1e-6)  # unused Guardian Angel
    elif died:
        td = K["dead_at"]
        dealt = dummy.hp - hp
        rate = dealt / max(td, 1e-6)
        tk = td + (hp / rate if rate > 1e-6 else math.inf)
    else:                                                       # timeout: estimate both
        dealt = dummy.hp - hp
        tk = t + hp / max(dealt / max(t, 1e-6), 1e-6)
        net = (K["taken"] - K["healed"]) / max(t, 1e-6)
        td = t + (k_eff / net if net > 1e-6 else math.inf)
    margin = min(opts.margin_cap, td / tk) if tk > 0 else opts.margin_cap
    return {"win": killed and not died, "tk": tk, "td": td, "margin": margin,
            "kal_hp_left": min(1.0, max(0.0, k_eff / K["max"])) if killed else 0.0,
            "enemy_hp_left": max(0.0, hp / dummy.hp),
            "taken_by": {k: round(v) for k, v in K["taken_by"].items()},
            "healed_by": {k: round(v) for k, v in K["healed_by"].items()},
            "dealt_by": {k: round(v) for k, v in by_src.items()},
            "ga_used": "3026" in has and not K["ga"],
            "trace": log}

def item_name(iid): return ITEMS[iid]["name"]
def item_cost(iid): return ITEMS[iid]["gold"]["total"]
