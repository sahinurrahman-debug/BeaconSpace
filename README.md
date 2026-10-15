<p align="left"><img src="app/assets/beaconspace.svg" alt="BeaconSpace logo" width="72"></p>

# BeaconSpace

> Satellite flood-damage mapping for rescue teams: give it an area and a flood date, and it shows where the flood hit, what was damaged, and which villages are cut off.

[![Repo](https://img.shields.io/badge/GitHub-Repo-black?style=for-the-badge&logo=github)](https://github.com/sahinurrahman-debug/BeaconSpace)
[![Live Demo](https://img.shields.io/badge/Live-Demo-blue?style=for-the-badge)](https://beaconspace.onrender.com)

*Multimodal AI Hackathon 2026 · Track B: Mapping Flood Damage from Space*

---

## What It Does

After a mountain flood, ground sensors are swept away and roads, bridges and phone lines fail, so rescue coordinators do not know where the damage is or which villages can no longer be reached. BeaconSpace takes **a bounding box and a flood date** and, using only free Sentinel radar and optical images, the Copernicus elevation model and OpenStreetMap as it was *before* the event, maps the flooded and debris-covered areas, estimates which buildings, roads and bridges were hit, and finds the settlements that lost their road connection to the nearest hospital or town. It runs end to end from raw satellite data for any area and date, and writes a map dashboard plus a one-page situation report in English and Nepali in which every number comes from the system's own maps.

Case study: the 26 August 2026 Bhote Koshi–Trishuli glacial-lake outburst flood in Nepal, compared with the official Copernicus EMS maps (EMSR927).

---

## Features

- **Same-track radar change detection** — Sentinel-1 pre/post pairs on the same orbit (never mixing tracks), with up to five earlier passes to learn each pixel's natural variability.
- **Flood water and debris/scour map** — water must be dark *and* have dropped ≥ 3 dB (so radar shadow is not mistaken for water); debris is change near rivers; terrain gates remove steep or high ground.
- **AI flood segmentation** — a U-Net trained on Kuro Siwo (Colab T4), exported to ONNX, evaluated on unseen events and ablated honestly.
- **Damage estimate** — pre-event OSM buildings (*likely destroyed / affected / exposed*), road kilometres and bridges hit.
- **Who is cut off** — road graph before vs after; settlements marked Critical (cut off), Watch (much longer route) or Normal, with the blocked road segment located.
- **Flood path (bonus)** — pick an upstream point; D8 flow routing traces the valley and lists the settlements downstream.
- **Water-rise preview** — slider for +0 to +60 m above the nearest river showing the area, buildings and settlements within reach (terrain-based, from the elevation data).
- **Bilingual situation report** — one page in English and one in Nepali, built from templates (no language model, no invented numbers).
- **Dashboard** — top navigation, mission-control map with frosted-glass panels, light and dark themes, designed empty and loading states.
- **Provenance and compliance** — every run records its sources and parameters in `provenance.json` (`forbidden_inputs_used: []`).

---

## Results (case study: Trishuli / Bhote Koshi, 26 Aug 2026)

`python -m floodsys run --preset trishuli` → `outputs/trishuli/` (≈ 3–10 min once OpenStreetMap tiles are cached).

| | Result |
|---|---|
| Flooded + debris | **1 364 ha** (61 ha water, 1 303 ha debris/scour) |
| Buildings | **2 610** affected of 74 869 mapped (1 984 likely destroyed) |
| Roads / bridges | **67 km** hit · **33 / 151** bridges |
| Cut off | **126** settlements (164 with a much longer route; 7 641 buildings in cut-off settlements); **range 74–153** depending on how strictly a road counts as blocked ([sensitivity](./docs/results/access_sensitivity_trishuli.json)): 74 if only pixels flagged by *both* radar tracks count, 123 / 153 with a tighter / wider blocking rule |
| Flow path | 90 km traced, 54 settlements in the corridor |

**Check against Copernicus EMS EMSR927** (inside its four mapped areas, 5 132 ha; checking only): IoU 0.48 (95 % CI 0.42–0.54) · precision 0.76 · recall 0.57 (with 30 m tolerance 0.82 / 0.76) · 56 % of EMS-affected buildings found · 85 % of EMS-affected road length covered.

**False-alarm test** (same pipeline on pairs where nothing happened): the first detector flagged 670–2 620 ha of "debris"; the final one flags 42–71 ha on late-season pairs versus 880–990 ha for the real event. Early-July pairs stay noisy because their pre-event series ends before the monsoon.

**AI model:** flood IoU 0.72 (10 m) / 0.71 (20 m) over all Kuro Siwo test-shard patches versus 0.50 for a threshold baseline, **but 19 of the 25 events in those shards also occur in the training patches, so this is optimistic.** On the 6 events never seen in training, per-event IoU is 0.15–0.92 (patch-weighted mean 0.46); 0.35 / 0.30 on mountainous patches; 2.6 % false flood on flood-free patches. **Ablation on this case study:** with vs without the network, EMS-area IoU is 0.483 vs 0.477 and affected buildings found 56 % vs 56 %. The physics change detector drives this debris-flow result; the network's measured value is on open-water floods. All raw numbers are in [`docs/results/`](./docs/results).

---

## Planning Docs

- [PRD](./docs/PRD.md)
- [Architecture](./docs/ARCHITECTURE.md)
- [API Spec](./docs/API_SPEC.md)
- [Roadmap](./docs/ROADMAP.md)
- Also: [Technical report (PDF)](./docs/Report.pdf) · [Judge quick-start](./docs/JUDGE_QUICKSTART.md) · [Colab training guide](./docs/COLAB_GUIDE.md) · [Q&A prep](./docs/QA_PREP.md) · [Demo script](./docs/DEMO_SCRIPT.md)

**Deviations from the plan:**
1. **OpenStreetMap provider.** The brief names the ohsome API; its geometry endpoint answered HTTP 403 from our network, so the loader tries ohsome first and falls back to date-pinned Overpass "attic" queries (slow, so tiles are cached and bundled).
2. **First detector over-alarmed.** A null-event test showed hundreds of false hectares from monsoon farmland. We added per-pixel pre-event variability (up to 5 images) and a river-proximity rule; recall fell from 0.65 to 0.57 in exchange.
3. **Evaluation claim corrected.** The Hugging Face "test" shards share events with the training shards, so we report the 6 truly unseen events instead of the headline number.
4. **Debris is not a network class.** Kuro Siwo has no debris-flow labels, so debris comes from the change detector; the network barely changes the case-study result (~1 %).
5. **AI option.** We built the flood-segmentation model; the situation-report copilot option was not built (the report is template-based).
6. **Additions beyond the brief:** the water-rise preview and a per-pixel variability baseline. **Left out on purpose:** rainfall, river-gauge and drone feeds (no such data in the allowed inputs) and population counts (no allowed dataset; buildings are reported instead).

---

## Architecture

```
area + flood date
 ├─ Sentinel-1 RTC (Planetary Computer) → same-track pairs: post + up to 5 pre → dB, per-pixel variability
 ├─ Copernicus DEM (AWS)               → slope, HAND, drainage network, D8 flow
 ├─ Sentinel-2 L2A (AWS)               → cloud-masked MNDWI water evidence (additive only)
 │
 ├─ detect: U-Net (ONNX, 7 ch) proposes water · physics + terrain + river-proximity gates · debris/scour change
 │
 ├─ OSM before the event: ohsome → Overpass [date:] attic → local file (tile cache)
 │     ├─ buildings / roads / bridges overlay → damage
 │     ├─ road graph before vs after          → cut_off / longer_route / connected
 │     └─ flow path + water-rise preview
 └─ outputs: summary.json · GeoTIFF/GeoJSON · map · EN+NE situation report · provenance.json
                                     └─ React dashboard + FastAPI server (top navigation, Leaflet map)
```

Data flow: the pipeline plans radar pairs, reads the clipped COGs in parallel, detects water and debris, overlays the pre-event OSM snapshot, rebuilds the road graph with the blocked segments removed, and writes plain files. The dashboard only reads those files (or triggers a run). See [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md).

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Language | Python 3.12+ (tested on 3.14) | Geospatial and ML ecosystem |
| Satellite access | Planetary Computer STAC (Sentinel-1 RTC), AWS Earth Search (Sentinel-2, DEM), rasterio | Open, no accounts, cloud-optimised reads |
| Geo processing | NumPy, SciPy, scikit-image, GeoPandas/Shapely, pyflwdir, NetworkX | Change detection, overlay, hydrology, road graph |
| AI | PyTorch + segmentation-models-pytorch (Colab T4), ONNX Runtime | Train on GPU, run on any CPU |
| Training data | Kuro Siwo (Bountos et al., NeurIPS 2024) | Pre/post SAR pairs with flood labels |
| Map data | OpenStreetMap via ohsome / Overpass attic | Pre-event snapshot only |
| UI | React 18 + Vite (top navigation), Leaflet via Folium, Inter + JetBrains Mono | Instant page switches, themeable, static build |
| Server | FastAPI + Uvicorn | Thin JSON API over the pipeline; serves the built front end |
| Reports | HTML templates → PDF (headless Edge/Chrome) | Numbers only from the maps |
| Tests | pytest, FastAPI TestClient | 20 tests, offline and synthetic |
| Deployment | Local, or container (`Dockerfile`, optional `render.yaml`) | No server state needed |

---

## Data Model (outputs)

No database: each run writes files to `outputs/<run>/`.

```text
summary.json          name, bbox, event_utc, area_ha{flood,debris,permanent}, damage{buildings,roads,bridges}, access{...}, settlements[], flowpath, s1_pairs[], s2, model, osm, runtime_s
classes.tif           0 none · 1 flood water · 2 debris/scour · 3 permanent water
settlements.geojson   name, status(cut_off|longer_route|connected|…), n_buildings, n_buildings_affected, dist_before_km, dist_after_km, dest_before, dest_after, cut_lon, cut_lat
buildings_affected    status(destroyed_likely|affected|exposed), overlap
waterrise.json/png    cumulative area / buildings / settlements for +0…+60 m above the nearest river
provenance.json       sources, parameters, forbidden_inputs_used: []
```
Full schema: [`docs/API_SPEC.md`](./docs/API_SPEC.md).

## Interfaces

**Command line**

| Command | What it does |
|---|---|
| `python -m floodsys run --preset trishuli` | the case study |
| `python -m floodsys run --bbox W S E N --event 2026-08-26` | any area and date |
| `python -m floodsys run … --res 10 --pairs 3 --trace LON LAT` | sharper, more tracks, flow-path bonus |
| `python scripts/evaluate_emsr927.py --run outputs/trishuli` | compare with EMSR927 (checking only) |
| `python scripts/null_test.py --preset trishuli --dates … --with-event` | false-alarm test |

**Dashboard pages**

| Page | Purpose | Needs a finished run |
|---|---|---|
| Overview | headline cards, map with water-rise slider, Critical / Watch panels | yes |
| Settlements | filterable table, CSV, flood path | yes |
| Situation report | EN + NE report, download | yes |
| Method & data | passes used, detector, OSM snapshot, provenance | yes |
| EMS check | comparison with EMSR927 | yes |
| New analysis | form → live progress → opens Overview | no |

---

## Getting Started

### Prerequisites

| Need | Version / detail | Why |
|---|---|---|
| Python | 3.12 or newer (developed and tested on **3.14**) | analysis pipeline and web server |
| Node.js + npm | Node 18 or newer (tested on 24) | builds the React front end (only needed once) |
| Git | any recent version | clone the repository |
| Internet | required for the first run of an area | Sentinel, elevation and OpenStreetMap data are streamed; repeats use the cache |
| Disk / memory | about 3 GB free for the cache of the case study; 8 GB RAM recommended for a 20 m run of the full case-study area | cached rasters and OSM tiles |
| Edge or Chrome | optional | PDF export of the situation report (without it you still get the HTML report) |
| Accounts / API keys | **none** | all data sources are open |

Python dependencies are pinned in [`requirements.txt`](./requirements.txt): numpy, scipy, pandas, shapely, pyproj, rasterio, geopandas, pyogrio, networkx, scikit-learn, scikit-image, requests, pystac-client, planetary-computer, pyflwdir, numba, onnxruntime, matplotlib, folium, fastapi, uvicorn, httpx and pytest. Front-end dependencies (React 18, React Router, Vite) are in [`web/package.json`](./web/package.json).

### Setup

```bash
git clone https://github.com/sahinurrahman-debug/BeaconSpace.git
cd BeaconSpace

# 1. Python environment and dependencies
python -m venv .venv
source .venv/bin/activate            # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Build the web front end (one time)
cd web
npm install
npm run build
cd ..

# 3. Check the install (about 30 s, works offline)
pytest -q
```

The Python package is called `floodsys`; **BeaconSpace** is the project name.

### Running the project

**Option A: explore the finished case study (no downloads, about 1 minute)**

```bash
# macOS / Linux
FLOODSYS_OUT=examples uvicorn app.server:app --port 8000
# Windows PowerShell
$env:FLOODSYS_OUT="examples"; uvicorn app.server:app --port 8000
```

Open http://localhost:8000. The Trishuli run in [`examples/trishuli/`](./examples/trishuli) opens on the Overview page.

**Option B: run an analysis yourself**

```bash
uvicorn app.server:app --port 8000
```

Open http://localhost:8000, go to **New analysis**, choose the Trishuli preset (or enter your own bounding box and flood date) and press **Run analysis**. Progress is shown step by step and the results open automatically. The first run of an area downloads data (minutes to an hour for a new area, because OpenStreetMap history is slow); repeat runs are cached. Results are written to `outputs/<run>/`.

**Option C: command line only**

```bash
python -m floodsys run --preset trishuli                                   # the case study
python -m floodsys run --bbox 85.30 28.10 85.45 28.25 --event 2026-08-25   # any area and date (west south east north)
python -m floodsys run --preset trishuli --res 10 --pairs 3 --trace 85.3835 28.2180   # sharper, more radar tracks, flood-path bonus
```

Then start the dashboard (Option B) to browse `outputs/`, or open `outputs/<run>/sitrep.pdf` and `dashboard_map.html` directly. All command-line options are listed in [`docs/API_SPEC.md`](./docs/API_SPEC.md).

**Option D: front-end development (hot reload)**

```bash
uvicorn app.server:app --port 8000      # terminal 1
cd web && npm run dev                   # terminal 2: http://localhost:5173, proxies /api to port 8000
```

**Option E: Docker (as deployed on Render)**

```bash
docker build -t beaconspace .
docker run -p 8000:8000 beaconspace     # http://localhost:8000, shows the bundled case study; new analyses are off by default
```

Set `BEACONSPACE_ANALYZE=on` to allow runs in the container (see the variables below). Deployment notes: [`render.yaml`](./render.yaml).

**Checking the results against the official maps (optional).** Download the EMSR927 vector products from the Copernicus EMS site into `data/reference/emsr927/` and run `python scripts/evaluate_emsr927.py --run outputs/trishuli`. These maps are used for checking only, never as input.

**Optional AI model.** `models/flood_unet.onnx` (about 98 MB) is not stored in the repository; see [`models/README.md`](./models/README.md). Without it the system runs its physics-based detector and the results differ by about 1 %. To train the model yourself on a free Colab GPU, follow [`docs/COLAB_GUIDE.md`](./docs/COLAB_GUIDE.md).

### Troubleshooting

| Symptom | Fix |
|---|---|
| Browser shows an API message or a blank page at `/` | the front end is not built: run `npm install && npm run build` in `web/` |
| "No analysis yet" on every page | no finished run found: use Option A, or run an analysis; check `FLOODSYS_OUT` |
| Analysis fails with "same-track Sentinel-1 pair" | no radar images before and after that date on one orbit: try another date or a larger area |
| A new area is very slow at the OSM step | the public Overpass server is slow; wait (tiles are cached and the run resumes) or use a smaller box |
| No `sitrep.pdf` | install Edge or Chrome; `sitrep.html` is always produced |
| `pip install` fails to build a package | use Python 3.12 or newer; on Linux install the GDAL/GEOS system libraries or use the Docker image |

Judges: start with [`docs/JUDGE_QUICKSTART.md`](./docs/JUDGE_QUICKSTART.md).

## Environment Variables

No API keys or accounts are needed. All variables are optional.

| Variable | Description | Default |
|---|---|---|
| `FLOODSYS_CACHE` | where downloaded rasters, terrain and OSM tiles are cached | `./cache` |
| `FLOODSYS_OUT` | where runs are written and the app looks for them | `./outputs` |
| `FLOODSYS_MODEL` | path to the ONNX model | `./models/flood_unet.onnx` |
| `BEACONSPACE_ANALYZE` | `off` disables new analyses (public demos); the Docker image sets it to `off` | `on` |
| `BEACONSPACE_TOKEN` | if set, starting an analysis needs this token | none |
| `BEACONSPACE_MAX_AREA_KM2` | largest area one request may cover | `6000` |
| `PORT` | port inside the container | `8000` |

## Data Access and Rules Flow

There is no login. Data are read from open endpoints: Sentinel-1 from Microsoft Planetary Computer (anonymous signed URLs), Sentinel-2 and the DEM from AWS public buckets, OpenStreetMap history via ohsome or Overpass.

| Rule | How it is enforced |
|---|---|
| Allowed inputs only: Sentinel-1/2, Copernicus DEM, OSM *before* the event, training datasets | `floodsys/data/*`; `provenance.json` lists every source |
| No EMS / UNOSAT damage maps as input; no post-event OSM edits | EMS is read only by `scripts/evaluate_emsr927.py`; OSM is requested with a snapshot date before the event (`RunConfig` rejects otherwise) |
| Runs end to end from raw data for any area and date | `python -m floodsys run --bbox … --event …` |
| Thresholds not tuned on EMSR927 | set from SAR physics, stable-terrain noise and null-event pairs, frozen before the comparison |

---

## Limitations

- **Debris = change near rivers.** Hill-slope landslides away from the drainage network are out of scope; farmland next to rivers can still false-alarm.
- Satellites revisit every few days: the maps show the scene **at the post-event pass**, cannot warn of a glacier collapse minutes ahead, and the flood may have changed since.
- 10–20 m pixels: single houses, small bridges and narrow roads are inferred from overlap with the footprint, not seen.
- Debris is detected as *change*; it cannot say whether it is mud, boulders or a landslide, nor its depth.
- Monsoon cloud limits optics (≈ 7 % clear in the final case study); radar is confused by wet snow and steep-slope geometry.
- The cut-off count is sensitive to the blocking rule (74–153 settlements, see Results); treat 126 as a central estimate, not an exact figure.
- Cut-off analysis uses *mapped* roads (OSM before the event): unmapped tracks, footpaths and later repairs are unknown; routes leaving the area are assumed intact.
- The trained model saw mostly low-relief floods and no debris-flow labels.
- Nepali text is template-based and needs review by a native speaker.

Full discussion in the [technical report](./docs/Report.pdf).

---

## What I Learned

The hardest challenge was **trusting our own results**. The first detector looked great against the official maps and then flagged thousands of hectares on image pairs where nothing had happened; only a null-event test exposed it, and fixing it traded some recall for far fewer false alarms. We also caught ourselves overclaiming: the AI's headline score used test data that shared events with training, and on the real Himalayan case the network added about 1 %.

What I would architect differently: build the per-pixel time-series baseline and an event-level train/test split on day one; make OpenStreetMap history (ohsome access or a regional extract) a first-class, cached input instead of a late fallback; and design the evaluation, not just the model, before writing the detector.

---

## Attribution

See [`ATTRIBUTION.md`](./ATTRIBUTION.md).

*Contains modified Copernicus Sentinel data 2026. Produced using Copernicus WorldDEM-30 © DLR e.V. 2010–2014 and © Airbus Defence and Space GmbH 2014–2018 provided under COPERNICUS by the European Union and ESA; all rights reserved. © OpenStreetMap contributors. Training data: Kuro Siwo — Bountos et al., NeurIPS 2024 (CC BY). Reference maps used for checking only: "European Union, Copernicus Emergency Management Service data" (EMSR927).*

License: MIT.
