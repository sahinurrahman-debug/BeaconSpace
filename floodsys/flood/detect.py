"""Physics-based SAR change detection for flood water and debris / scour.

Output classes (uint8 raster):
    0 nothing   1 flood water (new open water)   2 debris / scour / deposition   3 permanent water

Why this design (see report): in a steep Himalayan valley the dominant false alarms are radar
shadow (dark in *both* images), rain-wet soil (small, widespread change) and hill-slope
vegetation change. We therefore (a) compare only same-track images, (b) require a *drop*
relative to the pre-event image for water, (c) gate by slope and height-above-nearest-drainage
(HAND), and (d) keep only blobs that connect to the river corridor.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage as ndi
from skimage.filters import apply_hysteresis_threshold

from ..config import DetectParams

NOTHING, FLOOD, DEBRIS, PERM = 0, 1, 2, 3
CLASS_NAMES = {FLOOD: "flood water", DEBRIS: "debris / scour", PERM: "permanent water"}


def robust_sigma(x: np.ndarray) -> tuple[float, float]:
    v = x[np.isfinite(x)]
    if v.size == 0:
        return 0.0, 1.0
    if v.size > 2_000_000:
        v = np.random.default_rng(0).choice(v, 2_000_000, replace=False)
    med = float(np.median(v))
    return med, float(1.4826 * np.median(np.abs(v - med)) + 1e-6)


def smoothed_change_db(post_db: np.ndarray, pre_db: np.ndarray, res: float) -> np.ndarray:
    """Speckle-robust log-ratio: window-mean in the linear domain, then 10*log10(post/pre)."""
    size = max(3, int(round(50.0 / res)) | 1)
    ok = np.isfinite(post_db) & np.isfinite(pre_db)
    a = np.where(ok, 10 ** (post_db / 10), 0.0)
    b = np.where(ok, 10 ** (pre_db / 10), 0.0)
    w = ndi.uniform_filter(ok.astype("float32"), size)
    ratio = (ndi.uniform_filter(a, size) + 1e-6) / (ndi.uniform_filter(b, size) + 1e-6)
    out = 10 * np.log10(ratio)
    out[w < 0.6] = np.nan
    return out.astype("float32")


def _clean(mask: np.ndarray, min_px: int) -> np.ndarray:
    mask = ndi.binary_closing(mask, structure=np.ones((3, 3)))  # bridge 1-px speckle gaps
    lab, n = ndi.label(mask, structure=np.ones((3, 3)))
    if n == 0:
        return mask
    sizes = ndi.sum(mask, lab, index=np.arange(1, n + 1))
    keep = np.zeros(n + 1, bool)
    keep[1:] = sizes >= min_px
    return keep[lab]


def detect(db: dict, slope: np.ndarray, hand: np.ndarray, res: float, p: DetectParams | None = None,
           model_prob: np.ndarray | None = None, s2: dict | None = None) -> dict:
    """Run the change detector. ``db`` holds post/pre VV/VH in dB on the analysis grid."""
    p = p or DetectParams()
    pv, ph, qv, qh = db["post_vv"], db["post_vh"], db["pre_vv"], db["pre_vh"]
    valid = np.isfinite(pv) & np.isfinite(ph) & np.isfinite(qv) & np.isfinite(qh)
    dvv, dvh = pv - qv, ph - qh                       # per-pixel difference (dB)
    svv = smoothed_change_db(pv, qv, res)              # speckle-robust change (dB)
    svh = smoothed_change_db(ph, qh, res)
    hills = valid & (hand > 150)                       # stable terrain -> empirical noise floor
    mv, sv = robust_sigma(svv[hills if hills.sum() > 1000 else valid])
    mh, sh = robust_sigma(svh[hills if hills.sum() > 1000 else valid])
    zvv, zvh = (svv - mv) / sv, (svh - mh) / sh
    min_px = max(3, int(p.min_area_ha * 10000 / (res * res)))

    terrain_ok_w = (slope <= p.max_slope_water) & (hand <= p.max_hand_water)
    terrain_ok_d = (slope <= p.max_slope_debris) & (hand <= p.max_hand_debris)

    # --- permanent water: dark both before and after, low and flat
    perm = valid & (qv < p.water_vv_db) & (pv < p.water_vv_db) & (slope <= 6) & (hand <= 25)
    perm = _clean(perm, min_px)

    # --- new open water (flood): dark now, was not dark, dropped by >= 3 dB
    dark = (pv < p.water_vv_db) | (ph < p.water_vh_db)
    dropped = ((dvv <= -p.water_drop_db) | (dvh <= -p.water_drop_db))
    was_land = (qv >= p.water_vv_db) & (qh >= p.water_vh_db - 1.0)
    water = valid & dark & dropped & was_land & terrain_ok_w & ~perm
    sar_water = water.copy()

    if model_prob is not None:
        # the trained network proposes; physics gates (terrain + not-permanent-water) still apply
        model_water = (model_prob >= p.model_prob) & valid & terrain_ok_w & ~perm
        water = model_water
    water = _clean(water, min_px)

    # --- debris / scour / deposition: significant two-polarisation change that is not new water
    mag = np.fmax(np.abs(np.nan_to_num(svv - mv)), np.abs(np.nan_to_num(svh - mh)))
    zmag = np.fmax(np.abs(np.nan_to_num(zvv)), np.abs(np.nan_to_num(zvh)))
    low = np.maximum(p.min_change_db, p.change_low_k * np.maximum(sv, sh))
    high = np.maximum(p.min_change_db + 1.5, p.change_high_k * np.maximum(sv, sh))
    big = apply_hysteresis_threshold(np.where(valid & terrain_ok_d, mag, 0), low, high) & valid
    debris = big & terrain_ok_d & ~water & ~perm
    if s2 is not None and s2.get("debris") is not None:
        # Optical data only ADDS evidence (where the sky is clear); it never vetoes radar, because debris on
        # existing river gravel shows no vegetation loss and would be wrongly removed.
        clear = s2["clear"]
        water = water | (s2["water"] & clear & terrain_ok_w & ~perm & valid)
        # (optical vegetation-loss is *not* used to grow the debris mask: crop/terrace/haze differences make it
        #  unreliable without validation; it only raises confidence below)
    debris = _clean(debris, min_px)

    # --- valley connectivity: keep blobs that reach the river corridor
    cand = water | debris
    near_dil = int(round(60.0 / res))
    grown = ndi.binary_dilation(cand, iterations=max(1, near_dil))
    lab, n = ndi.label(grown)
    if n:
        corridor = (hand <= 15) | perm | ndi.binary_dilation(perm, iterations=2)
        has = ndi.maximum(corridor, lab, index=np.arange(1, n + 1))
        keep = np.zeros(n + 1, bool)
        keep[1:] = has > 0
        ok = keep[lab]
        water &= ok
        debris &= ok

    cls = np.zeros(slope.shape, np.uint8)
    cls[perm] = PERM
    cls[debris] = DEBRIS
    cls[water] = FLOOD

    # evidence count for confidence: SAR water, SAR change, optical, model
    ev = np.zeros(slope.shape, np.uint8)
    ev += (cls == FLOOD) & sar_water
    ev += ((cls == FLOOD) | (cls == DEBRIS)) & big
    if s2 is not None and s2.get("water") is not None:
        ev += ((cls == FLOOD) | (cls == DEBRIS)) & s2["clear"] & (s2["water"] | s2["debris"])
    if model_prob is not None:
        ev += (cls == FLOOD) & (model_prob >= p.model_prob)
    return {"cls": cls, "evidence": ev, "dvv": svv, "dvh": svh, "zvv": zvv, "zvh": zvh, "valid": valid,
            "noise": {"vv_med_db": mv, "vv_sigma_db": sv, "vh_med_db": mh, "vh_sigma_db": sh}}


def merge_tracks(results: list[dict]) -> dict:
    """Combine detections from several orbit tracks (each analysed in its own geometry).

    A pixel is flagged if any track flags it; ``support`` counts agreeing tracks among those that
    actually observed the pixel, which we report as confidence.
    """
    cls = np.zeros_like(results[0]["cls"])
    support = np.zeros(cls.shape, np.uint8)
    seen = np.zeros(cls.shape, np.uint8)
    for r in results:
        seen += r["valid"]
        hit = np.isin(r["cls"], (FLOOD, DEBRIS))
        support += hit
        for c in (PERM, DEBRIS, FLOOD):  # priority: flood > debris > permanent
            m = r["cls"] == c
            cls[m] = c
    return {"cls": cls, "support": support, "seen": seen, "evidence": np.maximum.reduce([r["evidence"] for r in results])}
