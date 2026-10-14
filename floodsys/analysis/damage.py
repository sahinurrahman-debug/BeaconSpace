"""Which buildings, roads and bridges were hit?  (overlay of pre-event OSM on the impact mask)"""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import shapely
from rasterio import features
from shapely.geometry import shape
from shapely.ops import unary_union

from ..config import DamageParams
from ..data.grid import Grid
from ..flood.detect import DEBRIS, FLOOD


def vectorize(cls: np.ndarray, grid: Grid, classes=(FLOOD, DEBRIS), min_ha: float = 0.0) -> gpd.GeoDataFrame:
    """Raster class map -> polygons in the grid CRS with area (ha) and class id."""
    rows = []
    for c in classes:
        m = (cls == c).astype("uint8")
        if not m.any():
            continue
        for geom, v in features.shapes(m, mask=m.astype(bool), transform=grid.transform, connectivity=8):
            g = shape(geom)
            ha = g.area / 1e4
            if ha >= min_ha:
                rows.append({"cls": int(c), "area_ha": ha, "geometry": g})
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=grid.crs) if rows else \
        gpd.GeoDataFrame({"cls": [], "area_ha": []}, geometry=[], crs=grid.crs)


def impact_geometry(polys: gpd.GeoDataFrame, buffer_m: float = 0.0):
    if polys.empty:
        return None
    g = unary_union(polys.geometry.values)
    return g.buffer(buffer_m) if buffer_m else g


def assess_buildings(buildings: gpd.GeoDataFrame, impact, grid: Grid, p: DamageParams) -> gpd.GeoDataFrame:
    """Status per building: ``destroyed_likely`` (>= severe_overlap inside the mask), ``affected`` (touches the
    mask +- uncertainty buffer), ``exposed`` (within exposed_buffer_m), else ``unaffected``."""
    if buildings.empty:
        return buildings.assign(status=[])
    b = buildings.to_crs(grid.crs).copy()
    b = b[b.geometry.notna() & ~b.geometry.is_empty].copy()
    b["status"] = "unaffected"
    b["overlap"] = 0.0
    if impact is None:
        return b
    near = shapely.buffer(impact, p.exposed_buffer_m)
    shapely.prepare(near)
    cand = np.asarray(shapely.intersects(b.geometry.values, near))
    idx = np.where(cand)[0]
    if idx.size:
        geoms = b.geometry.values[idx]
        inter = shapely.area(shapely.intersection(geoms, impact))
        area = np.maximum(shapely.area(geoms), 1.0)
        frac = inter / area
        buf_hit = np.asarray(shapely.intersects(geoms, shapely.buffer(impact, p.building_buffer_m)))
        status = np.where(frac >= p.severe_overlap, "destroyed_likely",
                          np.where((frac > 0) | buf_hit, "affected", "exposed"))
        b.iloc[idx, b.columns.get_loc("status")] = status
        b.iloc[idx, b.columns.get_loc("overlap")] = frac
    return b


def _road_class(tags) -> str:
    h = str(tags)
    if h in ("motorway", "trunk", "primary", "motorway_link", "trunk_link", "primary_link"):
        return "primary"
    if h in ("secondary", "tertiary", "secondary_link", "tertiary_link"):
        return "secondary"
    if h in ("track",):
        return "track"
    return "local"


def assess_roads(roads: gpd.GeoDataFrame, impact, grid: Grid, p: DamageParams) -> gpd.GeoDataFrame:
    r = roads.to_crs(grid.crs).copy()
    r["road_class"] = r["highway"].map(_road_class) if "highway" in r else "local"
    r["length_m"] = r.geometry.length
    r["hit_m"] = 0.0
    r["hit"] = False
    if impact is not None and len(r):
        buf = shapely.buffer(impact, grid.res * 0.5)
        shapely.prepare(buf)
        cand = np.where(np.asarray(shapely.intersects(r.geometry.values, buf)))[0]
        if cand.size:
            hit_len = shapely.length(shapely.intersection(r.geometry.values[cand], buf))
            r.iloc[cand, r.columns.get_loc("hit_m")] = hit_len
            r.iloc[cand, r.columns.get_loc("hit")] = hit_len >= p.road_min_overlap_m
    return r


def assess_bridges(roads_assessed: gpd.GeoDataFrame, impact, grid: Grid, p: DamageParams) -> gpd.GeoDataFrame:
    """Bridges are OSM highway ways tagged ``bridge=*`` (pre-event)."""
    if "bridge" not in roads_assessed:
        return roads_assessed.iloc[0:0].assign(bridge_hit=[])
    br = roads_assessed[roads_assessed["bridge"].notna() & ~roads_assessed["bridge"].isin(["no"])].copy()
    br["bridge_hit"] = False
    if impact is not None and len(br):
        buf = shapely.buffer(impact, p.bridge_buffer_m)
        shapely.prepare(buf)
        br["bridge_hit"] = np.asarray(shapely.intersects(br.geometry.values, buf))
    return br


def summarize(b: gpd.GeoDataFrame, r: gpd.GeoDataFrame, br: gpd.GeoDataFrame) -> dict:
    out = {"buildings": {"total": int(len(b)),
                         **{s: int((b["status"] == s).sum()) for s in
                            ("destroyed_likely", "affected", "exposed", "unaffected")}}}
    out["buildings"]["affected_total"] = out["buildings"]["destroyed_likely"] + out["buildings"]["affected"]
    roads = {}
    for cls, g in r.groupby("road_class"):
        roads[cls] = {"total_km": round(float(g["length_m"].sum()) / 1e3, 2),
                      "hit_km": round(float(g.loc[g["hit"], "hit_m"].sum()) / 1e3, 2),
                      "segments_hit": int(g["hit"].sum())}
    out["roads"] = roads
    out["roads_total_hit_km"] = round(float(r.loc[r["hit"], "hit_m"].sum()) / 1e3, 2)
    out["bridges"] = {"total": int(len(br)), "hit": int(br["bridge_hit"].sum()) if len(br) else 0}
    return out
