"""Compare a finished run with the official Copernicus EMS reference maps (activation EMSR927).

THE REFERENCE DATA IS USED FOR CHECKING ONLY - it is never read by the pipeline. Putting it in the pipeline's inputs
would break the challenge's data rules (disqualification). This script reads our *outputs* and the reference files.

How to get the reference files (free): https://mapping.emergency.copernicus.eu  ->  EMSR927  ->  download the vector
packages (zip) for each AOI (e.g. "Syapru Besi" GRA product) and unzip them (or leave the .zip) in
data/reference/emsr927/ .  Credit: "European Union, Copernicus Emergency Management Service data".

    python scripts/evaluate_emsr927.py --run outputs/trishuli
"""
import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from floodsys import config  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--run", type=Path, required=True)
ap.add_argument("--ref", type=Path, default=config.ROOT / "data" / "reference" / "emsr927")
ap.add_argument("--match-m", type=float, default=20.0, help="building match tolerance (m)")
a = ap.parse_args()

# ---- unpack (nested zips) and discover reference layers ---------------------------------------------------------
ext = a.ref / "_extracted"
done = set()
while True:
    todo = [z for z in list(a.ref.rglob("*.zip")) if z not in done]
    if not todo:
        break
    for z in todo:
        done.add(z)
        d = ext / z.stem
        if not d.exists():
            zipfile.ZipFile(z).extractall(d)
# one file per layer (.shp preferred over the identical .json), only the main PRODUCT maps (not the later MONIT updates)
files = sorted(f for f in a.ref.rglob("*.shp") if "MONIT" not in f.name.upper())
if not files:
    files = sorted(f for f in a.ref.rglob("*.json") if "MONIT" not in f.name.upper() and "_extracted" in str(f))
if not files:
    sys.exit(f"No reference vector files found in {a.ref}. See the docstring for how to download them.")
print(f"{len(files)} reference layers from products:", sorted({re.search(r'AOI\d+', f.name).group(0) for f in files if re.search(r'AOI\d+', f.name)}))


def find(pattern):
    return [f for f in files if re.search(pattern, f.name, re.I)]


def read_all(fs):
    gs = []
    for f in fs:
        try:
            g = gpd.read_file(f)
            if len(g):
                gs.append(g.to_crs(4326))
        except Exception as exc:
            print("skip", f.name, exc)
    return pd.concat(gs, ignore_index=True) if gs else gpd.GeoDataFrame(geometry=[], crs=4326)


S = json.loads((a.run / "summary.json").read_text(encoding="utf-8"))
grid_crs = "EPSG:326" + str(int((S["bbox"][0] + S["bbox"][2]) / 2 // 6 + 31))
res = {"reference": "Copernicus EMS EMSR927 (check only)", "run": a.run.name}

aoi = read_all(find(r"areaOfInterest"))
obs = read_all(find(r"observedEvent"))
ours = gpd.read_file(a.run / "impact_polygons.geojson") if (a.run / "impact_polygons.geojson").exists() else None
print("reference files:", sorted({f.name for f in files})[:30])
if len(obs) and ours is not None and len(ours):
    ours = ours.to_crs(grid_crs)
    obs = obs.to_crs(grid_crs)
    clip = aoi.to_crs(grid_crs).union_all() if len(aoi) else obs.union_all().convex_hull
    o_u = unary_union(ours.geometry.values).intersection(clip)
    r_u = unary_union(obs.geometry.values).intersection(clip)
    inter = o_u.intersection(r_u).area / 1e4
    res["extent"] = {"evaluated_inside_EMS_AOI_ha": round(clip.area / 1e4, 1), "ours_ha": round(o_u.area / 1e4, 1),
                     "reference_ha": round(r_u.area / 1e4, 1), "overlap_ha": round(inter, 1),
                     "IoU": round(inter / max((o_u.union(r_u)).area / 1e4, 1e-9), 3),
                     "precision": round(inter / max(o_u.area / 1e4, 1e-9), 3),
                     "recall": round(inter / max(r_u.area / 1e4, 1e-9), 3)}
    # uncertainty: spatial block bootstrap (1 km blocks, resampled with replacement) of the three areas behind IoU / precision / recall
    from shapely.geometry import box as _box
    x0, y0, x1, y1 = clip.bounds
    rows = []
    for gx in np.arange(x0, x1, 1000.0):
        for gy in np.arange(y0, y1, 1000.0):
            cell = _box(gx, gy, gx + 1000.0, gy + 1000.0).intersection(clip)
            if cell.area < 1.0:
                continue
            oc_, rc_ = o_u.intersection(cell), r_u.intersection(cell)
            rows.append((oc_.intersection(rc_).area, oc_.area, rc_.area))
    if len(rows) >= 8:
        arr = np.array(rows) / 1e4
        rng = np.random.default_rng(0)
        vals = []
        for _ in range(1000):
            t = arr[rng.integers(0, len(arr), len(arr))].sum(axis=0)
            vals.append((t[0] / max(t[1] + t[2] - t[0], 1e-9), t[0] / max(t[1], 1e-9), t[0] / max(t[2], 1e-9)))
        lo, hi = np.percentile(vals, [2.5, 97.5], axis=0)
        res["extent_95ci_block_bootstrap"] = {"blocks_1km": len(arr), "IoU": [round(lo[0], 3), round(hi[0], 3)],
                                              "precision": [round(lo[1], 3), round(hi[1], 3)], "recall": [round(lo[2], 3), round(hi[2], 3)]}
    # tolerance version: a 10 m pixel-level dislocation should not count as an error
    tol = 30.0
    rec_t = r_u.intersection(o_u.buffer(tol)).area / max(r_u.area, 1e-9)
    pre_t = o_u.intersection(r_u.buffer(tol)).area / max(o_u.area, 1e-9)
    res["extent_with_30m_tolerance"] = {"precision": round(pre_t, 3), "recall": round(rec_t, 3)}
    for col in ("event_type", "obj_desc", "notation"):
        if col in obs.columns:
            res["reference_classes"] = {str(k): round(v / 1e4, 1) for k, v in
                                        obs.assign(area=obs.geometry.intersection(clip).area).groupby(col)["area"].sum().items()}
            break
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(9, 9))
    gpd.GeoSeries([clip]).plot(ax=ax, facecolor="none", edgecolor="k", linewidth=0.7)
    gpd.GeoSeries([r_u]).plot(ax=ax, color="#1f77b4", alpha=0.55, label="EMSR927 observed event")
    gpd.GeoSeries([o_u]).plot(ax=ax, color="#ff7f0e", alpha=0.55, label="This system")
    ax.legend(); ax.set_title("Flood/debris extent vs Copernicus EMS EMSR927 (check only)")
    ax.set_axis_off(); fig.text(0.01, 0.01, config.EMS_CREDIT, fontsize=7)
    fig.savefig(a.run / "evaluation_extent.png", dpi=130, bbox_inches="tight")
else:
    res["extent"] = "no observedEvent layer or no polygons in our run"

# ---- buildings -------------------------------------------------------------------------------------------------
built = read_all(find(r"builtUp"))
ba = a.run / "buildings_affected.geojson"
if len(built) and ba.exists():
    built = built.to_crs(grid_crs)
    dmg_col = next((c for c in built.columns if re.search(r"damage|dmg", c, re.I)), None)
    print("builtUp columns:", list(built.columns), "damage column:", dmg_col)
    if dmg_col:
        aff_ref = built[built[dmg_col].astype(str).str.contains("Destroyed|Damaged|Possibly", case=False, na=False)]
    else:
        aff_ref = built
    ours_b = gpd.read_file(ba).to_crs(grid_crs)
    ours_aff = ours_b[ours_b["status"].isin(["destroyed_likely", "affected"])]
    area = aoi.to_crs(grid_crs).union_all() if len(aoi) else None
    if area is not None:
        aff_ref = aff_ref[aff_ref.geometry.centroid.within(area)]
        ours_aff = ours_aff[ours_aff.geometry.centroid.within(area)]
        ref_all = built[built.geometry.centroid.within(area)]
    else:
        ref_all = built
    rc = aff_ref.geometry.centroid
    oc = ours_aff.geometry.centroid
    from scipy.spatial import cKDTree
    hit_ref = 0
    if len(rc) and len(oc):
        d, _ = cKDTree(np.c_[oc.x, oc.y]).query(np.c_[rc.x, rc.y])
        hit_ref = int((d <= a.match_m).sum())
    res["buildings"] = {"reference_affected": int(len(aff_ref)), "reference_total_in_AOI": int(len(ref_all)),
                        "ours_affected_in_EMS_AOI": int(len(ours_aff)),
                        "reference_found_by_us(within %d m)" % a.match_m: hit_ref,
                        "recall": round(hit_ref / max(len(aff_ref), 1), 3),
                        "note": "our building set is OSM (pre-event); EMS maps buildings from VHR imagery, so totals differ"}

# ---- roads / bridges ---------------------------------------------------------------------------------------------
tl = read_all(find(r"transportation.*L"))
rh = a.run / "roads_hit.geojson"
if len(tl) and rh.exists():
    tl = tl.to_crs(grid_crs)
    dmg_col = next((c for c in tl.columns if re.search(r"damage|dmg", c, re.I)), None)
    aff = tl[tl[dmg_col].astype(str).str.contains("Destroyed|Damaged|Possibly", case=False, na=False)] if dmg_col else tl
    ours_r = gpd.read_file(rh).to_crs(grid_crs)
    area = aoi.to_crs(grid_crs).union_all() if len(aoi) else None
    if area is not None:
        aff = aff.intersection(area)
        ours_r = ours_r.intersection(area)
    ref_u, our_u = unary_union(list(aff.geometry)), unary_union(list(ours_r.geometry))
    both = ref_u.intersection(our_u.buffer(30)).length / 1e3
    res["roads"] = {"reference_affected_km": round(ref_u.length / 1e3, 2), "ours_hit_km": round(our_u.length / 1e3, 2),
                    "reference_covered_by_ours_km(30m)": round(both, 2),
                    "recall": round(both / max(ref_u.length / 1e3, 1e-9), 3),
                    "precision": round(our_u.intersection(ref_u.buffer(30)).length / max(our_u.length, 1e-9), 3)}

(a.run / "evaluation_emsr927.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
print(json.dumps(res, indent=2))
