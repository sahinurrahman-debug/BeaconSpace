"""Copernicus DEM GLO-30, terrain derivatives, HAND and D8 flow routing."""
from __future__ import annotations

import math

import numpy as np
from rasterio.enums import Resampling

from .. import config
from .grid import Grid, read_to_grid


def _tile_urls(bbox):
    lon0, lat0, lon1, lat1 = bbox
    urls = []
    for lat in range(math.floor(lat0), math.floor(lat1) + 1):
        for lon in range(math.floor(lon0), math.floor(lon1) + 1):
            urls.append(config.DEM_URL.format(ns="N" if lat >= 0 else "S", lat=abs(lat),
                                              ew="E" if lon >= 0 else "W", lon=abs(lon)))
    return urls


def load_dem(grid: Grid, pad_deg: float = 0.0) -> np.ndarray:
    """Copernicus GLO-30 elevation (m) bilinearly resampled onto ``grid``."""
    lon0, lat0, lon1, lat1 = grid.lonlat_bounds()
    out = np.full(grid.shape, np.nan, dtype="float32")
    for url in _tile_urls((lon0 - pad_deg, lat0 - pad_deg, lon1 + pad_deg, lat1 + pad_deg)):
        try:
            tile = read_to_grid(url, grid, resampling=Resampling.bilinear, nodata=-32767.0, workers=4)
        except Exception as exc:  # tile missing over ocean etc.
            print(f"[dem] skipped {url.rsplit('/', 1)[-1]}: {exc}")
            continue
        m = np.isnan(out) & np.isfinite(tile)
        out[m] = tile[m]
    return out


def slope_deg(dem: np.ndarray, res: float) -> np.ndarray:
    d = np.where(np.isfinite(dem), dem, np.nanmedian(dem))
    gy, gx = np.gradient(d, res)
    return np.degrees(np.arctan(np.hypot(gx, gy))).astype("float32")


def resample_nearest(arr: np.ndarray, src: Grid, dst: Grid) -> np.ndarray:
    """Nearest-neighbour resample between two grids of the same CRS (cell-centre lookup)."""
    rows = (np.arange(dst.height) + 0.5) * dst.res
    cols = (np.arange(dst.width) + 0.5) * dst.res
    ys = dst.transform.f - rows
    xs = dst.transform.c + cols
    r = np.clip(np.floor((src.transform.f - ys) / src.res).astype(int), 0, src.height - 1)
    c = np.clip(np.floor((xs - src.transform.c) / src.res).astype(int), 0, src.width - 1)
    return arr[np.ix_(r, c)]


def terrain_layers(grid: Grid, hydro_res: float = 30.0, log=print, chan_upa_km2: float = 5.0) -> dict:
    """DEM, slope and HAND on ``grid`` (hydrology computed once at ``hydro_res`` and cached)."""
    import hashlib
    key = hashlib.sha1(repr((grid.bbox_lonlat, grid.crs)).encode()).hexdigest()[:14]
    f = config.CACHE_DIR / "terrain" / f"{key}.npz"
    f.parent.mkdir(parents=True, exist_ok=True)
    hg = grid.with_res(hydro_res)
    if f.exists():
        z = np.load(f)
        dem_h, hand_h, upa_h, d8 = z["dem"], z["hand"], z["upa"], z["d8"]
        log("[dem] terrain cache hit")
    else:
        log("[dem] loading Copernicus DEM + computing HAND (first run only)...")
        dem_h = load_dem(hg)
        hand_h, flw, upa_h, _ = hand_and_flow(dem_h, hg)
        d8 = flw.to_array(ftype="d8").astype("uint8")
        np.savez_compressed(f, dem=dem_h, hand=hand_h, upa=upa_h, d8=d8)
    if abs(grid.res - hydro_res) < 1e-6:
        dem, hand, upa = dem_h, hand_h, upa_h
    else:
        dem = resample_nearest(dem_h, hg, grid)
        hand = resample_nearest(hand_h, hg, grid)
        upa = resample_nearest(upa_h, hg, grid)
    slope = slope_deg(dem_h, hg.res)
    slope = resample_nearest(slope, hg, grid) if abs(grid.res - hydro_res) > 1e-6 else slope
    # NaN HAND (no DEM) -> treat as "high" so nothing is detected there
    hand = np.where(np.isfinite(hand), hand, 9999.0).astype("float32")
    from scipy import ndimage as ndi
    chan = np.nan_to_num(upa, nan=0.0) >= chan_upa_km2
    chan_dist = (ndi.distance_transform_edt(~chan) * grid.res).astype("float32") if chan.any() else np.full(grid.shape, 1e6, "float32")
    return {"chan_dist": chan_dist, "dem": dem, "slope": slope, "hand": hand, "upa": upa, "d8": d8, "hydro_grid": hg, "dem_hydro": dem_h}


def hand_and_flow(dem: np.ndarray, grid: Grid, stream_min_km2: float = 2.0):
    """Height Above Nearest Drainage and a D8 flow-direction object.

    Hydrology is computed on the supplied grid (use <= 30 m for speed). Returns
    ``(hand, flwdir, upa_km2, streams)``; HAND is NaN where the DEM is missing.
    """
    import pyflwdir

    d = dem.astype("float32").copy()
    nodata = -9999.0
    d[~np.isfinite(d)] = nodata
    flw = pyflwdir.from_dem(d, nodata=nodata, transform=grid.transform, latlon=False, outlets="min")
    upa = flw.upstream_area(unit="km2")
    streams = upa > stream_min_km2
    hand = flw.hand(drain=streams, elevtn=d)
    hand = hand.astype("float32")
    hand[d == nodata] = np.nan
    return hand, flw, upa.astype("float32"), streams
