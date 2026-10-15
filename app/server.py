"""BeaconSpace web server:  uvicorn app.server:app --port 8000

A thin JSON API over the floodsys pipeline and the files in $FLOODSYS_OUT, plus the built React front end (web/dist).
Dev:  `npm run dev` in web/ (proxies /api to this server).  Prod:  `npm run build` in web/, then run this server only.
"""
import datetime as dt
import html
import json
import math
import os
import re
import secrets
import sys
import threading
import time
import uuid
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from floodsys import config  # noqa: E402
from floodsys.presets import PRESETS  # noqa: E402
from floodsys.report.sitrep import _title, facts  # noqa: E402

UTC = dt.timezone.utc
# Public deployments set BEACONSPACE_ANALYZE=off (view finished runs only); BEACONSPACE_TOKEN, if set, must be sent as X-Token to start a run.
ANALYZE_ON = os.environ.get("BEACONSPACE_ANALYZE", "on").lower() not in ("off", "0", "false", "no")
TOKEN = os.environ.get("BEACONSPACE_TOKEN", "")
MAX_AREA_KM2 = float(os.environ.get("BEACONSPACE_MAX_AREA_KM2", "6000"))
MAX_JOBS_KEPT = 20
DIST = ROOT / "web" / "dist"
FORMULA_START = ("=", "+", "-", "@", chr(9), chr(13))
NAME_OK = re.compile(r"^[A-Za-z0-9_.\-]+$")

app = FastAPI(title="BeaconSpace", docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(GZipMiddleware, minimum_size=1024)


def out_dir() -> Path:
    return config.OUTPUT_DIR


def clean(o):
    """JSON-safe copy: NaN/inf -> null, numpy scalars -> python."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if hasattr(o, "item") and not isinstance(o, (str, bytes)):
        try:
            o = o.item()
        except Exception:
            return str(o)
    if isinstance(o, float) and not math.isfinite(o):
        return None
    return o


def run_dir(name: str) -> Path:
    if not NAME_OK.match(name):
        raise HTTPException(404, "unknown run")
    d = out_dir() / name
    if not (d / "summary.json").exists():
        raise HTTPException(404, "unknown run")
    return d


def list_runs() -> list:
    od = out_dir()
    if not od.exists():
        return []
    ps = sorted(od.glob("*/summary.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    ps.sort(key=lambda p: p.parent.name != "trishuli")      # the case study first, then newest-first
    out = []
    for p in ps:
        try:
            out.append({"name": p.parent.name, "title": _title(p.parent.name)})
        except Exception:
            out.append({"name": p.parent.name, "title": p.parent.name.replace("_", " ")})
    return out


@app.get("/api/runs")
def api_runs():
    return list_runs()


@app.get("/api/presets")
def api_presets():
    return {"_config": {"analyze": ANALYZE_ON, "token": bool(TOKEN), "max_area_km2": MAX_AREA_KM2}, **{k: {"label": v["label"], "bbox": list(v["bbox"]), "event": v["event"].astimezone(UTC).strftime("%Y-%m-%dT%H:%M"),
                "trace_from": list(v["trace_from"]) if v.get("trace_from") else None} for k, v in PRESETS.items()}}


@app.get("/api/runs/{name}")
def api_run(name: str):
    d = run_dir(name)
    S = json.loads((d / "summary.json").read_text(encoding="utf-8"))
    F = facts(S)
    for k in ("cut", "longer", "pairs", "s2", "model", "osm", "flow"):          # already inside the summary; keep the payload small
        F.pop(k, None)
    S.pop("cut_off", None)
    S["settlements"] = [{k: r.get(k) for k in ("name", "status", "n_buildings", "n_buildings_affected", "dist_before_km", "dist_after_km",
                                               "dest_before", "reason", "lat", "lon")} for r in S.get("settlements", [])]
    ev = None
    if (d / "evaluation_emsr927.json").exists():
        ev = json.loads((d / "evaluation_emsr927.json").read_text(encoding="utf-8"))
    prov = json.loads((d / "provenance.json").read_text(encoding="utf-8")) if (d / "provenance.json").exists() else None
    files = {"map": (d / "dashboard_map.html").exists(), "sitrep": (d / "sitrep.html").exists(), "pdf": (d / "sitrep.pdf").exists(),
             "eval_images": sorted(f.name for f in d.glob("evaluation_*.png"))}
    attrib = config.attribution(int(S["event_utc"][:4]))[:3]
    return JSONResponse(clean({"name": name, "title": _title(name), "summary": S, "facts": F, "evaluation": ev,
                               "provenance": prov, "files": files, "attribution": attrib, "ems_credit": config.EMS_CREDIT}))


# ---------------------------------------------------------------- files (map / report / images)
def map_html(text: str, theme: str) -> str:
    """Loader overlay + light/dark choice inside the map iframe (same behaviour as the old dashboard); theme = light | dark | auto."""
    known = {"light": "true", "dark": "false"}.get(theme, "null")
    css = ("<style>:root{--l-bg:#120B14;--l-fg:#F6E9F2;--l-ac:#F472B6}"
           "@media (prefers-color-scheme:light){:root.auto{--l-bg:#FAF4F8;--l-fg:#2A1423;--l-ac:#BE185D}}"
           ":root.light{--l-bg:#FAF4F8;--l-fg:#2A1423;--l-ac:#BE185D}"
           "#bs-load{position:fixed;inset:0;z-index:99999;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:16px;"
           "background:var(--l-bg);color:var(--l-fg);font:16px Inter,system-ui,sans-serif;transition:opacity .2s}"
           "#bs-load .sp{width:32px;height:32px;border-radius:50%;border:3px solid rgba(128,128,128,.35);border-top-color:var(--l-ac);animation:r .8s linear infinite}"
           "@keyframes r{to{transform:rotate(360deg)}}@media (prefers-reduced-motion:reduce){#bs-load .sp{animation:none}}"
           "</style><div id='bs-load' role='status'><div class='sp'></div><div>Loading map…</div></div>")
    pre = (f"<script>var K={known};var LIGHT=K===null?window.matchMedia('(prefers-color-scheme: light)').matches:K;"
           "document.documentElement.classList.add(K===null?'auto':(LIGHT?'light':'dark'));if(LIGHT)document.body.classList.add('bs-light')</script>")
    js = ("<script>window.addEventListener('load',function(){setTimeout(function(){var l=document.getElementById('bs-load');"
          "if(l){l.style.opacity=0;setTimeout(function(){l.remove()},220)}},60);"
          "var want=LIGHT?'light':'dark';document.querySelectorAll('.leaflet-control-layers-base label').forEach(function(lb){"
          "if(lb.textContent.toLowerCase().indexOf(want)>-1){var i=lb.querySelector('input');if(i&&!i.checked){i.click()}}})})</script>")
    text = text.replace("<body>", "<body>" + css + pre, 1) if "<body>" in text else css + pre + text
    return text.replace("</body>", js + "</body>", 1)


@app.get("/api/runs/{name}/map", response_class=HTMLResponse)
def api_map(name: str, theme: str = "auto"):
    p = run_dir(name) / "dashboard_map.html"
    if not p.exists():
        raise HTTPException(404, "no map")
    return HTMLResponse(map_html(p.read_text(encoding="utf-8"), theme), headers={"Cache-Control": "private, max-age=300"})


@app.get("/api/runs/{name}/sitrep", response_class=HTMLResponse)
def api_sitrep(name: str, download: bool = False):
    p = run_dir(name) / "sitrep.html"
    if not p.exists():
        raise HTTPException(404, "no report")
    headers = {"Content-Disposition": 'attachment; filename="sitrep.html"'} if download else {}
    return HTMLResponse(p.read_text(encoding="utf-8"), headers=headers)


@app.get("/api/runs/{name}/sitrep.pdf")
def api_pdf(name: str):
    p = run_dir(name) / "sitrep.pdf"
    if not p.exists():
        raise HTTPException(404, "no pdf")
    return FileResponse(p, media_type="application/pdf", filename="sitrep.pdf")


@app.get("/api/runs/{name}/image/{fname}")
def api_image(name: str, fname: str):
    if not re.match(r"^evaluation_[A-Za-z0-9_\-]+\.png$", fname):
        raise HTTPException(404)
    p = run_dir(name) / fname
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="image/png")


@app.get("/api/runs/{name}/settlements.csv")
def api_csv(name: str, status: str = "", q: str = ""):
    S = json.loads((run_dir(name) / "summary.json").read_text(encoding="utf-8"))
    df = pd.DataFrame(S.get("settlements", []))
    if len(df):
        if status:
            df = df[df["status"].isin(status.split(","))]
        if q:
            df = df[df["name"].astype(str).str.contains(q, case=False, na=False, regex=False)]
        order = {"cut_off": 0, "longer_route": 1, "connected": 2, "not_assessable": 3, "no_road_data": 4}
        df = df.assign(_o=df["status"].map(order)).sort_values(["_o", "n_buildings"], ascending=[True, False]).drop(columns="_o")
    for c in [c for c in df.columns if not pd.api.types.is_numeric_dtype(df[c])]:           # neutralise spreadsheet formulas coming from OSM names
        df[c] = df[c].map(lambda v: "'" + v if isinstance(v, str) and v[:1] in FORMULA_START else v)
    return PlainTextResponse(df.to_csv(index=False), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{name}_settlements.csv"'})


# ---------------------------------------------------------------- analysis jobs (one at a time; progress is polled)
STEPS = [("Terrain", ("[dem]", "[run] AOI")), ("Optical", ("[s2]",)), ("Radar", ("[s1]", "[run] pair", "[run] AI")),
         ("Detect", ("[run] areas",)), ("OSM", ("[osm]",)), ("Damage", ("[run] damage",)),
         ("Cut-off", ("[access]", "[run] access", "[waterrise]")), ("Flow path", ("[flowpath]",)), ("Report", ("[sitrep]", "[run] done"))]
JOBS: dict = {}
LOCK = threading.Lock()


class AnalyzeIn(BaseModel):
    key: str = "custom"
    bbox: list[float] = Field(min_length=4, max_length=4)       # west, south, east, north
    date: str                                                   # YYYY-MM-DD (UTC)
    time: str = "00:00"
    res: int = 20
    pairs: int = 2
    use_s2: bool = True
    use_model: bool = True
    trace: bool = False
    trace_lon: float | None = None
    trace_lat: float | None = None


def unique_name(base: str) -> str:
    """Never overwrite a finished run: add _2, _3 … when the name is taken."""
    name, i = base, 2
    while (out_dir() / name).exists():
        name, i = f"{base}_{i}", i + 1
    return name


def _worker(job_id: str, a: AnalyzeIn):
    job = JOBS[job_id]
    try:
        from floodsys.pipeline import RunConfig, run
        w, s, e, n = a.bbox
        day = dt.date.fromisoformat(a.date)
        hh, mm = (int(x) for x in a.time.split(":")[:2])
        event = dt.datetime(day.year, day.month, day.day, hh, mm, tzinfo=UTC)
        cfg = RunConfig(bbox=(w, s, e, n), event=event, res=float(a.res), n_pairs=a.pairs, use_s2=a.use_s2, use_model=a.use_model,
                        trace_from=(a.trace_lon, a.trace_lat) if a.trace and a.trace_lon is not None and a.trace_lat is not None else None,
                        name=unique_name(f"{re.sub('[^A-Za-z0-9]', '', a.key) or 'custom'}_{day:%Y%m%d}_{int(a.res)}m"))

        def log(msg):
            job["lines"].append(str(msg))
            for i, (_, prefixes) in enumerate(STEPS):
                if any(str(msg).startswith(p) for p in prefixes):
                    job["step"] = max(job["step"], i)

        r = run(cfg, log=log)
        job["run"] = r["out"].name
        job["status"] = "done"
    except Exception as exc:                                    # shown to the user with a hint
        job["error"] = str(exc)
        job["hint"] = "same-track" if "same-track" in str(exc) else "other"
        job["status"] = "error"


@app.post("/api/analyze")
def api_analyze(a: AnalyzeIn, x_token: str = Header(default="")):
    if not ANALYZE_ON:
        raise HTTPException(403, "New analyses are switched off on this server; finished runs can still be explored.")
    if TOKEN and not secrets.compare_digest(x_token, TOKEN):
        raise HTTPException(401, "A valid access token is required to start an analysis.")
    w, s, e, n = a.bbox
    if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
        raise HTTPException(422, "The bounding box must be west < east and south < north, in degrees.")
    area = abs((e - w) * 111 * math.cos(math.radians((s + n) / 2))) * abs((n - s) * 111)
    if area > MAX_AREA_KM2:
        raise HTTPException(422, f"The area is about {area:,.0f} km²; this server accepts at most {MAX_AREA_KM2:,.0f} km². Choose a smaller box.")
    if a.res not in (10, 20, 40) or not 1 <= a.pairs <= 3:
        raise HTTPException(422, "Resolution must be 10, 20 or 40 m and radar tracks 1 to 3.")
    try:
        dt.date.fromisoformat(a.date)
    except ValueError:
        raise HTTPException(422, "The flood date is not a valid date (YYYY-MM-DD).")
    with LOCK:
        if any(j["status"] == "running" for j in JOBS.values()):
            raise HTTPException(409, "An analysis is already running.")
        jid = uuid.uuid4().hex[:10]
        for old in sorted(JOBS, key=lambda k: JOBS[k]["t0"])[:-MAX_JOBS_KEPT]:      # keep memory bounded
            JOBS.pop(old, None)
        JOBS[jid] = {"id": jid, "status": "running", "step": 0, "lines": ["Starting…"], "run": None, "error": None, "hint": None, "t0": time.time()}
    threading.Thread(target=_worker, args=(jid, a), daemon=True).start()
    return {"id": jid}


@app.get("/api/jobs/{jid}")
def api_job(jid: str):
    j = JOBS.get(jid)
    if not j:
        raise HTTPException(404, "unknown job")
    return {"id": jid, "status": j["status"], "step": j["step"], "steps": [n for n, _ in STEPS], "lines": j["lines"][-6:], "run": j["run"],
            "error": html.escape(j["error"][:300]) if j["error"] else None, "hint": j["hint"], "elapsed": round(time.time() - j["t0"])}


@app.get("/api/health")
def health():
    return {"ok": True, "analyze": ANALYZE_ON}


# ---------------------------------------------------------------- built front end (single-page app)
if DIST.exists():
    from fastapi.staticfiles import StaticFiles
    if (DIST / "assets").exists():
        app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        f = (DIST / path).resolve()
        if path and f.is_file() and DIST.resolve() in f.parents:
            return FileResponse(f)
        return FileResponse(DIST / "index.html", headers={"Cache-Control": "no-cache"})
