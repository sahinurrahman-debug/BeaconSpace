"""Compress the cached pre-event OSM tiles into data/osm_tiles/ so they can be committed (ODbL: keep attribution).
    python scripts/export_osm_tiles.py"""
import gzip, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
src, dst = ROOT / "cache" / "osm" / "tiles", ROOT / "data" / "osm_tiles"
dst.mkdir(parents=True, exist_ok=True)
n = size = 0
for f in src.glob("*.json"):
    out = dst / (f.name + ".gz")
    out.write_bytes(gzip.compress(f.read_bytes(), 9))
    n += 1; size += out.stat().st_size
(dst / "README.txt").write_text("Pre-event OpenStreetMap tiles (Overpass attic snapshot 2026-07-27) for the Trishuli case study.\n"
                                "(c) OpenStreetMap contributors, ODbL 1.0 - https://www.openstreetmap.org/copyright\n", encoding="utf-8")
print(f"{n} tiles -> {dst} ({size / 1e6:.1f} MB)")
