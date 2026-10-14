"""Map dashboard:  streamlit run app/dashboard.py

Pick an area + flood date -> the system searches Sentinel-1/2, finds same-track pre/post radar pairs, maps flood and
debris, overlays pre-event OSM buildings/roads/bridges, finds cut-off settlements and writes a bilingual situation report.
"""
import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from floodsys import config  # noqa: E402
from floodsys.presets import PRESETS  # noqa: E402
from floodsys.report.sitrep import facts  # noqa: E402

st.set_page_config(page_title="BeaconSpace", layout="wide", page_icon="🛰️")
UTC = dt.timezone.utc
OUT = config.OUTPUT_DIR

st.markdown("""<style>.block-container{padding-top:1.2rem} [data-testid=stMetricValue]{font-size:1.6rem}</style>""",
            unsafe_allow_html=True)
st.title("🛰️ BeaconSpace")
st.caption("Mapping flood damage from space · Where did the flood hit?  What was damaged?  Who is cut off?  — Sentinel-1/2 + Copernicus DEM + pre-event OpenStreetMap. "
           + config.DISCLAIMER)

runs = sorted([p for p in OUT.glob("*/summary.json")], key=lambda p: p.stat().st_mtime, reverse=True) if OUT.exists() else []

with st.sidebar:
    st.header("1 · Area and date")
    mode = st.radio("Source", ["Open a finished run", "Run a new analysis"], index=0 if runs else 1)
    if mode == "Run a new analysis":
        key = st.selectbox("Preset", list(PRESETS) + ["custom"], format_func=lambda k: PRESETS[k]["label"] if k in PRESETS else "Custom area")
        base = PRESETS.get(key, PRESETS["trishuli"])
        c1, c2 = st.columns(2)
        w = c1.number_input("West", value=float(base["bbox"][0]), format="%.4f")
        e = c2.number_input("East", value=float(base["bbox"][2]), format="%.4f")
        s = c1.number_input("South", value=float(base["bbox"][1]), format="%.4f")
        n = c2.number_input("North", value=float(base["bbox"][3]), format="%.4f")
        d = st.date_input("Flood date (UTC)", value=base["event"].date())
        tm = st.time_input("Approx. time (UTC)", value=base["event"].time())
        res = st.select_slider("Resolution (m)", [10, 20, 40], value=20, help="10 m = sharpest, slowest")
        pairs = st.slider("Radar tracks to combine", 1, 3, 2)
        use_s2 = st.checkbox("Use Sentinel-2 where cloud-free", True)
        use_model = st.checkbox("Use trained AI model if present", True)
        trace = st.checkbox("Trace flood path from an upstream point (bonus)", key == "trishuli")
        tlon = st.number_input("Upstream lon", value=float((base.get("trace_from") or (85.38, 28.2))[0]), format="%.4f", disabled=not trace)
        tlat = st.number_input("Upstream lat", value=float((base.get("trace_from") or (85.38, 28.2))[1]), format="%.4f", disabled=not trace)
        go = st.button("▶ Run analysis", type="primary", use_container_width=True)
        area_km2 = abs((e - w) * 111 * 0.88) * abs((n - s) * 111)
        st.caption(f"Area ≈ {area_km2:,.0f} km². First run of a new area downloads data (several minutes); repeats are cached.")
    else:
        names = [p.parent.name for p in runs]
        sel = st.selectbox("Run", names) if names else None
        go = False

if mode == "Run a new analysis" and go:
    from floodsys.pipeline import RunConfig, run
    cfg = RunConfig(bbox=(w, s, e, n), event=dt.datetime.combine(d, tm).replace(tzinfo=UTC), res=float(res), n_pairs=pairs,
                    use_s2=use_s2, use_model=use_model, trace_from=(tlon, tlat) if trace else None,
                    name=f"{key}_{d:%Y%m%d}_{res}m")
    box = st.status("Running analysis …", expanded=True)
    logs = []

    def log(m):
        logs.append(m)
        box.write(m)
    try:
        r = run(cfg, log=log)
        box.update(label="Done", state="complete")
        st.session_state["sel_run"] = r["out"].name
        st.rerun()
    except Exception as exc:  # show the reason instead of a stack trace
        box.update(label="Failed", state="error")
        st.error(f"{exc}")
        st.stop()

runs = sorted([p for p in OUT.glob("*/summary.json")], key=lambda p: p.stat().st_mtime, reverse=True) if OUT.exists() else []
if not runs:
    st.info("No finished run yet. Choose **Run a new analysis** in the sidebar (try the *Trishuli* preset).")
    st.stop()
name = st.session_state.get("sel_run") if mode == "Run a new analysis" else sel
rd = OUT / (name or runs[0].parent.name)
if not (rd / "summary.json").exists():
    rd = runs[0].parent
S = json.loads((rd / "summary.json").read_text(encoding="utf-8"))
F = facts(S)

c = st.columns(5)
c[0].metric("Flooded + debris", f"{F['impact_ha']:,.0f} ha", f"{F['flood_ha']:,.0f} water · {F['debris_ha']:,.0f} debris", delta_color="off")
c[1].metric("Buildings affected", f"{F['b_aff']:,}", f"of {F['b_total']:,} mapped", delta_color="off")
c[2].metric("Road hit", f"{F['road_hit_km']:,.1f} km", f"{F['br_hit']}/{F['br_total']} bridges", delta_color="off")
c[3].metric("Settlements cut off", F["n_cut"], f"{F['n_long']} longer route", delta_color="off")
c[4].metric("Run time", f"{S['runtime_s']:.0f} s", f"{S['resolution_m']:.0f} m grid", delta_color="off")

tab_map, tab_cut, tab_rep, tab_data, tab_eval = st.tabs(["🗺️ Map", "🚧 Who is cut off", "📄 Situation report", "🔎 Data & method", "✅ Check vs EMSR927"])
with tab_map:
    html = (rd / "dashboard_map.html")
    if html.exists():
        components.html(html.read_text(encoding="utf-8"), height=700, scrolling=False)
    st.caption("Basemaps are for display only and are not analysis inputs. " + " ".join(config.attribution(int(S["event_utc"][:4]))[:3]))
with tab_cut:
    df = pd.DataFrame(S["settlements"])
    if len(df):
        order = {"cut_off": 0, "longer_route": 1, "connected": 2, "not_assessable": 3, "no_road_data": 4}
        df["_o"] = df["status"].map(order)
        df = df.sort_values(["_o", "n_buildings"], ascending=[True, False]).drop(columns="_o")
        show = df[["name", "status", "n_buildings", "n_buildings_affected", "dist_before_km", "dist_after_km", "dest_before", "reason"]]
        st.dataframe(show, use_container_width=True, hide_index=True)
        st.download_button("Download CSV", show.to_csv(index=False), f"{S['name']}_settlements.csv")
    else:
        st.write("No settlements found in the mapped area.")
    if S.get("flowpath"):
        st.subheader("Flood path (bonus)")
        st.write(f"Traced **{S['flowpath']['length_km']} km** downstream; buildings in the susceptible corridor: {S['flowpath'].get('buildings_in_corridor')}")
        st.dataframe(pd.DataFrame(S["flowpath"]["settlements"]), use_container_width=True, hide_index=True)
with tab_rep:
    rep = rd / "sitrep.html"
    if rep.exists():
        components.html(rep.read_text(encoding="utf-8"), height=1100, scrolling=True)
        cols = st.columns(3)
        cols[0].download_button("Download HTML", rep.read_bytes(), "sitrep.html")
        if (rd / "sitrep.pdf").exists():
            cols[1].download_button("Download PDF (EN + नेपाली)", (rd / "sitrep.pdf").read_bytes(), "sitrep.pdf")
with tab_data:
    st.write("**Radar pairs used** (same relative orbit; different tracks are never compared pixel by pixel):")
    st.dataframe(pd.DataFrame(S["s1_pairs"]), use_container_width=True, hide_index=True)
    st.write("**Optical (Sentinel-2):**", S["s2"] or "no usable cloud-free overlap – radar only")
    st.write("**AI model:**", S["model"] or "not loaded – physics-based change detector used")
    st.write("**OpenStreetMap snapshot (pre-event):**", S["osm"])
    st.write("**Noise floor of stable terrain (dB):**", S["noise"])
    if (rd / "provenance.json").exists():
        with st.expander("Full provenance (parameters, forbidden inputs used = none)"):
            st.json(json.loads((rd / "provenance.json").read_text(encoding="utf-8")))
with tab_eval:
    ev = rd / "evaluation_emsr927.json"
    if ev.exists():
        st.json(json.loads(ev.read_text(encoding="utf-8")))
        for f in sorted(rd.glob("evaluation_*.png")):
            st.image(str(f))
    else:
        st.info("Run `python scripts/evaluate_emsr927.py` after placing the EMSR927 reference files in data/reference/emsr927/ "
                "(reference maps are used for checking only, never as input).")
