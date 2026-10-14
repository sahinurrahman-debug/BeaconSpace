"""Ready-made areas. The case study is the 26 Aug 2026 Bhote Koshi - Trishuli glacial-lake outburst flood."""
import datetime as dt

UTC = dt.timezone.utc

PRESETS = {
    "trishuli": {
        "label": "Trishuli / Bhote Koshi corridor, Nepal (26 Aug 2026 flood)",
        "bbox": (84.93, 27.78, 85.48, 28.32),
        # flood reported on the night of 25/26 Aug 2026 (UTC 22:00 on the 25th); the pipeline only uses the
        # event time to choose images strictly before / after it.
        "event": dt.datetime(2026, 8, 25, 22, 0, tzinfo=UTC),
        "trace_from": (85.3835, 28.2180),   # upstream start for the flow-path demo (Bhote Koshi, above Syaphrubesi)
    },
    "syaphrubesi": {
        "label": "Syaphrubesi / Langtang (small, fast demo)",
        "bbox": (85.30, 28.10, 85.45, 28.25),
        "event": dt.datetime(2026, 8, 25, 22, 0, tzinfo=UTC),
        "trace_from": (85.3835, 28.2180),
    },
}

