"""BeaconSpace dashboard ("mission control"):  streamlit run app/dashboard.py

Top navigation bar -> one page per panel: Overview · Settlements · Situation report · Method & data · EMS check · New analysis.

Pick an area + flood date -> Sentinel-1/2 + Copernicus DEM + pre-event OpenStreetMap -> flood/debris map, damage, cut-off
settlements, flow path, water-rise preview and a bilingual situation report.

Design system (see .streamlit/config.toml): obsidian-plum dark-first base with a faint cosmic glow, frosted-glass modules, ONE UI accent
(nebula rose; one token block below) and a traffic-light status scale (CRITICAL crimson / WATCH amber / NORMAL green), Inter + JetBrains Mono
only, 16 px base text, 8 px grid, symmetric layout (equal card rows, full-width viewport, equal twin panels), fast transform/opacity-only
animation (off for prefers-reduced-motion), designed empty and loading states. Light and dark themes follow the system setting.
Only real data is shown: no rainfall, gauge or drone feeds exist in this system, so none are simulated.
"""
import datetime as dt
import html
import json
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from floodsys import config  # noqa: E402
from floodsys.presets import PRESETS  # noqa: E402
from floodsys.report.sitrep import _title, facts  # noqa: E402

UTC = dt.timezone.utc
OUT = config.OUTPUT_DIR
esc = html.escape

try:
    from PIL import Image
    _icon = Image.open(ROOT / "app" / "assets" / "favicon.png")
except Exception:
    _icon = "🛰️"
st.set_page_config(page_title="BeaconSpace", page_icon=_icon, layout="wide", initial_sidebar_state="collapsed")

# ------------------------------------------------------------------------------------------------ design tokens (change the accent here)
DARK = dict(bg="#120B14", surface="rgba(30,20,35,.72)", surface_solid="#1E1423", surface2="#2A1B31", border="rgba(255,255,255,.09)",
            text="#F6E9F2", muted="#B79AAF", accent="#F472B6", accent_soft="rgba(244,114,182,.14)", on_accent="#2A0716",
            cut_off="#FF4040", longer_route="#FBBF24", connected="#34D399", neutral="#B79AAF", blue="#3B82F6",
            glow="radial-gradient(1100px 560px at 85% -8%, rgba(244,114,182,.12), transparent 60%),"
                 "radial-gradient(900px 520px at -8% 12%, rgba(99,102,241,.08), transparent 58%)",
            shadow="0 8px 28px rgba(0,0,0,.42)")
LIGHT = dict(bg="#FAF4F8", surface="rgba(255,255,255,.86)", surface_solid="#FFFFFF", surface2="#F6E9F1", border="rgba(70,20,50,.13)",
             text="#2A1423", muted="#6B4F62", accent="#BE185D", accent_soft="rgba(190,24,93,.09)", on_accent="#FFFFFF",
             cut_off="#D31F1F", longer_route="#A16207", connected="#15803D", neutral="#6B4F62", blue="#1D4ED8",
             glow="radial-gradient(1100px 560px at 85% -8%, rgba(190,24,93,.06), transparent 60%)",
             shadow="0 6px 22px rgba(70,20,50,.09)")


def theme_type() -> str:
    try:
        t = st.context.theme.type
    except Exception:
        t = None
    return t if t in ("light", "dark") else "dark"


THEME = theme_type()
P = LIGHT if THEME == "light" else DARK

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');
:root{--bs-bg:%(bg)s;--bs-surface:%(surface)s;--bs-solid:%(surface_solid)s;--bs-surface2:%(surface2)s;--bs-border:%(border)s;--bs-text:%(text)s;
--bs-muted:%(muted)s;--bs-accent:%(accent)s;--bs-accent-soft:%(accent_soft)s;--bs-on-accent:%(on_accent)s;--bs-shadow:%(shadow)s;
--bs-crit:%(cut_off)s;--bs-watch:%(longer_route)s;--bs-ok:%(connected)s;--bs-blue:%(blue)s;
--bs-font:'Inter',system-ui,-apple-system,'Segoe UI',sans-serif;--bs-mono:'JetBrains Mono',ui-monospace,SFMono-Regular,Consolas,monospace}
html,body,.stApp,.stApp button,.stApp input,.stApp textarea,.stApp [data-baseweb],.stMarkdown,.stApp p,.stApp label,.stApp a{font-family:var(--bs-font)!important}
.stApp{background:%(glow)s,var(--bs-bg)!important}
.stApp,.stApp p,.stApp li,.stApp label,.stApp [data-testid="stWidgetLabel"] p{font-size:16px}
h1,h2,h3,.bs-head{font-family:var(--bs-font)!important;letter-spacing:-.015em;font-weight:700}
.bs-mono{font-family:var(--bs-mono)!important}
.block-container{padding:96px 32px 72px;max-width:1600px;margin:0 auto}
[data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"],[data-testid="stExpandSidebarButton"]{display:none!important}
.stAppDeployButton,[data-testid="stToolbar"] .stAppDeployButton{display:none}
:focus-visible{outline:2px solid var(--bs-accent);outline-offset:2px;border-radius:6px}

/* ---- navbar (Streamlit top navigation) ---- */
header[data-testid="stHeader"]{background:%(surface)s!important;backdrop-filter:blur(16px) saturate(1.2);-webkit-backdrop-filter:blur(16px) saturate(1.2);
border-bottom:1px solid var(--bs-border);height:64px}
header[data-testid="stHeader"] nav,header[data-testid="stHeader"] [data-testid="stTopNavLinkContainer"]{gap:4px;justify-content:center}
header[data-testid="stHeader"] a,header[data-testid="stHeader"] button{font-size:16px!important;font-weight:600!important;border-radius:10px!important;
padding:8px 14px!important;color:var(--bs-muted)!important;transition:background .12s ease,color .12s ease}
header[data-testid="stHeader"] a:hover{background:var(--bs-accent-soft)!important;color:var(--bs-text)!important}
header[data-testid="stHeader"] a[aria-current="page"],header[data-testid="stHeader"] a[data-active="true"]{background:var(--bs-accent-soft)!important;color:var(--bs-accent)!important;
box-shadow:inset 0 -2px 0 var(--bs-accent)}

/* ---- symmetric page header ---- */
.bs-hero{display:flex;flex-direction:column;align-items:center;text-align:center;gap:8px;margin:0 0 24px;width:100%%}
.bs-brand{display:flex;align-items:center;justify-content:center;gap:16px;width:100%%}
.bs-brand h1{margin:0;padding:0;font-size:36px;line-height:1.1;color:var(--bs-text)}
.bs-tag{color:var(--bs-muted);font-size:16px;line-height:1.55;max-width:760px;margin:0}
.bs-page{text-align:center;margin:8px 0 24px}.bs-page h2{margin:0 0 4px;font-size:26px}.bs-page p{margin:0;color:var(--bs-muted)}

.bs-card{background:var(--bs-surface);border:1px solid var(--bs-border);border-radius:16px;padding:20px;box-shadow:var(--bs-shadow);
backdrop-filter:blur(14px) saturate(1.2);-webkit-backdrop-filter:blur(14px) saturate(1.2);transition:transform .15s ease,border-color .15s ease;box-sizing:border-box;height:100%%}
.bs-card:hover{transform:translateY(-1px);border-color:var(--bs-accent)}
.bs-label{font:600 12px/1.3 var(--bs-mono);letter-spacing:.12em;text-transform:uppercase;color:var(--bs-muted)}
.bs-value{font:600 34px/1.1 var(--bs-mono);color:var(--bs-text);margin:8px 0 4px}
.bs-value small{font-size:16px;color:var(--bs-muted);font-weight:500;margin-left:4px}
.bs-sub{font-size:14px;line-height:1.45;color:var(--bs-muted)}
.bs-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin:0 0 24px}
.bs-grid2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin:0 0 24px}
.bs-twin{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin:24px 0 0}
@media (max-width:1100px){.bs-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:760px){.bs-grid,.bs-grid2,.bs-twin{grid-template-columns:1fr}.block-container{padding:96px 12px 56px}}
.bs-dot{display:inline-block;width:10px;height:10px;border-radius:50%%;margin-right:8px;vertical-align:baseline}

.bs-strip{display:flex;flex-wrap:wrap;justify-content:center;gap:8px;margin:0 0 24px;font:500 13px/1.4 var(--bs-mono)}
.bs-strip span{background:var(--bs-surface);border:1px solid var(--bs-border);border-radius:10px;padding:6px 12px;color:var(--bs-text);backdrop-filter:blur(10px)}
.bs-strip i{font-style:normal;color:var(--bs-muted);margin-right:8px;letter-spacing:.08em}

.bs-badge{display:inline-flex;align-items:center;gap:6px;padding:2px 10px;border-radius:999px;font:600 12px/1.6 var(--bs-mono);letter-spacing:.08em;
border:1px solid color-mix(in srgb,currentColor 45%%,transparent);background:color-mix(in srgb,currentColor 12%%,transparent);white-space:nowrap}
.bs-badge.crit{color:var(--bs-crit)}.bs-badge.watch{color:var(--bs-watch)}.bs-badge.ok{color:var(--bs-ok)}.bs-badge.na{color:var(--bs-muted)}
.bs-badge.proto{color:var(--bs-accent)}
.bs-row{display:flex;gap:12px;align-items:flex-start;padding:12px 0;border-top:1px solid var(--bs-border)}
.bs-row:first-of-type{border-top:0}.bs-row .nm{font-size:16px;line-height:1.35;font-weight:500;word-break:break-word}
.bs-row .tm{font:400 13px/1.5 var(--bs-mono);color:var(--bs-muted)}.bs-row .bd{flex:none;padding-top:2px;min-width:92px}
.bs-list{min-height:430px}

.bs-empty{display:flex;flex-direction:column;align-items:center;text-align:center;gap:16px;padding:56px 24px;border:1px dashed var(--bs-border);
border-radius:16px;background:var(--bs-surface);color:var(--bs-text);backdrop-filter:blur(12px)}
.bs-empty h3{margin:0;font-size:24px}.bs-empty p{margin:0;max-width:560px;color:var(--bs-muted);font-size:16px;line-height:1.6}
.bs-steps{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;width:100%%;max-width:860px;margin-top:8px;text-align:left}
.bs-steps div{background:var(--bs-surface2);border-radius:12px;padding:16px;font-size:16px;line-height:1.5}
.bs-steps b{display:block;font:600 13px var(--bs-mono);letter-spacing:.1em;color:var(--bs-accent);margin-bottom:6px}
@media (max-width:760px){.bs-steps{grid-template-columns:1fr}}

.bs-table-wrap{max-height:560px;overflow:auto;border:1px solid var(--bs-border);border-radius:16px;background:var(--bs-surface);backdrop-filter:blur(12px)}
table.bs-table{width:100%%;border-collapse:separate;border-spacing:0;font-size:16px}
.bs-table th{position:sticky;top:0;background:var(--bs-solid);z-index:1;text-align:left;font:600 12px var(--bs-mono);letter-spacing:.1em;text-transform:uppercase;
color:var(--bs-muted);padding:14px 16px;border-bottom:1px solid var(--bs-border)}
.bs-table td{padding:14px 16px;border-bottom:1px solid var(--bs-border);vertical-align:top;line-height:1.5}
.bs-table tr:last-child td{border-bottom:0}.bs-table tr:hover td{background:var(--bs-surface2)}
.bs-table .m{color:var(--bs-muted);font-size:14px}.bs-table .n{text-align:right;font-family:var(--bs-mono);white-space:nowrap}

.stButton button,.stDownloadButton button{min-height:48px;font-weight:600;font-size:16px;transition:transform .12s ease}
.stButton button:hover,.stDownloadButton button:hover{transform:translateY(-1px)}
.stButton button[kind="primary"]{color:var(--bs-on-accent)}

.bs-enter{animation:bs-up .22s cubic-bezier(.2,.7,.2,1) both}
.bs-d1{animation-delay:.02s}.bs-d2{animation-delay:.05s}.bs-d3{animation-delay:.08s}.bs-d4{animation-delay:.11s}
@keyframes bs-up{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.bs-skel{position:relative;overflow:hidden;background:var(--bs-surface2);border-radius:12px}
.bs-skel::after{content:"";position:absolute;inset:0;transform:translateX(-100%%);background:linear-gradient(90deg,transparent,rgba(128,128,128,.22),transparent);animation:bs-shimmer 1.2s infinite}
@keyframes bs-shimmer{to{transform:translateX(100%%)}}
.bs-spin{width:20px;height:20px;border-radius:50%%;border:3px solid var(--bs-border);border-top-color:var(--bs-accent);animation:bs-rot .8s linear infinite;flex:none}
@keyframes bs-rot{to{transform:rotate(360deg)}}
.bs-stepper{display:grid;grid-template-columns:repeat(9,minmax(0,1fr));gap:8px;margin:16px 0}
.bs-step{font:500 13px var(--bs-mono);color:var(--bs-muted);padding:8px 0;border-top:3px solid var(--bs-border)}
.bs-step.done{border-top-color:var(--bs-accent);color:var(--bs-text)}
.bs-step.now{border-top-color:var(--bs-accent);color:var(--bs-accent);font-weight:600}
@media (max-width:900px){.bs-stepper{grid-template-columns:repeat(3,minmax(0,1fr))}}
.bs-log{font:13px/1.6 var(--bs-mono);color:var(--bs-muted);background:var(--bs-surface2);border-radius:12px;padding:16px;white-space:pre-wrap;word-break:break-word}
.bs-note{border-left:4px solid var(--bs-accent);background:var(--bs-accent-soft);padding:16px;border-radius:0 12px 12px 0;line-height:1.6}
.bs-foot{display:block;text-align:center!important;color:var(--bs-muted);font-size:13px;line-height:1.7;margin:32px auto 0!important;max-width:900px;width:100%%}
.bs-foot.cap{margin-top:12px!important}
@media (prefers-reduced-motion:reduce){*,*::before,*::after{animation-duration:.001ms!important;animation-iteration-count:1!important;transition:none!important}}
</style>
"""
st.markdown(CSS % P, unsafe_allow_html=True)

LOGO = ("<svg width='44' height='44' viewBox='0 0 48 48' role='img' aria-label='BeaconSpace logo'>"
        "<path d='M13.0 24.0A11.0 11.0 0 0 1 24.0 35.0' fill='none' stroke='var(--bs-accent)' stroke-width='3.2' stroke-linecap='round' opacity='1.0'/>"
        "<path d='M13.0 16.0A19.0 19.0 0 0 1 32.0 35.0' fill='none' stroke='var(--bs-accent)' stroke-width='3.2' stroke-linecap='round' opacity='0.62'/>"
        "<path d='M13.0 8.0A27.0 27.0 0 0 1 40.0 35.0' fill='none' stroke='var(--bs-accent)' stroke-width='3.2' stroke-linecap='round' opacity='0.34'/>"
        "<circle cx='13.0' cy='35.0' r='5.6' fill='var(--bs-accent)'/><circle cx='32.1' cy='15.9' r='3.3' fill='var(--bs-text)'/></svg>")
HERO = ("<svg viewBox='0 0 220 120' width='220' height='120' role='img' aria-label='Satellite scanning a mountain valley'>"
        "<path d='M0 100 L50 60 L80 82 L120 40 L170 84 L220 58 L220 120 L0 120Z' fill='var(--bs-surface2)'/>"
        "<path d='M96 120 C104 96 112 88 110 70 C108 56 116 50 120 40' stroke='var(--bs-accent)' stroke-width='3' fill='none' stroke-linecap='round'/>"
        "<g transform='translate(150 16)'><rect x='-10' y='-5' width='20' height='10' rx='2' fill='var(--bs-text)' opacity='.85'/>"
        "<rect x='-27' y='-3' width='13' height='6' fill='var(--bs-muted)'/><rect x='14' y='-3' width='13' height='6' fill='var(--bs-muted)'/></g>"
        "<path d='M150 24 L112 62 M150 24 L130 62' stroke='var(--bs-accent)' stroke-width='1.6' stroke-dasharray='4 4' opacity='.85'/></svg>")

LEVEL = {"cut_off": ("CRITICAL", "crit"), "longer_route": ("WATCH", "watch"), "connected": ("NORMAL", "ok"),
         "not_assessable": ("NO DATA", "na"), "no_road_data": ("NO DATA", "na")}
LABEL = {"cut_off": "Cut off", "longer_route": "Longer route", "connected": "Connected", "not_assessable": "Not assessable",
         "no_road_data": "No road data"}


# ------------------------------------------------------------------------------------------------ small components
def card(label, value, sub, delay=1, dot=None, unit=""):
    d = f"<span class='bs-dot' style='background:{dot}'></span>" if dot else ""
    u = f"<small>{esc(unit)}</small>" if unit else ""
    return (f"<div class='bs-card bs-enter bs-d{delay}'><div class='bs-label'>{d}{esc(label)}</div>"
            f"<div class='bs-value'>{value}{u}</div><div class='bs-sub'>{sub}</div></div>")


def badge(status):
    text, cls = LEVEL.get(status, ("NO DATA", "na"))
    return f"<span class='bs-badge {cls}'>{text}</span>"


def empty_state(title, body, icon=HERO, extra=""):
    return f"<div class='bs-empty bs-enter'>{icon}<h3 class='bs-head'>{esc(title)}</h3><p>{body}</p>{extra}</div>"


def page_title(title, sub):
    st.markdown(f"<div class='bs-page'><h2 class='bs-head'>{esc(title)}</h2><p>{sub}</p></div>", unsafe_allow_html=True)


STEPS = [("Terrain", ("[dem]", "[run] AOI")), ("Optical", ("[s2]",)), ("Radar", ("[s1]", "[run] pair", "[run] AI")),
         ("Detect", ("[run] areas",)), ("OSM", ("[osm]",)), ("Damage", ("[run] damage",)),
         ("Cut-off", ("[access]", "[run] access", "[waterrise]")), ("Flow path", ("[flowpath]",)), ("Report", ("[sitrep]", "[run] done"))]


def progress_html(step_idx, lines, title="Analysing…"):
    items = "".join(f"<div class='bs-step {'done' if i < step_idx else 'now' if i == step_idx else ''}'>{esc(n)}</div>"
                    for i, (n, _) in enumerate(STEPS))
    skel = "".join("<div class='bs-skel' style='height:120px'></div>" for _ in range(4))
    log = esc("\n".join(lines[-6:]))
    return (f"<div class='bs-card bs-enter' role='status' aria-live='polite'><div style='display:flex;gap:16px;align-items:center'>"
            f"<div class='bs-spin'></div><div><div class='bs-head' style='font-size:22px'>{esc(title)}</div>"
            f"<div class='bs-sub'>Streaming Sentinel data and building the road graph. First runs of a new area take a few minutes.</div></div></div>"
            f"<div class='bs-stepper'>{items}</div><div class='bs-grid' style='margin:0 0 16px'>{skel}</div>"
            f"<div class='bs-log'>{log}</div></div>")


def pretty_run(name):
    try:
        return _title(name)
    except Exception:
        return name.replace("_", " ")


def embed_html(text: str, height: int):
    """Embed generated HTML (our own pipeline output, escaped upstream) in an iframe; falls back to components.html on older Streamlit."""
    if hasattr(st, "iframe"):
        st.iframe(text, height=height)
    else:
        import streamlit.components.v1 as components
        components.html(text, height=height, scrolling=True)


def themed_map(text: str) -> str:
    light = THEME == "light"
    bg, fg, br = (P["bg"], P["text"], "rgba(128,128,128,.35)")
    css = (f"<style>#bs-load{{position:fixed;inset:0;z-index:99999;display:flex;align-items:center;justify-content:center;flex-direction:column;"
           f"gap:16px;background:{bg};color:{fg};font:16px Inter,system-ui,sans-serif;transition:opacity .25s}}"
           f"#bs-load .sp{{width:32px;height:32px;border-radius:50%;border:3px solid {br};border-top-color:{P['accent']};animation:r .8s linear infinite}}"
           "@keyframes r{to{transform:rotate(360deg)}}@media (prefers-reduced-motion:reduce){#bs-load .sp{animation:none}}"
           "</style><div id='bs-load' role='status'><div class='sp'></div><div>Loading map…</div></div>")
    js = ("<script>window.addEventListener('load',function(){setTimeout(function(){var l=document.getElementById('bs-load');"
          "if(l){l.style.opacity=0;setTimeout(function(){l.remove()},280)}"
          f"var want='{'light' if light else 'dark'}';document.querySelectorAll('.leaflet-control-layers-base label').forEach(function(lb){{"
          "if(lb.textContent.toLowerCase().indexOf(want)>-1){var i=lb.querySelector('input');if(i&&!i.checked){i.click()}}})},400)})</script>")
    body = "<body class='bs-light'>" if light else "<body>"
    text = text.replace("<body>", body + css, 1) if "<body>" in text else css + text
    return text.replace("</body>", js + "</body>", 1)


def access_list(rows, status, cap=7):
    sel = sorted([r for r in rows if r["status"] == status and "unnamed" not in str(r["name"]).lower()], key=lambda r: -r["n_buildings"])[:cap]
    out = ""
    for r in sel:
        after = f"{r['dist_after_km']} km" if pd.notna(r["dist_after_km"]) else "no route"
        before = f"{r['dist_before_km']} km" if pd.notna(r["dist_before_km"]) else "–"
        out += (f"<div class='bs-row'><div class='bd'>{badge(status)}</div><div><div class='nm'>{esc(str(r['name']))}</div>"
                f"<div class='tm'>{r['n_buildings']:,} bldg · {before} → {after}<br>{r['lat']:.3f}°N {r['lon']:.3f}°E</div></div></div>")
    return out or "<div class='bs-sub'>No named settlement in this class.</div>"


# ------------------------------------------------------------------------------------------------ run + selection state
runs = sorted(OUT.glob("*/summary.json"), key=lambda p: p.stat().st_mtime, reverse=True) if OUT.exists() else []
runs.sort(key=lambda p: p.parent.name != "trishuli")      # the case study first, then newest-first (sort is stable)
if "_goto_run" in st.session_state:
    st.session_state["sel_run"] = st.session_state.pop("_goto_run")
CTX = None


# ------------------------------------------------------------------------------------------------ pages
def page_overview():
    if not CTX:
        steps = ("<div class='bs-steps'><div><b>1 · CHOOSE</b>An area and the flood date.</div>"
                 "<div><b>2 · ANALYSE</b>Radar change detection, terrain and OpenStreetMap from before the event.</div>"
                 "<div><b>3 · ACT</b>Flood and debris map, damaged buildings, roads and bridges, and cut-off villages.</div></div>")
        st.markdown(empty_state("No analysis yet", "Run the Trishuli case study (26 August 2026) or choose your own area and date. "
                                "Everything is computed from free Sentinel, elevation and OpenStreetMap data.", extra=steps), unsafe_allow_html=True)
        _, mid, _ = st.columns([1, 1, 1])
        if mid.button("Open the analysis form", type="primary", icon=":material/arrow_forward:", width="stretch"):
            st.switch_page(PAGE_NEW)
        return
    rd, S, F = CTX["rd"], CTX["S"], CTX["F"]
    st.markdown("<div class='bs-grid'>"
                + card("Flooded / debris", f"{F['impact_ha']:,.0f}", f"{F['flood_ha']:,.0f} ha water · {F['debris_ha']:,.0f} ha debris", 1, unit="ha")
                + card("Buildings affected", f"{F['b_aff']:,}", f"of {F['b_total']:,} mapped · {F['b_severe']:,} likely destroyed", 2)
                + card("Road hit", f"{F['road_hit_km']:,.0f}", f"{F['br_hit']} of {F['br_total']} bridges hit", 3, unit="km")
                + card("Cut off", f"{F['n_cut']}", f"{F['n_long']} with a much longer route · {F['b_cut']:,} buildings", 4, dot=P["cut_off"])
                + "</div>", unsafe_allow_html=True)
    mp = rd / "dashboard_map.html"
    if mp.exists():
        embed_html(themed_map(mp.read_text(encoding="utf-8")), 880)
        st.markdown("<div class='bs-foot cap'>Orbital viewport · basemaps are for display only and are not analysis inputs.</div>", unsafe_allow_html=True)
    else:
        st.markdown(empty_state("The map file is missing", "This run has no <code>dashboard_map.html</code>. Re-run the analysis to regenerate it."),
                    unsafe_allow_html=True)
    rows = S.get("settlements", [])
    st.markdown("<div class='bs-twin'>"
                f"<div class='bs-card bs-list'><div class='bs-label'><span class='bs-dot' style='background:var(--bs-crit)'></span>Critical · cut off ({F['n_cut']})</div>"
                f"<div style='margin-top:8px'>{access_list(rows, 'cut_off')}</div></div>"
                f"<div class='bs-card bs-list'><div class='bs-label'><span class='bs-dot' style='background:var(--bs-watch)'></span>Watch · longer route ({F['n_long']})</div>"
                f"<div style='margin-top:8px'>{access_list(rows, 'longer_route')}</div></div></div>", unsafe_allow_html=True)
    st.markdown("<div class='bs-foot'>Largest named settlements first. The full list is under <b>Settlements</b>.</div>", unsafe_allow_html=True)


def page_settlements():
    if not CTX:
        return no_run_state()
    S = CTX["S"]
    page_title("Settlements", "Road access to the nearest hospital or town, before and after the event.")
    rows = S.get("settlements", [])
    if not rows:
        st.markdown(empty_state("No settlements found in this area", "OpenStreetMap had no named places or building clusters here before the "
                                "event, so there is nothing to assess for road access."), unsafe_allow_html=True)
    else:
        df = pd.DataFrame(rows)
        order = {"cut_off": 0, "longer_route": 1, "connected": 2, "not_assessable": 3, "no_road_data": 4}
        fc1, fc2 = st.columns(2)
        pick = fc1.pills("Show", list(order), selection_mode="multi", default=["cut_off", "longer_route"],
                         format_func=lambda k: f"{LEVEL[k][0].title()} · {LABEL[k]}", key="status_filter")
        q = fc2.text_input("Search a settlement", placeholder="e.g. Syapru")
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
                body += (f"<tr><td><b>{esc(str(r.name))}</b><div class='m'>{esc(str(r.reason))}</div></td><td>{badge(r.status)}</td>"
                         f"<td class='n'>{r.n_buildings:,}<div class='m'>{r.n_buildings_affected:,} affected</div></td>"
                         f"<td class='n'>{before} → {after}</td><td class='n'>{r.lat:.3f}°N {r.lon:.3f}°E</td>"
                         f"<td>{esc(str(r.dest_before)) if pd.notna(r.dest_before) else '–'}</td></tr>")
            st.markdown("<div class='bs-table-wrap bs-enter'><table class='bs-table'><thead><tr><th>Settlement</th><th>Level</th><th class='n'>Buildings</th>"
                        f"<th class='n'>Route before → after</th><th class='n'>Position</th><th>Was served by</th></tr></thead><tbody>{body}</tbody></table></div>",
                        unsafe_allow_html=True)
            st.caption(f"{len(df):,} settlements match" + (" (first 200 shown)" if len(df) > 200 else ""))
            _, mid, _ = st.columns([1, 1, 1])
            mid.download_button("Download as CSV", df.to_csv(index=False), f"{S['name']}_settlements.csv", icon=":material/download:", width="stretch")
    fp = S.get("flowpath")
    st.markdown("<div class='bs-page' style='margin-top:40px'><h2 class='bs-head'>Flood path downstream</h2>"
                "<p>Settlements along the traced valley, in downstream order.</p></div>", unsafe_allow_html=True)
    if fp and fp.get("settlements"):
        st.markdown(f"<p style='text-align:center'>Traced <b class='bs-mono'>{fp['length_km']} km</b> from the chosen upstream point; "
                    f"<b class='bs-mono'>{fp.get('buildings_in_corridor') or 0:,}</b> buildings lie in the susceptible corridor.</p>", unsafe_allow_html=True)
        fdf = pd.DataFrame(fp["settlements"])[["name", "km_along_path", "n_buildings"]].head(60)
        body = "".join(f"<tr><td>{esc(str(r.name))}</td><td class='n'>{r.km_along_path} km</td><td class='n'>{r.n_buildings:,}</td></tr>" for r in fdf.itertuples())
        st.markdown("<div class='bs-table-wrap'><table class='bs-table'><thead><tr><th>Settlement (downstream order)</th><th class='n'>Distance along path</th>"
                    f"<th class='n'>Buildings</th></tr></thead><tbody>{body}</tbody></table></div>", unsafe_allow_html=True)
    else:
        st.markdown(empty_state("No flood path traced", "Tick <b>Trace the flood path from an upstream point</b> on the New analysis page "
                                "to list the settlements along the valley in downstream order."), unsafe_allow_html=True)


def page_report():
    if not CTX:
        return no_run_state()
    rd = CTX["rd"]
    page_title("Situation report", "One page in English, one in Nepali. Every number comes from the maps; no value is generated by a language model.")
    rep = rd / "sitrep.html"
    if rep.exists():
        _, c1, c2, _ = st.columns([2, 1, 1, 2])
        c1.download_button("HTML", rep.read_bytes(), "sitrep.html", icon=":material/download:", help="Download the report as HTML", width="stretch")
        if (rd / "sitrep.pdf").exists():
            c2.download_button("PDF", (rd / "sitrep.pdf").read_bytes(), "sitrep.pdf", icon=":material/download:",
                               help="Download the report as PDF (English and Nepali)", width="stretch")
        embed_html(rep.read_text(encoding="utf-8"), 1180)
    else:
        st.markdown(empty_state("No situation report yet", "This run has no <code>sitrep.html</code>. Re-run the analysis to generate it."), unsafe_allow_html=True)


def page_method():
    if not CTX:
        return no_run_state()
    rd, S = CTX["rd"], CTX["S"]
    model_txt = S["model"]["file"] if S.get("model") else "physics only"
    prov = ", ".join(sorted(set(S["osm"]["provider"].values())))
    page_title("Method & data", "Which satellite passes, detector and map snapshot produced this result.")
    pr = S["s1_pairs"]
    ptxt = "".join(f"<tr><td>RO {p['rel_orbit']} · {esc(p['orbit_state'])}</td><td class='n'>{esc(p['post'][:16].replace('T', ' '))}Z</td>"
                   f"<td class='n'>{len(p['pre'])} images · latest {esc(p['pre'][0][:10])}</td>"
                   f"<td class='n'>{p['baseline_days']} d</td><td class='n'>{p['post_coverage']:.0%}</td></tr>" for p in pr)
    st.markdown("<div class='bs-grid'>"
                + card("Radar (Sentinel-1)", f"{len(pr)}", "Same-orbit pre/post pairs only. Different tracks are never compared pixel by pixel.", 1, unit="track" + ("s" if len(pr) != 1 else ""))
                + card("Optical clear sky", f"{S['s2']['clear_fraction']:.0%}" if S.get("s2") else "none",
                       "Cloud-masked Sentinel-2; adds flood-water evidence only where clear." if S.get("s2") else "No usable cloud-free overlap; radar only.", 2)
                + card("Detector", "AI + physics" if S.get("model") else "Physics", f"{esc(model_txt)}; terrain and river-proximity gates always apply.", 3)
                + card("OpenStreetMap", f"{S['osm']['snapshot']}", f"Pre-event snapshot via {esc(prov)}. No post-event edits are used.", 4)
                + "</div>", unsafe_allow_html=True)
    st.markdown("<div class='bs-table-wrap'><table class='bs-table'><thead><tr><th>Track</th><th class='n'>Post-event pass</th><th class='n'>Pre-event series</th>"
                f"<th class='n'>Baseline</th><th class='n'>Coverage</th></tr></thead><tbody>{ptxt}</tbody></table></div>", unsafe_allow_html=True)
    nz = S.get("noise", {})
    if nz:
        st.caption(f"Noise floor of stable terrain: VV σ {nz['vv_sigma_db']:.2f} dB · VH σ {nz['vh_sigma_db']:.2f} dB.")
    if (rd / "provenance.json").exists():
        with st.expander("Full provenance (parameters, inputs, forbidden inputs used: none)"):
            st.json(json.loads((rd / "provenance.json").read_text(encoding="utf-8")))


def page_ems():
    if not CTX:
        return no_run_state()
    rd = CTX["rd"]
    page_title("Check vs EMSR927", "Comparison with the official Copernicus EMS maps. Used for checking only, never as an input.")
    ev = rd / "evaluation_emsr927.json"
    if ev.exists():
        E = json.loads(ev.read_text(encoding="utf-8"))
        x = E["extent"]
        if isinstance(x, dict):
            b, rd_ = E.get("buildings", {}), E.get("roads", {})
            st.markdown("<div class='bs-grid'>"
                        + card("Overlap with EMS area", f"{x['IoU']:.2f}", "intersection over union", 1)
                        + card("Precision · recall", f"{x['precision']:.2f} · {x['recall']:.2f}", f"{E['extent_with_30m_tolerance']['precision']:.2f} · {E['extent_with_30m_tolerance']['recall']:.2f} with 30 m tolerance", 2)
                        + card("EMS buildings found", f"{b.get('recall', 0):.0%}", f"{b.get('reference_found_by_us(within 20 m)', 0):,} of {b.get('reference_affected', 0):,}", 3)
                        + card("EMS road length covered", f"{rd_.get('recall', 0):.0%}", f"our precision {rd_.get('precision', 0):.0%} (OSM maps more tracks than EMS assessed)", 4)
                        + "</div>", unsafe_allow_html=True)
        for f in sorted(rd.glob("evaluation_*.png")):
            _, mid, _ = st.columns([1, 3, 1])
            mid.image(str(f), width="stretch")
        st.markdown(f"<div class='bs-note'>Copernicus EMS maps are used for <b>checking only</b>. {esc(config.EMS_CREDIT)}.</div>", unsafe_allow_html=True)
    else:
        st.markdown(empty_state("No reference comparison for this run", "Download the EMSR927 vector products from the Copernicus EMS site into "
                                "<code>data/reference/emsr927/</code>, then run <code>python scripts/evaluate_emsr927.py --run outputs/&lt;run&gt;</code>. "
                                "They are used to check results only — never as input."), unsafe_allow_html=True)


def no_run_state():
    st.markdown(empty_state("No analysis yet", "Run an analysis first; results from finished runs appear on this page."), unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 1, 1])
    if mid.button("Open the analysis form", type="primary", icon=":material/arrow_forward:", width="stretch", key="goto_new"):
        st.switch_page(PAGE_NEW)


def page_new():
    page_title("New analysis", "Pick an area and a flood date. Results open on the Overview page when the run finishes.")
    left, right = st.columns(2, gap="large")
    with left:
        key = st.selectbox("Area", list(PRESETS) + ["custom"], format_func=lambda k: PRESETS[k]["label"] if k in PRESETS else "Custom area")
        base = PRESETS.get(key, PRESETS["trishuli"])
        with st.expander("Bounding box (west, south, east, north)", expanded=(key == "custom")):
            c1, c2 = st.columns(2)
            w = c1.number_input("West", value=float(base["bbox"][0]), format="%.4f")
            e = c2.number_input("East", value=float(base["bbox"][2]), format="%.4f")
            s = c1.number_input("South", value=float(base["bbox"][1]), format="%.4f")
            n = c2.number_input("North", value=float(base["bbox"][3]), format="%.4f")
        d1, d2 = st.columns(2)
        d = d1.date_input("Flood date (UTC)", value=base["event"].date())
        tm = d2.time_input("Approximate time (UTC)", value=base["event"].time())
        area_km2 = abs((e - w) * 111 * 0.88) * abs((n - s) * 111)
        st.caption(f"Area ≈ {area_km2:,.0f} km². Larger areas and first runs take longer; repeats are cached.")
    with right:
        res = st.select_slider("Resolution (m)", [10, 20, 40], value=20, help="10 m is sharpest and slowest; 40 m is a quick look.")
        pairs = st.slider("Radar tracks to combine", 1, 3, 2)
        use_s2 = st.checkbox("Use Sentinel-2 where the sky is clear", True)
        use_model = st.checkbox("Use the trained AI model if present", True)
        trace = st.checkbox("Trace the flood path from an upstream point", key == "trishuli")
        tlon, tlat = (base.get("trace_from") or (85.38, 28.2))
        if trace:
            t1, t2 = st.columns(2)
            tlon = t1.number_input("Upstream lon", value=float(tlon), format="%.4f")
            tlat = t2.number_input("Upstream lat", value=float(tlat), format="%.4f")
    _, mid, _ = st.columns([1, 1, 1])
    go = mid.button("Run analysis", type="primary", width="stretch", icon=":material/play_arrow:")
    if not go:
        st.markdown(empty_state("Ready when you are", "Press <b>Run analysis</b>. You will see each step as it runs; results open automatically."),
                    unsafe_allow_html=True)
        return
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
    except Exception as exc:
        hint = ("Radar needs images <b>before and after</b> the date on the <b>same orbit track</b> — try a different date or a larger area."
                if "same-track" in str(exc) else "Try a smaller area, a coarser resolution (40 m), or run again — remote data servers are sometimes busy.")
        ph.markdown(empty_state("The analysis could not finish", f"<code>{esc(str(exc))[:300]}</code><br><br>{hint}"), unsafe_allow_html=True)
        return
    ph.empty()
    st.session_state["_goto_run"] = r["out"].name
    st.switch_page(PAGE_OVERVIEW)


START = os.environ.get("BEACONSPACE_START", "overview")       # test hook: choose the landing page
PAGE_OVERVIEW = st.Page(page_overview, title="Overview", icon=":material/dashboard:", url_path="overview", default=(START == "overview"))
PAGE_SETT = st.Page(page_settlements, title="Settlements", icon=":material/alt_route:", url_path="settlements", default=(START == "settlements"))
PAGE_REPORT = st.Page(page_report, title="Situation report", icon=":material/description:", url_path="report", default=(START == "report"))
PAGE_METHOD = st.Page(page_method, title="Method & data", icon=":material/science:", url_path="method", default=(START == "method"))
PAGE_EMS = st.Page(page_ems, title="EMS check", icon=":material/fact_check:", url_path="ems", default=(START == "ems"))
PAGE_NEW = st.Page(page_new, title="New analysis", icon=":material/play_circle:", url_path="new", default=(START == "new"))
pg = st.navigation([PAGE_OVERVIEW, PAGE_SETT, PAGE_REPORT, PAGE_METHOD, PAGE_EMS, PAGE_NEW], position="top")

# ------------------------------------------------------------------------------------------------ shared header (symmetric: centred brand, run picker, telemetry)
st.markdown(f"<div class='bs-hero'><div class='bs-brand'>{LOGO}<h1>BeaconSpace</h1></div>"
            "<p class='bs-tag'>Satellite flood-damage mapping for rescue teams: where the flood hit, what was damaged, and who is cut off.</p></div>",
            unsafe_allow_html=True)

if runs and pg.title != "New analysis":
    names = [p.parent.name for p in runs]
    if st.session_state.get("sel_run") not in names:
        st.session_state["sel_run"] = names[0]
    _, pick_col, _ = st.columns([1, 2, 1])
    pick_col.selectbox("Run", names, key="sel_run", format_func=pretty_run)
    rd = OUT / st.session_state["sel_run"]
    with st.spinner("Loading results…"):
        S = json.loads((rd / "summary.json").read_text(encoding="utf-8"))
        CTX = {"rd": rd, "S": S, "F": facts(S)}
    model_txt = S["model"]["file"] if S.get("model") else "physics only"
    prov = ", ".join(sorted(set(S["osm"]["provider"].values())))
    passes = " · ".join(f"RO{p['rel_orbit']} {p['pre'][0][5:10]}→{p['post'][5:10]}" for p in S["s1_pairs"])
    st.markdown(
        "<div class='bs-strip'>"
        f"<span><i>FLOOD</i>{esc(S['event_utc'][:16].replace('T', ' '))}Z</span><span><i>GRID</i>{S['area_km2']:,.0f} km² · {S['resolution_m']:.0f} m</span>"
        f"<span><i>S1</i>{esc(passes)}</span><span><i>S2</i>{(str(round(S['s2']['clear_fraction'] * 100)) + '% clear') if S.get('s2') else 'radar only'}</span>"
        f"<span><i>DETECTOR</i>{esc(model_txt)}</span><span><i>OSM</i>{esc(S['osm']['snapshot'])} · {esc(prov)}</span>"
        f"<span><i>RUN</i>{S['runtime_s']:.0f} s</span></div>", unsafe_allow_html=True)

pg.run()

yr = int(CTX["S"]["event_utc"][:4]) if CTX else 2026
st.markdown("<div class='bs-foot'>" + " ".join(esc(a) for a in config.attribution(yr)[:3]) + "</div>", unsafe_allow_html=True)
