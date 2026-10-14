# BeaconSpace — judge quick-start (≈ 5 minutes to a first result)

**Nothing needs an account or API key.** Python 3.10–3.14.

```bash
git clone https://github.com/sahinurrahman-debug/BeaconSpace.git && cd BeaconSpace
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest -q                                          # 8 offline tests (+4 dashboard tests that need a finished run), ~30 s
```

## 1 · See finished results immediately (no download)
Open `examples/trishuli/`: `sitrep.pdf` (one page English + one page Nepali), `map.png`, `dashboard_map.html` (interactive map; open in any browser), `summary.json`, `provenance.json` (proves which inputs were used).

## 2 · Reproduce the case study (≈ 10 min; OpenStreetMap tiles are bundled)
```bash
python -m floodsys run --preset trishuli          # Sentinel-1/2 + DEM are streamed live; OSM comes from data/osm_tiles/
streamlit run app/dashboard.py                    # then choose "Open a finished run" → trishuli
```

## 3 · Your own area and date (the live evaluation)
Dashboard: sidebar → **Run a new analysis** → type a bounding box + flood date → **Run analysis**. Or:
```bash
python -m floodsys run --bbox 85.50 27.80 85.66 28.00 --event 2021-06-14T21:00 --name my_test
```
Expect **3–15 minutes** for a ≈ 300 km² area at the default 20 m: Sentinel data are streamed over the internet, and the
pre-event OpenStreetMap snapshot is fetched via the ohsome API (falling back to date-pinned Overpass "attic" queries, which can be slow
on the public server — a first run of a new area can take longer; repeats are cached). Tips:
* Use `--res 40` for a quick look, `--res 10` for detail, `--no-s2` to skip optical data.
* The area needs Sentinel-1 images **before and after** the date on the **same relative orbit** (the system tells you if not).
* The pre-event images should come from the **same season**: monsoon terraces and crops change a lot, and early-season-only baselines raise false alarms (see report §6).

## 4 · What to look for
| Question | Where |
|---|---|
| Where did the flood hit? | map layers *Flood water*, *Debris / scour*; `classes.tif`, `support.tif` (agreement of orbit tracks) |
| What was damaged? | *Buildings affected*, *Roads hit*, *Bridges hit*; counts in `summary.json` |
| Who is cut off? | tab **Who is cut off**; red markers = cut-off settlements, with the place where the road is blocked |
| AI component | `models/flood_unet.onnx` + card; report §4 (honest held-out numbers); ablation in §5 |
| Data rules | `provenance.json` → `forbidden_inputs_used: []`; EMS data only in `scripts/evaluate_emsr927.py` |
| Honesty about limits | report §7, README §5 |

## 5 · Files in this repo
`floodsys/` (pipeline) · `app/dashboard.py` · `notebooks/train_flood_unet.ipynb` (Colab training) · `scripts/` (evaluation, report build, OSM tools) ·
`docs/Report.pdf` · `docs/results/` (raw evaluation numbers) · `ATTRIBUTION.md`.
