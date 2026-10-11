"""Rune pages: Precision keystone, Legend rune, combat rune (data/wiki/runes.json)."""
from dataclasses import dataclass, replace

from params import RUNE

KEYSTONES = ["Press the Attack", "Lethal Tempo", "Conqueror", "Fleet Footwork"]
LEGENDS = ["Alacrity", "Bloodline"]
COMBAT = ["Coup de Grace", "Cut Down", "Last Stand"]


@dataclass
class RunePage:
    keystone: str = "Lethal Tempo"
    legend: str = "Alacrity"          # "Alacrity" / "Bloodline"
    legend_stacks: int = 10           # 0-10 on this scale (Bloodline maps to 0-15)
    combat: str = "Coup de Grace"     # "Coup de Grace" / "Cut Down" / "Last Stand"

    def alacrity_as(self):
        a = RUNE["Alacrity"]
        return (a["base_as"] + a["as_per_stack"] * self.legend_stacks) if self.legend == "Alacrity" else 0.0
    def _bl(self):
        m = RUNE["Bloodline"]["max_stacks"]
        return min(m, round(self.legend_stacks * m / 10))
    def bloodline_ls(self):
        return RUNE["Bloodline"]["lifesteal_per_stack"] * self._bl() if self.legend == "Bloodline" else 0.0
    def bloodline_hp(self):
        b = RUNE["Bloodline"]
        return b["full_hp"] if self.legend == "Bloodline" and self._bl() >= b["max_stacks"] else 0
    def label(self):
        return f"{self.keystone} / {self.legend} / {self.combat}"
    def at(self, stacks):
        return replace(self, legend_stacks=stacks)

    @classmethod
    def parse(cls, label, stacks=10):
        """'Press the Attack / Alacrity / Cut Down' -> RunePage."""
        ks, lg, cb = [p.strip() for p in label.split("/")]
        for v, ok in ((ks, KEYSTONES), (lg, LEGENDS), (cb, COMBAT)):
            if v not in ok: raise ValueError(f"unknown rune {v!r}; expected one of {ok}")
        return cls(ks, lg, stacks, cb)
