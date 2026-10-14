"""Copy a curated, small set of finished-run files into examples/<name>/ (committed, so a judge sees results with no download).
    python scripts/export_examples.py trishuli"""
import shutil, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
name = sys.argv[1] if len(sys.argv) > 1 else "trishuli"
src, dst = ROOT / "outputs" / name, ROOT / "examples" / name
dst.mkdir(parents=True, exist_ok=True)
files = ["sitrep.pdf", "sitrep.html", "map.png", "dashboard_map.html", "summary.json", "provenance.json", "evaluation_emsr927.json",
         "evaluation_extent.png", "settlements.geojson", "impact_polygons.geojson", "roads_hit.geojson", "flowpath.geojson"]
tot = 0
for f in files:
    if (src / f).exists():
        shutil.copy2(src / f, dst / f); tot += (src / f).stat().st_size
(dst / "README.txt").write_text("Output of `python -m floodsys run --preset trishuli`.\nContains modified Copernicus Sentinel data 2026. (c) OpenStreetMap contributors. "
    "Copernicus WorldDEM-30 (c) DLR e.V. 2010-2014 and (c) Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved.\n"
    "evaluation_* files compare with 'European Union, Copernicus Emergency Management Service data' (EMSR927, checking only).\n", encoding="utf-8")
print(f"{len(files)} candidates -> {dst}  ({tot / 1e6:.1f} MB)")
