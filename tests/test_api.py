"""Web server tests (FastAPI TestClient): run listing, payloads, map theming, files, CSV, analysis job hand-off and friendly errors."""
import importlib
import shutil
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

SRC = ROOT / "outputs" / "trishuli"
needs_run = pytest.mark.skipif(not (SRC / "summary.json").exists(), reason="needs a finished run in outputs/trishuli")


def _client(out: Path, monkeypatch):
    monkeypatch.setenv("FLOODSYS_OUT", str(out))
    from floodsys import config
    importlib.reload(config)
    import app.server as server
    importlib.reload(server)
    return TestClient(server.app), server


def _copy_run(tmp_path, name="trishuli"):
    shutil.copytree(SRC, tmp_path / name, ignore=shutil.ignore_patterns("*.tif"))


def test_empty_when_no_runs(tmp_path, monkeypatch):
    c, _ = _client(tmp_path, monkeypatch)
    assert c.get("/api/runs").json() == []
    assert c.get("/api/runs/nothing").status_code == 404
    assert c.get("/api/health").json()["ok"] is True


def test_rejects_path_tricks(tmp_path, monkeypatch):
    c, _ = _client(tmp_path, monkeypatch)
    assert c.get("/api/runs/..%2f..%2fetc/map").status_code == 404
    assert c.get("/api/runs/x/image/..%2fsecret.png").status_code == 404


@needs_run
def test_run_payload_has_everything_the_pages_need(tmp_path, monkeypatch):
    _copy_run(tmp_path)
    c, _ = _client(tmp_path, monkeypatch)
    runs = c.get("/api/runs").json()
    assert runs[0]["name"] == "trishuli" and "Trishuli" in runs[0]["title"]
    d = c.get("/api/runs/trishuli").json()
    F, S = d["facts"], d["summary"]
    assert F["n_cut"] >= 0 and F["b_aff"] >= 0 and F["impact_ha"] > 0
    assert len(S["s1_pairs"]) >= 1 and S["settlements"] and "status" in S["settlements"][0]
    assert d["files"]["map"] and d["files"]["sitrep"]
    assert d["attribution"] and "OpenStreetMap" in " ".join(d["attribution"])
    assert d["provenance"] and d["provenance"].get("forbidden_inputs_used") == []


@needs_run
def test_map_is_themed_inside_the_iframe(tmp_path, monkeypatch):
    _copy_run(tmp_path)
    c, _ = _client(tmp_path, monkeypatch)
    dark = c.get("/api/runs/trishuli/map?theme=dark").text
    light = c.get("/api/runs/trishuli/map?theme=light").text
    assert "var K=false" in dark and "var K=true" in light and "Loading map" in dark
    assert "var K=null" in c.get("/api/runs/trishuli/map").text            # no theme -> follow the system preference


@needs_run
def test_report_and_csv_downloads(tmp_path, monkeypatch):
    _copy_run(tmp_path)
    c, _ = _client(tmp_path, monkeypatch)
    r = c.get("/api/runs/trishuli/sitrep?download=true")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    csv = c.get("/api/runs/trishuli/settlements.csv?status=cut_off&q=").text.splitlines()
    assert csv[0].startswith("name") or "status" in csv[0]
    assert len(csv) > 1 and all("cut_off" in ln for ln in csv[1:])


@needs_run
def test_analysis_job_runs_and_hands_over(tmp_path, monkeypatch):
    _copy_run(tmp_path)
    c, server = _client(tmp_path, monkeypatch)
    import floodsys.pipeline as pl

    def fake_run(cfg, log=print):
        for m in ("[run] AOI", "[s2] cache hit", "[s1] reading post", "[run] areas", "[osm] roads", "[run] damage", "[access] graph", "[sitrep] wrote"):
            log(m)
        dst = tmp_path / "fresh_run"
        shutil.copytree(tmp_path / "trishuli", dst)
        return {"out": dst}

    monkeypatch.setattr(pl, "run", fake_run)
    body = {"key": "trishuli", "bbox": [84.93, 27.78, 85.48, 28.32], "date": "2026-08-25", "time": "22:00", "res": 20, "pairs": 2}
    jid = c.post("/api/analyze", json=body).json()["id"]
    for _ in range(50):
        j = c.get(f"/api/jobs/{jid}").json()
        if j["status"] != "running":
            break
        time.sleep(0.1)
    assert j["status"] == "done" and j["run"] == "fresh_run" and j["step"] >= 6
    assert {r["name"] for r in c.get("/api/runs").json()} >= {"trishuli", "fresh_run"}


def test_failure_is_reported_with_a_hint(tmp_path, monkeypatch):
    c, _ = _client(tmp_path, monkeypatch)
    import floodsys.pipeline as pl

    def boom(cfg, log=print):
        raise RuntimeError("No same-track Sentinel-1 pre/post pair covers this area and date.")

    monkeypatch.setattr(pl, "run", boom)
    jid = c.post("/api/analyze", json={"bbox": [85.3, 28.1, 85.45, 28.25], "date": "2026-08-25"}).json()["id"]
    for _ in range(50):
        j = c.get(f"/api/jobs/{jid}").json()
        if j["status"] != "running":
            break
        time.sleep(0.1)
    assert j["status"] == "error" and j["hint"] == "same-track" and "same-track" in j["error"]


def test_bad_box_is_rejected(tmp_path, monkeypatch):
    c, _ = _client(tmp_path, monkeypatch)
    r = c.post("/api/analyze", json={"bbox": [85.5, 28.1, 85.4, 28.25], "date": "2026-08-25"})
    assert r.status_code == 422


def test_analysis_limits_token_and_switch(tmp_path, monkeypatch):
    c, server = _client(tmp_path, monkeypatch)
    ok = {"bbox": [85.3, 28.1, 85.45, 28.25], "date": "2026-08-25"}
    assert c.post("/api/analyze", json={**ok, "bbox": [80, 20, 90, 30]}).status_code == 422         # far larger than the limit
    assert c.post("/api/analyze", json={**ok, "res": 5}).status_code == 422
    assert c.post("/api/analyze", json={**ok, "date": "2026-13-45"}).status_code == 422
    monkeypatch.setattr(server, "TOKEN", "s3cret")
    assert c.post("/api/analyze", json=ok).status_code == 401
    monkeypatch.setattr(server, "ANALYZE_ON", False)
    assert c.post("/api/analyze", json=ok, headers={"X-Token": "s3cret"}).status_code == 403
    assert c.get("/api/presets").json()["_config"]["analyze"] is False


def test_run_names_never_overwrite(tmp_path, monkeypatch):
    c, server = _client(tmp_path, monkeypatch)
    (tmp_path / "custom_20260825_20m").mkdir()
    (tmp_path / "custom_20260825_20m_2").mkdir()
    assert server.unique_name("custom_20260825_20m") == "custom_20260825_20m_3"


@needs_run
def test_csv_neutralises_formulas(tmp_path, monkeypatch):
    import json
    _copy_run(tmp_path)
    p = tmp_path / "trishuli" / "summary.json"
    S = json.loads(p.read_text(encoding="utf-8"))
    S["settlements"][0]["name"] = "=HYPERLINK(\"http://x\")"
    S["settlements"][0]["status"] = "cut_off"
    p.write_text(json.dumps(S), encoding="utf-8")
    c, _ = _client(tmp_path, monkeypatch)
    csv = c.get("/api/runs/trishuli/settlements.csv?status=cut_off").text
    assert "'=HYPERLINK" in csv and "\n=HYPERLINK" not in csv
