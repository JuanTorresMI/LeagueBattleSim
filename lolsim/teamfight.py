"""Team fights: Kalista (the full engine) with allies against an enemy team.

Every other unit, on both teams, is a class profile or a real kit acting on its own event
queue (enemies.Enemy). All units follow the same targeting rules (config/teamfight.json).
Kalista hits one target at a time; when it dies she moves on and her per-target state
(spears, Black Cleaver, Giant Slayer, Press the Attack stacks) resets while her own buffs
(Guinsoo's, Lethal Tempo, Conqueror) carry over. Runaan's bolts, Statikk's chain and Rend
on their spears land on the other enemies. When Kalista dies or kills the last enemy the
remaining units fight it out.

Limits: no positioning (the kiting share stands in for it), no ultimates or summoners for
the units, crowd control from abilities only."""
import heapq, json, os
from dataclasses import replace

from params import HERE
from .enemies import ALL_THREATS, Enemy, make_dummy
from .fight import Fight, Opts
from .stats import resist_mult, eff_resist

with open(os.path.join(HERE, "config", "teamfight.json"), encoding="utf-8") as _f:
    TF = json.load(_f)
SCENARIOS = TF["scenarios"]
KAL = "Kalista"


class UnitState:
    """The defensive state Enemy.step reads on a target (and on itself, for stuns)."""
    def __init__(self):
        self.dead_at, self.revive_until, self.cc_until, self.cc_at = None, -1.0, 0.0, -1.0


class _NoTenacity:
    tenacity = 0.0


class Unit:
    def __init__(self, side, key, level, n_items, mult, kite, uid):
        self.side, self.key, self.uid = side, key, uid
        self.role = TF["roles"].get(key, "carry")
        self.dummy = make_dummy(key, level, n_items)
        self.hp = self.max = self.dummy.hp
        self.state = UnitState()
        self.actor = Enemy(replace(ALL_THREATS[key], dmg_mult=mult), level, n_items, kite)
        self.actor.state = self.state
        delay = TF.get("engage_delay", {}).get(self.role, 0.0)
        if delay:
            self.actor.queue = [(t + delay, p, i) for t, p, i in self.actor.queue]
            heapq.heapify(self.actor.queue)
        self.target = None
        self.dealt = 0.0
        self.name = f"{'ally' if side == 'ally' else 'enemy'} {ALL_THREATS[key].name.lower()}"

    @property
    def alive(self): return self.state.dead_at is None


class View:
    """The fight as one unit sees it when it acts (the interface Enemy.step expects)."""
    def __init__(self, tf, unit):
        self.tf, self.u = tf, unit

    @property
    def t(self): return self.tf.t
    @t.setter
    def t(self, v): self.tf.t = v
    @property
    def hp(self): return 1.0 if self.u.alive else 0.0
    @property
    def kal(self): return self.tf.kal if self.u.target == KAL else self.u.target.state
    @property
    def st(self): return self.tf.st if self.u.target == KAL else _NoTenacity

    def take(self, src, raw, kind, is_attack=False, attacker=None):
        tf, tgt = self.tf, self.u.target
        if tgt == KAL:
            before = tf.kal.taken + sum(d[1] for d in tf.kal.dd)
            tf.take(f"{self.u.name}: {src}", raw, kind, is_attack, attacker)
            self.u.dealt += tf.kal.taken + sum(d[1] for d in tf.kal.dd) - before
        else:
            tf.unit_take(tgt, raw, kind, attacker, self.u)


class TeamFight(Fight):
    def __init__(self, item_ids, level, runes, scenario, ne, mults, kite=None, targeting="front",
                 opts=None, champ="Kalista", mirror=False):
        """mirror=True: a marksman profile stands in for Kalista (the even baseline)."""
        sc = SCENARIOS[scenario] if isinstance(scenario, str) else scenario
        opts = opts or Opts()
        kite = opts.kite_uptime if kite is None else kite
        self.mirror = mirror
        self.units, uid = [], 0
        allies = ([{"key": "marksman"}] if mirror else []) + sc["allies"]
        for side, members in (("ally", allies), ("enemy", sc["enemies"])):
            for m in members:
                n = ne * (TF["support_item_factor"] if m.get("support") else 1)
                self.units.append(Unit(side, m["key"], level, n, mults.get(m["key"], 1.0), kite, uid)); uid += 1
        self.k_order = TF["kalista_targeting"][targeting] if isinstance(targeting, str) else targeting
        self.views = {u.uid: View(self, u) for u in self.units}
        self.kills, self.log_events = {}, []
        self.target = None
        first = self._kalista_pick()
        super().__init__(item_ids, level, first.dummy, runes, replace(opts, max_time=TF["max_time"]),
                         first.actor.threat, ne, champ=champ)
        self.target = first
        self.kal.wounds = any(u.actor.wounds for u in self.enemies())
        self._update_secondaries()
        if mirror:
            self.kal.dead_at, self.kal.hp = -1.0, 0.0             # Kalista sits out

    # ---------------------------------------------------------------- units
    def enemies(self): return [u for u in self.units if u.side == "enemy" and u.alive]
    def allies(self): return [u for u in self.units if u.side == "ally" and u.alive]

    def unit_hp(self, u):
        return self.hp if u is self.target else u.hp

    def _kalista_pick(self):
        pool = self.enemies()
        if not pool: return None
        rank = {r: i for i, r in enumerate(self.k_order)}
        return min(pool, key=lambda u: (rank.get(u.role, 9), u.uid))

    def _pick(self, u):
        """Target for a unit by its role's preference list ('carry' includes Kalista)."""
        foes_side = "enemy" if u.side == "ally" else "ally"
        foes = [x for x in self.units if x.side == foes_side and x.alive]
        if foes_side == "ally" and self.kal.dead_at is None:
            foes = foes + [KAL]
        if not foes: return None
        rank = {r: i for i, r in enumerate(TF["targets"].get(u.role, TF["targets"]["carry"]))}
        return min(foes, key=lambda x: (rank.get("carry" if x == KAL else x.role, 9), -1 if x == KAL else x.uid))

    def _update_secondaries(self):
        self.n_sec = max(0, len(self.enemies()) - 1)

    def damage_unit(self, u, dmg, by):
        if dmg <= 0 or not u.alive: return
        if u is self.target:
            self.hp -= dmg
            if self.hp <= 0: self.kills[u.uid] = by
        else:
            u.hp -= dmg
            if u.hp <= 0: self._kill(u, by)

    def _kill(self, u, by):
        if not u.alive: return
        u.hp = 0
        u.state.dead_at = self.t
        self.kills.setdefault(u.uid, by)
        self.log_events.append((round(self.t, 2), f"{u.name} dies ({self.kills[u.uid]})"))
        for x in self.units:
            if x.target is u: x.target = None
        self._update_secondaries()

    def unit_take(self, tgt, raw, kind, attacker, by_unit):
        raw *= attacker.threat.dmg_mult
        if kind == "physical": dmg = raw * resist_mult(eff_resist(tgt.dummy.armor, 0, attacker.apen, 0))
        elif kind == "magic": dmg = raw * resist_mult(eff_resist(tgt.dummy.mr, 0, attacker.mpen[0], attacker.mpen[1]))
        else: dmg = raw
        dmg = min(dmg, max(self.unit_hp(tgt), 0))
        by_unit.dealt += dmg
        self.damage_unit(tgt, dmg, by_unit.name)

    # ---------------------------------------------------------------- Kalista's side
    def deal(self, src, raw, kind, is_attack=False):
        dmg = super().deal(src, raw, kind, is_attack)
        if self.target is not None and self.hp <= 0: self.kills.setdefault(self.target.uid, KAL)
        return dmg

    def splash(self, src, raw, kind, targets=1):
        """Multi-target damage lands on the other living enemies."""
        if raw <= 0 or targets <= 0: return
        st = self.st
        for u in [x for x in self.enemies() if x is not self.target][:targets]:
            if kind == "physical": m = resist_mult(eff_resist(u.dummy.armor, 0, st.armor_pen, st.lethality))
            elif kind == "magic": m = resist_mult(eff_resist(u.dummy.mr, 0, st.magic_pen_pct, st.magic_pen))
            else: m = 1.0
            dmg = min(raw * m, max(u.hp, 0))
            self.splash_by[src] = self.splash_by.get(src, 0) + dmg
            self.damage_unit(u, dmg, KAL)

    def try_finish(self):
        while True:
            if self.kal.dead_at is not None: return True
            if self.hp <= 0:
                self._kill(self.target, self.kills.get(self.target.uid, KAL))
                nxt = self._kalista_pick()
                if nxt is None: return True
                self.target = nxt
                self.switch_target(nxt.dummy, nxt.hp)
                continue
            if not Fight.try_finish(self): return False
            if self.kal.dead_at is not None: return True

    def run_enemies(self, until):
        """Every unit's actions up to `until`, in time order."""
        while True:
            # a unit killed at time t still finishes what it does at t, so simultaneous hits trade
            live = [u for u in self.units if u.alive or u.state.dead_at >= u.actor.next_time()]
            if not live: return
            u = min(live, key=lambda x: (x.actor.next_time(), x.uid))
            if u.actor.next_time() > until: return
            if u.target is None or (u.target == KAL and self.kal.dead_at is not None) or \
               (u.target != KAL and not u.target.alive):
                u.target = self._pick(u)
            if u.target is None: return
            u.actor.step(self.views[u.uid], until, vs_kalista=u.target == KAL)
            if self.target is not None and self.target.alive and self.hp <= 0:
                pass                                   # Kalista's loop handles her target's death

    # ---------------------------------------------------------------- whole fight
    def run_all(self):
        if not self.mirror: self.run()
        if self.target is not None and self.target.alive:
            self.target.hp = self.hp                   # hand the target's HP back to the unit
            if self.hp <= 0: self._kill(self.target, self.kills.get(self.target.uid, KAL))
        self.target = None
        if self.kal.dead_at is not None and not self.mirror:
            self.log_events.append((round(self.kal.dead_at, 2), "Kalista dies"))
        while self.t < TF["max_time"] and self.enemies() and (self.allies() or self.kal.dead_at is None):
            nxt = self.t + 0.25
            self.enemy_until(nxt); self.t = nxt
        return self.summary()

    def summary(self):
        kal_alive = self.kal.dead_at is None
        allies, enemies = [u for u in self.units if u.side == "ally"], [u for u in self.units if u.side == "enemy"]
        n_allies = len(allies) + (0 if self.mirror else 1)
        a_hp = (sum(max(u.hp, 0) / u.max for u in allies) + (max(self.kal.hp, 0) / self.kal.max if kal_alive else 0)) / n_allies
        e_hp = sum(max(u.hp, 0) / u.max for u in enemies) / len(enemies)
        a_alive = kal_alive or any(u.alive for u in allies)
        e_alive = any(u.alive for u in enemies)
        win = a_alive and not e_alive
        score = a_hp if win else (-e_hp if not a_alive else a_hp - e_hp)
        k_dealt = sum(self.by_src.values()) + sum(self.splash_by.values())
        team_dealt = k_dealt + sum(u.dealt for u in allies)
        return {"win": win, "score": round(score, 4), "time": round(self.t, 2),
                "ally_hp": round(a_hp, 3), "enemy_hp": round(e_hp, 3),
                "kalista": {"alive": kal_alive, "died_at": None if kal_alive else round(self.kal.dead_at, 2),
                            "dealt": round(k_dealt), "share": round(k_dealt / team_dealt, 3) if team_dealt else 0.0,
                            "kills": sum(1 for v in self.kills.values() if v == KAL),
                            "dealt_by": {k: round(v) for k, v in self.by_src.items()},
                            "splash_by": {k: round(v) for k, v in self.splash_by.items()},
                            "taken": round(self.kal.taken)},
                "events": self.log_events}


def teamfight(items, level, runes, scenario, ne, mults, kite=None, targeting="front", opts=None, champ="Kalista"):
    return TeamFight(items, level, runes, scenario, ne, mults, kite, targeting, opts, champ).run_all()


def mirror_baseline(level, scenario, ne, mults, kite=0.65, targeting="front"):
    """The same fight with a marksman profile in Kalista's place: about even by design."""
    from .runes import RunePage
    return TeamFight([], level, RunePage(), scenario, ne, mults, kite, targeting, mirror=True).run_all()
