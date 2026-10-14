"""Who is cut off?  Road-graph connectivity before vs. after the event."""
from __future__ import annotations

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
import shapely
from scipy.spatial import cKDTree
from shapely.geometry import LineString, Point
from sklearn.cluster import DBSCAN

from .. import config
from ..config import AccessParams
from ..data.grid import Grid

PRECISION = 7  # decimals on lon/lat used to merge shared OSM nodes into graph nodes


def build_graph(roads: gpd.GeoDataFrame, grid: Grid, impact, blocked_buffer_m: float, min_block_m: float):
    """Vertex-level road graph from pre-event OSM ways.

    Ways that share an OSM node share the exact coordinate, so rounding lon/lat merges junctions
    without needing node ids. Each edge records length, whether it is a bridge and whether the
    impact mask blocks it.
    """
    to_utm = grid.to_utm()
    node_xy, edges = {}, []
    for geom, hw, br in zip(roads.geometry.values, roads.get("highway", pd.Series([None] * len(roads))).values,
                            roads.get("bridge", pd.Series([None] * len(roads))).values):
        parts = [geom] if geom.geom_type == "LineString" else list(getattr(geom, "geoms", []))
        for ln in parts:
            coords = [(round(x, PRECISION), round(y, PRECISION)) for x, y in ln.coords]
            for a, b in zip(coords[:-1], coords[1:]):
                if a == b:
                    continue
                for n in (a, b):
                    if n not in node_xy:
                        node_xy[n] = to_utm.transform(*n)
                edges.append((a, b, hw, br))
    keys = list(node_xy)
    xy = np.array([node_xy[k] for k in keys])
    idx = {k: i for i, k in enumerate(keys)}
    ea = np.array([idx[e[0]] for e in edges])
    eb = np.array([idx[e[1]] for e in edges])
    length = np.hypot(*(xy[ea] - xy[eb]).T)
    lines = shapely.linestrings(np.stack([xy[ea], xy[eb]], axis=1))
    blocked = np.zeros(len(edges), bool)
    if impact is not None:
        buf = shapely.buffer(impact, blocked_buffer_m)
        shapely.prepare(buf)
        cand = np.where(np.asarray(shapely.intersects(lines, buf)))[0]
        if cand.size:
            inter = shapely.length(shapely.intersection(lines[cand], buf))
            # short OSM segments (< min_block_m) count as blocked when fully inside
            need = np.minimum(min_block_m, 0.5 * length[cand])
            blocked[cand] = inter >= need
    G0, G1 = nx.Graph(), nx.Graph()
    for i, (a, b, hw, br) in enumerate(edges):
        attrs = {"length": float(length[i]), "bridge": bool(br and br != "no"), "eid": i}
        G0.add_edge(ea[i], eb[i], **attrs)
        if not blocked[i]:
            G1.add_edge(ea[i], eb[i], **attrs)
    for n in G0.nodes:
        if n not in G1:
            G1.add_node(n)
    return {"G0": G0, "G1": G1, "xy": xy, "tree": cKDTree(xy), "lines": lines, "blocked": blocked,
            "bridge": np.array([bool(e[3] and e[3] != "no") for e in edges]), "keys": keys}


def settlements_from_osm(places: gpd.GeoDataFrame, buildings: gpd.GeoDataFrame, grid: Grid, p: AccessParams):
    """Settlement anchors = OSM place nodes + unnamed building clusters far from any place node."""
    to_utm = grid.to_utm()
    rows = []
    for _, r in places.iterrows():
        x, y = to_utm.transform(r.geometry.x, r.geometry.y)
        rows.append({"name": r.get("name") or r.get("name:en") or f"{r.get('place', 'place')} (unnamed)",
                     "kind": r.get("place"), "x": x, "y": y, "source": "osm_place"})
    anchors = pd.DataFrame(rows, columns=["name", "kind", "x", "y", "source"])
    bxy = np.empty((0, 2))
    if len(buildings):
        c = buildings.to_crs(grid.crs).geometry.centroid
        bxy = np.column_stack([c.x.values, c.y.values])
        if len(bxy) >= p.cluster_min_buildings:
            lab = DBSCAN(eps=p.cluster_eps_m, min_samples=p.cluster_min_buildings).fit_predict(bxy)
            extra = []
            atree = cKDTree(anchors[["x", "y"]].values) if len(anchors) else None
            for k in sorted(set(lab) - {-1}):
                cx, cy = bxy[lab == k].mean(axis=0)
                if atree is None or atree.query([cx, cy])[0] > 600:
                    extra.append({"name": f"Unnamed settlement {len(extra) + 1}", "kind": "cluster",
                                  "x": cx, "y": cy, "source": "building_cluster"})
            if extra:
                anchors = pd.concat([anchors, pd.DataFrame(extra)], ignore_index=True)
    anchors["n_buildings"] = 0
    anchors["bidx"] = [[] for _ in range(len(anchors))]
    if len(anchors) and len(bxy):
        d, j = cKDTree(anchors[["x", "y"]].values).query(bxy)
        for bi, (dist, aj) in enumerate(zip(d, j)):
            if dist <= 500:
                anchors.at[aj, "n_buildings"] += 1
                anchors.at[aj, "bidx"].append(bi)
    return anchors


def _nearest_dest(G, sources):
    """Distance (m) and nearest-source node for every node reachable from ``sources``."""
    srcs = [s for s in sources if s in G]
    if not srcs:
        return {}, {}
    dist, paths = nx.multi_source_dijkstra(G, srcs, weight="length")
    return dist, {n: p[0] for n, p in paths.items()}


def analyse_access(roads, places, health, buildings_status, grid: Grid, impact, aoi_lonlat,
                   p: AccessParams | None = None, blocked_buffer_m: float | None = None, log=print) -> dict:
    """Cut-off analysis.

    ``buildings_status`` is the output of ``damage.assess_buildings`` (used to count buildings per settlement).
    Returns dict with a settlements GeoDataFrame (EPSG:4326), blocked edges and summary numbers.
    """
    p = p or AccessParams()
    bb = blocked_buffer_m if blocked_buffer_m is not None else grid.res * 0.5
    g = build_graph(roads, grid, impact, bb, 10.0)
    G0, G1, xy, tree = g["G0"], g["G1"], g["xy"], g["tree"]
    log(f"[access] graph: {G0.number_of_nodes()} nodes, {G0.number_of_edges()} edges, "
        f"{int(g['blocked'].sum())} blocked segments")

    to_utm = grid.to_utm()
    dest_rows = []
    for _, r in health.iterrows():
        geom = r.geometry if r.geometry.geom_type == "Point" else r.geometry.centroid
        x, y = to_utm.transform(geom.x, geom.y)
        kind = r.get("amenity") or r.get("healthcare")
        dest_rows.append({"name": r.get("name") or f"{kind} (unnamed)", "kind": str(kind), "x": x, "y": y,
                          "type": "health"})
    for _, r in places[places["place"].isin(config.TOWN_CLASSES)].iterrows() if len(places) else []:
        x, y = to_utm.transform(r.geometry.x, r.geometry.y)
        dest_rows.append({"name": r.get("name") or "town", "kind": r["place"], "x": x, "y": y, "type": "town"})
    dest = pd.DataFrame(dest_rows, columns=["name", "kind", "x", "y", "type"])
    # prefer hospitals; clinics/doctors/towns are fallbacks counted as destinations too
    dest["node"] = -1
    if len(dest):
        d, j = tree.query(dest[["x", "y"]].values)
        dest["node"] = np.where(d <= p.snap_m, j, -1)
        dest["snap_m"] = d
    dest_ok = dest[dest["node"] >= 0] if len(dest) else dest
    log(f"[access] destinations snapped to road network: {len(dest_ok)}/{len(dest)}")

    dist0, src0 = _nearest_dest(G0, dest_ok["node"].tolist() if len(dest_ok) else [])
    dist1, src1 = _nearest_dest(G1, dest_ok["node"].tolist() if len(dest_ok) else [])
    node_to_dest = {int(r.node): r.name for r in dest_ok.itertuples()} if len(dest_ok) else {}

    S = settlements_from_osm(places, buildings_status if buildings_status is not None else gpd.GeoDataFrame(), grid, p)
    if len(S):
        d, j = tree.query(S[["x", "y"]].values)
        S["road_node"] = np.where(d <= p.snap_m, j, -1)
        S["snap_m"] = d
    results = []
    lon0, lat0, lon1, lat1 = aoi_lonlat
    from_utm = grid.from_utm()
    bstat = buildings_status.reset_index(drop=True) if buildings_status is not None and len(buildings_status) else None
    for r in S.itertuples():
        lon, lat = from_utm.transform(r.x, r.y)
        if not (lon0 <= lon <= lon1 and lat0 <= lat <= lat1):
            continue
        n_aff = 0
        if bstat is not None and r.bidx:
            n_aff = int(bstat.loc[r.bidx, "status"].isin(["destroyed_likely", "affected"]).sum())
        node = int(r.road_node)
        d0 = dist0.get(node, np.inf) if node >= 0 else np.inf
        d1 = dist1.get(node, np.inf) if node >= 0 else np.inf
        direct = bool(impact is not None and shapely.distance(Point(r.x, r.y), impact) <= grid.res) or \
            (r.n_buildings >= 3 and n_aff / max(r.n_buildings, 1) >= 0.3)
        if node < 0:
            status, why = "no_road_data", "no mapped road within %d m" % p.snap_m
        elif not np.isfinite(d0):
            status, why = "not_assessable", "no road route to any hospital/town in the pre-event map"
        elif not np.isfinite(d1):
            status, why = "cut_off", "pre-event road route to a hospital/town no longer exists"
        elif d1 > p.detour_ratio * max(d0, 100) and d1 - d0 > 1000:
            status, why = "longer_route", f"route now {d1 / max(d0, 1):.1f}x longer"
        else:
            status, why = "connected", "road route to a hospital/town remains"
        if direct and status in ("connected", "longer_route"):
            status_note = "inundated"
        else:
            status_note = ""
        cut_pt = None
        if status in ("cut_off", "longer_route") and np.isfinite(d0):
            # locate the blocked segment(s) on the pre-event shortest path (closest to the settlement)
            try:
                path = nx.shortest_path(G0, node, src0[node], weight="length")
                for a, b in zip(path[:-1], path[1:]):
                    if not G1.has_edge(a, b):
                        mx, my = (xy[a] + xy[b]) / 2
                        cut_pt = from_utm.transform(mx, my)
                        break
            except Exception:
                pass
        results.append({
            "name": r.name, "kind": r.kind, "source": r.source, "lon": lon, "lat": lat,
            "n_buildings": int(r.n_buildings), "n_buildings_affected": n_aff,
            "status": status, "inundated": status_note == "inundated" or (direct and status == "cut_off"),
            "reason": why,
            "dist_before_km": None if not np.isfinite(d0) else round(d0 / 1e3, 2),
            "dist_after_km": None if not np.isfinite(d1) else round(d1 / 1e3, 2),
            "dest_before": node_to_dest.get(int(src0[node])) if np.isfinite(d0) else None,
            "dest_after": node_to_dest.get(int(src1[node])) if np.isfinite(d1) else None,
            "cut_lon": None if cut_pt is None else cut_pt[0], "cut_lat": None if cut_pt is None else cut_pt[1],
        })
    df = pd.DataFrame(results)
    gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs=4326) if len(df) else \
        gpd.GeoDataFrame(df, geometry=[], crs=4326)
    # blocked road segments as lines for the map
    bl = np.where(g["blocked"])[0]
    to_ll = grid.from_utm()
    blocked_lines = []
    for i in bl:
        a, b = shapely.get_coordinates(g["lines"][i])
        blocked_lines.append({"bridge": bool(g["bridge"][i]),
                              "geometry": LineString([to_ll.transform(*a), to_ll.transform(*b)])})
    blocked_gdf = gpd.GeoDataFrame(blocked_lines, geometry="geometry", crs=4326) if blocked_lines else \
        gpd.GeoDataFrame({"bridge": []}, geometry=[], crs=4326)
    dest_ll = gpd.GeoDataFrame(dest_ok.drop(columns=["x", "y", "node", "snap_m"], errors="ignore"),
                               geometry=[Point(*from_utm.transform(x, y)) for x, y in dest_ok[["x", "y"]].values],
                               crs=4326) if len(dest_ok) else gpd.GeoDataFrame({"name": []}, geometry=[], crs=4326)
    summary = {"settlements": int(len(gdf)), "destinations": int(len(dest_ok)),
               "blocked_segments": int(g["blocked"].sum())}
    for st in ("connected", "longer_route", "cut_off", "not_assessable", "no_road_data"):
        summary[st] = int((gdf["status"] == st).sum()) if len(gdf) else 0
    summary["buildings_in_cut_off"] = int(gdf.loc[gdf["status"] == "cut_off", "n_buildings"].sum()) if len(gdf) else 0
    return {"settlements": gdf, "blocked": blocked_gdf, "destinations": dest_ll, "summary": summary}
