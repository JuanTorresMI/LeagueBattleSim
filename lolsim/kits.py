"""Champion kits. A kit decides what the champion does between auto attacks (abilities),
what each on-hit adds, how it finishes a target and what it fires when a trade ends.

To add another marksman: subclass Kit, read its numbers from data/wiki/champions.json,
and register it in KITS. The fight loop, items and runes are shared."""
from params import CHAMP

_K = CHAMP["Kalista"]
RANKS_BY_LEVEL = {int(k): tuple(v) for k, v in _K["ranks_by_level"].items()}   # (Q, W, E); E max, Q second
AA_AD_RATIO = _K["aa_ad_ratio"]   # 100% since V13.11
Q_BASE = _K["q_base"]; Q_RATIO = _K["q_ad_ratio"]; Q_CD = _K["q_cd"]; Q_CAST = _K["q_cast"]
E_FIRST = _K["e_first"]; E_FIRST_AD = _K["e_first_ad"]; E_FIRST_AP = _K["e_first_ap"]
E_ADD = _K["e_add"]; E_ADD_AD = _K["e_add_ad"]; E_ADD_AP = _K["e_add_ap"]


def skill_ranks(level, start=("Q", "W", "E"), priority=("Q", "E", "W")):
    """(Q, W, E) ranks at a level: one point each in `start` order at levels 1-3, then
    points go to the first ability in `priority` that can still rank up (rank <= level / 2,
    max 5). Levels 6, 11 and 16 go to the ultimate."""
    ranks = {"Q": 0, "W": 0, "E": 0}
    for lv in range(1, level + 1):
        if lv in (6, 11, 16): continue
        if lv <= 3:
            ranks[start[lv - 1]] += 1; continue
        for k in priority:
            if ranks[k] < 5 and ranks[k] < (lv + 1) // 2:
                ranks[k] += 1; break
    return ranks["Q"], ranks["W"], ranks["E"]


def rend_raw(ad, ap, rank, spears):
    if spears <= 0 or rank == 0: return 0.0
    r = rank - 1
    first = E_FIRST[r] + E_FIRST_AD * ad + E_FIRST_AP * ap
    each = E_ADD[r] + E_ADD_AD[r] * ad + E_ADD_AP * ap
    return first + (spears - 1) * each


class Kit:
    """Defaults: a champion that only auto attacks."""
    aa_ratio = 1.0
    ability_sources = frozenset()     # damage source names that count as champion abilities

    def __init__(self, f):
        self.f = f

    def before_attack(self, limit):
        """Cast abilities before the next auto. Return True if the fight ended."""
        return False

    def on_attack(self, hit):
        """Change the auto attack being built (empowered attacks)."""

    def on_hits(self, n):
        """n on-hit applications landed this attack."""

    def finisher(self):
        """Finish the target if a held-back ability would kill. Return True if it did."""
        return False

    def exit_burst(self, limit):
        """Damage fired when a short trade ends (e.g. Rend on the way out)."""
        return 0.0

    def scale_cooldowns(self, mult):
        """Scale remaining basic-ability cooldowns (Navori)."""

    def on_secondary_hits(self, n):
        """On-hit landed on n secondary targets (multi-target option)."""

    def counter(self):
        """A number for traces and results (Kalista: spears)."""
        return 0


class Kalista(Kit):
    """Pierce (Q) on cooldown; every on-hit adds a Rend spear; Rend (E) is held until it
    kills, or ripped when a trade ends."""
    aa_ratio = AA_AD_RATIO
    ability_sources = frozenset({"Pierce (Q)", "Rend (E)"})

    def __init__(self, f):
        super().__init__(f)
        self.qr, self.wr, self.er = RANKS_BY_LEVEL[f.level]
        self.spears = 0
        self.q_cd = 0.0
        self.soul_ready = 0.0 if f.opts.soul_mark and self.wr else None
        self.sec_spears = 0                  # spears on each secondary target (multi-target option)

    def before_attack(self, limit):
        f = self.f
        if not (f.opts.use_q and self.qr and self.q_cd <= f.t): return False
        f.deal("Pierce (Q)", Q_BASE[self.qr - 1] + Q_RATIO * f.cur_ad(), "physical")
        self.spears += 1; self.q_cd = f.t + Q_CD
        self.soul_mark()
        f.on_ability_cast()
        if f.try_finish(): return True
        f.tick(min(f.t + Q_CAST, limit)); f.t += Q_CAST
        f.wait_for_control()
        return f.try_finish()

    def on_hits(self, n):
        self.spears += n
        self.soul_mark()

    def soul_mark(self):
        """Sentinel (W) passive: with the Oathsworn support also hitting the target, a hit
        consumes both Soul-Marks for % max health magic damage (10 s per target)."""
        f = self.f
        if self.soul_ready is not None and f.t >= self.soul_ready and f.hp > 0:
            f.deal("Soul-Marked (W)", _K["w_soul_pct"][self.wr - 1] * f.dummy.hp, "magic")
            self.soul_ready = f.t + _K["w_target_cd"]

    def rend(self):
        return rend_raw(self.f.cur_ad(), self.f.cur_ap(), self.er, self.spears)

    def on_secondary_hits(self, n):
        if self.f.n_sec: self.sec_spears += n / self.f.n_sec       # spread over the secondary targets

    def rend_secondaries(self):
        f = self.f
        if f.n_sec and self.sec_spears >= 1 and self.er:
            f.splash("Rend (E)", rend_raw(f.cur_ad(), f.cur_ap(), self.er, int(self.sec_spears)), "physical", f.n_sec)
            self.sec_spears = 0

    def finisher(self):
        f = self.f
        if self.er and self.spears > 0:
            raw = self.rend()
            if raw * f.mitig("physical") * f.amp("physical") >= f.hp:
                self.rend_secondaries()
                f.deal("Rend (E)", raw, "physical"); return True
        return False

    def exit_burst(self, limit):
        if self.spears > 0 and self.er:
            self.f.t = limit
            self.rend_secondaries()
            return self.f.deal("Rend (E)", self.rend(), "physical")
        return 0.0

    def scale_cooldowns(self, mult):
        t = self.f.t
        if self.q_cd > t: self.q_cd = t + (self.q_cd - t) * mult

    def counter(self):
        return self.spears


_V = CHAMP["Vayne"]


class Vayne(Kit):
    """Tumble (Q) on cooldown empowers the next auto; every third on-hit procs Silver Bolts
    (W) for % max health true damage. Example of a second marksman on the shared engine."""
    aa_ratio = _V["aa_ad_ratio"]
    ability_sources = frozenset()          # Tumble's bonus is basic-attack damage

    def __init__(self, f):
        super().__init__(f)
        self.qr, self.wr, self.er = skill_ranks(f.level, _V["skill_start"], _V["skill_max"])
        self.q_cd, self.empowered, self.bolts = 0.0, False, 0

    def before_attack(self, limit):
        f = self.f
        if self.qr and self.q_cd <= f.t and f.opts.use_q:
            self.empowered = True
            self.q_cd = f.t + _V["q_cd"][self.qr - 1]
            f.on_ability_cast(damaging=False)
        return False

    def on_attack(self, hit):
        if self.empowered:
            self.empowered = False
            hit.bonus.append(("Tumble (Q)", _V["q_ad_ratio"][self.qr - 1] * hit.ad + _V["q_ap_ratio"] * hit.ap, "physical"))

    def on_hits(self, n):
        if not self.wr: return
        f = self.f
        for _ in range(n):
            self.bolts += 1
            if self.bolts == _V["w_stacks"]:
                self.bolts = 0
                f.deal("Silver Bolts (W)", _V["w_max_hp"][self.wr - 1] * f.dummy.hp, "true")

    def scale_cooldowns(self, mult):
        t = self.f.t
        if self.q_cd > t: self.q_cd = t + (self.q_cd - t) * mult

    def counter(self):
        return self.bolts


KITS = {"Kalista": Kalista, "Vayne": Vayne}


def kit_for(champ):
    """The champion's kit, or a plain auto-attacker for champions without one."""
    return KITS.get(champ, Kit)
