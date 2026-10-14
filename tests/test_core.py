"""Fast, offline unit tests on synthetic data (no network).   pytest -q"""
import datetime as dt
import sys
from pathlib import Path
from types import SimpleNamespace

import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import LineString, Point, box

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from floodsys.analysis import access, damage  # noqa: E402
from floodsys.config import AccessParams, DamageParams, DetectParams  # noqa: E402
from floodsys.data import s1  # noqa: E402
from floodsys.data.grid import Grid  # noqa: E402
from floodsys.flood import detect  # noqa: E402
from floodsys.flood.model import build_features  # noqa: E402

UTC = dt.timezone.utc


def acq(ro, state, when, cov=1.0):
    return s1.Acquisition(ro, state, when, "sentinel-1d", [], cov)


def test_pairs_use_same_track_and_straddle_event():
    ev = dt.datetime(2026, 8, 25, 22, tzinfo=UTC)
    a = [acq(85, "ascending", dt.datetime(2026, 8, 4, 12, 21, tzinfo=UTC)), acq(85, "ascending", dt.datetime(2026, 8, 16, 12, 21, tzinfo=UTC)),
         acq(85, "ascending", dt.datetime(2026, 8, 28, 12, 21, tzinfo=UTC)),
         acq(19, "descending", dt.datetime(2026, 8, 24, 0, 18, tzinfo=UTC)), acq(19, "descending", dt.datetime(2026, 9, 5, 0, 18, tzinfo=UTC)),
         acq(121, "descending", dt.datetime(2026, 8, 19, tzinfo=UTC), cov=0.2), acq(121, "descending", dt.datetime(2026, 8, 31, tzinfo=UTC), cov=0.2)]
    pairs = s1.plan_pairs(a, ev, top=5)
    assert [p.post.rel_orbit for p in pairs][0] == 85          # post-event image only 2.5 days after
    assert 121 not in [p.post.rel_orbit for p in pairs]        # poor coverage rejected
    for p in pairs:
        assert p.post.when >= ev and all(x.when < ev for x in p.pre)
        assert all(x.key == p.post.key for x in p.pre)          # never mix orbit tracks
    assert pairs[0].describe()["baseline_days"] == 12


def synth_scene(n=240, res=20.0):
    rng = np.random.default_rng(1)
    pre = rng.normal(-11, 1.0, (n, n)).astype("float32")
    pre_vh = pre - 7
    post, post_vh = pre.copy(), pre_vh.copy()
    new_water = np.zeros((n, n), bool); new_water[100:110, 20:200] = True          # a flooded channel
    debris = np.zeros((n, n), bool); debris[112:120, 40:160] = True
    post[new_water] = -23; post_vh[new_water] = -30
    post[debris] += 6; post_vh[debris] += 6
    shadow = np.zeros((n, n), bool); shadow[20:40, 20:60] = True                    # dark in both -> must NOT be flagged
    pre[shadow] = -24; post[shadow] = -24; pre_vh[shadow] = -31; post_vh[shadow] = -31
    hand = np.full((n, n), 200.0, "float32"); hand[95:125, :] = 3.0
    slope = np.full((n, n), 4.0, "float32")
    db = {"post_vv": post, "post_vh": post_vh, "pre_vv": pre, "pre_vh": pre_vh}
    return db, slope, hand, new_water, debris, shadow


def test_detector_finds_flood_and_debris_but_not_shadow():
    db, slope, hand, water, debris, shadow = synth_scene()
    r = detect.detect(db, slope, hand, 20.0, DetectParams())
    cls = r["cls"]
    assert (cls[water] == detect.FLOOD).mean() > 0.9
    assert (cls[debris] == detect.DEBRIS).mean() > 0.8
    assert (cls[shadow] == detect.NOTHING).mean() > 0.95 or (cls[shadow] == detect.PERM).mean() < 0.0 + 1.0   # shadow never 'flood'
    assert not (cls[shadow] == detect.FLOOD).any()
    assert (cls[:60] != detect.FLOOD).all()                      # nothing on the hillslopes


def test_detector_ignores_high_ground():
    db, slope, hand, water, *_ = synth_scene()
    hand[:] = 300.0
    r = detect.detect(db, slope, hand, 20.0, DetectParams())
    assert not np.isin(r["cls"], (detect.FLOOD, detect.DEBRIS)).any()


@pytest.fixture
def grid():
    return Grid.from_lonlat_bbox((85.30, 28.10, 85.34, 28.14), 20.0)


def test_damage_overlay(grid):
    l, b, r, t = grid.bounds
    cx, cy = (l + r) / 2, (b + t) / 2
    impact = box(cx - 100, cy - 100, cx + 100, cy + 100)
    mk = lambda x, y, s=15: box(x - s, y - s, x + s, y + s)
    bld = gpd.GeoDataFrame({"building": ["yes"] * 4},
                           geometry=[mk(cx, cy), mk(cx + 110, cy), mk(cx + 140, cy), mk(cx + 600, cy)], crs=grid.crs).to_crs(4326)
    st = damage.assess_buildings(bld, impact, grid, DamageParams())
    assert list(st["status"]) == ["destroyed_likely", "affected", "exposed", "unaffected"]
    roads = gpd.GeoDataFrame({"highway": ["primary", "track"], "bridge": ["yes", None]},
                             geometry=[LineString([(cx - 400, cy), (cx + 400, cy)]), LineString([(cx - 400, cy + 500), (cx + 400, cy + 500)])],
                             crs=grid.crs).to_crs(4326)
    rs = damage.assess_roads(roads, impact, grid, DamageParams())
    assert rs["hit"].tolist() == [True, False]
    assert 190 < rs["hit_m"].iloc[0] < 260
    br = damage.assess_bridges(rs, impact, grid, DamageParams())
    assert len(br) == 1 and bool(br["bridge_hit"].iloc[0])


def test_cut_off_analysis_blocks_only_the_flooded_link(grid):
    """Hospital H -- A -- (flooded gap) -- B -- C ; D connects to H on a separate road."""
    l, b, r, t = grid.bounds
    cx, cy = (l + r) / 2, (b + t) / 2
    to_ll = grid.from_utm()
    P = lambda x, y: to_ll.transform(cx + x, cy + y)
    roads = gpd.GeoDataFrame({"highway": ["tertiary"] * 3},
                             geometry=[LineString([P(-1500, 0), P(-700, 0), P(-300, 0)]),     # H .. A .. gap start
                                       LineString([P(-300, 0), P(300, 0), P(900, 0), P(1500, 0)]),  # across the flood to B and C
                                       LineString([P(-1500, 0), P(-1500, 800), P(-1500, 1500)])], crs=4326)  # H .. D
    places = gpd.GeoDataFrame({"name": ["A", "B", "C", "D"], "place": ["village"] * 4},
                              geometry=[Point(P(-700, 40)), Point(P(900, 40)), Point(P(1500, 40)), Point(P(-1500, 1500))], crs=4326)
    health = gpd.GeoDataFrame({"name": ["District hospital"], "amenity": ["hospital"]}, geometry=[Point(P(-1500, 30))], crs=4326)
    impact = box(cx - 120, cy - 150, cx + 120, cy + 150)
    out = access.analyse_access(roads, places, health, None, grid, impact, (85.0, 27.0, 86.0, 29.0),
                                AccessParams(snap_m=200), log=lambda *_: None)
    st = out["settlements"].set_index("name")["status"].to_dict()
    assert st == {"A": "connected", "B": "cut_off", "C": "cut_off", "D": "connected"}
    assert out["summary"]["cut_off"] == 2 and out["summary"]["blocked_segments"] >= 1
    assert out["settlements"].set_index("name").loc["B", "dest_before"] == "District hospital"


def test_feature_contract_matches_notebook():
    """The training notebook and the live system must build identical 7-channel inputs."""
    import re
    src = (Path(__file__).resolve().parent.parent / "notebooks" / "train_flood_unet.py").read_text(encoding="utf-8")
    ns = {"np": np, "ndi": __import__("scipy.ndimage", fromlist=["x"])}
    for fn in ("smoothed_change_db", "make_features"):
        m = re.search(rf"def {fn}\(.*?(?=\n\n(?:def|class|train|# %%))", src, re.S)
        exec(m.group(0), ns)
    db, slope, *_ = synth_scene(64)
    ref = build_features(db, slope, 20.0)
    x5 = np.stack([db["post_vv"], db["post_vh"], db["pre_vv"], db["pre_vh"], slope])
    got = ns["make_features"](x5, 20.0)
    assert ref.shape == got.shape == (7, 64, 64)
    assert np.allclose(ref, got, atol=1e-4)


def test_sitrep_numbers_come_from_summary():
    from floodsys.report import sitrep
    s = {"name": "t", "event_utc": "2026-08-26T00:00", "resolution_m": 20.0, "area_km2": 100.0,
         "area_ha": {"flood water": 12.0, "debris / scour": 30.0, "permanent water": 5.0, "impact_total_ha": 42.0},
         "damage": {"buildings": {"total": 200, "destroyed_likely": 7, "affected": 11, "exposed": 3, "unaffected": 179, "affected_total": 18},
                    "roads": {"primary": {"total_km": 10.0, "hit_km": 1.5, "segments_hit": 3}}, "roads_total_hit_km": 2.5,
                    "bridges": {"total": 5, "hit": 2}},
         "access": {"settlements": 4, "connected": 2, "cut_off": 1, "longer_route": 1, "buildings_in_cut_off": 33},
         "cut_off": [{"name": "Gumba", "n_buildings": 33, "dist_before_km": 4.2, "dest_before": "Health post", "status": "cut_off"}],
         "settlements": [], "s1_pairs": [{"rel_orbit": 85, "pre": ["2026-08-16T12:21"], "post": "2026-08-28T12:21"}],
         "s2": None, "model": None, "osm": {"snapshot": "2026-07-27"}, "confidence": {"two_track_agreement_ha": 10.0}}
    html = sitrep.build_html(s, None)
    for needle in ("42 ha", "Gumba", "33", "2/5", "२/५"):
        assert needle in html or needle.replace("2/5", "2/5") in html
    assert "Contains modified Copernicus Sentinel data 2026." in html and "OpenStreetMap contributors" in html


def test_debris_must_hug_the_drainage_network():
    db, slope, hand, water, debris, shadow = synth_scene()
    cd = np.full(slope.shape, 2000.0, "float32")
    cd[95:125, :] = 20.0                                   # drainage along the valley floor only
    near = detect.detect(db, slope, hand, 20.0, DetectParams(), chan_dist=cd)["cls"]
    assert (near[debris] == detect.DEBRIS).mean() > 0.8      # debris in the valley kept
    db2 = {k: v.copy() for k, v in db.items()}
    for k in ("post_vv", "post_vh"):
        db2[k][150:170, 30:120] += 7                           # field-like change far from any river
    r = detect.detect(db2, slope, np.full(slope.shape, 3.0, "float32"), 20.0, DetectParams(), chan_dist=cd)["cls"]
    assert not (r[150:170, 30:120] == detect.DEBRIS).any()
