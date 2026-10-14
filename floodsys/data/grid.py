"""Raster grid definition and parallel, retrying COG reads onto that grid."""
from __future__ import annotations

import math
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import numpy as np
import rasterio
from affine import Affine
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.windows import Window


@dataclass(frozen=True)
class Grid:
    """A north-up UTM grid; every raster in a run lives on one Grid."""
    crs: str
    transform: Affine
    width: int
    height: int
    bbox_lonlat: tuple  # requested AOI (lon0, lat0, lon1, lat1)

    @property
    def res(self) -> float:
        return float(self.transform.a)

    @property
    def shape(self):
        return (self.height, self.width)

    @property
    def bounds(self):
        t = self.transform
        return (t.c, t.f - self.height * self.res, t.c + self.width * self.res, t.f)

    @classmethod
    def from_lonlat_bbox(cls, bbox, res: float = 20.0) -> "Grid":
        lon0, lat0, lon1, lat1 = bbox
        cx, cy = (lon0 + lon1) / 2, (lat0 + lat1) / 2
        zone = int((cx + 180) // 6) + 1
        epsg = (32600 if cy >= 0 else 32700) + zone
        tr = Transformer.from_crs(4326, epsg, always_xy=True)
        xs, ys = tr.transform([lon0, lon1, lon0, lon1], [lat0, lat0, lat1, lat1])
        # snap to a 10 m lattice so Sentinel-1 RTC (10 m, UTM) needs no resampling
        left = math.floor(min(xs) / 10) * 10
        right = math.ceil(max(xs) / 10) * 10
        bottom = math.floor(min(ys) / 10) * 10
        top = math.ceil(max(ys) / 10) * 10
        w = int(math.ceil((right - left) / res))
        h = int(math.ceil((top - bottom) / res))
        return cls(f"EPSG:{epsg}", Affine(res, 0, left, 0, -res, top), w, h, tuple(bbox))

    # coordinate helpers -----------------------------------------------------
    def to_utm(self):
        return Transformer.from_crs(4326, self.crs, always_xy=True)

    def from_utm(self):
        return Transformer.from_crs(self.crs, 4326, always_xy=True)

    def xy_to_rc(self, x, y):
        inv = ~self.transform
        c, r = inv * (np.asarray(x), np.asarray(y))
        return np.floor(r).astype(int), np.floor(c).astype(int)

    def lonlat_bounds(self):
        l, b, r, t = self.bounds
        tr = self.from_utm()
        xs, ys = tr.transform([l, r, l, r], [b, b, t, t])
        return min(xs), min(ys), max(xs), max(ys)

    def with_res(self, res: float) -> "Grid":
        return Grid.from_lonlat_bbox(self.bbox_lonlat, res)


def _read_chunk(href, grid: Grid, rows: tuple, resampling, nodata, vrt_kwargs=None):
    r0, r1 = rows
    out = np.full((r1 - r0, grid.width), np.nan, dtype="float32")
    with rasterio.open(href) as src:
        src_nd = src.nodata if nodata is None else nodata
        k = grid.res / src.res[0]
        if src.crs.to_string() == grid.crs and k >= 1 and abs(k - round(k)) < 1e-6:
            # fast path: same UTM zone, integer decimation -> windowed read (uses COG overviews)
            col_off = (grid.transform.c - src.transform.c) / src.res[0]
            row_off = (src.transform.f - grid.transform.f) / src.res[0] + r0 * k
            win = Window(col_off, row_off, grid.width * k, (r1 - r0) * k)
            # intersect with the dataset so we only fetch what exists
            full = Window(0, 0, src.width, src.height)
            try:
                inter = win.intersection(full)
            except Exception:
                return out
            if inter.width < 1 or inter.height < 1:
                return out
            oc = int(round((inter.col_off - win.col_off) / k))
            orow = int(round((inter.row_off - win.row_off) / k))
            ow = max(1, int(round(inter.width / k)))
            oh = max(1, int(round(inter.height / k)))
            ow = min(ow, grid.width - oc)
            oh = min(oh, (r1 - r0) - orow)
            data = src.read(1, window=inter, out_shape=(oh, ow), resampling=resampling).astype("float32")
            if src_nd is not None:
                data[data == src_nd] = np.nan
            data[~np.isfinite(data)] = np.nan
            out[orow:orow + oh, oc:oc + ow] = data
        else:
            with WarpedVRT(src, crs=grid.crs, transform=grid.transform, width=grid.width, height=grid.height,
                           resampling=resampling, src_nodata=src_nd, nodata=np.nan, dtype="float32",
                           **(vrt_kwargs or {})) as vrt:
                data = vrt.read(1, window=Window(0, r0, grid.width, r1 - r0)).astype("float32")
                out[:] = data
    return out


def read_to_grid(href: str, grid: Grid, resampling=Resampling.average, nodata=None, chunk_rows: int = 512,
                 workers: int = 8, retries: int = 4, vrt_kwargs=None) -> np.ndarray:
    """Read a (remote) single-band raster onto ``grid`` using parallel row-chunks.

    Values equal to the source nodata become NaN. Returns float32 (H, W).
    """
    chunks = [(r, min(r + chunk_rows, grid.height)) for r in range(0, grid.height, chunk_rows)]

    def job(rows):
        for attempt in range(retries):
            try:
                return _read_chunk(href, grid, rows, resampling, nodata, vrt_kwargs)
            except Exception:
                if attempt == retries - 1:
                    raise
                time.sleep(1.5 * (attempt + 1))

    with ThreadPoolExecutor(workers) as ex:
        parts = list(ex.map(job, chunks))
    return np.vstack(parts)
