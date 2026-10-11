"""Champion kits. A kit decides what the champion does between auto attacks (abilities),
what each on-hit adds, how it finishes a target and what it fires when a trade ends.

To add another marksman: subclass Kit, read its numbers from data/wiki/champions.json,
and register it in KITS. The fight loop, items and runes are shared."""
from params import CHAMP

_K = CHAMP["Kalista"]
RANKS_BY_LEVEL = {int(k): tuple(v) for k, v in _K["ranks_by_level"].items()}   # (Q, W, E); E max, Q second
AA_AD_RATIO = _K["aa_ad_ratio"]   # VERIFY
Q_BASE = _K["q_base"]; Q_RATIO = _K["q_ad_ratio"]; Q_CD = _K["q_cd"]; Q_CAST = _K["q_cast"]
E_FIRST = _K["e_first"]; E_FIRST_AD = _K["e_first_ad"]; E_FIRST_AP = _K["e_first_ap"]
E_ADD = _K["e_add"]; E_ADD_AD = _K["e_add_ad"]; E_ADD_AP = _K["e_add_ap"]


def rend_raw(ad, ap, rank, spears):
    if spears <= 0 or rank == 0: return 0.0
    r = rank - 1
    first = E_FIRST[r] + E_FIRST_AD * ad + E_FIRST_AP * ap
    each = E_ADD[r] + E_ADD_AD[r] * ad + E_ADD_AP * ap
    return first + (spears - 1) * each


class Kit:
    """Defaults: a champion that only auto attacks."""
    aa_ratio = 1.0

    def __init__(self, f):
        self.f = f

    def before_attack(self, limit):
        """Cast abilities before the next auto. Return True if the fight ended."""
        return False

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

    def counter(self):
        """A number for traces and results (Kalista: spears)."""
        return 0


class Kalista(Kit):
    """Pierce (Q) on cooldown; every on-hit adds a Rend spear; Rend (E) is held until it
    kills, or ripped when a trade ends."""
    aa_ratio = AA_AD_RATIO

    def __init__(self, f):
        super().__init__(f)
        self.qr, self.wr, self.er = RANKS_BY_LEVEL[f.level]
        self.spears = 0
        self.q_cd = 0.0

    def before_attack(self, limit):
        f = self.f
        if not (f.opts.use_q and self.qr and self.q_cd <= f.t): return False
        f.deal("Pierce (Q)", Q_BASE[self.qr - 1] + Q_RATIO * f.cur_ad(), "physical")
        self.spears += 1; self.q_cd = f.t + Q_CD
        f.on_ability_cast()
        if f.try_finish(): return True
        f.tick(min(f.t + Q_CAST, limit)); f.t += Q_CAST
        f.wait_for_control()
        return f.try_finish()

    def on_hits(self, n):
        self.spears += n

    def rend(self):
        return rend_raw(self.f.cur_ad(), self.f.cur_ap(), self.er, self.spears)

    def finisher(self):
        f = self.f
        if self.er and self.spears > 0:
            raw = self.rend()
            if raw * f.mitig("physical") * f.amp("physical") >= f.hp:
                f.deal("Rend (E)", raw, "physical"); return True
        return False

    def exit_burst(self, limit):
        if self.spears > 0 and self.er:
            self.f.t = limit
            return self.f.deal("Rend (E)", self.rend(), "physical")
        return 0.0

    def scale_cooldowns(self, mult):
        t = self.f.t
        if self.q_cd > t: self.q_cd = t + (self.q_cd - t) * mult

    def counter(self):
        return self.spears


KITS = {"Kalista": Kalista}
