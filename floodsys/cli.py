"""Command line:  python -m floodsys run --preset trishuli   |   python -m floodsys run --bbox W S E N --event 2026-08-26"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from . import config
from .presets import PRESETS

UTC = dt.timezone.utc


def parse_event(s: str) -> dt.datetime:
    s = s.strip().replace("Z", "")
    t = dt.datetime.fromisoformat(s if "T" in s or " " in s else s + "T00:00:00")
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="floodsys", description="BeaconSpace: flood damage mapping from space")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run the full pipeline for an area and flood date")
    r.add_argument("--preset", choices=list(PRESETS))
    r.add_argument("--bbox", nargs=4, type=float, metavar=("W", "S", "E", "N"))
    r.add_argument("--event", type=str, help="flood date/time UTC, e.g. 2026-08-26 or 2026-08-25T22:00")
    r.add_argument("--res", type=float, default=20.0, help="analysis resolution in metres (10, 20 or 40)")
    r.add_argument("--pairs", type=int, default=2, help="how many same-track radar pairs to combine")
    r.add_argument("--name", default="")
    r.add_argument("--trace", nargs=2, type=float, metavar=("LON", "LAT"), help="upstream point for the flow-path bonus")
    r.add_argument("--no-s2", action="store_true", help="radar only")
    r.add_argument("--no-model", action="store_true", help="ignore the trained AI model")
    r.add_argument("--snapshot", type=str, help="OSM snapshot date (must predate the event)")
    r.add_argument("--out", type=Path)
    a = ap.parse_args(argv)

    from .pipeline import RunConfig, run
    if a.preset:
        p = PRESETS[a.preset]
        bbox, event, trace = p["bbox"], p["event"], p.get("trace_from")
        name = a.name or a.preset
    else:
        if not (a.bbox and a.event):
            ap.error("give --preset or both --bbox and --event")
        bbox, event, trace, name = tuple(a.bbox), parse_event(a.event), None, a.name
    if a.bbox:
        bbox = tuple(a.bbox)
    if a.event:
        event = parse_event(a.event)
    if a.trace:
        trace = tuple(a.trace)
    cfg = RunConfig(bbox=bbox, event=event, name=name, res=a.res, n_pairs=a.pairs, use_s2=not a.no_s2,
                    use_model=not a.no_model, trace_from=trace, out_dir=a.out,
                    snapshot=dt.date.fromisoformat(a.snapshot) if a.snapshot else None)
    res = run(cfg, log=lambda m: print(m, flush=True))
    print(f"\nOutputs in: {res['out']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
