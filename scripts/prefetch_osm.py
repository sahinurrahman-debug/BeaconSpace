"""Pre-fetch (and cache) the pre-event OSM snapshot for an area.  Run once; slow on the public Overpass server.

    python scripts/prefetch_osm.py --preset trishuli
"""
import argparse, datetime as dt, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from floodsys import config
from floodsys.data import osm
from floodsys.pipeline import _buffered, _pad
from floodsys.presets import PRESETS

ap = argparse.ArgumentParser()
ap.add_argument("--preset", default="trishuli")
ap.add_argument("--layers", default="roads,places,health,buildings")
a = ap.parse_args()
p = PRESETS[a.preset]
snap = osm.latest_snapshot(p["event"].date())
print("snapshot", snap, flush=True)
layers = a.layers.split(",")
big = [l for l in layers if l != "buildings"]
if big:
    osm.load_osm(_buffered(p["bbox"], config.Settings().access.osm_buffer_km), snap, layers=tuple(big))
if "buildings" in layers:
    osm.load_osm(_pad(p["bbox"], 0.005), snap, layers=("buildings",))
print("done", flush=True)
