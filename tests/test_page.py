"""The results page: template filled, main script parses, embedded engine works."""
import json, os, re, shutil, subprocess, sys

import pytest

import build_page
from lolsim.editor import evaluate_build
from tests.conftest import ROOT


@pytest.fixture(scope="module")
def html(spikes_json_mod, lane_json_mod):
    return build_page.render(spikes_json_mod, lane_json_mod)


@pytest.fixture(scope="module")
def spikes_json_mod():
    with open(os.path.join(ROOT, "spikes.json")) as f: return json.load(f)


@pytest.fixture(scope="module")
def lane_json_mod():
    with open(os.path.join(ROOT, "lane.json")) as f: return json.load(f)


def test_placeholders_filled(html):
    for ph in ("__DATA__", "__ENGINE__", "__EDITOR__", "__PATCH__"):
        assert ph not in html
    for sec in ('id="lane"', 'id="goals"', 'id="editor"', 'id="cross"'):
        assert sec in html


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_main_script_parses(html, tmp_path):
    script = re.findall(r"<script>(.*?)</script>", html, re.S)[-1]
    (tmp_path / "main.js").write_text(script)
    subprocess.run(["node", "--check", str(tmp_path / "main.js")], check=True)


def test_embedded_engine_runs_standalone(html, tmp_path, spikes_json_mod, lane_json_mod):
    """Write the page's engine bundle to a folder and run the editor there, as Pyodide does."""
    files = json.loads(re.search(r'<script type="application/json" id="engine-files">(.*?)</script>', html, re.S).group(1))
    for path, text in files.items():
        p = tmp_path / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    args = {"items": ["3032", "3031", "3036", "3006"], "level": 13, "page": "Press the Attack / Alacrity / Cut Down",
            "stacks": 7, "enemy_items": None,
            "duel_mults": {k: v["mult"] for k, v in spikes_json_mod["calibration"].items()},
            "lane_mults": {k: v["mult"] for k, v in lane_json_mod["calibration"].items()}, "kite": 0.65}
    code = ("import sys, json; sys.path.insert(0, '.'); from lolsim.editor import evaluate_build; "
            f"print(json.dumps(evaluate_build(**json.loads({json.dumps(json.dumps(args))}))))")
    out = subprocess.run([sys.executable, "-I", "-c", code], cwd=tmp_path, capture_output=True, text=True, check=True).stdout
    assert json.loads(out) == json.loads(json.dumps(evaluate_build(**args)))
    args.update(champion="Vayne", threats=["marksman", "Caitlyn", "Nautilus"], lane_threats={"Lux": "Lux"}, secondary=2)
    code = ("import sys, json; sys.path.insert(0, '.'); from lolsim.editor import evaluate_build; "
            f"print(json.dumps(evaluate_build(**json.loads({json.dumps(json.dumps(args))}))))")
    out = subprocess.run([sys.executable, "-I", "-c", code], cwd=tmp_path, capture_output=True, text=True, check=True).stdout
    assert json.loads(out) == json.loads(json.dumps(evaluate_build(**args)))


def test_editor_warnings():
    r = evaluate_build(["3036", "3033", "3006", "3047", "3031", "3031"], 13)
    assert any("Only one of" in w for w in r["warnings"])
    assert "Only one pair of boots." in r["warnings"]
    assert any("Duplicate" in w for w in r["warnings"])
