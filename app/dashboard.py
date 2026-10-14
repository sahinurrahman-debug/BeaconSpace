"""BeaconSpace dashboard:  streamlit run app/dashboard.py

Pick an area + flood date -> Sentinel-1/2 + Copernicus DEM + pre-event OpenStreetMap -> flood/debris map, damage, cut-off
settlements, flow path and a bilingual situation report.

Design system (see .streamlit/config.toml): one accent ("beacon amber") on neutral surfaces, Inter + Space Grotesk only,
16 px base text, 8 px spacing grid, transform/opacity-only animation (disabled for prefers-reduced-motion), designed empty and
loading states, light + dark themes that follow the system setting.
"""
import datetime as dt
import html
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
from floodsys.report.mapplot import STATUS_LABEL  # noqa: E402
from floodsys.report.sitrep import _title, facts  # noqa: E402

UTC = dt.timezone.utc
OUT = config.OUTPUT_DIR
esc = html.escape

try:
    from PIL import Image
    _icon = Image.open(ROOT / "app" / "assets" / "favicon.png")
except Exception:
    _icon = "🛰️"
st.set_page_config(page_title="BeaconSpace", page_icon=_icon, layout="wide", initial_sidebar_state="expanded")

# ------------------------------------------------------------------------------------------------ design tokens
LIGHT = dict(bg="#F5F6FA", surface="#FFFFFF", surface2="#EEF1F7", border="#D9DEE8", text="#0F172A", muted="#566178",
             accent="#B45309", accent_soft="#FDF0DD", on_accent="#FFFFFF", cut_off="#B01316", longer_route="#8F5300",
             connected="#157A36", neutral="#566178", shadow="0 1px 2px rgba(15,23,42,.06), 0 6px 20px rgba(15,23,42,.06)")
DARK = dict(bg="#0B1220", surface="#131C2E", surface2="#1A2540", border="#26324A", text="#E8ECF4", muted="#9AA7BE",
            accent="#F5A524", accent_soft="#2B2210", on_accent="#0B1220", cut_off="#FF7A7D", longer_route="#FFB454",
            connected="#5FD38A", neutral="#9AA7BE", shadow="0 1px 2px rgba(0,0,0,.45), 0 10px 28px rgba(0,0,0,.35)")


def theme_type() -> str:
    try:
        t = st.context.theme.type
    except Exception:
        t = None
    return t if t in ("light", "dark") else "light"


THEME = theme_type()
P = DARK if THEME == "dark" else LIGHT

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Space+Grotesk:wght@500;600;700&display=swap');
:root{--bs-bg:%(bg)s;--bs-surface:%(surface)s;--bs-surface2:%(surface2)s;--bs-border:%(border)s;--bs-text:%(text)s;--bs-muted:%(muted)s;
--bs-accent:%(accent)s;--bs-accent-soft:%(accent_soft)s;--bs-on-accent:%(on_accent)s;--bs-shadow:%(shadow)s;
--bs-font:'Inter',system-ui,-apple-system,'Segoe UI',sans-serif;--bs-head:'Space Grotesk','Inter',system-ui,sans-serif}
html,body,.stApp,.stApp button,.stApp input,.stApp textarea,.stApp [data-baseweb],.stMarkdown,.stApp p,.stApp label{font-family:var(--bs-font)!important}
.stApp,.stApp p,.stApp li,.stApp label,.stApp [data-testid="stWidgetLabel"] p{font-size:16px}
h1,h2,h3,.bs-head{font-family:var(--bs-head)!important;letter-spacing:-.01em}
.block-container{padding:32px 40px 72px;max-width:1320px}
[data-testid="stHeader"]{background:transparent}
.stAppDeployButton,[data-testid="stToolbar"] .stAppDeployButton{display:none}
[data-testid="stSidebar"]{border-right:1px solid var(--bs-border)}
[data-testid="stSidebar"] .block-container,[data-testid="stSidebarContent"]{padding-top:16px}
:focus-visible{outline:2px solid var(--bs-accent);outline-offset:2px;border-radius:6px}

.bs-brand{display:flex;align-items:center;gap:16px;margin-bottom:8px}
.bs-brand h1{margin:0;padding:0;font-size:40px;line-height:1.1;font-weight:700;color:var(--bs-text)}
.bs-tag{color:var(--bs-muted);font-size:18px;line-height:1.5;max-width:760px;margin:0 0 24px}
.bs-mini{display:flex;align-items:center;gap:12px;margin:0 0 24px}
.bs-mini b{font-family:var(--bs-head);font-size:22px}

.bs-card{background:var(--bs-surface);border:1px solid var(--bs-border);border-radius:16px;padding:24px;box-shadow:var(--bs-shadow);
transition:transform .18s ease,box-shadow .18s ease;height:100%%;box-sizing:border-box}
.bs-card:hover{transform:translateY(-2px)}
.bs-label{font-size:14px;letter-spacing:.06em;text-transform:uppercase;color:var(--bs-muted);font-weight:600}
.bs-value{font-family:var(--bs-head);font-size:40px;line-height:1.1;font-weight:700;color:var(--bs-text);margin:8px 0}
.bs-sub{font-size:16px;line-height:1.5;color:var(--bs-muted)}
.bs-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin:0 0 24px}
.bs-grid3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin:0 0 24px}
.bs-grid2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin:0 0 24px}
@media (max-width:1100px){.bs-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.bs-grid3{grid-template-columns:1fr}}
@media (max-width:640px){.bs-grid,.bs-grid2{grid-template-columns:1fr}.block-container{padding:24px 16px 56px}}
.bs-dot{display:inline-block;width:10px;height:10px;border-radius:50%%;margin-right:8px;vertical-align:baseline}

.bs-chips{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 24px}
.bs-chip{display:inline-flex;align-items:center;gap:8px;padding:4px 12px;border-radius:999px;border:1px solid var(--bs-border);
background:var(--bs-surface);font-size:14px;font-weight:500;color:var(--bs-text);line-height:1.6}
.bs-chip.s{border-color:transparent;font-weight:600}
.bs-legend{display:flex;flex-wrap:wrap;gap:16px;margin:16px 0 0;font-size:14px;color:var(--bs-muted)}

.bs-empty{display:flex;flex-direction:column;align-items:center;text-align:center;gap:16px;padding:56px 24px;border:1px dashed var(--bs-border);
border-radius:16px;background:var(--bs-surface);color:var(--bs-text)}
.bs-empty h3{margin:0;font-size:24px}.bs-empty p{margin:0;max-width:560px;color:var(--bs-muted);font-size:16px;line-height:1.6}
.bs-steps{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;width:100%%;max-width:860px;margin-top:8px;text-align:left}
.bs-steps div{background:var(--bs-surface2);border-radius:12px;padding:16px;font-size:16px;line-height:1.5}
.bs-steps b{display:block;font-family:var(--bs-head);color:var(--bs-accent);margin-bottom:4px}
@media (max-width:760px){.bs-steps{grid-template-columns:1fr}}

.bs-table-wrap{max-height:560px;overflow:auto;border:1px solid var(--bs-border);border-radius:16px;background:var(--bs-surface)}
table.bs-table{width:100%%;border-collapse:separate;border-spacing:0;font-size:16px}
.bs-table th{position:sticky;top:0;background:var(--bs-surface);z-index:1;text-align:left;font-size:14px;letter-spacing:.05em;text-transform:uppercase;
color:var(--bs-muted);padding:16px;border-bottom:1px solid var(--bs-border);font-weight:600}
.bs-table td{padding:16px;border-bottom:1px solid var(--bs-border);vertical-align:top;line-height:1.5}
.bs-table tr:last-child td{border-bottom:0}.bs-table tr:hover td{background:var(--bs-surface2)}
.bs-table .m{color:var(--bs-muted);font-size:14px}.bs-table .n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}

.stTabs [data-baseweb="tab-list"]{gap:8px;border-bottom:1px solid var(--bs-border)}
.stTabs [data-baseweb="tab"]{height:auto;padding:16px;font-size:16px;font-weight:600}
.stTabs [data-baseweb="tab-highlight"]{background:var(--bs-accent);height:3px;border-radius:3px}
.stTabs [data-baseweb="tab-panel"]{padding-top:24px}
.stButton button,.stDownloadButton button{min-height:48px;font-weight:600;font-size:16px;transition:transform .15s ease,box-shadow .15s ease}
.stButton button:hover,.stDownloadButton button:hover{transform:translateY(-1px)}
.stButton button[kind="primary"]{color:var(--bs-on-accent)}

.bs-enter{animation:bs-up .36s cubic-bezier(.2,.7,.2,1) both}
.bs-d1{animation-delay:.04s}.bs-d2{animation-delay:.08s}.bs-d3{animation-delay:.12s}.bs-d4{animation-delay:.16s}
@keyframes bs-up{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
.bs-skel{position:relative;overflow:hidden;background:var(--bs-surface2);border-radius:12px}
.bs-skel::after{content:"";position:absolute;inset:0;transform:translateX(-100%%);background:linear-gradient(90deg,transparent,rgba(128,128,128,.22),transparent);animation:bs-shimmer 1.3s infinite}
@keyframes bs-shimmer{to{transform:translateX(100%%)}}
.bs-spin{width:20px;height:20px;border-radius:50%%;border:3px solid var(--bs-border);border-top-color:var(--bs-accent);animation:bs-rot .8s linear infinite;flex:none}
@keyframes bs-rot{to{transform:rotate(360deg)}}
.bs-stepper{display:grid;grid-template-columns:repeat(9,minmax(0,1fr));gap:8px;margin:16px 0}
.bs-step{font-size:14px;color:var(--bs-muted);padding:8px 0;border-top:3px solid var(--bs-border);font-weight:500}
.bs-step.done{border-top-color:var(--bs-accent);color:var(--bs-text)}
.bs-step.now{border-top-color:var(--bs-accent);color:var(--bs-accent);font-weight:600}
@media (max-width:900px){.bs-stepper{grid-template-columns:repeat(3,minmax(0,1fr))}}
.bs-log{font:14px/1.6 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;color:var(--bs-muted);background:var(--bs-surface2);border-radius:12px;padding:16px;
white-space:pre-wrap;word-break:break-word}
.bs-note{border-left:4px solid var(--bs-accent);background:var(--bs-accent-soft);padding:16px;border-radius:0 12px 12px 0;line-height:1.6}
@media (prefers-reduced-motion:reduce){*,*::before,*::after{animation-duration:.001ms!important;animation-iteration-count:1!important;transition:none!important}}
</style>
"""
st.markdown(CSS % P, unsafe_allow_html=True)

LOGO = ("<svg width='46' height='46' viewBox='0 0 48 48' role='img' aria-label='BeaconSpace logo'>"
        "<path d='M13.0 24.0A11.0 11.0 0 0 1 24.0 35.0' fill='none' stroke='var(--bs-accent)' stroke-width='3.2' stroke-linecap='round' opacity='1.0'/><path d='M13.0 16.0A19.0 19.0 0 0 1 32.0 35.0' fill='none' stroke='var(--bs-accent)' stroke-width='3.2' stroke-linecap='round' opacity='0.62'/><path d='M13.0 8.0A27.0 27.0 0 0 1 40.0 35.0' fill='none' stroke='var(--bs-accent)' stroke-width='3.2' stroke-linecap='round' opacity='0.34'/><circle cx='13.0' cy='35.0' r='5.6' fill='var(--bs-accent)'/><circle cx='32.1' cy='15.9' r='3.3' fill='var(--bs-text)'/></svg>")
HERO = ("<svg viewBox='0 0 220 120' width='220' height='120' role='img' aria-label='Satellite scanning a mountain valley'>"
        "<path d='M0 100 L50 60 L80 82 L120 40 L170 84 L220 58 L220 120 L0 120Z' fill='var(--bs-surface2)'/>"
        "<path d='M96 120 C104 96 112 88 110 70 C108 56 116 50 120 40' stroke='var(--bs-accent)' stroke-width='3' fill='none' stroke-linecap='round'/>"
        "<g transform='translate(150 16)'><rect x='-10' y='-5' width='20' height='10' rx='2' fill='var(--bs-text)' opacity='.85'/>"
        "<rect x='-27' y='-3' width='13' height='6' fill='var(--bs-muted)'/><rect x='14' y='-3' width='13' height='6' fill='var(--bs-muted)'/></g>"
        "<path d='M150 24 L112 62 M150 24 L130 62' stroke='var(--bs-accent)' stroke-width='1.6' stroke-dasharray='4 4' opacity='.85'/></svg>")


# ------------------------------------------------------------------------------------------------ small components
def card(label, value, sub, delay=1, dot=None):
    d = f"<span class='bs-dot' style='background:{dot}'></span>" if dot else ""
    return (f"<div class='bs-card bs-enter bs-d{delay}'><div class='bs-label'>{d}{esc(label)}</div>"
            f"<div class='bs-value'>{value}</div><div class='bs-sub'>{sub}</div></div>")


def chip(text, status=None):
    if status:
        col = P.get(status, P["neutral"])
        return (f"<span class='bs-chip s' style='color:{col};background:color-mix(in srgb,{col} 14%,transparent)'>"
                f"<span class='bs-dot' style='background:{col};margin:0'></span>{esc(text)}</span>")
    return f"<span class='bs-chip'>{esc(text)}</span>"


def empty_state(title, body, icon=HERO, extra=""):
    return f"<div class='bs-empty bs-enter'>{icon}<h3 class='bs-head'>{esc(title)}</h3><p>{body}</p>{extra}</div>"


STEPS = [("Terrain", ("[dem]", "[run] AOI")), ("Optical", ("[s2]",)), ("Radar", ("[s1]", "[run] pair", "[run] AI")),
         ("Detect", ("[run] areas",)), ("OpenStreetMap", ("[osm]",)), ("Damage", ("[run] damage",)),
         ("Cut-off", ("[access]", "[run] access")), ("Flow path", ("[flowpath]",)), ("Report", ("[sitrep]", "[run] done"))]


def progress_html(step_idx, lines, title="Analysing…"):
    items = "".join(f"<div class='bs-step {'done' if i < step_idx else 'now' if i == step_idx else ''}'>{esc(n)}</div>"
                    for i, (n, _) in enumerate(STEPS))
    skel = "".join("<div class='bs-skel' style='height:136px'></div>" for _ in range(4))
    log = esc("\n".join(lines[-6:]))
    return (f"<div class='bs-card bs-enter' role='status' aria-live='polite'><div style='display:flex;gap:16px;align-items:center'>"
            f"<div class='bs-spin'></div><div><div class='bs-head' style='font-size:22px;font-weight:600'>{esc(title)}</div>"
            f"<div class='bs-sub'>Streaming Sentinel data and building the road graph — first runs of a new area take a few minutes.</div></div></div>"
            f"<div class='bs-stepper'>{items}</div><div class='bs-grid' style='margin:0 0 16px'>{skel}</div>"
            f"<div class='bs-log'>{log}</div></div>")


def pretty_run(name):
    try:
        return _title(name)
    except Exception:
        return name.replace("_", " ")


# ------------------------------------------------------------------------------------------------ state + sidebar
runs = sorted(OUT.glob("*/summary.json"), key=lambda p: p.stat().st_mtime, reverse=True) if OUT.exists() else []
runs.sort(key=lambda p: p.parent.name != "trishuli")      # the case study first, then newest-first (sort is stable)
if "mode" not in st.session_state:
    st.session_state["mode"] = "Finished runs" if runs else "New analysis"
if "_goto" in st.session_state:
    st.session_state["mode"] = st.session_state.pop("_goto")
if "_goto_run" in st.session_state:
    st.session_state["sel_run"] = st.session_state.pop("_goto_run")

go = False
with st.sidebar:
    st.markdown(f"<div class='bs-mini'>{LOGO}<b>BeaconSpace</b></div>", unsafe_allow_html=True)
    st.radio("View", ["Finished runs", "New analysis"], key="mode", horizontal=True, label_visibility="collapsed")
    if st.session_state["mode"] == "New analysis":
        key = st.selectbox("Area", list(PRESETS) + ["custom"], format_func=lambda k: PRESETS[k]["label"] if k in PRESETS else "Custom area")
        base = PRESETS.get(key, PRESETS["trishuli"])
        with st.expander("Bounding box", expanded=(key == "custom")):
            c1, c2 = st.columns(2)
            w = c1.number_input("West", value=float(base["bbox"][0]), format="%.4f")
            e = c2.number_input("East", value=float(base["bbox"][2]), format="%.4f")
            s = c1.number_input("South", value=float(base["bbox"][1]), format="%.4f")
            n = c2.number_input("North", value=float(base["bbox"][3]), format="%.4f")
        d = st.date_input("Flood date (UTC)", value=base["event"].date())
        tm = st.time_input("Approximate time (UTC)", value=base["event"].time())
        res = st.select_slider("Resolution (m)", [10, 20, 40], value=20, help="10 m is sharpest and slowest; 40 m is a quick look.")
        pairs = st.slider("Radar tracks to combine", 1, 3, 2)
        use_s2 = st.checkbox("Use Sentinel-2 where the sky is clear", True)
        use_model = st.checkbox("Use the trained AI model if present", True)
        trace = st.checkbox("Trace the flood path from an upstream point", key == "trishuli")
        if trace:
            tl1, tl2 = st.columns(2)
            tlon = tl1.number_input("Upstream lon", value=float((base.get("trace_from") or (85.38, 28.2))[0]), format="%.4f")
            tlat = tl2.number_input("Upstream lat", value=float((base.get("trace_from") or (85.38, 28.2))[1]), format="%.4f")
        area_km2 = abs((e - w) * 111 * 0.88) * abs((n - s) * 111)
        st.caption(f"Area ≈ {area_km2:,.0f} km². Larger areas and first runs take longer; repeats are cached.")
        go = st.button("Run analysis", type="primary", width="stretch", icon=":material/play_arrow:")
    else:
        names = [p.parent.name for p in runs]
        if names:
            if st.session_state.get("sel_run") not in names:
                st.session_state["sel_run"] = names[0]
            st.selectbox("Run", names, key="sel_run", format_func=pretty_run)
    st.caption("Theme follows your system. Change it under ⋮ ▸ Settings.")

# ------------------------------------------------------------------------------------------------ header
st.markdown(f"<div class='bs-brand'>{LOGO}<h1>BeaconSpace</h1></div>"
            "<p class='bs-tag'>Satellite flood-damage mapping for rescue teams: where the flood hit, what was damaged, and who is cut off. "
            f"{esc(config.DISCLAIMER)}</p>", unsafe_allow_html=True)

# ------------------------------------------------------------------------------------------------ run a new analysis
if go:
    from floodsys.pipeline import RunConfig, run
    cfg = RunConfig(bbox=(w, s, e, n), event=dt.datetime.combine(d, tm).replace(tzinfo=UTC), res=float(res), n_pairs=pairs,
                    use_s2=use_s2, use_model=use_model, trace_from=(tlon, tlat) if trace else None,
                    name=f"{key}_{d:%Y%m%d}_{int(res)}m")
    ph = st.empty()
    state = {"step": 0, "lines": []}

    def log(msg):
        state["lines"].append(str(msg))
        for i, (_, prefixes) in enumerate(STEPS):
            if any(str(msg).startswith(p) for p in prefixes):
                state["step"] = max(state["step"], i)
        ph.markdown(progress_html(state["step"], state["lines"]), unsafe_allow_html=True)

    log("Starting…")
    try:
        r = run(cfg, log=log)
        ph.empty()
        st.session_state["_goto"] = "Finished runs"
        st.session_state["_goto_run"] = r["out"].name
        st.rerun()
    except Exception as exc:
        hint = ("Radar needs images <b>before and after</b> the date on the <b>same orbit track</b> — try a different date or a larger area."
                if "same-track" in str(exc) else "Try a smaller area, a coarser resolution (40 m), or run again — remote data servers are sometimes busy.")
        ph.markdown(empty_state("The analysis could not finish", f"<code>{esc(str(exc))[:300]}</code><br><br>{hint}"), unsafe_allow_html=True)
        st.stop()

# ------------------------------------------------------------------------------------------------ nothing to show yet
if st.session_state["mode"] == "Finished runs" and not runs:
    steps = ("<div class='bs-steps'><div><b>1 · Choose</b>An area and the flood date.</div>"
             "<div><b>2 · Analyse</b>Radar change detection, terrain and OpenStreetMap from before the event.</div>"
             "<div><b>3 · Act</b>Flood and debris map, damaged buildings, roads and bridges, and cut-off villages.</div></div>")
    st.markdown(empty_state("No analysis yet", "Run the Trishuli case study (26 August 2026) or choose your own area and date. "
                            "Everything is computed from free Sentinel, elevation and OpenStreetMap data.", extra=steps), unsafe_allow_html=True)
    st.button("Open the analysis form", type="primary", icon=":material/arrow_forward:",
              on_click=lambda: st.session_state.update(_goto="New analysis"))
    st.stop()
if st.session_state["mode"] == "New analysis":
    st.markdown(empty_state("Ready when you are", "Pick an area and date in the sidebar, then press <b>Run analysis</b>. "
                            "You will see each step as it runs; results open here automatically."), unsafe_allow_html=True)
    st.stop()

# ------------------------------------------------------------------------------------------------ a finished run
rd = OUT / st.session_state.get("sel_run", runs[0].parent.name)
if not (rd / "summary.json").exists():
    rd = runs[0].parent
with st.spinner("Loading results…"):
    S = json.loads((rd / "summary.json").read_text(encoding="utf-8"))
    F = facts(S)

model_txt = S["model"]["file"] if S.get("model") else "physics-based detector"
s2_txt = f"optical {S['s2']['clear_fraction']:.0%} clear" if S.get("s2") else "radar only"
prov = ", ".join(sorted(set(S["osm"]["provider"].values())))
st.markdown(
    f"<h2 class='bs-head' style='margin:0 0 8px;font-size:28px'>{esc(pretty_run(S['name']))}</h2><div class='bs-chips'>"
    + chip(f"Flood {S['event_utc'][:10]}") + chip(f"{S['area_km2']:,.0f} km² · {S['resolution_m']:.0f} m") + chip(f"Detector: {model_txt}")
    + chip(s2_txt) + chip(f"OSM snapshot {S['osm']['snapshot']} ({prov})") + chip(f"{S['runtime_s']:.0f} s run") + "</div>", unsafe_allow_html=True)

st.markdown("<div class='bs-grid'>"
            + card("Flooded or debris-covered", f"{F['impact_ha']:,.0f} ha", f"{F['flood_ha']:,.0f} ha water · {F['debris_ha']:,.0f} ha debris", 1)
            + card("Buildings affected", f"{F['b_aff']:,}", f"of {F['b_total']:,} mapped · {F['b_severe']:,} likely destroyed", 2)
            + card("Road hit", f"{F['road_hit_km']:,.0f} km", f"{F['br_hit']} of {F['br_total']} bridges hit", 3)
            + card("Cut off", f"{F['n_cut']}", f"{F['n_long']} with a much longer route · {F['b_cut']:,} buildings", 4, dot=P["cut_off"])
            + "</div>", unsafe_allow_html=True)

tabs = st.tabs([":material/map: Map", ":material/alt_route: Who is cut off", ":material/description: Situation report",
                ":material/science: Data & method", ":material/fact_check: Check vs EMSR927"])


def themed_map(text: str) -> str:
    dark = THEME == "dark"
    bg, fg, br = (P["bg"], P["text"], P["border"])
    css = (f"<style>#bs-load{{position:fixed;inset:0;z-index:99999;display:flex;align-items:center;justify-content:center;flex-direction:column;"
           f"gap:16px;background:{bg};color:{fg};font:16px Inter,system-ui,sans-serif;transition:opacity .3s}}"
           f"#bs-load .sp{{width:32px;height:32px;border-radius:50%;border:3px solid {br};border-top-color:{P['accent']};animation:r .8s linear infinite}}"
           "@keyframes r{to{transform:rotate(360deg)}}@media (prefers-reduced-motion:reduce){#bs-load .sp{animation:none}}")
    if dark:
        css += (".leaflet-control-layers,.leaflet-popup-content-wrapper,.leaflet-popup-tip,.leaflet-bar a,.leaflet-control-attribution,"
                f".bs-title{{background:{P['surface']}!important;color:{P['text']}!important}}.leaflet-container a{{color:{P['accent']}}}")
    css += "</style><div id='bs-load' role='status'><div class='sp'></div><div>Loading map…</div></div>"
    js = ("<script>window.addEventListener('load',function(){setTimeout(function(){var l=document.getElementById('bs-load');"
          "if(l){l.style.opacity=0;setTimeout(function(){l.remove()},320)}"
          f"var want='{'dark' if dark else 'light'}';document.querySelectorAll('.leaflet-control-layers-base label').forEach(function(lb){{"
          "if(lb.textContent.toLowerCase().indexOf(want)>-1){var i=lb.querySelector('input');if(i&&!i.checked){i.click()}}})},400)})</script>")
    text = text.replace("<body>", "<body>" + css, 1) if "<body>" in text else css + text
    return text.replace("</body>", js + "</body>", 1)


with tabs[0]:
    mp = rd / "dashboard_map.html"
    if mp.exists():
        components.html(themed_map(mp.read_text(encoding="utf-8")), height=680, scrolling=False)
        st.markdown("<div class='bs-legend'>"
                    + "".join(f"<span><span class='bs-dot' style='background:{c}'></span>{t}</span>" for c, t in
                              (("#0047ff", "Flood water"), ("#ff8c00", "Debris / scour"), ("#ff2d55", "Road hit"), ("#ff00ff", "Building affected"),
                               (P["cut_off"], "Cut off"), (P["longer_route"], "Longer route"), (P["connected"], "Connected")))
                    + "</div>", unsafe_allow_html=True)
        st.caption("Basemaps are for display only and are not analysis inputs. "
                   + " ".join(config.attribution(int(S["event_utc"][:4]))[:3]))
    else:
        st.markdown(empty_state("The map file is missing", "This run has no <code>dashboard_map.html</code>. Re-run the analysis to regenerate it."),
                    unsafe_allow_html=True)

with tabs[1]:
    rows = S.get("settlements", [])
    if not rows:
        st.markdown(empty_state("No settlements found in this area", "OpenStreetMap had no named places or building clusters here before the "
                                "event, so there is nothing to assess for road access."), unsafe_allow_html=True)
    else:
        df = pd.DataFrame(rows)
        order = {"cut_off": 0, "longer_route": 1, "connected": 2, "not_assessable": 3, "no_road_data": 4}
        fc1, fc2 = st.columns([3, 2])
        pick = fc1.pills("Show", ["cut_off", "longer_route", "connected", "not_assessable", "no_road_data"], selection_mode="multi",
                         default=["cut_off", "longer_route"], format_func=lambda k: STATUS_LABEL.get(k, k), key="status_filter")
        q = fc2.text_input("Search a settlement", placeholder="e.g. Syapru", label_visibility="visible")
        df = df[df["status"].isin(pick or list(order))]
        if q:
            df = df[df["name"].astype(str).str.contains(q, case=False, na=False)]
        df = df.assign(_o=df["status"].map(order)).sort_values(["_o", "n_buildings"], ascending=[True, False]).drop(columns="_o")
        if df.empty:
            st.markdown(empty_state("Nothing matches these filters", "Try selecting more statuses or clearing the search box."), unsafe_allow_html=True)
        else:
            body = ""
            for r in df.head(200).itertuples():
                before = f"{r.dist_before_km} km" if pd.notna(r.dist_before_km) else "–"
                after = f"{r.dist_after_km} km" if pd.notna(r.dist_after_km) else "no route"
                body += (f"<tr><td><b>{esc(str(r.name))}</b><div class='m'>{esc(str(r.reason))}</div></td><td>{chip(STATUS_LABEL.get(r.status, r.status), r.status if r.status in P else None)}</td>"
                         f"<td class='n'>{r.n_buildings:,}<div class='m'>{r.n_buildings_affected:,} affected</div></td>"
                         f"<td class='n'>{before} → {after}</td><td>{esc(str(r.dest_before)) if pd.notna(r.dest_before) else '–'}</td></tr>")
            st.markdown("<div class='bs-table-wrap bs-enter'><table class='bs-table'><thead><tr><th>Settlement</th><th>Status</th><th class='n'>Buildings</th>"
                        f"<th class='n'>Route before → after</th><th>Was served by</th></tr></thead><tbody>{body}</tbody></table></div>", unsafe_allow_html=True)
            st.caption(f"{len(df):,} settlements match" + (" (first 200 shown)" if len(df) > 200 else ""))
            st.download_button("Download as CSV", df.to_csv(index=False), f"{S['name']}_settlements.csv", icon=":material/download:")
    fp = S.get("flowpath")
    st.markdown("<h3 class='bs-head' style='margin:32px 0 16px'>Flood path downstream (bonus)</h3>", unsafe_allow_html=True)
    if fp and fp.get("settlements"):
        st.markdown(f"<p>Traced <b>{fp['length_km']} km</b> down the valley from the chosen upstream point; "
                    f"<b>{fp.get('buildings_in_corridor') or 0:,}</b> buildings lie in the susceptible corridor.</p>", unsafe_allow_html=True)
        fdf = pd.DataFrame(fp["settlements"])[["name", "km_along_path", "n_buildings"]].head(60)
        body = "".join(f"<tr><td>{esc(str(r.name))}</td><td class='n'>{r.km_along_path} km</td><td class='n'>{r.n_buildings:,}</td></tr>" for r in fdf.itertuples())
        st.markdown("<div class='bs-table-wrap'><table class='bs-table'><thead><tr><th>Settlement (downstream order)</th><th class='n'>Distance along path</th>"
                    f"<th class='n'>Buildings</th></tr></thead><tbody>{body}</tbody></table></div>", unsafe_allow_html=True)
    else:
        st.markdown(empty_state("No flood path traced", "Tick <b>Trace the flood path from an upstream point</b> in the sidebar when running an analysis "
                                "to list the settlements along the valley in downstream order."), unsafe_allow_html=True)

with tabs[2]:
    rep = rd / "sitrep.html"
    if rep.exists():
        c1, c2, _ = st.columns([1, 1, 2])
        c1.download_button("HTML", rep.read_bytes(), "sitrep.html", icon=":material/download:", help="Download the report as HTML", width="stretch")
        if (rd / "sitrep.pdf").exists():
            c2.download_button("PDF", (rd / "sitrep.pdf").read_bytes(), "sitrep.pdf", icon=":material/download:", help="Download the report as PDF (English and Nepali)", width="stretch")
        st.caption("One page in English, one in Nepali. Every number comes from the maps; no value is generated by a language model.")
        components.html(rep.read_text(encoding="utf-8"), height=1180, scrolling=True)
    else:
        st.markdown(empty_state("No situation report yet", "This run has no <code>sitrep.html</code>. Re-run the analysis to generate it."), unsafe_allow_html=True)

with tabs[3]:
    pr = S["s1_pairs"]
    ptxt = "".join(f"<tr><td>RO {p['rel_orbit']} · {esc(p['orbit_state'])}</td><td>{esc(p['post'][:10])}</td><td>{len(p['pre'])} images, latest {esc(p['pre'][0][:10])}</td>"
                   f"<td class='n'>{p['baseline_days']} d</td><td class='n'>{p['post_coverage']:.0%}</td></tr>" for p in pr)
    st.markdown("<div class='bs-grid2'>"
                + card("Radar (Sentinel-1)", f"{len(pr)} track{'s' if len(pr) != 1 else ''}", "Same-orbit pre/post pairs only — different tracks are never compared pixel by pixel.", 1)
                + card("Optical (Sentinel-2)", f"{S['s2']['clear_fraction']:.0%} clear" if S.get("s2") else "radar only",
                       "Cloud-masked; adds flood-water evidence only where the sky is clear." if S.get("s2") else "No usable cloud-free overlap.", 2)
                + card("Detector", "AI + physics" if S.get("model") else "Physics", f"{esc(model_txt)}; terrain and river-proximity gates always apply.", 3)
                + card("OpenStreetMap", f"{S['osm']['snapshot']}", f"Pre-event snapshot via {esc(prov)}. No post-event edits are used.", 4)
                + "</div>", unsafe_allow_html=True)
    st.markdown("<div class='bs-table-wrap'><table class='bs-table'><thead><tr><th>Track</th><th>Post-event pass</th><th>Pre-event series</th>"
                f"<th class='n'>Baseline</th><th class='n'>Coverage</th></tr></thead><tbody>{ptxt}</tbody></table></div>", unsafe_allow_html=True)
    nz = S.get("noise", {})
    if nz:
        st.caption(f"Noise floor of stable terrain: VV σ {nz['vv_sigma_db']:.2f} dB · VH σ {nz['vh_sigma_db']:.2f} dB.")
    if (rd / "provenance.json").exists():
        with st.expander("Full provenance (parameters, inputs, forbidden inputs used: none)"):
            st.json(json.loads((rd / "provenance.json").read_text(encoding="utf-8")))

with tabs[4]:
    ev = rd / "evaluation_emsr927.json"
    if ev.exists():
        E = json.loads(ev.read_text(encoding="utf-8"))
        x = E["extent"]
        if isinstance(x, dict):
            b, rd_ = E.get("buildings", {}), E.get("roads", {})
            st.markdown("<div class='bs-grid'>"
                        + card("Overlap with EMS event area", f"{x['IoU']:.2f}", "intersection over union", 1)
                        + card("Precision · recall", f"{x['precision']:.2f} · {x['recall']:.2f}", f"{E['extent_with_30m_tolerance']['precision']:.2f} · {E['extent_with_30m_tolerance']['recall']:.2f} with 30 m tolerance", 2)
                        + card("EMS buildings found", f"{b.get('recall', 0):.0%}", f"{b.get('reference_found_by_us(within 20 m)', 0):,} of {b.get('reference_affected', 0):,}", 3)
                        + card("EMS road length covered", f"{rd_.get('recall', 0):.0%}", f"our precision {rd_.get('precision', 0):.0%} (OSM maps more tracks than EMS assessed)", 4)
                        + "</div>", unsafe_allow_html=True)
        for f in sorted(rd.glob("evaluation_*.png")):
            st.image(str(f), width="stretch")
        st.markdown("<div class='bs-note'>Copernicus EMS maps are used for <b>checking only</b>, never as an input. "
                    f"{esc(config.EMS_CREDIT)}.</div>", unsafe_allow_html=True)
    else:
        st.markdown(empty_state("No reference comparison for this run", "Download the EMSR927 vector products from the Copernicus EMS site into "
                                "<code>data/reference/emsr927/</code>, then run <code>python scripts/evaluate_emsr927.py --run outputs/&lt;run&gt;</code>. "
                                "They are used to check results only — never as input."), unsafe_allow_html=True)
