"""How much do the cut-off counts depend on our own choices?   python scripts/sensitivity_access.py outputs/trishuli

Re-runs only the road-access analysis (cached OSM, saved classes.tif / support.tif) with different rules for when a road segment
counts as blocked, and writes docs/results/access_sensitivity_<run>.json:

  base         flood/debris mask dilated by 0.5 pixel (what the pipeline uses)
  tight        mask not dilated (fewer blocked segments)
  wide         mask dilated by 2 pixels (more blocked segments)
  both_tracks  only pixels flagged by every radar track (conservative)
"""
import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from floodsys import config  # noqa: E402
from floodsys.analysis import access, damage  # noqa: E402
from floodsys.data import osm as osmmod  # noqa: E402
from floodsys.data.grid import Grid  # noqa: E402
from floodsys.flood import detect  # noqa: E402
from floodsys.pipeline import _bbox_gdf, _buffered, _pad  # noqa: E402

out = Path(sys.argv[1])
S = json.loads((out / "summary.json").read_text(encoding="utf-8"))
bbox = tuple(S["bbox"])
with rasterio.open(out / "classes.tif") as src:
    cls = src.read(1)
    grid = Grid(src.crs.to_string(), src.transform, src.width, src.height, bbox)
with rasterio.open(out / "support.tif") as src:
    support = src.read(1)
n_tracks = len(S["s1_pairs"])
params = config.Settings()

import datetime as dt
event = dt.datetime.fromisoformat(S["event_utc"].replace("Z", "+00:00"))
snap = dt.date.fromisoformat(S["osm"]["snapshot"])
ob = _buffered(bbox, params.access.osm_buffer_km)
osm = osmmod.load_osm(ob, snap, layers=("roads", "places", "health"))


def impact_for(mask_cls):
    polys = damage.vectorize(mask_cls, grid, classes=(detect.FLOOD, detect.DEBRIS), min_ha=0.0)
    return polys, damage.impact_geometry(polys)


polys, impact = impact_for(cls)
big = polys[polys["area_ha"] >= 3.0]
core = damage.impact_geometry(big) if len(big) else impact
from shapely.ops import transform as _tf
region = _tf(grid.from_utm().transform, core.buffer(1500).simplify(150))
osm.update(osmmod.load_osm(_pad(bbox, 0.005), snap, layers=("buildings",), region=region))
clip = _bbox_gdf(bbox)
b_aoi = gpd.clip(osm["buildings"], clip) if len(osm["buildings"]) else osm["buildings"]
bstat = damage.assess_buildings(b_aoi, impact, grid, params.damage)

both = np.where((support >= n_tracks) & np.isin(cls, (detect.FLOOD, detect.DEBRIS)), cls, 0).astype(cls.dtype)
_, impact_both = impact_for(both)
res = grid.res
scenarios = {"base": (impact, res * 0.5), "tight": (impact, 0.0), "wide": (impact, res * 2.0), "both_tracks": (impact_both, res * 0.5)}
rows = {}
for name, (imp, buf) in scenarios.items():
    r = access.analyse_access(osm["roads"], osm["places"], osm["health"], bstat, grid, imp, bbox, params.access,
                              blocked_buffer_m=buf, log=lambda *_: None)["summary"]
    rows[name] = {k: r[k] for k in ("blocked_segments", "cut_off", "longer_route", "connected", "buildings_in_cut_off")}
    print(name, rows[name])
cuts = [v["cut_off"] for v in rows.values()]
result = {"run": out.name, "scenarios": rows, "cut_off_range": [min(cuts), max(cuts)],
          "note": "Counts of settlements whose road connection to a hospital/town is lost, under four rules for when a road segment is blocked."}
dst = ROOT / "docs" / "results" / f"access_sensitivity_{out.name}.json"
dst.write_text(json.dumps(result, indent=2), encoding="utf-8")
print("wrote", dst)
