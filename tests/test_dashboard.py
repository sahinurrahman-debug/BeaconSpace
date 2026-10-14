"""Dashboard behaviour tests (Streamlit AppTest): empty state, results view, and the run -> results hand-off (pipeline stubbed)."""
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


def _app(out: Path):
    os.environ["FLOODSYS_OUT"] = str(out)
    import importlib
    from floodsys import config
    importlib.reload(config)
    return AppTest.from_file(str(ROOT / "app" / "dashboard.py"), default_timeout=90)


def _text(at):
    return " ".join(m.value for m in at.markdown)


def test_empty_state_when_no_runs(tmp_path):
    at = _app(tmp_path).run()
    assert not at.exception
    assert "Ready when you are" in _text(at)


def test_finished_run_shows_cards_and_tabs(tmp_path):
    shutil.copytree(SRC, tmp_path / "trishuli", ignore=shutil.ignore_patterns("*.tif"))
    at = _app(tmp_path).run()
    assert not at.exception
    t = _text(at)
    assert "Flooded or debris-covered" in t and "Buildings affected" in t and "Cut off" in t
    assert len(at.tabs) == 5


def test_run_hands_over_to_results(tmp_path, monkeypatch):
    shutil.copytree(SRC, tmp_path / "trishuli", ignore=shutil.ignore_patterns("*.tif"))
    import floodsys.pipeline as pl

    def fake_run(cfg, log=print):
        for m in ("[run] AOI", "[s2] cache hit", "[s1] reading post", "[run] areas", "[osm] roads", "[run] damage", "[access] graph", "[sitrep] wrote"):
            log(m)
        dst = tmp_path / "fresh_run"
        shutil.copytree(tmp_path / "trishuli", dst)
        return {"out": dst}

    monkeypatch.setattr(pl, "run", fake_run)
    at = _app(tmp_path).run()
    at.radio(key="mode").set_value("New analysis").run()
    at.button[0].click().run()
    assert not at.exception, at.exception
    assert at.session_state["mode"] == "Finished runs"
    assert at.session_state["sel_run"] == "fresh_run"
    assert "Flooded or debris-covered" in _text(at)


def test_failure_shows_friendly_message(tmp_path, monkeypatch):
    import floodsys.pipeline as pl

    def boom(cfg, log=print):
        raise RuntimeError("No same-track Sentinel-1 pre/post pair covers this area and date.")

    monkeypatch.setattr(pl, "run", boom)
    at = _app(tmp_path).run()
    at.button[0].click().run()
    t = _text(at)
    assert "could not finish" in t and "same orbit track" in t
