"""End-to-end pipeline: area + flood date  ->  maps, damage, cut-off settlements, situation report."""
from __future__ import annotations

import datetime as dt
import json
import platform
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio

from . import config
from .analysis import access, damage, flowpath
from .data import dem as demmod
from .data import osm as osmmod
from .data import s1 as s1mod
from .data import s2 as s2mod
from .data.grid import Grid
from .flood import detect
from .flood.model import FloodModel, build_features

UTC = dt.timezone.utc


@dataclass
class RunConfig:
    bbox: tuple                     # lon0, lat0, lon1, lat1
    event: dt.datetime              # best estimate of the flood time (UTC)
    name: str = ""
    res: float = 20.0               # analysis resolution in metres (10 = full, 20 = fast)
    n_pairs: int = 2                # radar tracks to combine
    use_s2: bool = True
    use_model: bool = True
    snapshot: dt.date | None = None  # OSM snapshot (default: latest before event)
    trace_from: tuple | None = None  # (lon, lat) upstream point for the flow-path bonus
    out_dir: Path | None = None
    settings: config.Settings = field(default_factory=config.Settings)

    def slug(self) -> str:
        if self.name:
            return re.sub(r"[^A-Za-z0-9_-]+", "_", self.name)
        return f"aoi_{self.bbox[0]:.2f}_{self.bbox[1]:.2f}_{self.event:%Y%m%d}_{int(self.res)}m"


def _write_raster(path: Path, arr: np.ndarray, grid: Grid, nodata=None):
    with rasterio.open(path, "w", driver="GTiff", height=grid.height, width=grid.width, count=1, dtype=arr.dtype,
                       crs=grid.crs, transform=grid.transform, nodata=nodata, compress="deflate") as dst:
        dst.write(arr, 1)


def _gdf_out(gdf: gpd.GeoDataFrame, path: Path, simplify: float = 0.0):
    if gdf is None or not len(gdf):
        path.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
        return
    g = gdf.copy()
    if simplify:
        g["geometry"] = g.geometry.simplify(simplify)
    for c in g.columns:
        if g[c].dtype == "object" and c != "geometry":
            g[c] = g[c].astype(str)
    g.to_crs(4326).to_file(path, driver="GeoJSON")


def run(cfg: RunConfig, log=print) -> dict:
    t_start = time.time()
    S = cfg.settings
    out = (cfg.out_dir or config.OUTPUT_DIR) / cfg.slug()
    out.mkdir(parents=True, exist_ok=True)
    event = cfg.event if cfg.event.tzinfo else cfg.event.replace(tzinfo=UTC)
    grid = Grid.from_lonlat_bbox(cfg.bbox, cfg.res)
    log(f"[run] AOI {cfg.bbox}  grid {grid.width}x{grid.height} @ {grid.res:.0f} m ({grid.crs})")
    area_km2 = grid.width * grid.height * (grid.res / 1000) ** 2
    prov = {"created": dt.datetime.now(UTC).isoformat(), "bbox": list(cfg.bbox), "event_utc": event.isoformat(),
            "resolution_m": cfg.res, "area_km2": round(area_km2, 1), "python": platform.python_version(),
            "inputs_allowed": ["Sentinel-1 RTC (Copernicus Sentinel data)", "Sentinel-2 L2A", "Copernicus DEM GLO-30",
                               "OpenStreetMap snapshot predating the event", "Kuro Siwo (model training only)"],
            "forbidden_inputs_used": [], "parameters": {k: vars(v) for k, v in vars(S).items()}}

    # ---- terrain -----------------------------------------------------------
    terrain = demmod.terrain_layers(grid, log=log)
    slope, hand = terrain["slope"], terrain["hand"]

    # ---- Sentinel-2 evidence (optional) ----------------------------------------
    s2ev = None
    if cfg.use_s2:
        try:
            s2ev = s2mod.optical_evidence(cfg.bbox, event, grid, S.detect, log=log)
        except Exception as exc:
            log(f"[s2] skipped ({exc})")
    prov["sentinel2"] = None if s2ev is None else {"post_dates": s2ev["post_dates"], "pre_dates": s2ev["pre_dates"],
                                                    "clear_fraction": round(s2ev["clear_fraction"], 3)}

    # ---- Sentinel-1 pairs -> detections -----------------------------------------
    d0 = event.date()
    acqs = s1mod.search_acquisitions(cfg.bbox, d0 - dt.timedelta(days=75), d0 + dt.timedelta(days=40))
    pairs = s1mod.plan_pairs(acqs, event, top=cfg.n_pairs)
    if not pairs:
        raise RuntimeError("No same-track Sentinel-1 pre/post pair covers this area and date. "
                           "(Needs data before and after the event on the same relative orbit.)")
    model = FloodModel.load_if_available(config.MODEL_PATH) if cfg.use_model else None
    prov["model"] = None if model is None else {"file": model.path.name, **model.card}
    log(f"[run] AI model: {'loaded ' + model.path.name if model else 'not found -> physics-based detector only'}")
    results, pair_info = [], []
    for pr in pairs:
        log(f"[run] pair: {pr.describe()}")
        stack = s1mod.load_pair(pr, grid, log=log)
        db = s1mod.prepare_db(stack, grid.res)
        prob = None
        if model is not None:
            prob = model.predict(build_features(db, slope, grid.res))
        res = detect.detect(db, slope, hand, grid.res, S.detect, model_prob=prob, s2=s2ev, chan_dist=terrain["chan_dist"])
        res["db"] = db
        res["model_prob"] = prob
        results.append(res)
        pair_info.append(pr.describe())
    merged = detect.merge_tracks(results) if len(results) > 1 else {
        "cls": results[0]["cls"], "support": np.isin(results[0]["cls"], (1, 2)).astype("uint8"),
        "seen": results[0]["valid"].astype("uint8"), "evidence": results[0]["evidence"]}
    cls = merged["cls"]
    prov["sentinel1_pairs"] = pair_info
    ha = grid.res ** 2 / 1e4
    area = {n: round(float((cls == k).sum() * ha), 1) for k, n in detect.CLASS_NAMES.items()}
    area["impact_total_ha"] = round(area["flood water"] + area["debris / scour"], 1)
    log(f"[run] areas (ha): {area}")

    # ---- vectors + rasters ----------------------------------------------------------
    polys = damage.vectorize(cls, grid, classes=(detect.FLOOD, detect.DEBRIS), min_ha=0.0)
    impact = damage.impact_geometry(polys)
    _write_raster(out / "classes.tif", cls, grid, nodata=None)
    _write_raster(out / "support.tif", merged["support"], grid)
    _write_raster(out / "s1_post_vv_db.tif", results[0]["db"]["post_vv"].astype("float32"), grid, nodata=np.nan)
    _gdf_out(polys, out / "impact_polygons.geojson", simplify=grid.res / 3)

    # ---- OSM (pre-event) -----------------------------------------------------------
    snap = cfg.snapshot or osmmod.latest_snapshot(event.date())
    if snap >= event.date():
        raise ValueError("OSM snapshot must predate the event (data rule).")
    ob = _buffered(cfg.bbox, S.access.osm_buffer_km)
    osm = osmmod.load_osm(ob, snap, layers=("roads", "places", "health"), log=log)
    region = None
    if impact is not None:   # buildings only matter near the impacted corridor (keeps the slow public OSM fetch small)
        from shapely.ops import transform as _tf
        big = polys[polys["area_ha"] >= 3.0]          # ignore tiny scattered detections
        core = damage.impact_geometry(big) if len(big) else impact
        region = _tf(grid.from_utm().transform, core.buffer(1500).simplify(150))
    osm.update(osmmod.load_osm(_pad(cfg.bbox, 0.005), snap, layers=("buildings",), log=log, region=region))
    prov["osm"] = {"snapshot": snap.isoformat(),
                   "provider": {k: v.attrs.get("provider") for k, v in osm.items()},
                   "features": {k: int(len(v)) for k, v in osm.items()}}
    aoi_poly = gpd.GeoSeries.from_xy([cfg.bbox[0], cfg.bbox[2]], [cfg.bbox[1], cfg.bbox[3]], crs=4326)
    clip = _bbox_gdf(cfg.bbox)
    b_all = osm["buildings"]
    b_aoi = gpd.clip(b_all, clip) if len(b_all) else b_all

    # ---- damage ----------------------------------------------------------------------
    bstat = damage.assess_buildings(b_aoi, impact, grid, S.damage)
    r_aoi = osm["roads"]
    rstat = damage.assess_roads(r_aoi, impact, grid, S.damage)
    brs = damage.assess_bridges(rstat, impact, grid, S.damage)
    # restrict reported numbers to the AOI
    clip_utm = clip.to_crs(grid.crs).geometry.iloc[0]
    rstat_aoi = rstat[rstat.geometry.intersects(clip_utm)]
    brs_aoi = brs[brs.geometry.intersects(clip_utm)]
    dmg = damage.summarize(bstat, rstat_aoi, brs_aoi)
    log(f"[run] damage: {dmg['buildings']}  roads hit {dmg['roads_total_hit_km']} km  bridges {dmg['bridges']}")
    _gdf_out(bstat[bstat["status"] != "unaffected"][["status", "overlap", "geometry"]], out / "buildings_affected.geojson",
             simplify=1.0)
    _gdf_out(rstat_aoi[rstat_aoi["hit"]][["highway", "road_class", "bridge", "hit_m", "geometry"]
                       if "bridge" in rstat_aoi else ["highway", "road_class", "hit_m", "geometry"]],
             out / "roads_hit.geojson", simplify=2.0)
    _gdf_out(brs_aoi[brs_aoi["bridge_hit"]][["highway", "geometry"]] if len(brs_aoi) else brs_aoi,
             out / "bridges_hit.geojson")

    # ---- who is cut off ---------------------------------------------------------------
    acc = access.analyse_access(osm["roads"], osm["places"], osm["health"], bstat, grid, impact, cfg.bbox,
                                S.access, log=log)
    _gdf_out(acc["settlements"], out / "settlements.geojson")
    _gdf_out(acc["blocked"], out / "blocked_segments.geojson")
    _gdf_out(acc["destinations"], out / "destinations.geojson")
    log(f"[run] access: {acc['summary']}")

    # ---- bonus: flow path ---------------------------------------------------------------
    fp = None
    if cfg.trace_from:
        try:
            sett_pts = acc["settlements"][["name", "n_buildings", "geometry"]].copy() if len(acc["settlements"]) else None
            fp = flowpath.trace(cfg.trace_from[0], cfg.trace_from[1], terrain, grid, sett_pts, b_aoi, log=log)
            _gdf_out(gpd.GeoDataFrame({"km": [fp["length_km"]]}, geometry=[
                __import__("shapely.geometry", fromlist=["LineString"]).LineString(fp["path_lonlat"])], crs=4326),
                out / "flowpath.geojson")
            _gdf_out(fp["corridor"], out / "flowpath_corridor.geojson", simplify=0.0002)
            fp["settlements"].to_csv(out / "flowpath_settlements.csv", index=False)
        except Exception as exc:
            log(f"[flowpath] failed: {exc}")

    # ---- summary ----------------------------------------------------------------------
    conf = {"two_track_agreement_ha": 0.0}
    if len(results) > 1:
        both = (merged["support"] >= 2)
        conf["two_track_agreement_ha"] = round(float(both.sum() * ha), 1)
    summary = {
        "name": cfg.slug(), "bbox": list(cfg.bbox), "event_utc": event.isoformat(), "resolution_m": cfg.res,
        "area_km2": round(area_km2, 1), "area_ha": area, "damage": dmg, "access": acc["summary"],
        "cut_off": [r for r in acc["settlements"].drop(columns="geometry").to_dict("records")
                    if r["status"] == "cut_off"] if len(acc["settlements"]) else [],
        "settlements": acc["settlements"].drop(columns="geometry").to_dict("records") if len(acc["settlements"]) else [],
        "flowpath": None if fp is None else {"length_km": fp["length_km"], "settlements": fp["settlements"].to_dict("records"),
                                              "buildings_in_corridor": fp.get("buildings_in_corridor")},
        "confidence": conf, "s1_pairs": pair_info, "s2": prov["sentinel2"],
        "noise": results[0]["noise"], "model": prov["model"], "osm": prov["osm"],
        "runtime_s": round(time.time() - t_start, 1),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    prov["summary_file"] = "summary.json"
    (out / "provenance.json").write_text(json.dumps(prov, indent=2, default=str), encoding="utf-8")

    from .report import mapplot, sitrep
    ctx = {"grid": grid, "cls": cls, "db": results[0]["db"], "buildings": bstat, "roads": rstat_aoi,
           "settlements": acc["settlements"], "blocked": acc["blocked"], "destinations": acc["destinations"],
           "flow": fp, "bbox": cfg.bbox, "year": event.year}
    mapplot.static_map(ctx, out / "map.png")
    sitrep.write_all(summary, out, log=log)
    mapplot.interactive_map(out, summary, ctx, out / "dashboard_map.html")
    log(f"[run] done in {summary['runtime_s']} s -> {out}")
    return {"out": out, "summary": summary, "ctx": ctx}


def _buffered(bbox, km):
    lon0, lat0, lon1, lat1 = bbox
    dlat = km / 111.0
    dlon = km / (111.0 * max(np.cos(np.radians((lat0 + lat1) / 2)), 0.2))
    return (lon0 - dlon, lat0 - dlat, lon1 + dlon, lat1 + dlat)


def _pad(bbox, d):
    return (bbox[0] - d, bbox[1] - d, bbox[2] + d, bbox[3] + d)


def _bbox_gdf(bbox):
    from shapely.geometry import box
    return gpd.GeoDataFrame(geometry=[box(*bbox)], crs=4326)
