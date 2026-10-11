"""Fight state and loop.

A Fight holds both sides' state. Kalista's actions run in a loop (abilities via the
kit, then an auto attack); between her actions `tick` advances time: the enemy's event
queue (autos, abilities), Death's Dance bleed, then timed effects (DoTs, delayed procs).
Items and runes plug in through effect hooks (effects.py)."""
import math
from dataclasses import dataclass

from params import SCORING, MECH
from .stats import build_stats, resist_mult, eff_resist
from .runes import RunePage
from .enemies import Enemy
from .kits import KITS
from .effects import effects_for

FIGHT = SCORING["fight"]
GW_CUT = MECH["grievous_wounds"]["healing_cut"]


@dataclass
class Opts:
    use_q: bool = True
    energized_full_at_start: bool = True
    hop_units_per_attack: float = FIGHT["hop_units_per_attack"]
    yuntal_prestacked: bool = True
    kite_uptime: float = FIGHT["kite_uptime"]   # share of melee damage that lands while Kalista kites
    max_time: float = FIGHT["max_time"]
    window: float = 0.0            # >0: a short trade that ends after this many seconds
    exit_e: bool = False           # rip Rend at the end of the trade window
    enemy_start: float = 1.0       # enemy's starting HP fraction
    kal_start: float = 1.0         # Kalista's starting HP fraction
    gunblade_active: bool = True   # Hextech Gunblade's active is off cooldown
    margin_cap: float = FIGHT["margin_cap"]


class Hit:
    """One auto attack being built up by the effect hooks."""
    __slots__ = ("extra_as", "ad", "bad", "ap", "times", "ph", "mg", "rune", "pta_now", "spellblade")

    def __init__(self, extra_as, ad, bad, ap, spellblade):
        self.extra_as, self.ad, self.bad, self.ap = extra_as, ad, bad, ap
        self.times, self.ph, self.mg, self.rune = 1, 0.0, 0.0, 0.0
        self.pta_now, self.spellblade = False, spellblade


class Side:
    """Kalista's defensive state (used in duels)."""
    def __init__(self, hp, max_hp):
        self.hp, self.max = hp, max_hp
        self.shields = []            # [name, amount, expires, "magic" | "any"]
        self.ichor = 0.0
        self.cc_until = 0.0
        self.dead_at = None
        self.revive_until = -1.0
        self.ga = False              # an unused Guardian Angel
        self.dd = []                 # Death's Dance: [last bleed time, stored damage]
        self.taken = self.healed = 0.0
        self.taken_by, self.healed_by = {}, {}
        self.wounds = False


class Fight:
    def __init__(self, item_ids, level, dummy, runes=None, opts=None, threat=None, enemy_items=0,
                 trace=False, champ="Kalista"):
        self.runes = runes = runes or RunePage()
        self.opts = opts = opts or Opts()
        self.st = st = build_stats(champ, level, item_ids, runes)
        self.has = set(item_ids)
        self.level, self.dummy, self.threat = level, dummy, threat
        self.duel = threat is not None
        self.hp = self.hp0 = dummy.hp * opts.enemy_start
        self.t = 0.0
        self.attacks = 0
        self.spellblade = False
        self.by_src, self.log, self.trace = {}, [], trace
        self.adaptive_magic = st.ap > st.bonus_ad
        self.kal = Side(st.hp * opts.kal_start, st.hp)
        self.enemy = None
        if self.duel:
            self.enemy = Enemy(threat, level, enemy_items, opts.kite_uptime)
            self.kal.wounds = self.enemy.wounds
        self.kit = KITS[champ](self)
        self.effects, H = effects_for(self)
        self.h_amp, self.h_dealt, self.h_vamp = H["damage_amp"], H["on_damage"], H["omnivamp"]
        self.h_dealt_heal, self.h_tick, self.h_exec = H["on_damage_heal"], H["on_tick"], H["execute"]
        self.h_armor_red, self.h_armor_pen, self.h_mr_red = H["armor_reduction"], H["armor_pen"], H["mr_reduction"]
        self.h_cast, self.h_as, self.h_attack = H["on_ability"], H["attack_speed"], H["on_attack"]
        self.h_on_hit, self.h_bonus, self.h_rune, self.h_after = H["on_hit"], H["on_attack_bonus"], H["on_rune"], H["after_attack"]
        self.h_taken_mult, self.h_take, self.h_low, self.h_lethal = H["attack_taken_mult"], H["on_take_damage"], H["on_low_hp"], H["on_lethal"]
        self.h_overheal, self.h_start = H["on_overheal"], H["on_fight_start"]
        self.dyn = H["dyn_stats"][0] if H["dyn_stats"] else None
        bonus_crit = 0
        for h in H["bonus_crit"]: bonus_crit += h()
        self.crit = min(1.0, st.crit + bonus_crit)
        self.crit_factor = 1 + self.crit * (st.crit_damage - 1)

    # ---------------------------------------------------------------- current stats
    def cur_ad(self):  return self.st.ad + self.dyn()[0] if self.dyn else self.st.ad
    def cur_bad(self): return self.st.bonus_ad + self.dyn()[0] if self.dyn else self.st.bonus_ad
    def cur_ap(self):  return self.st.ap + self.dyn()[1] if self.dyn else self.st.ap

    # ---------------------------------------------------------------- dealing damage
    def amp(self, kind, is_attack=False):
        m = 1.0
        for h in self.h_amp: m *= h(kind, is_attack)
        return m

    def mitig(self, kind):
        st = self.st
        if kind == "physical":
            red = dark = 0
            for h in self.h_armor_red: red += h()
            for h in self.h_armor_pen: dark += h()
            pen = 1 - (1 - st.armor_pen) * (1 - dark)
            return resist_mult(eff_resist(self.dummy.armor, red, pen, st.lethality))
        if kind == "magic":
            red = 0
            for h in self.h_mr_red: red += h()
            return resist_mult(eff_resist(self.dummy.mr, red, st.magic_pen_pct, st.magic_pen))
        return 1.0

    def deal(self, src, raw, kind, is_attack=False):
        if raw <= 0 or self.hp <= 0: return 0.0
        dmg = raw * self.mitig(kind) * self.amp(kind, is_attack)
        if self.duel: dmg = min(dmg, self.hp)
        self.hp -= dmg
        self.by_src[src] = self.by_src.get(src, 0) + dmg
        for h in self.h_dealt: h(kind, dmg)
        if self.duel:
            vamp = self.st.omnivamp
            for h in self.h_vamp: vamp += h()
            self.heal("Omnivamp", vamp * dmg)
            if is_attack: self.heal("Lifesteal", self.st.lifesteal * dmg)
            for h in self.h_dealt_heal: h(dmg)
        return dmg

    def heal(self, src, amount):
        kal = self.kal
        if not self.duel or amount <= 0 or kal.dead_at is not None or self.t < kal.revive_until: return
        amount *= (1 - GW_CUT) if kal.wounds else 1.0
        h = min(kal.max - kal.hp, amount)
        kal.hp += h
        if h > 0:
            kal.healed += h; kal.healed_by[src] = kal.healed_by.get(src, 0) + h
        over = amount - h
        if over > 0:
            for hk in self.h_overheal: hk(src, over)

    # ---------------------------------------------------------------- taking damage
    def take(self, src, raw, kind, is_attack=False):
        """Enemy damage to Kalista."""
        kal, e = self.kal, self.enemy
        if kal.dead_at is not None or self.t < kal.revive_until: return
        raw *= self.threat.dmg_mult
        if kind == "physical":
            dmg = raw * resist_mult(eff_resist(self.st.armor, 0, e.apen, 0))
            if is_attack:
                for h in self.h_taken_mult: dmg *= h()
        elif kind == "magic":
            dmg = raw * resist_mult(eff_resist(self.st.mr, 0, e.mpen[0], e.mpen[1]))
        else:
            dmg = raw
        e.dealt += dmg
        kal.taken_by[src] = kal.taken_by.get(src, 0) + dmg
        for h in self.h_take: dmg = h(kind, dmg)
        after = kal.hp - dmg              # lifeline shields trigger on damage that would drop below 30%
        for h in self.h_low: h(kind, after)
        self.apply_to_hp(dmg, kind)

    def apply_to_hp(self, dmg, kind):
        kal, t = self.kal, self.t
        for sh in kal.shields:
            if sh[2] < t or sh[1] <= 0: continue
            if sh[3] == "magic" and kind != "magic": continue
            a = min(sh[1], dmg); sh[1] -= a; dmg -= a
            kal.healed_by[sh[0]] = kal.healed_by.get(sh[0], 0) + a
        if dmg > 0 and kal.ichor > 0:
            a = min(kal.ichor, dmg); kal.ichor -= a; dmg -= a
        kal.taken += dmg
        kal.hp -= dmg
        if kal.hp <= 0:
            for h in self.h_lethal:
                if h(): return
            kal.hp = 0; kal.dead_at = t

    # ---------------------------------------------------------------- time
    def enemy_until(self, until):
        """Run enemy actions (and Death's Dance bleed) up to `until`."""
        if not self.duel: return
        saved = self.t
        self.enemy.run_until(self, until)
        kal = self.kal
        if kal.dead_at is None and kal.dd:                 # stored damage bleeds as true damage
            bleed = self.effects_dd_duration
            for d in kal.dd:
                start, amt = d
                due = amt * min(1.0, (until - start) / bleed)
                if due > 0:
                    d[1] -= due; d[0] = until
                    self.t = until
                    kal.taken_by["Death's Dance bleed"] = kal.taken_by.get("Death's Dance bleed", 0) + due
                    self.apply_to_hp(due, "true")
            kal.dd = [d for d in kal.dd if d[1] > 1e-6]
        self.t = saved

    effects_dd_duration = None   # set below from data

    def tick(self, now):
        """Advance enemy actions and timed effects to `now`."""
        self.enemy_until(now)
        saved = self.t
        for h in self.h_tick: h(now)
        self.t = saved

    def wait_for_control(self):
        """Kalista can't act while crowd-controlled or reviving."""
        if not self.duel: return
        kal = self.kal
        while True:
            free = max(kal.cc_until, kal.revive_until)
            if free <= self.t: return
            self.tick(free); self.t = free

    def try_finish(self):
        if self.hp <= 0: return True
        if self.duel and self.kal.dead_at is not None: return True
        for h in self.h_exec:
            if h(): return True
        return self.kit.finisher()

    def on_ability_cast(self):
        for h in self.h_cast: h()

    # ---------------------------------------------------------------- loop
    def attack(self):
        st = self.st
        extra = 0.0
        for h in self.h_as: extra += h()
        aspd = st.attack_speed(extra)
        self.attacks += 1
        hit = Hit(extra, self.cur_ad(), self.cur_bad(), self.cur_ap(), self.spellblade)
        self.spellblade = False
        for h in self.h_attack: h(hit)                     # Phantom Hit, spellblade
        for _ in range(hit.times):
            ph = mg = 0.0
            for h in self.h_on_hit:
                a, b = h(hit); ph += a; mg += b
            hit.ph += ph; hit.mg += mg
        self.kit.on_hits(hit.times)
        for h in self.h_bonus: h(hit)                      # Kraken, Energized
        for h in self.h_rune: h(hit)                       # keystone procs
        self.deal("Auto attacks", hit.ad * self.kit.aa_ratio * self.crit_factor, "physical", True)
        self.deal("On-hit (physical)", hit.ph, "physical", True)
        self.deal("On-hit (magic)", hit.mg, "magic", True)
        self.deal(self.runes.keystone, hit.rune, "magic" if self.adaptive_magic else "physical")
        for h in self.h_after: h(hit)
        if self.trace: self.log.append((round(self.t, 2), round(self.hp), self.kit.counter(), round(self.kal.hp)))
        return aspd

    def run(self):
        opts = self.opts
        for h in self.h_start: h()
        limit = opts.window if opts.window > 0 else opts.max_time
        while self.t <= limit:
            self.tick(self.t); self.wait_for_control()
            if self.try_finish(): break
            if self.kit.before_attack(limit): break
            aspd = self.attack()
            if self.try_finish(): break
            nxt = self.t + 1 / aspd
            self.tick(min(nxt, limit)); self.t = nxt
            if self.try_finish(): break
        return self.window_result(limit) if opts.window > 0 else self.result()

    # ---------------------------------------------------------------- results
    def _rounded(self):
        kal = self.kal
        return {"taken_by": {k: round(v) for k, v in kal.taken_by.items()},
                "healed_by": {k: round(v) for k, v in kal.healed_by.items()},
                "dealt_by": {k: round(v) for k, v in self.by_src.items()}}

    def window_result(self, limit):
        kal, opts = self.kal, self.opts
        end = min(self.t, limit)
        exit_burst = 0.0
        if opts.exit_e and self.hp > 0 and (not self.duel or kal.dead_at is None):
            exit_burst = self.kit.exit_burst(limit)
        killed = self.hp <= 0
        return {"killed": killed, "kill_time": end if killed else None,
                "died": self.duel and kal.dead_at is not None,
                "dealt_frac": (self.hp0 - max(self.hp, 0)) / self.dummy.hp,
                # damage still stored in Death's Dance lands after the trade, so it counts
                "taken_frac": ((self.st.hp * opts.kal_start - kal.hp + sum(d[1] for d in kal.dd)) / kal.max) if self.duel else 0.0,
                "exit_rend": exit_burst, "spears": self.kit.counter(), **self._rounded()}

    def result(self):
        kal, t, hp, dummy = self.kal, self.t, self.hp, self.dummy
        killed = hp <= 0
        if not self.duel:
            ttk = t if killed else math.inf
            return {"ttk": ttk, "dps": dummy.hp / ttk if ttk < math.inf else 0,
                    "attacks": self.attacks, "spears": self.kit.counter(), "by_source": self.by_src, "trace": self.log}
        died = kal.dead_at is not None
        k_eff = kal.hp + kal.ichor + sum(sh[1] for sh in kal.shields if sh[2] >= t)
        if killed:
            tk = t
            net = (kal.taken - kal.healed) / max(tk, 1e-6)      # HP lost per second, net of healing
            td = tk + (k_eff / net if net > 1e-6 else math.inf)
            if kal.ga: td += 4 + 0.5 * self.st.base_hp / max(net, 1e-6)  # unused Guardian Angel
        elif died:
            td = kal.dead_at
            dealt = dummy.hp - hp
            rate = dealt / max(td, 1e-6)
            tk = td + (hp / rate if rate > 1e-6 else math.inf)
        else:                                                       # timeout: estimate both
            dealt = dummy.hp - hp
            tk = t + hp / max(dealt / max(t, 1e-6), 1e-6)
            net = (kal.taken - kal.healed) / max(t, 1e-6)
            td = t + (k_eff / net if net > 1e-6 else math.inf)
        margin = min(self.opts.margin_cap, td / tk) if tk > 0 else self.opts.margin_cap
        return {"win": killed and not died, "tk": tk, "td": td, "margin": margin,
                "kal_hp_left": min(1.0, max(0.0, k_eff / kal.max)) if killed else 0.0,
                "enemy_hp_left": max(0.0, hp / dummy.hp),
                **self._rounded(),
                "ga_used": "3026" in self.has and not kal.ga,
                "trace": self.log}


from params import ITEM as _ITEM
Fight.effects_dd_duration = _ITEM["6333"]["bleed_duration"]


def simulate(item_ids, level, dummy, runes=None, opts=None, threat=None, enemy_items=0, trace=False,
             champ="Kalista"):
    """Fight `dummy`. With `threat`, the dummy fights back (two-way duel).

    Returns kill time, (duel) death time, margin = death time / kill time,
    HP left on both sides, and damage / healing breakdowns."""
    return Fight(item_ids, level, dummy, runes, opts, threat, enemy_items, trace, champ).run()
