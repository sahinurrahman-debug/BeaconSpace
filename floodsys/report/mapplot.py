"""Static (PNG) and interactive (Leaflet/folium) maps."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

STATUS_COLOR = {"cut_off": "#FF4D5E", "longer_route": "#FBBF24", "connected": "#34D399",
                "not_assessable": "#8FA0BD", "no_road_data": "#A78BFA"}
STATUS_LABEL = {"cut_off": "Cut off", "longer_route": "Longer route", "connected": "Connected",
                "not_assessable": "Not assessable", "no_road_data": "No road data"}


def _font_fallback():
    """Let matplotlib draw Nepali (Devanagari) place names if a suitable font exists."""
    import matplotlib
    from matplotlib import font_manager as fm
    have = {f.name for f in fm.fontManager.ttflist}
    extra = [n for n in ("Nirmala UI", "Noto Sans Devanagari", "Mangal", "Lohit Devanagari") if n in have]
    matplotlib.rcParams["font.family"] = ["DejaVu Sans"] + extra


def static_map(ctx: dict, path: Path):
    import matplotlib
    matplotlib.use("Agg")
    _font_fallback()
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    from scipy import ndimage as ndi

    grid, cls, db = ctx["grid"], ctx["cls"], ctx["db"]
    l, b, r, t = grid.bounds
    # crop to the affected corridor (+ margin) so the picture is about the damage, not the empty hills
    imp = np.isin(cls, (1, 2))
    if imp.any():
        rr, cc = np.where(imp)
        m = int(4000 / grid.res)
        r0, r1 = max(rr.min() - m, 0), min(rr.max() + m, grid.height)
        c0, c1 = max(cc.min() - m, 0), min(cc.max() + m, grid.width)
    else:
        r0, r1, c0, c1 = 0, grid.height, 0, grid.width
    ext = (l + c0 * grid.res, l + c1 * grid.res, t - r1 * grid.res, t - r0 * grid.res)
    w, h = ext[1] - ext[0], ext[3] - ext[2]
    fig, ax = plt.subplots(figsize=(10, 10 * h / w + 1.3), dpi=130)
    bg = np.clip((db["post_vv"][r0:r1, c0:c1] + 25) / 25, 0, 1)
    ax.imshow(np.where(np.isfinite(bg), bg, 0.5), cmap="gray", extent=ext, vmin=0, vmax=1.2, zorder=0)
    roads = ctx.get("roads")
    if roads is not None and len(roads):
        roads.plot(ax=ax, color="#ffffff", linewidth=0.3, alpha=0.5, zorder=1)
    s = ctx.get("settlements")
    if s is not None and len(s):
        st = s.to_crs(grid.crs)
        for k, size, alpha in (("no_road_data", 5, 0.35), ("not_assessable", 5, 0.35), ("connected", 9, 0.7)):
            mm = st[st["status"] == k]
            if len(mm):
                ax.scatter(mm.geometry.x, mm.geometry.y, s=size, c=STATUS_COLOR[k], alpha=alpha, linewidths=0, zorder=2)
    # impact on top, slightly dilated for display only (20 m pixels are tiny at this scale)
    show = ndi.binary_dilation(cls == 2, iterations=1)
    rgba = np.zeros(cls.shape + (4,))
    rgba[cls == 3] = [0.1, 0.8, 0.9, 0.6]
    rgba[ndi.binary_dilation(cls == 2, iterations=1) & (cls != 1)] = [1.0, 0.55, 0.0, 0.9]
    rgba[show] = [0.0, 0.3, 1.0, 0.95]
    ax.imshow(rgba[r0:r1, c0:c1], extent=ext, zorder=3, interpolation="nearest")
    if roads is not None and len(roads):
        hit = roads[roads["hit"]]
        if len(hit):
            hit.plot(ax=ax, color="#ff2d55", linewidth=1.2, zorder=4)
    blk = ctx.get("blocked")
    if blk is not None and len(blk):
        blk.to_crs(grid.crs).plot(ax=ax, color="#ff0000", linewidth=2.2, zorder=4)
    bd = ctx.get("buildings")
    if bd is not None and len(bd):
        aff = bd[bd["status"].isin(["destroyed_likely", "affected"])]
        if len(aff):
            c = aff.geometry.centroid
            ax.scatter(c.x, c.y, s=3, c="#ff00ff", marker="s", zorder=5, linewidths=0)
    if s is not None and len(s):
        for k in ("longer_route", "cut_off"):
            mm = st[st["status"] == k]
            if len(mm):
                ax.scatter(mm.geometry.x, mm.geometry.y, s=34, c=STATUS_COLOR[k], edgecolors="black", linewidths=0.6, zorder=6)
        top = st[st["status"] == "cut_off"].sort_values("n_buildings", ascending=False)
        top = top[~top["name"].astype(str).str.contains("unnamed", case=False)].head(10)
        for _, row in top.iterrows():
            ax.annotate(str(row["name"])[:20], (row.geometry.x, row.geometry.y), xytext=(5, 5), textcoords="offset points",
                        fontsize=7, color="white", zorder=7, bbox=dict(boxstyle="round,pad=0.15", fc="black", ec="none", alpha=0.65))
    d = ctx.get("destinations")
    if d is not None and len(d):
        dd = d.to_crs(grid.crs)
        ax.scatter(dd.geometry.x, dd.geometry.y, s=60, marker="P", c="#00ff66", edgecolors="black", linewidths=0.6, zorder=6)
    fp = ctx.get("flow")
    if fp and fp.get("path_lonlat"):
        from pyproj import Transformer
        tr = Transformer.from_crs(4326, grid.crs, always_xy=True)
        xs, ys = zip(*[tr.transform(*p) for p in fp["path_lonlat"]])
        ax.plot(xs, ys, color="#c77dff", linewidth=1.6, zorder=4)
    ax.set_xlim(ext[0], ext[1]); ax.set_ylim(ext[2], ext[3])
    ax.set_xticks([]); ax.set_yticks([]); ax.set_xlabel(""); ax.set_ylabel("")
    handles = [Patch(color="#004dff", label="Flood water"), Patch(color="#ff8c00", label="Debris / scour"),
               Patch(color="#19ccdd", label="Permanent water"), Line2D([], [], color="#ff2d55", lw=2, label="Road hit"),
               Line2D([], [], marker="s", ls="", color="#ff00ff", label="Building affected"),
               Line2D([], [], marker="P", ls="", color="#00ff66", mec="black", label="Hospital / town")]
    for k in ("cut_off", "longer_route", "connected"):
        handles.append(Line2D([], [], marker="o", ls="", color=STATUS_COLOR[k], mec="black", label=STATUS_LABEL[k]))
    if fp:
        handles.append(Line2D([], [], color="#c77dff", lw=2, label="Traced flood path"))
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.01), ncol=5, fontsize=7.5, frameon=False)
    fig.text(0.01, 0.005, f"Contains modified Copernicus Sentinel data {ctx.get('year', 2026)}. Copernicus DEM © DLR/Airbus. "
             "© OpenStreetMap contributors. Educational prototype.", fontsize=5.5, color="#444")
    plt.tight_layout(rect=(0, 0.015, 1, 1))
    fig.savefig(path)
    plt.close(fig)


def interactive_map(out: Path, summary: dict, ctx: dict, path: Path):
    import folium

    l0, b0, l1, b1 = ctx["bbox"]
    m = folium.Map(location=[(b0 + b1) / 2, (l0 + l1) / 2], zoom_start=11, tiles=None, control_scale=True)
    _esri = "https://server.arcgisonline.com/ArcGIS/rest/services/{}/MapServer/tile/{{z}}/{{y}}/{{x}}"
    _attr = "Tiles &copy; Esri &mdash; display only"
    folium.TileLayer(_esri.format("Canvas/World_Dark_Gray_Base"), attr=_attr, name="Basemap: dark (display only)",
                     max_native_zoom=16, max_zoom=18).add_to(m)
    folium.TileLayer(_esri.format("Canvas/World_Light_Gray_Base"), attr=_attr, name="Basemap: light (display only)",
                     show=False, max_native_zoom=16, max_zoom=18).add_to(m)
    folium.TileLayer("Esri.WorldTopoMap", name="Basemap: topographic (display only)", show=False).add_to(m)
    folium.TileLayer("Esri.WorldImagery", name="Basemap: imagery (display only)", show=False).add_to(m)

    def load(name):
        f = out / name
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"type": "FeatureCollection", "features": []}

    imp = load("impact_polygons.geojson")
    for cid, label, col in ((1, "Flood water", "#3B82F6"), (2, "Debris / scour", "#ff8c00")):
        feats = [f for f in imp["features"] if int(f["properties"].get("cls", 0)) == cid]
        if feats:
            folium.GeoJson({"type": "FeatureCollection", "features": feats}, name=label,
                           style_function=lambda _, c=col: {"color": c, "fillColor": c, "weight": 0.6, "fillOpacity": 0.65}).add_to(m)
    for fname, label, kw in (("roads_hit.geojson", "Roads hit", {"color": "#FF4D5E", "weight": 3}),
                             ("blocked_segments.geojson", "Blocked road segments", {"color": "#FF4D5E", "weight": 5}),
                             ("flowpath.geojson", "Traced flood path", {"color": "#A78BFA", "weight": 4}),
                             ("flowpath_corridor.geojson", "Susceptible corridor (height above path)",
                              {"color": "#A78BFA", "fillColor": "#A78BFA", "weight": 0.5, "fillOpacity": 0.2})):
        d = load(fname)
        if d["features"]:
            folium.GeoJson(d, name=label, show=fname != "flowpath_corridor.geojson",
                           style_function=lambda _, k=kw: k).add_to(m)
    bd = load("buildings_affected.geojson")
    if bd["features"]:
        folium.GeoJson(bd, name="Buildings affected / exposed", show=True,
                       style_function=lambda f: {"color": {"destroyed_likely": "#C026D3", "affected": "#E879F9",
                                                           "exposed": "#F5D0FE"}.get(f["properties"].get("status"), "#999"),
                                                 "weight": 1, "fillOpacity": 0.8},
                       tooltip=folium.GeoJsonTooltip(fields=["status"])).add_to(m)
    br = load("bridges_hit.geojson")
    if br["features"]:
        folium.GeoJson(br, name="Bridges hit", style_function=lambda _: {"color": "#ff00ff", "weight": 7}).add_to(m)
    fg = folium.FeatureGroup(name="Settlements (colour = road access)")
    fg_other = folium.FeatureGroup(name="Settlements without usable road data (off by default)", show=False)
    for s in summary["settlements"]:
        target = fg if s["status"] in ("cut_off", "longer_route", "connected") else fg_other
        col = STATUS_COLOR.get(s["status"], "#999")
        html = (f"<b>{s['name']}</b><br>{STATUS_LABEL.get(s['status'], s['status'])}"
                f"<br>{s['reason']}<br>Buildings: {s['n_buildings']} (affected: {s['n_buildings_affected']})"
                f"<br>Route before: {s['dist_before_km']} km → {s['dest_before']}"
                f"<br>Route after: {s['dist_after_km']} km → {s['dest_after']}")
        folium.CircleMarker([s["lat"], s["lon"]], radius=7, color="black", weight=1, fill=True, fill_color=col,
                            fill_opacity=0.95, popup=folium.Popup(html, max_width=320),
                            tooltip=f"{s['name']} – {STATUS_LABEL.get(s['status'], s['status'])}").add_to(target)
        if s.get("cut_lon") is not None and s["cut_lon"] == s["cut_lon"] and s.get("cut_lat") == s.get("cut_lat"):
            folium.Marker([s["cut_lat"], s["cut_lon"]], icon=folium.Icon(color="red", icon="remove"),
                          tooltip=f"Road cut on route from {s['name']}").add_to(fg)
    fg.add_to(m)
    fg_other.add_to(m)
    dest = load("destinations.geojson")
    if dest["features"]:
        folium.GeoJson(dest, name="Hospitals / towns (route targets)",
                       marker=folium.Marker(icon=folium.Icon(color="green", icon="plus")),
                       tooltip=folium.GeoJsonTooltip(fields=["name"])).add_to(m)
    folium.LayerControl(collapsed=True).add_to(m)
    m.get_root().header.add_child(folium.Element(_PANEL_CSS))
    A, D, AC = summary["area_ha"], summary["damage"], summary["access"]
    nm = summary["name"].replace("_", " ")
    ev_date = summary["event_utc"][:10]
    hdr = (f"<div class='bs-glass bs-hdr'><div class='bs-k'>BEACONSPACE · FLOOD IMPACT</div><div class='bs-t'>{nm}</div>"
           f"<div class='bs-stats'><div><b>{A['impact_total_ha']:,.0f}</b><span>ha flooded / debris</span></div>"
           f"<div><b>{D['buildings']['affected_total']:,}</b><span>buildings affected</span></div>"
           f"<div><b>{D['roads_total_hit_km']:,.0f}</b><span>km road hit</span></div>"
           f"<div class='crit'><b>{AC.get('cut_off', 0)}</b><span>cut off</span></div></div>"
           f"<div class='bs-m'>FLOOD {ev_date} · Contains modified Copernicus Sentinel data {summary['event_utc'][:4]} · © OpenStreetMap contributors · "
           f"Copernicus DEM © DLR/Airbus · educational prototype</div></div>")
    legend = ("<div class='bs-glass bs-leg'>" + "".join(f"<div><i style='background:{c}'></i>{t}</div>" for c, t in (
        ("#3B82F6", "Flood water"), ("#FF8C00", "Debris / scour"), ("#FF4D5E", "Road hit"), ("#E879F9", "Building affected"),
        (STATUS_COLOR["cut_off"], "Critical: cut off"), (STATUS_COLOR["longer_route"], "Watch: longer route"),
        (STATUS_COLOR["connected"], "Normal: connected"))) + "</div>")
    m.get_root().html.add_child(folium.Element(hdr + legend))
    wr_meta = out / "waterrise.json"
    if wr_meta.exists() and (out / "waterrise.png").exists():
        import base64
        meta = json.loads(wr_meta.read_text(encoding="utf-8"))
        png = base64.b64encode((out / "waterrise.png").read_bytes()).decode()
        panel = ("<div class='bs-glass bs-wr'><div class='bs-k'>WATER-RISE PREVIEW</div>"
                 "<label for='bs-h'>+<b id='bs-hv'>5</b> m above the nearest river</label>"
                 f"<input id='bs-h' type='range' min='0' max='{meta['max_h']}' value='5' step='1' aria-label='Water level above nearest river in metres'>"
                 "<div class='bs-row'><div><b id='bs-a'>–</b><span>ha</span></div><div><b id='bs-b'>–</b><span>buildings</span></div>"
                 "<div><b id='bs-s'>–</b><span>settlements</span></div></div>"
                 "<div class='bs-n'>Indicative, terrain-only (height above nearest drainage). Not a flood forecast.</div></div>")
        js = ("<script>(function(){var D=" + json.dumps({k: meta[k] for k in ('bounds', 'area_ha', 'buildings', 'settlements', 'n_buildings', 'n_settlements')})
              + ";var SRC='data:image/png;base64," + png + "';var NAME='" + m.get_name() + "';"
              + _WR_JS + "})();</script>")
        m.get_root().html.add_child(folium.Element(panel + js))
    m.fit_bounds([[b0, l0], [b1, l1]])
    m.save(path)


_PANEL_CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');
:root{--g-bg:rgba(15,21,33,.66);--g-fg:#E6EAF2;--g-mut:#8FA0BD;--g-line:rgba(255,255,255,.10);--g-acc:#22D3EE;--g-crit:#FF4D5E}
.bs-light{--g-bg:rgba(255,255,255,.74);--g-fg:#0B1220;--g-mut:#526079;--g-line:rgba(15,23,42,.14);--g-acc:#0E7490;--g-crit:#C81E2E}
.bs-glass{position:fixed;z-index:9999;background:var(--g-bg);color:var(--g-fg);border:1px solid var(--g-line);border-radius:14px;
backdrop-filter:blur(14px) saturate(1.25);-webkit-backdrop-filter:blur(14px) saturate(1.25);box-shadow:0 8px 28px rgba(0,0,0,.35);
font:14px/1.4 Inter,system-ui,sans-serif;padding:14px 16px}
.bs-k{font:600 11px/1.2 'JetBrains Mono',ui-monospace,Consolas,monospace;letter-spacing:.12em;color:var(--g-acc);margin-bottom:6px}
.bs-t{font-weight:700;font-size:16px;margin-bottom:10px}
.bs-hdr{top:12px;left:56px;max-width:min(560px,calc(100vw - 150px))}
.bs-stats{display:grid;grid-template-columns:repeat(4,auto);gap:4px 20px}
.bs-stats b{display:block;font:600 22px/1.1 'JetBrains Mono',ui-monospace,Consolas,monospace}
.bs-stats span,.bs-row span{display:block;font-size:12px;color:var(--g-mut)}.bs-stats .crit b{color:var(--g-crit)}
.bs-m{margin-top:10px;font:400 10.5px/1.45 'JetBrains Mono',ui-monospace,Consolas,monospace;color:var(--g-mut)}
.bs-leg{right:12px;bottom:28px;font-size:13px;padding:10px 14px;display:grid;gap:4px}
.bs-leg i{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:8px}
.bs-wr{left:12px;bottom:28px;width:min(340px,calc(100vw - 24px))}
.bs-wr label{display:block;font-size:15px;margin:2px 0 8px}.bs-wr label b{font:600 18px 'JetBrains Mono',ui-monospace,monospace;color:var(--g-acc)}
.bs-wr input[type=range]{width:100%;accent-color:var(--g-acc);height:28px;cursor:pointer}
.bs-row{display:flex;gap:18px;margin-top:6px}.bs-row b{font:600 18px 'JetBrains Mono',ui-monospace,monospace}
.bs-n{margin-top:8px;font-size:12px;color:var(--g-mut)}
.leaflet-control-layers,.leaflet-bar a,.leaflet-control-attribution,.leaflet-popup-content-wrapper,.leaflet-popup-tip{background:var(--g-bg)!important;color:var(--g-fg)!important;
backdrop-filter:blur(10px);border:1px solid var(--g-line)}
.leaflet-container a{color:var(--g-acc)}.leaflet-control-layers-expanded{padding:10px 14px}
@media (max-width:700px){.bs-hdr{left:56px;right:12px}.bs-stats{grid-template-columns:repeat(2,auto)}.bs-leg{display:none}}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
</style>"""

_WR_JS = r"""
function init(){
  var map=window[NAME]; if(!map||!window.L){return setTimeout(init,150)}
  var img=new Image();
  img.onload=function(){
    var W=img.width,H=img.height,sc=document.createElement('canvas');sc.width=W;sc.height=H;
    var sx=sc.getContext('2d');sx.drawImage(img,0,0);var sd=sx.getImageData(0,0,W,H).data;
    var cv=document.createElement('canvas');cv.width=W;cv.height=H;var cx=cv.getContext('2d'),out=cx.createImageData(W,H),o=out.data;
    map.createPane('waterrise');map.getPane('waterrise').style.zIndex=350;map.getPane('waterrise').style.pointerEvents='none';
    var im=new Image();var ov=L.imageOverlay(im,D.bounds,{pane:'waterrise',opacity:.7,interactive:false}).addTo(map);var last=null;
    function show(){cv.toBlob(function(b){var u=URL.createObjectURL(b);im.src=u;if(last){URL.revokeObjectURL(last)}last=u})}
    var el=function(i){return document.getElementById(i)};
    function paint(h){
      for(var i=0,j=0;i<sd.length;i+=4,j+=4){var v=sd[i];
        if(v<=h){o[j]=34;o[j+1]=211;o[j+2]=238;o[j+3]=v>=h-1?255:205}else{o[j+3]=0}}
      cx.putImageData(out,0,0);show();
      el('bs-hv').textContent=h;el('bs-a').textContent=Math.round(D.area_ha[h]).toLocaleString();
      el('bs-b').textContent=D.buildings[h].toLocaleString();el('bs-s').textContent=D.settlements[h].toLocaleString();
    }
    var sl=el('bs-h'),t=null;paint(+sl.value);
    sl.addEventListener('input',function(){clearTimeout(t);var v=+sl.value;t=setTimeout(function(){paint(v)},40)});
  };
  img.src=SRC;
}
window.addEventListener('load',init);
"""
