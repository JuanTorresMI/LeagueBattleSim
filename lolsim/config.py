"""Run configuration: defaults from config/*.json, overridable from the command line.

Scenario flags (threats, kiting share, trade windows, weights) change what is scored.
Calibration always uses config/calibration.json against the default scenario, so a flag
shows how results move relative to the same fair baseline."""
from dataclasses import dataclass, field, replace

from params import SCORING, CALIBRATION, THREAT_CFG

SP, LN, FT = SCORING["spikes"], SCORING["lane"], SCORING["fight"]


@dataclass
class Config:
    threats: tuple = tuple(THREAT_CFG["threats"])                      # full-fight enemies
    kite_uptime: float = FT["kite_uptime"]
    slots: tuple = tuple(tuple(s) for s in SP["slots"])
    weights: dict = field(default_factory=lambda: {int(k): v for k, v in SP["weights"].items()})
    legend: dict = field(default_factory=lambda: {int(k): v for k, v in SP["legend_stacks"].items()})
    kill_grid: tuple = tuple(SP["kill_hp_grid"])
    duel_grid: tuple = tuple(SP["duel_hp_grid"])
    td_cap: float = SP["td_cap"]
    beam_width: int = SP["beam_width"]
    kite_check: tuple = tuple(SP["kite_check"])
    early_rune_levels: tuple = tuple(SP["early_rune_levels"])
    lane_threats: dict = field(default_factory=lambda: dict(LN["threats"]))
    quick_windows: tuple = tuple(LN["quick_windows"])
    long_windows: tuple = tuple(LN["long_windows"])
    lane_stages: tuple = tuple(tuple(s) for s in LN["stages"])
    lane_weights: dict = field(default_factory=lambda: dict(LN["weights"]))
    execute: dict = field(default_factory=lambda: dict(LN["execute"]))
    pressure: dict = field(default_factory=lambda: dict(LN["pressure"]))
    gunblade_share: float = LN["gunblade_trade_share"]
    duel_cal: dict = field(default_factory=lambda: dict(CALIBRATION["duel"]))
    lane_cal: dict = field(default_factory=lambda: dict(CALIBRATION["lane"]))
    jobs: int = 1                                                     # worker processes

    def with_(self, **kw):
        return replace(self, **{k: v for k, v in kw.items() if v is not None})

    def changed(self):
        """Fields that differ from the defaults (for reports)."""
        d = Config()
        return {k: getattr(self, k) for k in self.__dataclass_fields__
                if k != "jobs" and getattr(self, k) != getattr(d, k)}
