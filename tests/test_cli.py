"""Command-line parsing and quick end-to-end runs."""
import json, os, subprocess, sys

import pytest

from lolsim import cli
from lolsim.config import Config
from tests.conftest import ROOT

KALISTA = [sys.executable, os.path.join(ROOT, "kalista")]


def test_find_item():
    assert cli.find_item("ie") == "3031"
    assert cli.find_item("BotRK") == "3153"
    assert cli.find_item("3153") == "3153"
    assert cli.find_item("dusk and dawn") == "2510"
    with pytest.raises(SystemExit):
        cli.find_item("nonsense item")


def parse(args):
    ap = cli.argparse.ArgumentParser()
    cli.add_scenario(ap)
    return cli.config_from(ap.parse_args(args))


def test_scenario_flags_build_a_config():
    cfg = parse(["--threat", "bruiser,tank", "--kite", "0.8", "--weights", "0.2,0.2,0.2,0.2,0.2",
                 "--quick-windows", "1.5,2", "--lane-weights", "0.5,0.5,0", "--jobs", "1"])
    assert cfg.threats == ("bruiser", "tank") and cfg.kite_uptime == 0.8
    assert cfg.weights == {1: 0.2, 2: 0.2, 3: 0.2, 4: 0.2, 5: 0.2}
    assert cfg.quick_windows == (1.5, 2.0)
    assert cfg.lane_weights == {"quick": 0.5, "long": 0.5, "pressure": 0.0}
    assert set(cfg.changed()) == {"threats", "kite_uptime", "weights", "quick_windows", "lane_weights"}


def test_defaults_are_unchanged():
    assert parse(["--jobs", "1"]).changed() == {}
    assert Config().kite_uptime == 0.65


def test_bad_threat_is_rejected():
    with pytest.raises(SystemExit):
        parse(["--threat", "dragon"])


def test_build_command_runs():
    out = subprocess.run(KALISTA + ["build", "yuntal", "ie", "zerks", "--level", "11"],
                         capture_output=True, text=True, check=True).stdout
    assert "Yun Tal Wildarrows" in out and "bruiser" in out and "quick" in out


def test_optimize_json_with_fixed_runes():
    out = subprocess.run(KALISTA + ["optimize", "--goal", "kill", "--runes", "Lethal Tempo / Alacrity / Cut Down",
                                    "--threat", "tank", "--beam-width", "2", "--jobs", "2", "--json"],
                         capture_output=True, text=True, check=True).stdout
    r = json.loads(out)
    assert r["page"] == "Lethal Tempo / Alacrity / Cut Down" and len(r["path"]) == 5
    assert set(r["path"][0]["per"]) == {"tank"}
