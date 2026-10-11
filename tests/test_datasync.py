"""Offline checks of the data-update parsers (no network)."""
from lolsim.datasync import item_changes, parse_champion_module, stat_mismatches

LUA = '''return {
  ["Kalista"] = {
    ["id"]         = 429,
    ["apiname"]    = "Kalista",
    ["stats"] = {
      ["hp_base"]  = 560,
      ["hp_lvl"]   = 114,
      ["dam_base"] = 57,
      ["dam_lvl"]  = 4.75,
      ["as_base"]  = 0.694,
    },
  },
  ["Gnar"] = {
    ["apiname"]    = "Gnar",
    ["stats"] = {
      ["dam_lvl"]  = 3.2,
      ["mega"] = {
      	["dam_lvl"] = 9.9,
      },
    },
  },
}'''


def test_parse_champion_module():
    out = parse_champion_module(LUA)
    assert out["Kalista"] == {"hp_base": 560, "hp_lvl": 114, "dam_base": 57, "dam_lvl": 4.75, "as_base": 0.694}
    assert out["Gnar"]["dam_lvl"] == 3.2          # nested alternate forms are skipped


def test_item_changes():
    old = {"1": {"name": "A", "description": "x", "stats": {"s": 1}, "gold": {"total": 100}},
           "2": {"name": "B", "description": "y", "stats": {}, "gold": {"total": 50}}}
    new = {"1": {"name": "A", "description": "x2", "stats": {"s": 2}, "gold": {"total": 120}}}
    rows = item_changes(old, new, {"1", "2"})
    assert rows == ["1 A: description changed", "1 A: stats {'s': 1} -> {'s': 2}", "1 A: cost 100 -> 120",
                    "2 B: removed"]


def test_stat_mismatches():
    champs = {"Kalista": {"stats": {"hp": 560, "hpperlevel": 114, "attackdamage": 57, "attackspeed": 0.694}}}
    assert stat_mismatches(parse_champion_module(LUA), champs) == []
    champs["Kalista"]["stats"]["hp"] = 600
    assert stat_mismatches(parse_champion_module(LUA), champs) == ["Kalista: hp Data Dragon 600 vs wiki 560"]
