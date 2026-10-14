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
    path = _follow_d8(terrain["d8"], int(r), int(c))      # cell indices; metric distances are computed below
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

    # settlements / buildings inside the susceptible corridor: fast raster look-up (corridor mask dilated by 2 cells)
    cor = ndi.binary_dilation(corridor, iterations=2)

    def inside(xs_, ys_):
        r_, c_ = hg.xy_to_rc(np.asarray(xs_), np.asarray(ys_))
        ok = (r_ >= 0) & (r_ < hg.height) & (c_ >= 0) & (c_ < hg.width)
        res = np.zeros(len(r_), bool)
        res[ok] = cor[r_[ok], c_[ok]]
        return res

    rows = []
    if settlements is not None and len(settlements):
        from scipy.spatial import cKDTree
        s = settlements.to_crs(grid.crs).reset_index(drop=True)
        px, py = s.geometry.x.values, s.geometry.y.values
        msk = inside(px, py)
        kd = cKDTree(np.column_stack([xs, ys]))
        for i in np.where(msk)[0]:
            d, j = kd.query([px[i], py[i]])
            rows.append({"name": s.loc[i, "name"], "lon": float(settlements.iloc[i].geometry.x),
                         "lat": float(settlements.iloc[i].geometry.y), "km_along_path": round(float(along[j]) / 1e3, 2),
                         "dist_to_channel_m": round(float(d)), "n_buildings": int(s.loc[i].get("n_buildings", 0))})
    df = pd.DataFrame(rows).sort_values("km_along_path") if rows else pd.DataFrame(
        columns=["name", "lon", "lat", "km_along_path", "dist_to_channel_m", "n_buildings"])
    out["settlements"] = df.reset_index(drop=True)
    if buildings is not None and len(buildings):
        cen = buildings.to_crs(grid.crs).geometry.centroid
        out["buildings_in_corridor"] = int(inside(cen.x.values, cen.y.values).sum())
    log(f"[flowpath] traced {out['length_km']} km, {len(df)} settlements in the susceptible corridor")
    return out


_D8 = {1: (0, 1), 2: (1, 1), 4: (1, 0), 8: (1, -1), 16: (0, -1), 32: (-1, -1), 64: (-1, 0), 128: (-1, 1)}


def _follow_d8(d8: np.ndarray, r: int, c: int, max_steps: int = 200000) -> np.ndarray:
    """Follow ESRI-style D8 codes downstream from (r, c) until a pit / the domain edge; returns flat cell indices."""
    h, w = d8.shape
    out = [r * w + c]
    seen = {out[0]}
    for _ in range(max_steps):
        step = _D8.get(int(d8[r, c]))
        if step is None:
            break
        r, c = r + step[0], c + step[1]
        if not (0 <= r < h and 0 <= c < w) or r * w + c in seen:
            break
        seen.add(r * w + c)
        out.append(r * w + c)
    return np.asarray(out)
