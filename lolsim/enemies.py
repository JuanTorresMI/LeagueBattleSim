"""The other side of the fight: fastest-kill dummies, threat profiles (config/threats.json)
and the enemy's actions as an event queue."""
import heapq
from dataclasses import dataclass

from params import THREAT_CFG, KIT
from .stats import CHAMPS, AS_CAP, CRIT_BASE, AD_GROWTH_OVERRIDE, growth, lvl_scale, level_value


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
    """The enemy's defensive side: a class dummy (champion base stats + per-item stats),
    or a real champion kit from data/wiki/enemy_kits.json."""
    if kind in KIT_THREATS:
        return make_kit_dummy(kind, level, n_items)
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


@dataclass
class KitThreat:
    """A real champion's kit (data/wiki/enemy_kits.json). Per-item stats copy the class
    profile in items_like. Never calibrated (dmg_mult stays 1.0 unless set)."""
    key: str
    name: str
    melee: bool
    items_like: str
    kit: dict
    ad_per_item: float = 0.0; as_per_item: float = 0.0; crit_per_item: float = 0.0; ap_per_item: float = 0.0
    armor_pen_at: tuple = (99, 0.0)
    magic_pen_at: tuple = (99, 0.0, 0)
    wounds_at: int = 99
    abilities: tuple = ()
    dmg_mult: float = 1.0

    @classmethod
    def load(cls, key, v):
        prof = THREAT_CFG["threats"][v["items_like"]]
        return cls(key, v["name"], v["melee"], v["items_like"], v,
                   ad_per_item=prof["ad_per_item"], as_per_item=prof["as_per_item"],
                   crit_per_item=prof.get("crit_per_item", 0.0), ap_per_item=prof.get("ap_per_item", 0.0),
                   armor_pen_at=tuple(prof.get("armor_pen_at", (99, 0.0))),
                   magic_pen_at=tuple(prof.get("magic_pen_at", (99, 0.0, 0))), wounds_at=prof.get("wounds_at", 99))


KIT_THREATS = {k: KitThreat.load(k, v) for k, v in KIT.items()}
ALL_THREATS = {**THREATS, **KIT_THREATS}


def make_kit_dummy(key, level, n_items):
    kt = KIT_THREATS[key]
    d = THREAT_CFG["dummies"][kt.items_like]
    s = CHAMPS[kt.name]["stats"]; g = growth(level)
    bonus = d["hp_per_item"] * n_items
    return Dummy(f"{kt.name} (lvl {level}, {n_items} items)", s["hp"] + s["hpperlevel"] * g + bonus,
                 s["armor"] + s["armorperlevel"] * g + d["armor_per_item"] * n_items,
                 s["spellblock"] + s["spellblockperlevel"] * g + d["mr_per_item"] * n_items, bonus, key)


def _rank(x, r):
    return x[r - 1] if isinstance(x, list) else x

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
        kit = isinstance(th, KitThreat)
        if kit:
            s = CHAMPS[th.name]["stats"]; g = growth(level)
            self.ad = s["attackdamage"] + AD_GROWTH_OVERRIDE.get(th.name, 0) * g + self.bonus_ad
            self.as_ = min(AS_CAP, s["attackspeed"] * (1 + s["attackspeedperlevel"] / 100 * g + th.as_per_item * n))
        else:
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
        self.autos, self.marked = 0, False
        # runtime abilities: [cd, kind, raw on first cast, later-cast multiplier, stun, stun every cast, label]
        self.abil, self.procs, firsts = [], [], []
        if kit:
            from .kits import skill_ranks
            ranks = dict(zip("QWE", skill_ranks(level, tuple(th.kit["skill_start"]), tuple(th.kit["skill_max"]))))
            for a in th.kit["abilities"]:
                r = ranks[a["slot"]]
                if not r: continue
                raw = a.get("base_mult", 1.0) * (_rank(a["base"], r) + _rank(a.get("ad_ratio", 0), r) * self.ad
                                                 + _rank(a.get("bonus_ad_ratio", 0), r) * self.bonus_ad
                                                 + _rank(a.get("ap_ratio", 0), r) * self.ap)
                self.abil.append([_rank(a["cd"], r) - a.get("cd_refund", 0), a["kind"], raw, 1.0, a.get("cc", 0.0), True, a["name"]])
                firsts.append(a["first"])
            for p in th.kit.get("auto_procs", ()):
                q = dict(p, ready=0.0)
                if "ad_pct_by_level" in p:
                    pct = max(v for lv, v in p["ad_pct_by_level"] if level >= lv)
                    q["raw"] = self.ad * (pct + ((self.crit_f - 1) if p.get("plus_crit") else 0))
                else:
                    q["raw"] = level_value(p["base"], level) + p.get("ap_ratio", 0) * self.ap
                self.procs.append(q)
        else:
            for a in th.abilities:
                raw = lvl_scale(a.base_lo, a.base_hi, level) + a.bonus_ad_ratio * self.bonus_ad + a.ap_ratio * self.ap
                self.abil.append([a.cd, a.kind, raw, a.repeat_scale * (self.uptime if th.melee else 1.0), a.cc, False,
                                  "Enemy abilities"])
                firsts.append(a.first)
        self.casts = [0] * len(self.abil)
        self.queue = [(ENEMY_ITEMS["melee_first_auto"] if th.melee else 0.0, 0, _AUTO)]
        self.queue += [(t0, i + 1, i) for i, t0 in enumerate(firsts)]
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
                self.autos += 1
                for p in self.procs:
                    if (p.get("every") and self.autos % p["every"] == 0) or \
                       (p.get("per_target_cd") and tm >= p["ready"]) or (p.get("after_ability") and self.marked):
                        f.take(p["name"], p["raw"] * self.uptime, p["kind"], True)
                        p["ready"] = tm + p.get("per_target_cd", 0)
                        if p.get("after_ability"): self.marked = False
                heapq.heapreplace(q, (tm + 1 / self.as_, pr, i))
            else:
                cd, kind, raw, later, cc, cc_every, label = self.abil[i]
                first = self.casts[i] == 0
                f.take(label, raw * (1.0 if first else later), kind)
                if cc and (first or cc_every) and f.t >= kal.revive_until:
                    kal.cc_until = max(kal.cc_until, f.t + cc * (1 - f.st.tenacity))
                self.casts[i] += 1
                self.marked = True
                heapq.heapreplace(q, (tm + cd, pr, i))
