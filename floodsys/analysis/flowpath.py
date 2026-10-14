"""Bonus: trace the flood path down the valley from any upstream point and list settlements along it.

Method: D8 flow directions from the Copernicus DEM (hydrologically conditioned by pyflwdir). From the
start point (snapped to the highest-upstream-area stream cell within a search radius) we follow
steepest descent to the edge of the analysis area. The *susceptible corridor* is every cell whose height
above that traced channel (HAND relative to the path) is below ``corridor_height_m``. Settlements are
those with a building/place inside the corridor, ordered by distance along the path.
"""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy import ndimage as ndi
from shapely.geometry import LineString, Point

from ..data.grid import Grid


def trace(lon: float, lat: float, terrain: dict, grid: Grid, settlements: gpd.GeoDataFrame | None = None,
          buildings: gpd.GeoDataFrame | None = None, corridor_height_m: float = 30.0, snap_radius_m: float = 600.0,
          log=print) -> dict:
    import pyflwdir

    hg: Grid = terrain["hydro_grid"]
    flw = pyflwdir.from_array(terrain["d8"], ftype="d8", transform=hg.transform, latlon=False,
                              cache=True)
    x, y = grid.to_utm().transform(lon, lat)
    r, c = hg.xy_to_rc(x, y)
    r, c = int(r), int(c)
    if not (0 <= r < hg.height and 0 <= c < hg.width):
        raise ValueError("start point is outside the analysis area")
    upa = terrain["upa"] if terrain["upa"].shape == hg.shape else None
    if upa is None:  # terrain dict carries upa on analysis grid; recompute on hydrology grid
        upa = flw.upstream_area(unit="km2")
    k = int(snap_radius_m / hg.res)
    r0, r1, c0, c1 = max(0, r - k), min(hg.height, r + k + 1), max(0, c - k), min(hg.width, c + k + 1)
    win = upa[r0:r1, c0:c1]
    rr, cc = np.unravel_index(np.nanargmax(win), win.shape)
    r, c = r0 + rr, c0 + cc
    idx = r * hg.width + c
    paths, dists = flw.path(idxs=[idx], unit="m") if _accepts_unit(flw) else flw.path(idxs=[idx])
    path = np.asarray(paths[0])
    pr, pc = np.divmod(path, hg.width)
    xs = hg.transform.c + (pc + 0.5) * hg.res
    ys = hg.transform.f - (pr + 0.5) * hg.res
    step = np.hypot(np.diff(xs), np.diff(ys))
    along = np.concatenate([[0], np.cumsum(step)])

    # corridor: height above the traced channel
    drain = np.zeros(hg.shape, bool)
    drain[pr, pc] = True
    hand_path = flw.hand(drain=drain, elevtn=terrain["dem_hydro"].astype("float32"))
    corridor = (hand_path <= corridor_height_m) & np.isfinite(hand_path)
    # keep only the part within ~3 km of the path to avoid joining unrelated low ground
    near = ndi.binary_dilation(drain, iterations=int(3000 / hg.res))
    corridor &= near

    from rasterio import features
    from shapely.geometry import shape
    shp = [shape(g) for g, v in features.shapes(corridor.astype("uint8"), mask=corridor, transform=hg.transform)]
    corridor_gdf = gpd.GeoDataFrame({"geometry": shp}, crs=hg.crs)
    line = LineString(np.column_stack([xs, ys])) if len(xs) > 1 else None

    out = {"path_lonlat": [], "corridor": corridor_gdf.to_crs(4326), "length_km": round(float(along[-1]) / 1e3, 2),
           "settlements": pd.DataFrame(), "start_snapped": None}
    to_ll = grid.from_utm()
    pts = [to_ll.transform(a, b) for a, b in zip(xs, ys)]
    out["path_lonlat"] = pts
    out["start_snapped"] = pts[0]

    rows = []
    if settlements is not None and len(settlements):
        s = settlements.to_crs(grid.crs)
        from shapely import STRtree
        zone = corridor_gdf.union_all() if len(corridor_gdf) else None
        tree_pts = np.column_stack([xs, ys])
        from scipy.spatial import cKDTree
        kd = cKDTree(tree_pts)
        for _, rw in s.iterrows():
            px, py = rw.geometry.x, rw.geometry.y
            d, j = kd.query([px, py])
            inside = bool(zone is not None and zone.buffer(50).contains(rw.geometry))
            if inside:
                rows.append({"name": rw["name"], "lon": float(settlements.loc[rw.name, "geometry"].x),
                             "lat": float(settlements.loc[rw.name, "geometry"].y),
                             "km_along_path": round(float(along[j]) / 1e3, 2), "dist_to_channel_m": round(float(d)),
                             "n_buildings": int(rw.get("n_buildings", 0))})
    df = pd.DataFrame(rows).sort_values("km_along_path") if rows else pd.DataFrame(
        columns=["name", "lon", "lat", "km_along_path", "dist_to_channel_m", "n_buildings"])
    out["settlements"] = df.reset_index(drop=True)
    if buildings is not None and len(buildings) and len(corridor_gdf):
        b = buildings.to_crs(grid.crs)
        zone = corridor_gdf.union_all()
        out["buildings_in_corridor"] = int(b.geometry.centroid.within(zone).sum())
    log(f"[flowpath] traced {out['length_km']} km, {len(df)} settlements in the susceptible corridor")
    return out


def _accepts_unit(flw) -> bool:
    import inspect
    return "unit" in inspect.signature(flw.path).parameters
