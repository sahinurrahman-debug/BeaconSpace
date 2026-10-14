"""Sentinel-1 (radar): search, same-orbit-track pair planning, loading, speckle filtering.

Source: Microsoft Planetary Computer ``sentinel-1-rtc`` (radiometrically terrain-corrected
gamma-nought, 10 m, linear power) -- derived from Copernicus Sentinel-1 GRD data.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.ndimage import uniform_filter
from shapely.geometry import box, shape

from .. import config
from .grid import Grid, read_to_grid

UTC = dt.timezone.utc


@dataclass
class Acquisition:
    """All slices of one relative orbit on one pass that touch the AOI."""
    rel_orbit: int
    orbit_state: str
    when: dt.datetime
    platform: str
    items: list = field(repr=False, default_factory=list)
    coverage: float = 0.0  # fraction of the AOI covered by the union of slices

    @property
    def key(self):
        return (self.rel_orbit, self.orbit_state)

    def label(self) -> str:
        return f"{self.platform} RO{self.rel_orbit}/{self.orbit_state[:3]} {self.when:%Y-%m-%d %H:%M}Z"


@dataclass
class Pair:
    post: Acquisition
    pre: list  # list[Acquisition], nearest first
    score: float

    def describe(self) -> dict:
        return {"rel_orbit": self.post.rel_orbit, "orbit_state": self.post.orbit_state,
                "post": self.post.when.isoformat(), "pre": [a.when.isoformat() for a in self.pre],
                "post_coverage": round(self.post.coverage, 3),
                "pre_coverage": [round(a.coverage, 3) for a in self.pre],
                "baseline_days": round((self.post.when - self.pre[0].when).total_seconds() / 86400, 2)}


def _catalog():
    import planetary_computer as pc
    import pystac_client
    return pystac_client.Client.open(config.PC_STAC, modifier=pc.sign_inplace)


def search_acquisitions(bbox, start: dt.date, end: dt.date) -> list[Acquisition]:
    cat = _catalog()
    res = cat.search(collections=["sentinel-1-rtc"], bbox=list(bbox),
                     datetime=f"{start.isoformat()}/{end.isoformat()}", max_items=500).item_collection()
    aoi = box(*bbox)
    groups = defaultdict(list)
    for it in res:
        p = it.properties
        if not {"VV", "VH"} <= set(p.get("sar:polarizations", [])):
            continue
        t = it.datetime.astimezone(UTC)
        groups[(p["sat:relative_orbit"], p["sat:orbit_state"], t.date())].append(it)
    acqs = []
    for (ro, state, _), its in groups.items():
        union = None
        for it in its:
            g = shape(it.geometry)
            union = g if union is None else union.union(g)
        cov = union.intersection(aoi).area / aoi.area
        when = min(i.datetime for i in its).astimezone(UTC)
        acqs.append(Acquisition(ro, state, when, its[0].properties.get("platform", "sentinel-1"), its, cov))
    return sorted(acqs, key=lambda a: a.when)


def plan_pairs(acqs: list[Acquisition], event: dt.datetime, max_post_days: float = 30, n_pre: int = 2,
               min_cov: float = 0.5, pre_window_days: float = 60, top: int = 3) -> list[Pair]:
    """Same relative-orbit pairs: one pre/post for each track, ranked.

    Score favours (1) AOI coverage, (2) small delay after the event, (3) a pre-image
    close to 12 days before the post image (the Sentinel-1 repeat cycle), (4) the pre image
    being as recent as possible. Different tracks are never mixed pixel-by-pixel.
    """
    event = event if event.tzinfo else event.replace(tzinfo=UTC)
    by_track = defaultdict(list)
    for a in acqs:
        by_track[a.key].append(a)
    pairs = []
    for _, lst in by_track.items():
        lst.sort(key=lambda a: a.when)
        posts = [a for a in lst if a.when >= event and (a.when - event).days <= max_post_days and a.coverage >= min_cov]
        pres = [a for a in lst if a.when < event - dt.timedelta(hours=1) and
                (event - a.when).days <= pre_window_days and a.coverage >= min_cov]
        if not posts or not pres:
            continue
        post = min(posts, key=lambda a: a.when)  # first usable post-event image on this track
        pres_sorted = sorted(pres, key=lambda a: a.when, reverse=True)
        chosen = [pres_sorted[0]]
        for a in pres_sorted[1:]:
            if len(chosen) >= n_pre:
                break
            gap = (chosen[-1].when - a.when).total_seconds() / 86400
            if gap > 5:  # distinct acquisition, not the same pass
                chosen.append(a)
        base = (post.when - chosen[0].when).total_seconds() / 86400
        delay = (post.when - event).total_seconds() / 86400
        score = (100 * min(post.coverage, chosen[0].coverage) - 4 * delay - 2 * abs(base - 12)
                 - 0.5 * (event - chosen[0].when).days)
        pairs.append(Pair(post, chosen, score))
    return sorted(pairs, key=lambda p: -p.score)[:top]


def _sign(item):
    import planetary_computer as pc
    return pc.sign(item)


def _load_acq(acq: Acquisition, grid: Grid, workers: int = 8):
    """Mosaic all slices of an acquisition onto the grid -> (vv, vh) linear power (NaN = no data)."""
    out = {}
    for pol in ("vv", "vh"):
        mosaic = np.full(grid.shape, np.nan, dtype="float32")
        for it in acq.items:
            href = _sign(it).assets[pol].href
            arr = read_to_grid(href, grid, nodata=-32768.0, workers=workers)
            take = np.isnan(mosaic) & np.isfinite(arr)
            mosaic[take] = arr[take]
        out[pol] = mosaic
    return out


def _cache_key(pair: Pair, grid: Grid) -> Path:
    h = hashlib.sha1(json.dumps([pair.describe(), grid.crs, grid.bounds, grid.res], sort_keys=True).encode()).hexdigest()[:16]
    d = config.CACHE_DIR / "s1"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{h}.npz"


def load_pair(pair: Pair, grid: Grid, log=print) -> dict:
    """Return linear-power arrays: post_vv/vh and pre_vv/vh (mean of the pre images) + n_pre."""
    f = _cache_key(pair, grid)
    if f.exists():
        z = np.load(f)
        log(f"[s1] cache hit {f.name}")
        return {k: z[k] for k in z.files}
    log(f"[s1] reading post {pair.post.label()} ...")
    post = _load_acq(pair.post, grid)
    pres = []
    for a in pair.pre:
        log(f"[s1] reading pre  {a.label()} ...")
        pres.append(_load_acq(a, grid))
    out = {"post_vv": post["vv"], "post_vh": post["vh"]}
    for pol in ("vv", "vh"):
        stack = np.stack([p[pol] for p in pres])
        out[f"pre_{pol}"] = np.nanmean(stack, axis=0).astype("float32")  # linear-domain temporal mean
        out[f"pre1_{pol}"] = pres[0][pol]
    np.savez_compressed(f, **out)
    return out


# --- radiometry --------------------------------------------------------------------------------
def to_db(x: np.ndarray, floor: float = 1e-4) -> np.ndarray:
    return (10.0 * np.log10(np.maximum(x, floor))).astype("float32")


def lee_filter(x: np.ndarray, size: int = 3) -> np.ndarray:
    """Simple Lee speckle filter on linear intensity (NaN-safe)."""
    valid = np.isfinite(x)
    v = np.where(valid, x, 0.0).astype("float64")
    w = valid.astype("float64")
    n = uniform_filter(w, size)
    n[n == 0] = 1
    mean = uniform_filter(v, size) / n
    sq = uniform_filter(v * v, size) / n
    var = np.maximum(sq - mean * mean, 0)
    noise = (mean ** 2) / 4.0  # ~4-look GRD, ENL approx; coefficient of variation^2 = 1/ENL
    k = var / (var + noise + 1e-12)
    out = mean + k * (v - mean)
    out[~valid] = np.nan
    return out.astype("float32")


def prepare_db(stack: dict, res: float, despeckle: bool = True) -> dict:
    """Linear -> dB with consistent speckle handling. At 10 m a 3x3 Lee filter (as Kuro Siwo used)."""
    out = {}
    for k in ("post_vv", "post_vh", "pre_vv", "pre_vh"):
        x = stack[k]
        if despeckle and res <= 10.5:
            x = lee_filter(x, 3)
        out[k] = to_db(x)
        out[k][~np.isfinite(stack[k])] = np.nan
    return out
