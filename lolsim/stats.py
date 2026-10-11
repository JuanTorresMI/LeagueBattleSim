"""Stat engine: any champion, any level, any items (Riot Data Dragon + data/wiki)."""
import json, os
from dataclasses import dataclass

from params import HERE, ITEM, MECH, CHAMP


def _load(name):
    with open(os.path.join(HERE, "data", name), encoding="utf-8") as f:
        return json.load(f)["data"]


CHAMPS = _load("champion.json")
ITEMS = _load("item.json")

CRIT_BASE = MECH["crit"]["base_damage"]          # VERIFY: wiki lists 200% default crit damage
AS_CAP = MECH["attack_speed"]["cap"]
AD_GROWTH_OVERRIDE = CHAMP["ad_growth"]
_GA, _GB = MECH["stat_growth"]["a"], MECH["stat_growth"]["b"]

EXTRA_ITEM_STATS = {iid: v["stats"] for iid, v in ITEM.items() if "stats" in v}   # description-only stats


def growth(level):
    n = level - 1
    return n * (_GA + _GB * n)


def lvl_scale(lo, hi, level):
    """Level-based value on League's growth curve (lo at 1, hi at 18)."""
    return lo + (hi - lo) * growth(level) / growth(18)


def lvl_linear(lo, hi, level):
    return lo + (hi - lo) * (level - 1) / 17


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
    from .runes import RunePage
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
    if "4633" in item_ids: st.ap += ITEM["4633"]["bonus_hp_to_ap"] * st.bonus_hp   # Riftmaker Void Infusion
    if "3089" in item_ids: st.ap *= ITEM["3089"]["ap_mult"]                         # Rabadon's
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
    """% reduction, then % penetration, then flat penetration, floored at 0."""
    r = resist * (1 - reduction_pct)
    if r <= 0: return r
    return max(0.0, r * (1 - pen_pct) - flat_pen)


def item_name(iid): return ITEMS[iid]["name"]
def item_cost(iid): return ITEMS[iid]["gold"]["total"]
