"""Sentinel-2 L2A (optical) evidence: cloud-masked pre/post composites, water & vegetation-loss indices.

Source: AWS Earth Search ``sentinel-2-l2a`` COGs (Copernicus Sentinel data, no login). Used only where the
scene-classification layer says the pixel is clear -- in monsoon season much of the corridor will not be.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

import numpy as np
from scipy import ndimage as ndi
from shapely.geometry import box, shape

from .. import config
from .grid import Grid, read_to_grid

CLEAR_SCL = (2, 4, 5, 6, 7)   # dark areas, vegetation, bare soil, water, unclassified  (not cloud/shadow/snow)
UTC = dt.timezone.utc


def _catalog():
    import pystac_client
    return pystac_client.Client.open(config.AWS_STAC)


def search(bbox, start: dt.date, end: dt.date, max_cloud: float = 90.0):
    res = _catalog().search(collections=["sentinel-2-l2a"], bbox=list(bbox),
                            datetime=f"{start.isoformat()}/{end.isoformat()}",
                            query={"eo:cloud_cover": {"lt": max_cloud}}, max_items=400).item_collection()
    by_day = defaultdict(list)
    for it in res:
        by_day[it.datetime.astimezone(UTC).date()].append(it)
    return dict(sorted(by_day.items()))


def _scl(items, grid: Grid, workers: int = 6):
    out = np.full(grid.shape, np.nan, "float32")
    aoi = box(*grid.bbox_lonlat)
    for it in items:
        if shape(it.geometry).intersection(aoi).area < 1e-5:
            continue
        a = read_to_grid(it.assets["scl"].href, grid, resampling=__import__("rasterio").enums.Resampling.nearest,
                         nodata=0.0, workers=workers)
        take = np.isnan(out) & np.isfinite(a)
        out[take] = a[take]
    return out


def _bands(items, grid: Grid, names=("green", "red", "nir", "swir16", "blue"), workers: int = 6):
    out = {n: np.full(grid.shape, np.nan, "float32") for n in names}
    aoi = box(*grid.bbox_lonlat)
    for it in items:
        if shape(it.geometry).intersection(aoi).area < 1e-5:
            continue
        for n in names:
            a = read_to_grid(it.assets[n].href, grid, nodata=0.0, workers=workers)
            take = np.isnan(out[n]) & np.isfinite(a)
            out[n][take] = a[take]
    return out


def _composite(days, grid: Grid, order, min_clear: float, max_scenes: int, log=print):
    """Fill pixels with the first clear observation along ``order`` of dates."""
    bands = None
    clear_any = np.zeros(grid.shape, bool)
    used = []
    for d in order:
        if len(used) >= max_scenes:
            break
        cc = [it.properties.get("eo:cloud_cover", 100) for it in days[d]]
        if cc and min(cc) > 85:      # granule metadata says (almost) fully cloudy: don't even read it
            log(f"[s2]   {d}: skipped (catalogue cloud cover {min(cc):.0f}%)")
            continue
        scl = _scl(days[d], grid)
        clear = np.isin(scl, CLEAR_SCL)
        new = clear & ~clear_any
        frac_new = new.mean()
        log(f"[s2]   {d}: clear {clear.mean():.0%}, adds {frac_new:.0%}")
        if frac_new < min_clear:
            continue
        b = _bands(days[d], grid)
        if bands is None:
            bands = {k: np.full(grid.shape, np.nan, "float32") for k in b}
        for k in b:
            take = new & np.isfinite(b[k])
            bands[k][take] = b[k][take] / 10000.0
        clear_any |= new & np.isfinite(b["green"])
        used.append(d)
    return bands, clear_any, used


def _idx(b):
    g, r, n, s, bl = (b[k] for k in ("green", "red", "nir", "swir16", "blue"))
    with np.errstate(invalid="ignore", divide="ignore"):
        mndwi = (g - s) / (g + s)
        ndvi = (n - r) / (n + r)
        bsi = ((s + r) - (n + bl)) / ((s + r) + (n + bl))
    return mndwi, ndvi, bsi


def optical_evidence(bbox, event: dt.datetime, grid: Grid, p, post_days: int = 14, pre_days: int = 30,
                     log=print) -> dict | None:
    """Return boolean evidence layers on ``grid`` or ``None`` if no usable cloud-free pixels exist."""
    d0 = event.date()
    days = search(bbox, d0 - dt.timedelta(days=pre_days), d0 + dt.timedelta(days=post_days))
    pre_order = [d for d in sorted(days, reverse=True) if d < d0]
    post_order = [d for d in sorted(days) if d > d0]
    log(f"[s2] {len(pre_order)} pre-event and {len(post_order)} post-event dates in catalogue")
    if not pre_order or not post_order:
        return None
    log("[s2] post-event composite:")
    post, clear_post, used_post = _composite(days, grid, post_order, 0.05, 2, log)
    log("[s2] pre-event composite:")
    pre, clear_pre, used_pre = _composite(days, grid, pre_order, 0.05, 2, log)
    if post is None or pre is None:
        return None
    clear = clear_post & clear_pre
    if clear.mean() < 0.02:
        log("[s2] too little cloud-free overlap; skipping optical evidence")
        return None
    mw1, nv1, bs1 = _idx(post)
    mw0, nv0, bs0 = _idx(pre)
    with np.errstate(invalid="ignore"):
        water = (mw1 > p.s2_water_mndwi) & (mw0 < 0.0)
        veg_loss = ((nv0 - nv1) > p.s2_ndvi_drop) & (nv1 < 0.35)
        bare_gain = (bs1 - bs0) > 0.05
    debris = veg_loss & bare_gain
    # speckle-sized blobs are not evidence
    water = ndi.binary_opening(np.nan_to_num(water, nan=0).astype(bool), np.ones((2, 2))) & clear
    debris = ndi.binary_opening(np.nan_to_num(debris, nan=0).astype(bool), np.ones((2, 2))) & clear
    return {"water": water, "debris": debris, "clear": clear, "clear_fraction": float(clear.mean()),
            "post_dates": [d.isoformat() for d in used_post], "pre_dates": [d.isoformat() for d in used_pre],
            "ndvi_post": nv1, "mndwi_post": mw1}
