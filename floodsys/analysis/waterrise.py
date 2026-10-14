"""Water-rise preview: how much terrain, how many buildings and settlements lie within +h metres of the nearest river.

Uses HAND (height above nearest drainage) from the Copernicus DEM. This is a *terrain-only* approximation -- it ignores flow,
channel capacity, culverts and travel time, so it is a "what-if" aid for operators.
Outputs (next to the run's other files): ``waterrise.png`` (8-bit, EPSG:3857, value = floor(HAND m), 255 = outside the preview)
and ``waterrise.json`` (image bounds + cumulative counts for h = 0..MAX_H).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image
from pyproj import Transformer
from rasterio.transform import array_bounds
from rasterio.warp import Resampling, calculate_default_transform, reproject

MAX_H = 60


def build(out: Path, grid, hand: np.ndarray, buildings_xy: np.ndarray | None, settlements_ll: np.ndarray | None, log=print) -> dict:
    """``buildings_xy``: (N, 2) building centroids in the grid CRS; ``settlements_ll``: (M, 2) lon/lat of settlements."""
    h = np.where(np.isfinite(hand) & (hand < 9000), hand, np.inf)
    q = np.where(h > MAX_H, 255, np.clip(np.floor(h), 0, MAX_H)).astype("uint8")
    ha = grid.res ** 2 / 1e4

    def cum(vals: np.ndarray) -> list:
        vals = vals[vals <= MAX_H]
        return np.bincount(vals, minlength=MAX_H + 1)[: MAX_H + 1].cumsum().tolist()

    def sample(xs, ys):
        r, c = grid.xy_to_rc(xs, ys)
        ok = (r >= 0) & (r < grid.height) & (c >= 0) & (c < grid.width)
        return q[r[ok], c[ok]]

    area = (np.bincount(q[q <= MAX_H], minlength=MAX_H + 1)[: MAX_H + 1].cumsum() * ha).round(1).tolist()
    nb = ns = 0
    b_cum = s_cum = [0] * (MAX_H + 1)
    if buildings_xy is not None and len(buildings_xy):
        b_cum, nb = cum(sample(buildings_xy[:, 0], buildings_xy[:, 1])), int(len(buildings_xy))
    if settlements_ll is not None and len(settlements_ll):
        x, y = grid.to_utm().transform(settlements_ll[:, 0], settlements_ll[:, 1])
        s_cum, ns = cum(sample(np.asarray(x), np.asarray(y))), int(len(settlements_ll))

    tr, w, hh = calculate_default_transform(grid.crs, "EPSG:3857", grid.width, grid.height, *grid.bounds, resolution=grid.res * 2)
    dst = np.full((hh, w), 255, "uint8")
    reproject(q, dst, src_transform=grid.transform, src_crs=grid.crs, dst_transform=tr, dst_crs="EPSG:3857",
              resampling=Resampling.nearest, src_nodata=255, dst_nodata=255)
    west, south, east, north = array_bounds(hh, w, tr)
    inv = Transformer.from_crs(3857, 4326, always_xy=True)
    (w_lon, s_lat), (e_lon, n_lat) = inv.transform(west, south), inv.transform(east, north)
    Image.fromarray(dst).save(out / "waterrise.png", optimize=True)
    meta = {"bounds": [[s_lat, w_lon], [n_lat, e_lon]], "max_h": MAX_H, "area_ha": area, "buildings": b_cum, "settlements": s_cum,
            "n_buildings": nb, "n_settlements": ns,
            "note": "Terrain-based preview from height above nearest drainage."}
    (out / "waterrise.json").write_text(json.dumps(meta), encoding="utf-8")
    log(f"[waterrise] preview written ({w}x{hh}px, {nb:,} buildings, {ns:,} settlements)")
    return meta
