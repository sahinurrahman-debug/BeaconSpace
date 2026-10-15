"""OpenStreetMap *as it was before the event*.

Providers (tried in order, all pinned to a snapshot date strictly before the event so that
edits made after the disaster can never leak into the analysis):

1. ohsome API ``elements/geometry``  (the provider named in the challenge brief)
2. Overpass API with ``[date:"<snapshot>"]`` (attic / historical query)
3. a user-supplied GeoJSON/GPKG/PBF-derived file per layer in ``data/osm_snapshot/``
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import time

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import LineString, Point, Polygon, shape

from .. import config, sources

UA = {"User-Agent": "BeaconSpace/0.1 (flood mapping)"}
# Only mirrors that really support attic ([date:]) queries; others silently return *current* data.
OVERPASS = ["https://overpass-api.de/api/interpreter"]


def latest_snapshot(event_date: dt.date) -> dt.date:
    """Latest available snapshot strictly before the event day."""
    try:
        meta = requests.get(sources.check(f"{config.OHSOME}/metadata"), timeout=30, headers=UA).json()
        latest = dt.datetime.fromisoformat(
            meta["extractRegion"]["temporalExtent"]["toTimestamp"].replace("Z", "+00:00")).date()
    except Exception:
        latest = event_date - dt.timedelta(days=1)
    return min(latest, event_date - dt.timedelta(days=1))


def _split(bbox, max_deg):
    lon0, lat0, lon1, lat1 = bbox
    nx = max(1, int(-(-(lon1 - lon0) // max_deg)))
    ny = max(1, int(-(-(lat1 - lat0) // max_deg)))
    for i in range(nx):
        for j in range(ny):
            yield (lon0 + (lon1 - lon0) * i / nx, lat0 + (lat1 - lat0) * j / ny,
                   lon0 + (lon1 - lon0) * (i + 1) / nx, lat0 + (lat1 - lat0) * (j + 1) / ny)


def _lattice(bbox, step):
    import math
    lon0, lat0, lon1, lat1 = bbox
    for i in range(math.floor(lon0 / step), math.ceil(lon1 / step)):
        for j in range(math.floor(lat0 / step), math.ceil(lat1 / step)):
            yield (round(i * step, 6), round(j * step, 6), round((i + 1) * step, 6), round((j + 1) * step, 6))


# ------------------------------------------------------------------ ohsome
OHSOME_FILTERS = {
    "roads": "highway in (" + ",".join(config.ROAD_CLASSES) + ") and geometry:line",
    "buildings": "building=* and geometry:polygon",
    "places": "place in (" + ",".join(config.PLACE_CLASSES) + ") and geometry:point",
    "health": "amenity in (hospital,clinic,doctors) or healthcare in (hospital,clinic,centre)",
}


def _ohsome_fetch(bbox, snapshot, layer, retries=2):
    feats = []
    for tile in _split(bbox, 0.12):
        data = {"bboxes": ",".join(f"{v:.6f}" for v in tile), "time": snapshot.isoformat(),
                "filter": OHSOME_FILTERS[layer], "properties": "tags"}
        for attempt in range(retries):
            r = requests.post(sources.check(f"{config.OHSOME}/elements/geometry"), data=data, timeout=180, headers=UA)
            if r.status_code == 200:
                feats.extend(r.json().get("features", []))
                break
            if r.status_code == 403:
                raise PermissionError("ohsome extraction endpoint refused (HTTP 403)")
            time.sleep(2 * (attempt + 1))
        else:
            raise RuntimeError("ohsome failed")
    rows, geoms, seen = [], [], set()
    for f in feats:
        p = f.get("properties", {})
        if p.get("@osmId") in seen or not f.get("geometry"):
            continue
        seen.add(p.get("@osmId"))
        rows.append({k: v for k, v in p.items() if not k.startswith("@")} | {"osm_id": p.get("@osmId")})
        geoms.append(shape(f["geometry"]))
    return gpd.GeoDataFrame(pd.DataFrame(rows), geometry=geoms, crs=4326)


# ------------------------------------------------------------------ Overpass (attic)
def _overpass_ql(layer, tile, snapshot):
    s, w, n, e = tile[1], tile[0], tile[3], tile[2]
    bb = f"({s:.5f},{w:.5f},{n:.5f},{e:.5f})"
    head = f'[out:json][timeout:60][date:"{snapshot.isoformat()}T00:00:00Z"];'
    if layer == "roads":
        hw = "|".join(config.ROAD_CLASSES)
        return head + f'way["highway"~"^({hw})$"]{bb};out tags geom;'
    if layer == "buildings":
        return head + f'way["building"]{bb};out tags geom;'
    if layer == "places":
        pl = "|".join(config.PLACE_CLASSES)
        return head + f'node["place"~"^({pl})$"]{bb};out body;'
    if layer == "health":
        return (head + f'(nwr["amenity"~"^(hospital|clinic|doctors)$"]{bb};'
                f'nwr["healthcare"~"^(hospital|clinic|centre)$"]{bb};);out tags center;')
    raise KeyError(layer)


def _overpass_fetch(bbox, snapshot, layer, log=print, region=None):
    """Date-pinned (attic) Overpass fetch. Resumable: every tile is cached on disk as soon as it arrives."""
    step = 0.04 if layer == "buildings" else 0.20
    tiles = list(_lattice(bbox, step))   # fixed global lattice -> cached tiles are reusable for any overlapping area
    if region is not None:      # only tiles that touch the area of interest (e.g. the flood corridor + buffer)
        from shapely.geometry import box as _box
        tiles = [t for t in tiles if region.intersects(_box(*t))]
    tdir = config.CACHE_DIR / "osm" / "tiles"
    tdir.mkdir(parents=True, exist_ok=True)
    elements, pending = [], []
    for tile in tiles:
        tf = tdir / (hashlib.sha1(f"{layer}{snapshot}{[round(v, 5) for v in tile]}{'v2' if layer == 'places' else ''}".encode()).hexdigest()[:16] + ".json")
        bundled = config.ROOT / "data" / "osm_tiles" / (tf.stem + ".json.gz")      # shipped with the repo (ODbL, pre-event)
        if tf.exists():
            elements.extend(json.loads(tf.read_text(encoding="utf-8")))
        elif bundled.exists():
            import gzip
            els = json.loads(gzip.decompress(bundled.read_bytes()).decode("utf-8"))
            tf.write_text(json.dumps(els), encoding="utf-8")                          # warm the local cache
            elements.extend(els)
        else:
            pending.append((tile, tf))
    log(f"[osm]   {layer}: {len(tiles) - len(pending)}/{len(tiles)} tiles cached, {len(pending)} to fetch")
    from concurrent.futures import ThreadPoolExecutor

    def fetch_one(item):
        tile, tf = item
        q = _overpass_ql(layer, tile, snapshot).replace("[timeout:60]", "[timeout:240]")
        for attempt in range(3):
            try:
                r = requests.post(sources.check(OVERPASS[0]), data={"data": q}, timeout=260, headers=UA)
                if r.status_code == 200:
                    els = r.json().get("elements", [])
                    tf.write_text(json.dumps(els), encoding="utf-8")
                    return els
                if r.status_code == 429:
                    time.sleep(40)
            except (requests.RequestException, ValueError):
                pass
            time.sleep(10 * (attempt + 1))
        return None

    workers = 2 if layer == "buildings" else 1
    for rnd in range(6):  # several passes: a busy public server fails tiles at random
        failed = []
        with ThreadPoolExecutor(workers) as ex:
            for i, (item, els) in enumerate(zip(pending, ex.map(fetch_one, pending))):
                if els is None:
                    failed.append(item)
                else:
                    elements.extend(els)
                if (i + 1) % 10 == 0:
                    log(f"[osm]   {layer}: pass {rnd + 1}, {i + 1}/{len(pending)} (failed so far {len(failed)})")
        pending = failed
        if not pending:
            break
        time.sleep(30)
    if pending:
        raise RuntimeError(f"Overpass could not deliver {len(pending)} tile(s) for '{layer}'; re-run to resume")
    rows, geoms, seen = [], [], set()
    for el in elements:
        if el["id"] in seen:
            continue
        seen.add(el["id"])
        tags = el.get("tags", {})
        g = None
        if el["type"] == "way" and "geometry" in el:
            pts = [(p["lon"], p["lat"]) for p in el["geometry"]]
            if layer == "buildings":
                if len(pts) >= 4 and pts[0] == pts[-1]:
                    g = Polygon(pts)
            elif len(pts) >= 2:
                g = LineString(pts)
        elif el["type"] == "node":
            g = Point(el["lon"], el["lat"])
        elif "center" in el:
            g = Point(el["center"]["lon"], el["center"]["lat"])
        if g is None or g.is_empty:
            continue
        rows.append(tags | {"osm_id": f'{el["type"]}/{el["id"]}'})
        geoms.append(g)
    return gpd.GeoDataFrame(pd.DataFrame(rows), geometry=geoms, crs=4326)


KEEP_TAGS = {"roads": ["highway", "bridge", "tunnel", "surface", "name", "oneway", "access", "layer", "man_made"],
             "buildings": ["building", "name", "amenity", "building:levels"],
             "places": ["place", "name", "name:en", "name:ne", "population"],
             "health": ["amenity", "healthcare", "name", "name:en", "emergency", "beds"]}


def _tidy(gdf, layer):
    """Keep a small, case-insensitively unique set of tag columns (GPKG rejects e.g. FIXME vs fixme)."""
    if not len(gdf):
        return gdf
    cols = [c for c in KEEP_TAGS.get(layer, []) if c in gdf.columns]
    return gdf[cols + ["osm_id", "geometry"]].copy()


def _local_file(layer):
    d = config.ROOT / "data" / "osm_snapshot"
    for ext in ("gpkg", "geojson", "json", "shp"):
        f = d / f"{layer}.{ext}"
        if f.exists():
            return gpd.read_file(f).to_crs(4326)
    return None


def load_osm(bbox, snapshot: dt.date, layers=("roads", "buildings", "places", "health"), log=print, region=None) -> dict:
    """Return ``{layer: GeoDataFrame}`` (EPSG:4326) with the provenance recorded in ``gdf.attrs``."""
    out = {}
    d = config.CACHE_DIR / "osm"
    d.mkdir(parents=True, exist_ok=True)
    for layer in layers:
        key = hashlib.sha1(json.dumps([bbox, snapshot.isoformat(), layer,
                                       region.wkb_hex if (region is not None and layer == "buildings") else None]).encode()).hexdigest()[:14]
        f = d / f"{layer}_{key}.gpkg"
        meta = d / f"{layer}_{key}.json"
        if f.exists():
            g = gpd.read_file(f)
            g.attrs["provider"] = json.loads(meta.read_text(encoding="utf-8"))["provider"] if meta.exists() else "cache"
            out[layer] = g
            log(f"[osm] {layer}: {len(g)} features (cache, {g.attrs['provider']})")
            continue
        gdf, provider = None, None
        for name, fn in (("ohsome", _ohsome_fetch),
                         ("overpass-attic", lambda b, sn, l: _overpass_fetch(b, sn, l, log, region if l == "buildings" else None))):
            try:
                log(f"[osm] {layer} via {name} @ {snapshot} ...")
                gdf, provider = fn(bbox, snapshot, layer), name
                break
            except Exception as exc:
                log(f"[osm]   {name} unavailable: {exc}")
        if gdf is None:
            local = _local_file(layer)
            if local is not None:
                gdf, provider = local, "local-file"
                log(f"[osm] {layer}: using data/osm_snapshot/ file ({len(local)} features) -- make sure it predates the event!")
        if gdf is None:
            raise RuntimeError(f"No OSM provider could deliver layer '{layer}'. See README > OSM fallback.")
        if len(gdf):
            gdf = _tidy(gdf, layer)
            gdf.to_file(f, driver="GPKG")
            meta.write_text(json.dumps({"provider": provider, "snapshot": snapshot.isoformat()}), encoding="utf-8")
        gdf.attrs["provider"] = provider
        out[layer] = gdf
        log(f"[osm] {layer}: {len(gdf)} features ({provider})")
    return out

