"""Static (PNG) and interactive (Leaflet/folium) maps."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

STATUS_COLOR = {"cut_off": "#d7191c", "longer_route": "#fdae61", "connected": "#1a9641",
                "not_assessable": "#999999", "no_road_data": "#7b3294"}
STATUS_LABEL = {"cut_off": "Cut off", "longer_route": "Longer route", "connected": "Connected",
                "not_assessable": "Not assessable", "no_road_data": "No road data"}


def static_map(ctx: dict, path: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    grid, cls, db = ctx["grid"], ctx["cls"], ctx["db"]
    l, b, r, t = grid.bounds
    fig, ax = plt.subplots(figsize=(9, 9 * (t - b) / (r - l) + 0.6), dpi=130)
    bg = np.clip((db["post_vv"] + 25) / 25, 0, 1)
    ax.imshow(np.where(np.isfinite(bg), bg, 0.5), cmap="gray", extent=(l, r, b, t), vmin=0, vmax=1.15, zorder=0)
    rgba = np.zeros(cls.shape + (4,))
    rgba[cls == 3] = [0.1, 0.8, 0.9, 0.55]
    rgba[cls == 2] = [1.0, 0.55, 0.0, 0.85]
    rgba[cls == 1] = [0.0, 0.3, 1.0, 0.9]
    ax.imshow(rgba, extent=(l, r, b, t), zorder=1, interpolation="nearest")
    roads = ctx.get("roads")
    if roads is not None and len(roads):
        roads.plot(ax=ax, color="#ffffff", linewidth=0.35, alpha=0.55, zorder=2)
        hit = roads[roads["hit"]]
        if len(hit):
            hit.plot(ax=ax, color="#ff2d55", linewidth=1.4, zorder=3)
    blk = ctx.get("blocked")
    if blk is not None and len(blk):
        blk.to_crs(grid.crs).plot(ax=ax, color="#ff0000", linewidth=2.2, zorder=4)
    bd = ctx.get("buildings")
    if bd is not None and len(bd):
        aff = bd[bd["status"].isin(["destroyed_likely", "affected"])]
        if len(aff):
            c = aff.geometry.centroid
            ax.scatter(c.x, c.y, s=5, c="#ff00ff", marker="s", zorder=5, linewidths=0)
    s = ctx.get("settlements")
    if s is not None and len(s):
        st = s.to_crs(grid.crs)
        for k, col in STATUS_COLOR.items():
            m = st[st["status"] == k]
            if len(m):
                ax.scatter(m.geometry.x, m.geometry.y, s=60, c=col, edgecolors="black", linewidths=0.8, zorder=6)
        for _, row in st[st["status"].isin(["cut_off", "longer_route"])].head(12).iterrows():
            ax.annotate(str(row["name"])[:22], (row.geometry.x, row.geometry.y), xytext=(4, 4), textcoords="offset points",
                        fontsize=6.5, color="white", zorder=7,
                        bbox=dict(boxstyle="round,pad=0.15", fc="black", ec="none", alpha=0.6))
    d = ctx.get("destinations")
    if d is not None and len(d):
        dd = d.to_crs(grid.crs)
        ax.scatter(dd.geometry.x, dd.geometry.y, s=70, marker="P", c="#00ff66", edgecolors="black", zorder=6)
    fp = ctx.get("flow")
    if fp and fp.get("path_lonlat"):
        from pyproj import Transformer
        tr = Transformer.from_crs(4326, grid.crs, always_xy=True)
        xs, ys = zip(*[tr.transform(*p) for p in fp["path_lonlat"]])
        ax.plot(xs, ys, color="#c77dff", linewidth=1.6, zorder=4)
    ax.set_xlim(l, r)
    ax.set_ylim(b, t)
    ax.set_xticks([]); ax.set_yticks([])
    handles = [Patch(color="#004dff", label="Flood water"), Patch(color="#ff8c00", label="Debris / scour"),
               Patch(color="#19ccdd", label="Permanent water"), Line2D([], [], color="#ff2d55", lw=2, label="Road hit"),
               Line2D([], [], marker="s", ls="", color="#ff00ff", label="Building affected"),
               Line2D([], [], marker="P", ls="", color="#00ff66", mec="black", label="Hospital / town")]
    for k in ("cut_off", "longer_route", "connected"):
        handles.append(Line2D([], [], marker="o", ls="", color=STATUS_COLOR[k], mec="black", label=STATUS_LABEL[k]))
    if fp:
        handles.append(Line2D([], [], color="#c77dff", lw=2, label="Traced flood path"))
    ax.legend(handles=handles, loc="lower left", fontsize=6.5, framealpha=0.85)
    fig.text(0.01, 0.005, "Contains modified Copernicus Sentinel data 2026. Copernicus DEM © DLR/Airbus. "
             "© OpenStreetMap contributors. Educational prototype.", fontsize=5.5, color="#444")
    plt.tight_layout(rect=(0, 0.015, 1, 1))
    fig.savefig(path)
    plt.close(fig)


def interactive_map(out: Path, summary: dict, ctx: dict, path: Path):
    import folium

    l0, b0, l1, b1 = ctx["bbox"]
    m = folium.Map(location=[(b0 + b1) / 2, (l0 + l1) / 2], zoom_start=11, tiles=None, control_scale=True)
    folium.TileLayer("CartoDB positron", name="Basemap: light (display only)").add_to(m)
    folium.TileLayer("Esri.WorldImagery", name="Basemap: imagery (display only)", show=False).add_to(m)

    def load(name):
        f = out / name
        return json.loads(f.read_text()) if f.exists() else {"type": "FeatureCollection", "features": []}

    imp = load("impact_polygons.geojson")
    for cid, label, col in ((1, "Flood water", "#0047ff"), (2, "Debris / scour", "#ff8c00")):
        feats = [f for f in imp["features"] if int(f["properties"].get("cls", 0)) == cid]
        if feats:
            folium.GeoJson({"type": "FeatureCollection", "features": feats}, name=label,
                           style_function=lambda _, c=col: {"color": c, "fillColor": c, "weight": 0.6, "fillOpacity": 0.65}).add_to(m)
    for fname, label, kw in (("roads_hit.geojson", "Roads hit", {"color": "#ff2d55", "weight": 3}),
                             ("blocked_segments.geojson", "Blocked road segments", {"color": "#ff0000", "weight": 5}),
                             ("flowpath.geojson", "Traced flood path", {"color": "#7b2cbf", "weight": 4}),
                             ("flowpath_corridor.geojson", "Susceptible corridor (height above path)",
                              {"color": "#c77dff", "fillColor": "#c77dff", "weight": 0.5, "fillOpacity": 0.25})):
        d = load(fname)
        if d["features"]:
            folium.GeoJson(d, name=label, show=fname != "flowpath_corridor.geojson",
                           style_function=lambda _, k=kw: k).add_to(m)
    bd = load("buildings_affected.geojson")
    if bd["features"]:
        folium.GeoJson(bd, name="Buildings affected / exposed", show=True,
                       style_function=lambda f: {"color": {"destroyed_likely": "#7a0177", "affected": "#e7298a",
                                                           "exposed": "#fcc5c0"}.get(f["properties"].get("status"), "#999"),
                                                 "weight": 1, "fillOpacity": 0.8},
                       tooltip=folium.GeoJsonTooltip(fields=["status"])).add_to(m)
    br = load("bridges_hit.geojson")
    if br["features"]:
        folium.GeoJson(br, name="Bridges hit", style_function=lambda _: {"color": "#ff00ff", "weight": 7}).add_to(m)
    fg = folium.FeatureGroup(name="Settlements (colour = road access)")
    for s in summary["settlements"]:
        col = STATUS_COLOR.get(s["status"], "#999")
        html = (f"<b>{s['name']}</b><br>{STATUS_LABEL.get(s['status'], s['status'])}"
                f"<br>{s['reason']}<br>Buildings: {s['n_buildings']} (affected: {s['n_buildings_affected']})"
                f"<br>Route before: {s['dist_before_km']} km → {s['dest_before']}"
                f"<br>Route after: {s['dist_after_km']} km → {s['dest_after']}")
        folium.CircleMarker([s["lat"], s["lon"]], radius=7, color="black", weight=1, fill=True, fill_color=col,
                            fill_opacity=0.95, popup=folium.Popup(html, max_width=320),
                            tooltip=f"{s['name']} – {STATUS_LABEL.get(s['status'], s['status'])}").add_to(fg)
        if s.get("cut_lon"):
            folium.Marker([s["cut_lat"], s["cut_lon"]], icon=folium.Icon(color="red", icon="remove"),
                          tooltip=f"Road cut on route from {s['name']}").add_to(fg)
    fg.add_to(m)
    dest = load("destinations.geojson")
    if dest["features"]:
        folium.GeoJson(dest, name="Hospitals / towns (route targets)",
                       marker=folium.Marker(icon=folium.Icon(color="green", icon="plus")),
                       tooltip=folium.GeoJsonTooltip(fields=["name"])).add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    title = (f"<div style='position:fixed;top:10px;left:50px;z-index:9999;background:white;padding:6px 10px;"
             f"border-radius:6px;font:13px sans-serif;box-shadow:0 1px 4px #0004'>"
             f"<b>Flood impact – {summary['name']}</b><br>"
             f"Impacted: {summary['area_ha']['impact_total_ha']} ha &middot; cut-off settlements: {summary['access'].get('cut_off', 0)}"
             f"<br><span style='font-size:10px;color:#555'>Contains modified Copernicus Sentinel data 2026 &middot; "
             f"© OpenStreetMap contributors &middot; Copernicus DEM © DLR/Airbus. Educational prototype.</span></div>")
    m.get_root().html.add_child(folium.Element(title))
    m.fit_bounds([[b0, l0], [b1, l1]])
    m.save(path)
