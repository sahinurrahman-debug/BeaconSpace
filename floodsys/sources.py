"""Data-rule guard: every remote read goes through ``check`` and anything outside the allowed sources is refused.

Allowed inputs (challenge rules): Sentinel-1/2, Copernicus DEM, OpenStreetMap as it was before the event.
Not allowed: Copernicus EMS / UNOSAT maps, post-event OSM edits. ``provenance.json`` lists what was actually accessed in a run.
"""
import threading
from urllib.parse import urlparse

ALLOWED_HOSTS = (
    "planetarycomputer.microsoft.com", "blob.core.windows.net",          # Sentinel-1 RTC (Microsoft Planetary Computer)
    "earth-search.aws.element84.com", "amazonaws.com",                    # Sentinel-2 L2A and Copernicus DEM on AWS
    "api.ohsome.org", "overpass-api.de",                                  # OpenStreetMap history (queried with a pre-event date)
)
FORBIDDEN_MARKERS = ("emsr", "mapping.emergency.copernicus", "unosat", "data/reference", "data\reference")

_lock = threading.Lock()
_used: set = set()


def reset() -> None:
    with _lock:
        _used.clear()


def check(url: str) -> str:
    """Record ``url`` (host only) and raise PermissionError if it is not an allowed source."""
    u = str(url)
    low = u.lower().replace("\\", "/")
    if any(m.replace("\\", "/") in low for m in FORBIDDEN_MARKERS):
        raise PermissionError(f"Data rule: {u!r} looks like a reference/damage map, which must never be a pipeline input.")
    if low.startswith("/vsicurl/"):
        u = u[len("/vsicurl/"):]
    parsed = urlparse(u)
    host = "s3.amazonaws.com" if parsed.scheme == "s3" else parsed.hostname          # s3:// = AWS open-data buckets
    if host is None:                       # local file (cache or bundled data): not a new remote source
        return u
    if not any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS):
        raise PermissionError(f"Data rule: host {host!r} is not an allowed input source.")
    with _lock:
        _used.add(host)
    return u


def used() -> list:
    with _lock:
        return sorted(_used)
