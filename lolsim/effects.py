"""Item and rune effects, registered by hook.

Each effect is a class keyed by an item id or a rune name. A fight builds one instance
per owned item / chosen rune and calls its hook methods at fixed points:

  fight setup     bonus_crit, dyn_stats, on_fight_start
  own damage      damage_amp (multiplier), armor_reduction, armor_pen, mr_reduction,
                  on_damage(src, kind, dmg), omnivamp, on_damage_heal, execute
  abilities       on_ability(damaging) (after each cast)
  attacks         attack_speed, on_attack (before on-hit), on_hit (each application,
                  returns physical, magic), on_attack_bonus, on_rune, after_attack
  time            on_tick (DoTs and delayed effects)
  damage taken    attack_taken_mult, on_take_damage, on_low_hp, on_lethal, on_overheal
  team fights     on_target_switch (reset per-target state when Kalista changes target)

Handlers of one hook run in the order the classes are defined below; that order matches
the original simulator wherever it changes a result (damage multipliers, attack-speed and
on-hit sums, which shield absorbs first). Numbers come from data/wiki (ITEM / RUNE)."""
import math

from params import ITEM, RUNE, MECH
from .stats import level_value

HOOKS = ("bonus_crit", "dyn_stats", "on_fight_start", "damage_amp", "armor_reduction", "armor_pen",
         "mr_reduction", "on_damage", "omnivamp", "on_damage_heal", "execute", "on_ability",
         "attack_speed", "on_attack", "on_hit", "on_attack_bonus", "on_rune", "after_attack",
         "on_tick", "attack_taken_mult", "on_take_damage", "on_low_hp", "on_lethal", "on_overheal",
         "on_target_switch")

EN = MECH["energized"]
REGISTRY = []      # effect classes in definition (= hook) order


def effect(*keys, rune=False):
    def wrap(cls):
        cls.keys, cls.is_rune = keys, rune
        cls.hook_names = tuple(h for h in HOOKS if h in cls.__dict__)
        REGISTRY.append(cls)
        return cls
    return wrap


class Effect:
    keys, is_rune = (), False

    def __init__(self, f):
        self.f = f
        self.v = RUNE[self.keys[0]] if self.is_rune else ITEM.get(self.keys[0], {})

    @classmethod
    def applies(cls, f):
        if cls.is_rune:
            return f.runes.keystone in cls.keys or f.runes.combat in cls.keys
        return any(k in f.has for k in cls.keys)


_owned = {}      # (items, keystone, combat) -> effect classes that apply


def effects_for(f):
    """Instantiate the effects a fight owns and return {hook: [bound handlers]}."""
    key = (frozenset(f.has), f.runes.keystone, f.runes.combat)
    classes = _owned.get(key)
    if classes is None:
        classes = _owned[key] = [cls for cls in REGISTRY if cls.applies(f)]
    effs = [cls(f) for cls in classes]
    hooks = {h: [] for h in HOOKS}
    for e in effs:
        for h in e.hook_names:
            hooks[h].append(getattr(e, h))
    return effs, hooks


# ------------------------------------------------------------- damage multipliers first
@effect("3036")
class LordDominiks(Effect):
    def __init__(self, f):
        super().__init__(f)
        self.on_target_switch()
    def on_target_switch(self):
        self.giant = 1 + self.v["giant_slayer_max"] * min(self.f.dummy.bonus_hp / self.v["giant_slayer_hp_diff"], 1)
    def damage_amp(self, kind, is_attack): return self.giant


@effect("Press the Attack", rune=True)
class PressTheAttack(Effect):
    def __init__(self, f):
        super().__init__(f)
        self.stacks, self.cd, self.amp_on = 0, 0.0, False
    def damage_amp(self, kind, is_attack):
        return 1 + self.v["amp"] if self.amp_on and kind != "true" else 1.0
    def on_rune(self, hit):
        f, v = self.f, self.v
        self.stacks += 1
        if self.stacks >= v["hits"] and self.cd <= f.t:
            hit.rune += level_value(v["damage"], f.level); self.stacks = 0; self.cd = f.t + v["cd"]
            hit.pta_now = True
    def after_attack(self, hit):
        if hit.pta_now: self.amp_on = True
    def on_target_switch(self): self.stacks = 0


@effect("4633")
class Riftmaker(Effect):
    def damage_amp(self, kind, is_attack):
        return 1 + min(self.v["amp_max"], self.v["amp_per_s"] * math.floor(self.f.t))
    def omnivamp(self):                                           # max strength, ranged
        return self.v["omnivamp_ranged"] if self.f.t >= self.v["full_after"] else 0.0


@effect("6653")
class Liandrys(Effect):
    def __init__(self, f):
        super().__init__(f)
        self.until, self.last = -1.0, 0.0
    def damage_amp(self, kind, is_attack):
        return 1 + min(self.v["amp_max"], self.v["amp_per_s"] * math.floor(self.f.t))
    def on_ability(self, damaging):
        if not damaging: return
        t = self.f.t
        if self.until < t: self.last = t
        self.until = t + self.v["burn_duration"]
    def on_target_switch(self): self.until, self.last = -1.0, 0.0      # the burn stays on the old target
    def on_tick(self, now):
        f = self.f
        if self.until > self.last:
            end = min(now, self.until)
            if end > self.last:
                f.t = end
                f.deal("Liandry's burn", self.v["burn_max_hp_per_s"] * f.dummy.hp * (end - self.last), "magic")
                self.last = end


@effect("Coup de Grace", rune=True)
class CoupDeGrace(Effect):
    def damage_amp(self, kind, is_attack):
        return 1 + self.v["amp"] if self.f.hp / self.f.dummy.hp < self.v["below"] else 1.0


@effect("Cut Down", rune=True)
class CutDown(Effect):
    def damage_amp(self, kind, is_attack):
        return 1 + self.v["amp"] if self.f.hp / self.f.dummy.hp > self.v["above"] else 1.0


@effect("Last Stand", rune=True)
class LastStand(Effect):
    def damage_amp(self, kind, is_attack):
        f, v = self.f, self.v
        if not f.duel: return 1.0
        kf = f.kal.hp / f.kal.max
        if kf >= v["start_below"]: return 1.0
        return 1 + v["min_amp"] + v["extra_amp"] * min(1.0, (v["start_below"] - kf) / (v["start_below"] - v["full_at"]))


@effect("4645")
class Shadowflame(Effect):
    def damage_amp(self, kind, is_attack):
        return 1 + self.v["amp"] if kind in ("magic", "true") and self.f.hp / self.f.dummy.hp < self.v["below"] else 1.0


@effect("2523")
class Hexoptics(Effect):
    def damage_amp(self, kind, is_attack):
        return 1 + self.v["attack_amp"] if is_attack else 1.0


# ------------------------------------------------------------- on-hit and attack speed
@effect("3153")
class RuinedKing(Effect):
    def on_hit(self, hit): return self.v["current_hp_ranged"] * max(self.f.hp, 0), 0.0


@effect("3124")
class Guinsoos(Effect):
    def __init__(self, f):
        super().__init__(f)
        self.stacks, self.phantom = 0, 0
    def attack_speed(self): return self.v["as_per_stack"] * self.stacks
    def on_attack(self, hit):                                     # Phantom Hit: on-hit twice
        if self.stacks == self.v["max_stacks"]:
            if self.phantom == self.v["phantom_every"] - 1: hit.times += 1; self.phantom = 0
            else: self.phantom += 1
    def on_hit(self, hit): return 0.0, self.v["on_hit"]
    def after_attack(self, hit): self.stacks = min(self.v["max_stacks"], self.stacks + 1)


@effect("Lethal Tempo", rune=True)
class LethalTempo(Effect):
    def __init__(self, f):
        super().__init__(f)
        self.stacks = 0
    def attack_speed(self): return self.v["as_per_stack"] * self.stacks
    def on_rune(self, hit):
        v = self.v
        self.stacks = min(v["max_stacks"], self.stacks + 1)
        if self.stacks == v["max_stacks"]:
            hit.rune += level_value(v["damage"], self.f.level) * (1 + self.f.st.bonus_as + hit.extra_as)


@effect("3091")
class WitsEnd(Effect):
    def on_hit(self, hit): return 0.0, self.v["on_hit"]


@effect("3302")
class Terminus(Effect):
    def __init__(self, f):
        super().__init__(f)
        self.dark = 0
    def armor_pen(self): return self.v["pen_per_stack"] * self.dark
    def on_hit(self, hit): return 0.0, self.v["on_hit"] + self.v["bonus_ad_ratio"] * hit.bad + self.v["ap_ratio"] * hit.ap
    def after_attack(self, hit):
        if self.f.attacks % self.v["attacks_per_stack"] == 0: self.dark = min(self.v["max_stacks"], self.dark + 1)


@effect("3115")
class Nashors(Effect):
    def on_hit(self, hit): return 0.0, self.v["on_hit"] + self.v["ap_ratio"] * hit.ap


@effect("3032")
class YunTal(Effect):
    def __init__(self, f):
        super().__init__(f)
        self.flurry_until, self.flurry_cd = -1.0, 0.0
    def bonus_crit(self):                                         # unstacked the slot it is bought
        return self.v["stacked_crit"] if self.f.opts.yuntal_prestacked else 0
    def attack_speed(self):
        t, v = self.f.t, self.v
        if self.flurry_cd <= t and self.flurry_until < t:
            self.flurry_until = t + v["flurry_duration"]; self.flurry_cd = t + v["flurry_cd"]
        return v["flurry_as"] if t < self.flurry_until else 0.0
    def after_attack(self, hit):
        self.flurry_cd -= self.v["cd_per_attack"] + self.v["cd_per_crit"] * self.f.crit


@effect("3100")
class LichBane(Effect):
    def on_ability(self, damaging): self.f.spellblade = True
    def attack_speed(self): return self.v["as_after_spell"] if self.f.spellblade else 0.0
    def on_attack(self, hit):
        if hit.spellblade: hit.mg += self.v["base_ad_ratio"] * self.f.st.base_ad + self.v["ap_ratio"] * hit.ap


@effect("2510")
class DuskAndDawn(Effect):
    def on_ability(self, damaging): self.f.spellblade = True
    def on_attack(self, hit):                                     # VERIFY: the repeat adds a spear
        if hit.spellblade:
            hit.mg += self.v["base_ad_ratio"] * self.f.st.base_ad + self.v["ap_ratio"] * hit.ap
            hit.times += self.v["extra_on_hit"]
    def after_attack(self, hit):                                  # the empowered hit heals
        if hit.spellblade:
            v, st = self.v, self.f.st
            self.f.heal("Dusk and Dawn", v["heal_ap_ratio"] * hit.ap + v["heal_bonus_hp_ratio"] * st.bonus_hp)


@effect("6672")
class Kraken(Effect):
    def on_attack_bonus(self, hit):                               # VERIFY: ranged scaling
        f, v = self.f, self.v
        if f.attacks % v["every"] == 0:
            hit.ph += level_value(v["ranged"], f.level) * (1 + v["missing_hp_amp"] * (1 - max(f.hp, 0) / f.dummy.hp))


@effect("3087", "3095", "3094")
class Energized(Effect):
    """One shared charge for the Energized items you own."""
    def __init__(self, f):
        super().__init__(f)
        has = f.has
        self.proc = (ITEM["3087"]["energized"] * ("3087" in has) + ITEM["3095"]["energized"] * ("3095" in has)
                     + ITEM["3094"]["energized"] * ("3094" in has))
        self.per = (ITEM["3087"]["charge_per_attack"] if "3087" in has else EN["charge_per_attack"]) \
            + f.opts.hop_units_per_attack / EN["units_per_charge"]
        self.charge = EN["max"] if f.opts.energized_full_at_start else 0
    def on_attack_bonus(self, hit):
        if self.charge >= EN["max"]:
            self.charge = 0
            hit.mg += self.proc
            f = self.f
            if f.n_sec and "3087" in f.has:                      # Statikk chain lightning
                n = min(f.n_sec, chain_targets(f.level) - 1)
                ph, mg = f.secondary_on_hit(hit)
                f.splash("Statikk chain", ITEM["3087"]["energized"], "magic", n)
                f.splash("On-hit (secondary)", ph, "physical", n); f.splash("On-hit (secondary)", mg, "magic", n)
                f.kit.on_secondary_hits(n)
        else:
            self.charge = min(EN["max"], self.charge + self.per)


def chain_targets(level):
    return max(n for lv, n in ITEM["3087"]["chain_targets_by_level"] if level >= lv)


@effect("3085")
class Runaans(Effect):
    """Bolts at up to 2 other enemies (multi-target option only)."""
    def on_attack_bonus(self, hit):
        f, v = self.f, self.v
        n = min(f.n_sec, v["bolts"])
        if not n: return
        ph, mg = f.secondary_on_hit(hit)
        f.splash("Runaan's bolts", v["bolt_ad_ratio"] * hit.ad * f.crit_factor, "physical", n)
        f.splash("On-hit (secondary)", ph, "physical", n); f.splash("On-hit (secondary)", mg, "magic", n)
        f.kit.on_secondary_hits(n * hit.times)


# ------------------------------------------------------------- damage taken
@effect("3047")
class PlatedSteelcaps(Effect):
    def attack_taken_mult(self): return self.v["attack_damage_taken"]


@effect("6333")
class DeathsDance(Effect):
    def on_take_damage(self, kind, dmg):
        if kind == "true": return dmg
        stored = self.v["stored_ranged"] * dmg
        self.f.kal.dd.append([self.f.t, stored])
        return dmg - stored


@effect("3156")
class Maw(Effect):
    def __init__(self, f):
        super().__init__(f)
        self.used = self.vamp_on = False
    def omnivamp(self): return self.v["omnivamp"] if self.vamp_on else 0.0
    def on_low_hp(self, kind, after):
        f, v = self.f, self.v
        if kind == "magic" and not self.used and after < v["trigger_below"] * f.kal.max:
            self.used = self.vamp_on = True
            f.kal.shields.append(["Maw shield", v["shield_base"] + v["shield_bonus_ad_ratio"] * f.cur_bad(), f.t + v["duration"], "magic"])


@effect("6673")
class Shieldbow(Effect):
    def __init__(self, f):
        super().__init__(f)
        self.used = False
    def on_low_hp(self, kind, after):
        f, v = self.f, self.v
        if not self.used and after < v["trigger_below"] * f.kal.max:
            self.used = True
            f.kal.shields.append(["Shieldbow", level_value(v["shield"], f.level), f.t + v["duration"], "any"])


@effect("4646")
class Stormsurge(Effect):
    def __init__(self, f):
        super().__init__(f)
        self.window, self.at, self.used = [], None, False
    def on_damage(self, src, kind, dmg):
        if self.used: return
        f, v = self.f, self.v
        self.window.append((f.t, dmg))
        self.window = [(a, b) for a, b in self.window if f.t - a <= v["window"]]
        if sum(b for _, b in self.window) >= v["threshold"] * f.dummy.hp:
            self.used = True; self.at = f.t + v["delay"]
    def on_target_switch(self): self.window, self.at, self.used = [], None, False
    def on_tick(self, now):
        if self.at is not None and self.at <= now:
            f = self.f
            f.t = self.at; self.at = None
            f.deal("Stormsurge", self.v["base"] + self.v["ap_ratio"] * f.cur_ap(), "magic")


@effect("3146")
class Gunblade(Effect):
    def on_fight_start(self):
        f, v = self.f, self.v
        if f.opts.gunblade_active:
            f.deal("Gunblade active", level_value(v["active"], f.level) + v["active_ap_ratio"] * f.cur_ap(), "magic")


@effect("6676")
class Collector(Effect):
    def execute(self):
        f = self.f
        if f.hp < self.v["execute_below"] * f.dummy.hp:
            f.deal("Collector execute", f.hp, "true"); return True
        return False


@effect("3071")
class BlackCleaver(Effect):
    def __init__(self, f):
        super().__init__(f)
        self.stacks = 0
    def armor_reduction(self): return self.v["shred_per_stack"] * self.stacks
    def on_target_switch(self): self.stacks = 0
    def on_damage(self, src, kind, dmg):
        if kind == "physical": self.stacks = min(self.v["max_stacks"], self.stacks + 1)


@effect("8010")
class Bloodletters(Effect):
    def __init__(self, f):
        super().__init__(f)
        self.stacks = 0
    def mr_reduction(self): return self.v["shred_per_stack"] * self.stacks
    def on_target_switch(self): self.stacks = 0
    def on_damage(self, src, kind, dmg):                          # only champion-ability magic damage
        if kind == "magic" and src in self.f.kit.ability_sources:
            self.stacks = min(self.v["max_stacks"], self.stacks + 1)


@effect("3072")
class Bloodthirster(Effect):
    def on_overheal(self, src, over):                             # Ichorshield from lifesteal overheal
        if src != "Lifesteal": return
        f = self.f
        cap = level_value(self.v["shield"], f.level)
        add = min(over, cap - f.kal.ichor)
        if add > 0:
            f.kal.ichor += add
            f.kal.healed_by["Ichorshield"] = f.kal.healed_by.get("Ichorshield", 0) + add


@effect("3026")
class GuardianAngel(Effect):
    def __init__(self, f):
        super().__init__(f)
        f.kal.ga = True
    def on_lethal(self):
        f, kal = self.f, self.f.kal
        if not kal.ga: return False
        kal.ga = False; kal.revive_until = f.t + self.v["revive_time"]
        kal.hp = self.v["revive_base_hp"] * f.st.base_hp
        kal.dd.clear()
        kal.healed_by["Guardian Angel"] = self.v["revive_base_hp"] * f.st.base_hp
        return True


@effect("Conqueror", rune=True)
class Conqueror(Effect):
    def __init__(self, f):
        super().__init__(f)
        self.stacks = 0
        v = self.v
        self.ap_per = level_value(v["ap"], f.level)
        self.ad_per = level_value(v["ad"], f.level)
    def dyn_stats(self):
        if self.f.adaptive_magic: return 0.0, self.stacks * self.ap_per
        return self.stacks * self.ad_per, 0.0
    def on_ability(self, damaging):
        if damaging: self.stacks = min(self.v["max_stacks"], self.stacks + self.v["stacks_per_ability"])
    def after_attack(self, hit): self.stacks = min(self.v["max_stacks"], self.stacks + self.v["stacks_per_attack"])
    def on_damage_heal(self, dmg):
        if self.stacks >= self.v["max_stacks"]: self.f.heal("Conqueror", self.v["heal_full"] * dmg)


@effect("Fleet Footwork", rune=True)
class FleetFootwork(Effect):
    def __init__(self, f):
        super().__init__(f)
        self.charge = EN["max"]
    def after_attack(self, hit):
        f, v = self.f, self.v
        if not f.duel: return
        if self.charge >= EN["max"]:
            self.charge = 0
            f.heal("Fleet Footwork", level_value(v["heal"], f.level) + v["bonus_ad_ratio"] * hit.bad + v["ap_ratio"] * hit.ap)
        else:
            self.charge = min(EN["max"], self.charge + EN["charge_per_attack"] + f.opts.hop_units_per_attack / EN["units_per_charge"])


@effect("6675")
class Navori(Effect):
    def after_attack(self, hit): self.f.kit.scale_cooldowns(self.v["cd_left_per_attack"])
