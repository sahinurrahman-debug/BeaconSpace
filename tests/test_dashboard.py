"""Dashboard behaviour tests (Streamlit AppTest): navbar pages, empty state, results view, run -> results hand-off, error message."""
import importlib
import os
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest  # noqa: E402

SRC = ROOT / "outputs" / "trishuli"
pytestmark = pytest.mark.skipif(not (SRC / "summary.json").exists(), reason="needs a finished run in outputs/trishuli")


def _app(out: Path, start="overview"):
    os.environ["FLOODSYS_OUT"] = str(out)
    os.environ["BEACONSPACE_START"] = start
    from floodsys import config
    importlib.reload(config)
    return AppTest.from_file(str(ROOT / "app" / "dashboard.py"), default_timeout=90)


def _text(at):
    return " ".join(m.value for m in at.markdown)


def _copy_run(tmp_path, name="trishuli"):
    shutil.copytree(SRC, tmp_path / name, ignore=shutil.ignore_patterns("*.tif"))


def test_empty_state_when_no_runs(tmp_path):
    at = _app(tmp_path).run()
    assert not at.exception
    assert "No analysis yet" in _text(at)


def test_overview_shows_cards_map_and_twin_lists(tmp_path):
    _copy_run(tmp_path)
    at = _app(tmp_path).run()
    assert not at.exception
    t = _text(at)
    assert "Flooded / debris" in t and "Buildings affected" in t and "Cut off" in t
    assert "Critical · cut off" in t and "Watch · longer route" in t          # symmetric twin panels
    assert "BeaconSpace" in t


@pytest.mark.parametrize("page,needle", [("settlements", "Road access to the nearest hospital"), ("report", "Situation report"),
                                         ("method", "Method &amp; data"), ("ems", "Check vs EMSR927")])
def test_each_navbar_page_renders(tmp_path, page, needle):
    _copy_run(tmp_path)
    at = _app(tmp_path, start=page).run()          # BEACONSPACE_START picks the landing page (callable pages can't be switched in AppTest)
    assert not at.exception, at.exception
    assert needle.replace("&amp;", "&") in _text(at).replace("&amp;", "&")


def test_run_hands_over_to_overview(tmp_path, monkeypatch):
    _copy_run(tmp_path)
    import floodsys.pipeline as pl

    def fake_run(cfg, log=print):
        for m in ("[run] AOI", "[s2] cache hit", "[s1] reading post", "[run] areas", "[osm] roads", "[run] damage", "[access] graph", "[sitrep] wrote"):
            log(m)
        dst = tmp_path / "fresh_run"
        shutil.copytree(tmp_path / "trishuli", dst)
        return {"out": dst}

    monkeypatch.setattr(pl, "run", fake_run)
    at = _app(tmp_path, start="new").run()
    assert "New analysis" in _text(at)
    at.button[0].click().run()
    assert not at.exception, at.exception
    assert at.session_state["sel_run"] == "fresh_run"
    assert "Flooded / debris" in _text(at)


def test_failure_shows_friendly_message(tmp_path, monkeypatch):
    import floodsys.pipeline as pl

    def boom(cfg, log=print):
        raise RuntimeError("No same-track Sentinel-1 pre/post pair covers this area and date.")

    monkeypatch.setattr(pl, "run", boom)
    at = _app(tmp_path, start="new").run()
    at.button[0].click().run()
    t = _text(at)
    assert "could not finish" in t and "same orbit track" in t
