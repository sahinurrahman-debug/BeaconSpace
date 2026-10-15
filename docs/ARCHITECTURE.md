# BeaconSpace — architecture

## Overview
A Python pipeline (`floodsys/`) turns *(bounding box, flood time)* into maps, damage statistics, cut-off settlements and a report.
A FastAPI server (`app/server.py`) exposes the same pipeline and the run files as a JSON API, and serves the React front end (`web/`, Vite build). There is no database and no login: results are plain files
in `outputs/<run>/`, and remote data are open endpoints.

```
 area + flood time
   │
   ├─ data/s1.py   Planetary Computer Sentinel-1 RTC → same-track pairs (post + up to 5 pre) → dB, per-pixel pre-event variability
   ├─ data/dem.py  Copernicus DEM → slope, HAND, drainage network (upstream area), D8 flow
   ├─ data/s2.py   Sentinel-2 L2A → cloud-masked composites → MNDWI water evidence
   │
   ├─ flood/detect.py   water + debris/scour + permanent water   (physics, terrain gates, river proximity)
   │  flood/model.py    ONNX U-Net (7 channels) proposes flood water; physics still gates it
   │
   ├─ data/osm.py       OSM before the event: ohsome → Overpass [date:] attic → local file (tile cache)
   ├─ analysis/damage.py    buildings / roads / bridges vs the impact mask
   ├─ analysis/access.py    road graph before vs after → cut_off / longer_route / connected
   ├─ analysis/flowpath.py  D8 flow path + settlements in the corridor
   ├─ analysis/waterrise.py HAND-based "+h m above the river" preview
   │
   └─ report/   sitrep (EN + NE, templates only) · mapplot (static + interactive Leaflet map)
 pipeline.py ties it together and writes summary.json + provenance.json
```

## Key decisions
| Decision | Why |
|---|---|
| Same relative orbit only | Different tracks see the terrain from different angles; pixel comparison is invalid |
| Water = dark **and** dropped ≥ 3 dB vs pre-event | Radar shadow is dark in both images |
| Debris from smoothed log-ratio normalised by each pixel's own pre-event variability, within 150 m of a river | A null-event test showed farmland and monsoon soils otherwise cause hundreds of hectares of false alarms |
| Optical never vetoes radar | Debris on river gravel shows no vegetation loss |
| OSM requested with a snapshot date < event | Post-event crowd edits must never enter the analysis (15 % of buildings in one dense tile had been edited after the snapshot) |
| Provider chain for OSM | The public ohsome geometry endpoint returned HTTP 403 from the dev network |
| Reports are templates, not LLM output | Every number must come from the maps |
| AI exported to ONNX | CPU inference in the live system, no PyTorch needed at run time |

## Data and compute
- Grid: UTM, default 20 m (10 / 40 m selectable); remote COGs read in parallel row chunks with retries.
- Caches in `cache/` (S1 stacks, terrain, S2 evidence, OSM tiles). Bundled OSM tiles for the case study live in `data/osm_tiles/`.
- Typical case-study run (3 300 km², everything cached): 3–10 minutes on a laptop CPU.

## Interfaces
CLI (`python -m floodsys run …`), dashboard (`uvicorn app.server:app`, front end built from `web/`), Python API (`floodsys.pipeline.run`). See [API_SPEC.md](API_SPEC.md).

## Quality
- `pytest -q`: synthetic unit tests (pair planning, detector incl. shadow and river-proximity, overlay, cut-off graph, feature contract between notebook and runtime, report numbers) and API tests (FastAPI TestClient: run payloads, map theming, downloads, analysis job and error hand-off).
- `scripts/null_test.py` (false alarms) and `scripts/evaluate_emsr927.py` (checking only) for evaluation.
- `floodsys/sources.py` is the data-rule guard: every raster/OSM read is checked against the allowed hosts and reference-map paths are refused.
- `scripts/sensitivity_access.py` and the block-bootstrap CI in `scripts/evaluate_emsr927.py` quantify how far the cut-off counts and the EMS agreement move with our own choices.
- Untrusted text (OSM names) is HTML-escaped before it reaches popups or tables.
