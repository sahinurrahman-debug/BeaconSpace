"""Null-event test: how many false alarms does the system raise on Himalayan terrain when NOTHING happened?

For several 'fake event' dates *before* the real flood we run the same S1 pipeline (same-track pre/post pair, same
terrain gating).  Any flagged area is a false alarm by construction.  No reference map is needed.

    python scripts/null_test.py --preset trishuli --dates 2026-07-02 2026-07-14 2026-07-26 2026-08-07
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from floodsys import config  # noqa: E402
from floodsys.data import dem as demmod, s1 as s1mod  # noqa: E402
from floodsys.data.grid import Grid  # noqa: E402
from floodsys.flood import detect  # noqa: E402
from floodsys.flood.model import FloodModel, build_features  # noqa: E402
from floodsys.presets import PRESETS  # noqa: E402

UTC = dt.timezone.utc
ap = argparse.ArgumentParser()
ap.add_argument("--preset", default="trishuli")
ap.add_argument("--dates", nargs="+", required=True, help="fake event dates (must be well before the real event)")
ap.add_argument("--res", type=float, default=20.0)
ap.add_argument("--no-model", action="store_true")
ap.add_argument("--with-event", action="store_true", help="also report the real event pairs (signal next to noise)")
ap.add_argument("--tag", default="")
a = ap.parse_args()

p = PRESETS[a.preset]
bbox = p["bbox"]
real = p["event"]
grid = Grid.from_lonlat_bbox(bbox, a.res)
terr = demmod.terrain_layers(grid)
model = None if a.no_model else FloodModel.load_if_available(config.MODEL_PATH)
area_km2 = grid.width * grid.height * (grid.res / 1000) ** 2
acqs = s1mod.search_acquisitions(bbox, dt.date(2026, 5, 1), real.date() + dt.timedelta(days=40))   # null pairs below only use images before the flood
rows = []
real_rows = []
for d in a.dates:
    ev = dt.datetime.fromisoformat(d).replace(tzinfo=UTC, hour=12)
    # only images strictly before the real event may be used
    usable = [x for x in acqs if x.when < real - dt.timedelta(days=1)]
    pairs = s1mod.plan_pairs(usable, ev, top=3, max_post_days=8)
    for pr in pairs:
        st = s1mod.load_pair(pr, grid)
        db = s1mod.prepare_db(st, grid.res)
        prob = model.predict(build_features(db, terr["slope"], grid.res)) if model else None
        r = detect.detect(db, terr["slope"], terr["hand"], grid.res, model_prob=prob, chan_dist=terr["chan_dist"])
        ha = grid.res ** 2 / 1e4
        fl, de = float((r["cls"] == detect.FLOOD).sum() * ha), float((r["cls"] == detect.DEBRIS).sum() * ha)
        rows.append({"fake_event": d, "rel_orbit": pr.post.rel_orbit, "pre": pr.pre[0].when.date().isoformat(),
                     "post": pr.post.when.date().isoformat(), "false_flood_ha": round(fl, 1), "false_debris_ha": round(de, 1),
                     "per_1000km2_ha": round((fl + de) / area_km2 * 1000, 1)})
        print(rows[-1], flush=True)
if a.with_event:
    for pr in s1mod.plan_pairs(acqs, real, top=2):
        st = s1mod.load_pair(pr, grid)
        db = s1mod.prepare_db(st, grid.res)
        prob = model.predict(build_features(db, terr["slope"], grid.res)) if model else None
        r = detect.detect(db, terr["slope"], terr["hand"], grid.res, model_prob=prob, chan_dist=terr["chan_dist"])
        ha = grid.res ** 2 / 1e4
        ev_row = {"fake_event": "REAL EVENT", "rel_orbit": pr.post.rel_orbit, "pre": pr.pre[0].when.date().isoformat(),
                  "post": pr.post.when.date().isoformat(), "flood_ha": round(float((r["cls"] == detect.FLOOD).sum() * ha), 1),
                  "debris_ha": round(float((r["cls"] == detect.DEBRIS).sum() * ha), 1)}
        print(ev_row, flush=True)
        real_rows.append(ev_row)
out = config.OUTPUT_DIR / "evaluation"
out.mkdir(parents=True, exist_ok=True)
summary = {"area_km2": round(area_km2, 1), "pairs": rows, "real_event": real_rows,
           "mean_false_alarm_ha_per_1000km2": round(float(np.mean([r["per_1000km2_ha"] for r in rows])), 2) if rows else None,
           "model": None if model is None else model.path.name}
(out / f"null_test{a.tag}.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary, indent=2))
