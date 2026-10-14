"""Re-render map / report / dashboard map from a finished run without recomputing (design iteration helper).
    python scripts/rebuild_outputs.py outputs/trishuli"""
import json, sys
from pathlib import Path
import geopandas as gpd, numpy as np, rasterio
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from floodsys.data.grid import Grid
from floodsys.report import mapplot, sitrep
out = Path(sys.argv[1]); S = json.loads((out / "summary.json").read_text(encoding="utf-8"))
with rasterio.open(out / "classes.tif") as src:
    cls = src.read(1); grid = Grid(src.crs.to_string(), src.transform, src.width, src.height, tuple(S["bbox"]))
with rasterio.open(out / "s1_post_vv_db.tif") as src: db = {"post_vv": src.read(1)}
from shapely.geometry import LineString
fl = None
if (out / "flowpath.geojson").exists():
    g = gpd.read_file(out / "flowpath.geojson")
    if len(g): fl = {"path_lonlat": list(g.geometry.iloc[0].coords)}
def rd(n, t=4326):
    f = out / n
    return gpd.read_file(f).to_crs(grid.crs) if f.exists() else None
import pandas as pd
roads = rd("roads_hit.geojson")
if roads is not None and len(roads): roads["hit"] = True
ctx = {"grid": grid, "cls": cls, "db": db, "buildings": rd("buildings_affected.geojson"), "roads": roads,
       "settlements": gpd.read_file(out / "settlements.geojson"), "blocked": gpd.read_file(out / "blocked_segments.geojson"),
       "destinations": gpd.read_file(out / "destinations.geojson"), "flow": fl, "bbox": tuple(S["bbox"]), "year": int(S["event_utc"][:4])}
mapplot.static_map(ctx, out / "map.png"); sitrep.write_all(S, out); mapplot.interactive_map(out, S, ctx, out / "dashboard_map.html")
print("rebuilt", out)
