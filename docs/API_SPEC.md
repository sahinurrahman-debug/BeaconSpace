# BeaconSpace — interface spec

BeaconSpace has no database. Its interfaces are a command line, a Python function, a small JSON web API behind the React dashboard, and a set of output files.

## Command line
`python -m floodsys run [options]`

| Option | Default | Meaning |
|---|---|---|
| `--preset {trishuli,syaphrubesi}` | – | ready-made area, event time and flow-path start |
| `--bbox W S E N` | – | custom area (lon/lat, EPSG:4326) |
| `--event DATE` | – | flood date/time in UTC (`2026-08-26` or `2026-08-25T22:00`) |
| `--res {10,20,40}` | 20 | analysis grid in metres |
| `--pairs N` | 2 | radar tracks to combine |
| `--trace LON LAT` | – | upstream point for the flow-path bonus |
| `--no-s2` / `--no-model` | off | radar only / ignore the AI model |
| `--snapshot DATE` | latest before event | OSM snapshot (must predate the event) |
| `--name`, `--out` | derived, `outputs/` | run name and output folder |

Other scripts: `scripts/null_test.py` (false alarms), `scripts/evaluate_emsr927.py` (check vs EMS), `scripts/prefetch_osm.py`, `scripts/build_report.py`, `scripts/rebuild_outputs.py`, `scripts/make_logo.py`.

## Python
```python
from floodsys.pipeline import RunConfig, run
res = run(RunConfig(bbox=(85.30, 28.10, 85.45, 28.25), event=datetime(2026, 8, 25, 22, tzinfo=UTC), res=20))
res["out"], res["summary"]          # output folder, summary dict
```
`RunConfig`: `bbox`, `event`, `name`, `res`, `n_pairs`, `use_s2`, `use_model`, `snapshot`, `trace_from`, `out_dir`, `settings`.
Raises `RuntimeError` if no same-track pre/post Sentinel-1 pair covers the area and date.

## Web API (`uvicorn app.server:app`)
| Endpoint | Purpose |
|---|---|
| `GET /api/runs` · `GET /api/presets` | finished runs (case study first) · ready-made areas |
| `GET /api/runs/{run}` | summary, headline facts, EMS comparison, provenance, available files, attribution |
| `GET /api/runs/{run}/map?theme=light\|dark` | interactive map, themed inside the frame |
| `GET /api/runs/{run}/sitrep` · `/sitrep.pdf` · `/settlements.csv?status=&q=` · `/image/{evaluation_*.png}` | report and downloads |
| `POST /api/analyze` → `GET /api/jobs/{id}` | start one analysis at a time; poll its step, log lines, result or error |
| `GET /api/health` | health check (used by Render) |

## Dashboard pages (top navigation)
| Page | URL path | Content | Needs a finished run |
|---|---|---|---|
| Overview | `/overview` | 4 headline cards, map with water-rise slider, Critical / Watch panels | yes |
| Settlements | `/settlements` | filterable table, CSV download, flood-path table | yes |
| Situation report | `/report` | EN + NE report, HTML/PDF download | yes |
| Method & data | `/method` | passes used, detector, OSM snapshot, provenance | yes |
| EMS check | `/ems` | comparison with EMSR927 (checking only) | yes |
| New analysis | `/new` | form → live progress → opens Overview | no |

## Output files (`outputs/<run>/`)
| File | Content |
|---|---|
| `classes.tif` | uint8: 0 none · 1 flood water · 2 debris/scour · 3 permanent water (UTM, analysis grid) |
| `support.tif` | number of orbit tracks that flagged each pixel |
| `impact_polygons.geojson` | vectorised flood + debris (`cls`, `area_ha`) |
| `buildings_affected.geojson` | `status` ∈ destroyed_likely / affected / exposed, `overlap` |
| `roads_hit.geojson`, `bridges_hit.geojson`, `blocked_segments.geojson` | damaged / blocking road geometry |
| `settlements.geojson` | `name, kind, source, n_buildings, n_buildings_affected, status, inundated, reason, dist_before_km, dist_after_km, dest_before, dest_after, cut_lon, cut_lat` |
| `destinations.geojson` | hospitals / clinics / towns used as route targets |
| `flowpath.geojson`, `flowpath_corridor.geojson`, `flowpath_settlements.csv` | bonus outputs |
| `waterrise.png` / `waterrise.json` | HAND preview raster (EPSG:3857) + cumulative area/building/settlement counts for +0…+60 m |
| `summary.json` | `name, bbox, event_utc, resolution_m, area_km2, area_ha, damage, access, cut_off, settlements, flowpath, confidence, s1_pairs, s2, noise, model, osm, runtime_s` |
| `provenance.json` | sources, parameters, `forbidden_inputs_used: []` |
| `sitrep.html/pdf`, `map.png`, `dashboard_map.html` | report and maps |

`status` values for settlements: `cut_off` (CRITICAL), `longer_route` (WATCH), `connected` (NORMAL), `not_assessable`, `no_road_data`.

## AI model contract (`models/flood_unet.onnx`)
Input `(N, 7, H, W)` float32: post VV, post VH, pre VV, pre VH (dB, scaled), smoothed log-ratio VV and VH, terrain slope.
Output `(N, 3, H, W)` logits: 0 no water · 1 permanent water · 2 new flood water. Built identically in `notebooks/train_flood_unet.py` and `floodsys/flood/model.py` (a unit test enforces it).

## Environment variables
`FLOODSYS_CACHE`, `FLOODSYS_OUT`, `FLOODSYS_MODEL` (paths), `BEACONSPACE_ANALYZE` (`off` = view finished runs only; default on), `BEACONSPACE_TOKEN` (if set, `POST /api/analyze` needs header `X-Token`), `BEACONSPACE_MAX_AREA_KM2` (default 6000), `PORT` (container).
