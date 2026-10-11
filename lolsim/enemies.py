"""The other side of the fight: fastest-kill dummies, threat profiles (config/threats.json)
and the enemy's actions as an event queue."""
import heapq
from dataclasses import dataclass

from params import THREAT_CFG
from .stats import CHAMPS, AS_CAP, CRIT_BASE, growth, lvl_scale


@dataclass
class Dummy:
    name: str
    hp: float
    armor: float
    mr: float
    bonus_hp: float = 0.0
    kind: str = ""


# kind -> (champion whose base stats are used, per-item HP, armor, MR)
DUMMY_KINDS = {k: (v["champion"], v["hp_per_item"], v["armor_per_item"], v["mr_per_item"])
               for k, v in THREAT_CFG["dummies"].items() if not k.startswith("_")}


def make_dummy(kind, level, n_items):
    champ, hp_i, ar_i, mr_i = DUMMY_KINDS[kind]
    s = CHAMPS[champ]["stats"]; g = growth(level)
    bonus = hp_i * n_items
    return Dummy(f"{kind} (lvl {level}, {n_items} items)",
                 s["hp"] + s["hpperlevel"] * g + bonus,
                 s["armor"] + s["armorperlevel"] * g + ar_i * n_items,
                 s["spellblock"] + s["spellblockperlevel"] * g + mr_i * n_items,
                 bonus, kind)


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
    wounds_at: int = 99                    # items needed for Grievous Wounds
    abilities: tuple = ()
    dmg_mult: float = 1.0                  # calibration multiplier on all damage dealt


def threat_from_config(cfg):
    c = dict(cfg)
    c["abilities"] = tuple(Ability(**a) for a in c.get("abilities", ()))
    for k in ("armor_pen_at", "magic_pen_at"):
        if k in c: c[k] = tuple(c[k])
    return Threat(**c)


THREATS = {k: threat_from_config(v) for k, v in THREAT_CFG["threats"].items()}
ENEMY_ITEMS = THREAT_CFG["enemy_items"]

_AUTO = -1


class Enemy:
    """A threat at one level with n items, acting on a time-ordered event queue.

    Events are (time, priority, action): the auto attack has priority 0 and the
    abilities 1, 2, ... in profile order, so an auto and a cast at the same time
    resolve auto first."""

    def __init__(self, threat, level, n, kite_uptime):
        th = self.threat = threat
        self.level = level
        self.bonus_ad = th.ad_per_item * n
        self.ad = lvl_scale(th.ad_lo, th.ad_hi, level) + self.bonus_ad
        self.as_ = min(AS_CAP, th.as_base * (1 + th.as_per_lvl * (level - 1) + th.as_per_item * n))
        e_crit = min(1.0, th.crit_per_item * n)
        self.ap = th.ap_per_item * n * (ENEMY_ITEMS["ap_mult"] if n >= ENEMY_ITEMS["ap_mult_from"] and th.ap_per_item else 1)
        self.crit_f = 1 + e_crit * (CRIT_BASE + (ENEMY_ITEMS["crit_damage_bonus"]
                                                if n >= ENEMY_ITEMS["crit_damage_from"] and e_crit else 0) - 1)
        self.apen = th.armor_pen_at[1] if n >= th.armor_pen_at[0] else 0.0
        self.mpen = (th.magic_pen_at[1], th.magic_pen_at[2]) if n >= th.magic_pen_at[0] else (0.0, 0)
        self.wounds = n >= th.wounds_at
        self.uptime = kite_uptime if th.melee else 1.0
        self.dealt = 0.0
        self.casts = [0] * len(th.abilities)
        self.queue = [(ENEMY_ITEMS["melee_first_auto"] if th.melee else 0.0, 0, _AUTO)]
        self.queue += [(a.first, i + 1, i) for i, a in enumerate(th.abilities)]
        heapq.heapify(self.queue)

    def run_until(self, f, until):
        """Resolve every enemy action up to `until` against fight `f`."""
        th, kal, q = self.threat, f.kal, self.queue
        while f.hp > 0 and kal.dead_at is None:
            tm, pr, i = q[0]
            if tm > until: break
            f.t = tm
            if i == _AUTO:
                f.take("Enemy autos", self.ad * self.crit_f * self.uptime, "physical", True)
                heapq.heapreplace(q, (tm + 1 / self.as_, pr, i))
            else:
                a = th.abilities[i]
                first = self.casts[i] == 0
                scale = 1.0 if first else a.repeat_scale * (self.uptime if th.melee else 1.0)
                raw = (lvl_scale(a.base_lo, a.base_hi, self.level) + a.bonus_ad_ratio * self.bonus_ad
                       + a.ap_ratio * self.ap) * scale
                f.take("Enemy abilities", raw, a.kind)
                if a.cc and first and f.t >= kal.revive_until:
                    kal.cc_until = max(kal.cc_until, f.t + a.cc * (1 - f.st.tenacity))
                self.casts[i] += 1
                heapq.heapreplace(q, (tm + a.cd, pr, i))
