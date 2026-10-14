"""One-page bilingual (English / Nepali) situation report.

Deliberately *template-based*: every number is read from ``summary.json`` (i.e. from the system's maps),
so nothing can be invented by a language model. ``floodsys.copilot`` offers Q&A under the same rule.
"""
from __future__ import annotations

import base64
import time
import html
import shutil
import subprocess
from pathlib import Path

from .. import config

DEV = str.maketrans("0123456789", "\u0966\u0967\u0968\u0969\u096a\u096b\u096c\u096d\u096e\u096f")


def ne_name(name) -> str:
    """Localise the generic parts of auto-generated names (real OSM names are already Nepali)."""
    import re
    n = html.escape(str(name))
    n = re.sub(r"Unnamed settlement #(\d+) \(near (.+?), ([\d.]+) km\)",
               lambda m: f"नाम नखुलेको बस्ती #{ne(m.group(1))} ({m.group(2)} नजिक, {ne(m.group(3))} कि.मी.)", n)
    n = n.replace("Unnamed settlement", "नाम नखुलेको बस्ती")
    for en, npl in (("hospital (unnamed)", "अस्पताल (नाम नखुलेको)"), ("clinic (unnamed)", "क्लिनिक (नाम नखुलेको)"),
                    ("doctors (unnamed)", "डाक्टर क्लिनिक (नाम नखुलेको)"), ("health facility (unnamed)", "स्वास्थ्य संस्था (नाम नखुलेको)"),
                    ("village (unnamed)", "गाउँ (नाम नखुलेको)"), ("hamlet (unnamed)", "बस्ती (नाम नखुलेको)")):
        n = n.replace(en, npl)
    return n


def ne(x) -> str:
    """Devanagari digits for Nepali text."""
    return str(x).translate(DEV)


def _fmt(x, nd=1):
    if x is None:
        return "n/a"
    return f"{x:,.{nd}f}" if isinstance(x, float) else f"{x:,}"


def _title(name: str) -> str:
    from ..presets import PRESETS
    key = name.split("_")[0]
    return PRESETS[key]["label"] if key in PRESETS else name.replace("_", " ")


def _named(rows):
    return [r for r in rows if "unnamed" not in str(r["name"]).lower()]


def facts(s: dict) -> dict:
    """Flatten the summary into the figures used by the text (single source of truth)."""
    a, d, ac = s["area_ha"], s["damage"], s["access"]
    cut = sorted(s["cut_off"], key=lambda r: -r["n_buildings"])
    longer = sorted([r for r in s["settlements"] if r["status"] == "longer_route"], key=lambda r: -r["n_buildings"])
    prim = d["roads"].get("primary", {"hit_km": 0.0, "total_km": 0.0})
    return {
        "name": _title(s["name"]), "event": s["event_utc"][:16].replace("T", " ") + " UTC", "res": int(s["resolution_m"]),
        "area_km2": s["area_km2"], "flood_ha": a["flood water"], "debris_ha": a["debris / scour"],
        "impact_ha": a["impact_total_ha"], "perm_ha": a["permanent water"],
        "b_total": d["buildings"]["total"], "b_aff": d["buildings"]["affected_total"],
        "b_severe": d["buildings"]["destroyed_likely"], "b_exposed": d["buildings"]["exposed"],
        "road_hit_km": d["roads_total_hit_km"], "prim_hit_km": prim["hit_km"], "prim_total_km": prim["total_km"],
        "br_total": d["bridges"]["total"], "br_hit": d["bridges"]["hit"],
        "n_sett": ac.get("settlements", 0), "n_cut": ac.get("cut_off", 0), "n_long": ac.get("longer_route", 0),
        "n_conn": ac.get("connected", 0), "n_na": ac.get("not_assessable", 0) + ac.get("no_road_data", 0),
        "b_cut": ac.get("buildings_in_cut_off", 0), "cut": cut[:8], "longer": longer[:5], "n_longer_all": len(longer),
        "pairs": s["s1_pairs"], "s2": s["s2"], "model": s["model"], "osm": s["osm"],
        "agree_ha": s["confidence"].get("two_track_agreement_ha", 0), "flow": s.get("flowpath"),
    }


def _sar_line(f):
    p = f["pairs"][0]
    tracks = ", ".join(f"RO{q['rel_orbit']} ({q['pre'][0][:10]}\u2192{q['post'][:10]})" for q in f["pairs"])
    return tracks, p


def english(f: dict) -> str:
    tracks, _ = _sar_line(f)
    opt = (f"Sentinel-2 cloud-free overlap {f['s2']['clear_fraction']:.0%} of the area" if f["s2"] else
           "Sentinel-2: no usable cloud-free pixels (monsoon cloud) \u2013 radar only")
    ai = (f"AI flood-segmentation model ({f['model']['file']})" if f["model"] else "physics-based change detector")
    cut_rows = "".join(
        f"<tr><td>{html.escape(str(r['name']))}</td><td>{r['n_buildings']}</td><td>{r['dist_before_km'] or '\u2013'} km</td>"
        f"<td>{html.escape(str(r['dest_before'] or '\u2013'))}</td></tr>" for r in f["cut"]) or \
        "<tr><td colspan=4>No settlement lost its road connection to a hospital/town in the mapped network.</td></tr>"
    top_long = "; ".join(f"{html.escape(str(r['name']))} ({r['n_buildings']} buildings, {r['reason']})" for r in f["longer"]) or "none"
    longer = f"{f['n_longer_all']} settlements; largest: {top_long}"
    flow = ""
    if f["flow"]:
        names = ", ".join(f"{html.escape(str(r['name']))} ({r['km_along_path']} km)" for r in f["flow"]["settlements"][:10])
        flow = (f"<p><b>Downstream flood path:</b> traced {f['flow']['length_km']} km from the chosen upstream point; "
                f"settlements in the susceptible corridor, in downstream order: {names or 'none found'}.</p>")
    return f"""
<h2>Situation report &mdash; {html.escape(f['name'])}</h2>
<p class=meta>Flood date: {f['event']} &middot; analysed area {f['area_km2']:,.0f} km&sup2; at {f['res']} m &middot;
detector: {ai} &middot; radar tracks: {tracks} &middot; {opt}</p>
<div class=kpis>
<div><b>{_fmt(f['impact_ha'], 0)} ha</b>flooded or debris-covered<br><small>{_fmt(f['flood_ha'], 0)} ha water &middot; {_fmt(f['debris_ha'], 0)} ha debris/scour</small></div>
<div><b>{_fmt(f['b_aff'])}</b>buildings affected<br><small>of {_fmt(f['b_total'])} mapped &middot; {_fmt(f['b_severe'])} likely destroyed &middot; {_fmt(f['b_exposed'])} exposed nearby</small></div>
<div><b>{_fmt(f['road_hit_km'])} km</b>road hit &middot; {f['br_hit']}/{f['br_total']} bridges<br><small>{_fmt(f['prim_hit_km'])} of {_fmt(f['prim_total_km'])} km primary road</small></div>
<div><b>{f['n_cut']}</b>settlements cut off<br><small>{f['n_long']} with a longer route &middot; {f['n_conn']} still connected &middot; {_fmt(f['b_cut'])} buildings in cut-off settlements</small></div>
</div>
<h3>Who is cut off (road connection to nearest hospital/town lost)</h3>
<table><tr><th>Settlement</th><th>Buildings</th><th>Route before</th><th>Was served by</th></tr>{cut_rows}</table>
<p><b>Longer route only:</b> {longer}.</p>
{flow}
<h3>How reliable is this?</h3>
<p>Two-track agreement covers {_fmt(f['agree_ha'], 0)} ha. Radar sees through cloud but cannot tell debris from other
rough change with certainty; roads are blocked only if the mapped road (as of {f['osm']['snapshot']}) crosses the detected
area, so unmapped roads, bridges that survived inside the mask and smaller-than-pixel damage are not captured. Satellites revisit
every few days: this describes the scene as of the post-event pass, not the situation now. Verify before acting.</p>
"""


def nepali(f: dict) -> str:
    """Nepali template (needs review by a native speaker before operational use)."""
    cut_rows = "".join(
        f"<tr><td>{ne_name(r['name'])}</td><td>{ne(r['n_buildings'])}</td>"
        f"<td>{ne(r['dist_before_km'] or '–')} कि.मी.</td><td>{ne_name(r['dest_before'] or '–')}</td></tr>"
        for r in f["cut"]) or \
        "<tr><td colspan=4>नक्साङ्कित सडक सञ्जालमा अस्पताल/सहरसँगको सडक सम्पर्क गुमेको कुनै बस्ती भेटिएन।</td></tr>"
    flow = ""
    if f["flow"]:
        names = ", ".join(f"{ne_name(r['name'])} ({ne(r['km_along_path'])} कि.मी.)"
                          for r in f["flow"]["settlements"][:10])
        flow = (f"<p><b>बाढी बगेको बाटो (तल्लो भागतर्फ):</b> {ne(f['flow']['length_km'])} कि.मी. पत्ता लगाइयो; "
                f"जोखिमयुक्त करिडोरका बस्तीहरू (तलतल्तिर क्रमबद्ध): {names or 'भेटिएन'}।</p>")
    return f"""
<h2>स्थिति प्रतिवेदन — {html.escape(f['name'])}</h2>
<p class=meta>बाढीको मिति: {ne(f['event'])} · विश्लेषण गरिएको क्षेत्र {ne(round(f['area_km2']))} वर्ग कि.मी. ({ne(f['res'])} मिटर विभेदन)</p>
<div class=kpis>
<div><b>{ne(round(f['impact_ha']))} हेक्टर</b>बाढी वा भग्नावशेषले ढाकेको<br><small>पानी {ne(round(f['flood_ha']))} हे. · भग्नावशेष/कटान {ne(round(f['debris_ha']))} हे.</small></div>
<div><b>{ne(f['b_aff'])}</b>प्रभावित भवन<br><small>नक्साङ्कित {ne(f['b_total'])} मध्ये · पूर्ण क्षति हुन सक्ने {ne(f['b_severe'])} · नजिकै जोखिममा {ne(f['b_exposed'])}</small></div>
<div><b>{ne(f['road_hit_km'])} कि.मी.</b>सडक प्रभावित · पुल {ne(f['br_hit'])}/{ne(f['br_total'])}<br><small>मुख्य सडक {ne(f['prim_hit_km'])} / {ne(f['prim_total_km'])} कि.मी.</small></div>
<div><b>{ne(f['n_cut'])}</b>सडक सम्पर्क टुटेका बस्ती<br><small>बाटो लामो भएका {ne(f['n_long'])} · सम्पर्क कायमै {ne(f['n_conn'])} · सम्पर्क टुटेका बस्तीमा भवन {ne(f['b_cut'])}</small></div>
</div>
<h3>को को टाढा परेका छन् (नजिकको अस्पताल/सहरसँगको सडक सम्पर्क गुमेका)</h3>
<table><tr><th>बस्ती</th><th>भवन</th><th>पहिलेको दूरी</th><th>पहिले सेवा दिने ठाउँ</th></tr>{cut_rows}</table>
{flow}
<div class=disc><b>सावधानी:</b> उपग्रह-आधारित अनुमानमा अनिश्चितता हुन्छ; कारबाही गर्नुअघि स्थलगत पुष्टि गर्नुहोस्।
यो चित्र उपग्रहले अन्तिम पटक हेरेको समयको हो, अहिलेको अवस्था होइन। यो शैक्षिक प्रोटोटाइप हो, सञ्चालनात्मक उपकरण होइन।</div>
<p class=meta>सबै अङ्क प्रणालीका नक्सा/गणनाबाट स्वचालित रूपमा लिइएका हुन्; कुनै भाषा मोडेलले अङ्क बनाएको होइन।
(नेपाली पाठ टेम्प्लेटमा आधारित छ; प्रयोगअघि मूल नेपाली भाषीबाट समीक्षा आवश्यक।)</p>
"""


CSS = """
@page { size: A4; margin: 10mm }
body{font:10.5px/1.4 'Segoe UI','Nirmala UI',Arial,sans-serif;color:#1b1b1b;margin:0}
.page{max-width:190mm;margin:auto}
h2{font-size:15px;margin:2px 0 3px} h3{font-size:11.5px;margin:7px 0 3px;border-bottom:1px solid #ccc}
.meta{color:#555;font-size:9px;margin:2px 0 6px}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin:4px 0}
.kpis>div{background:#f2f5f9;border-radius:5px;padding:5px 7px;font-size:9.5px}
.kpis b{display:block;font-size:17px;color:#0b3d91}
table{border-collapse:collapse;width:100%;font-size:9.5px} th,td{border:1px solid #ddd;padding:2px 5px;text-align:left}
th{background:#eef1f5} .map{width:100%;max-height:105mm;object-fit:contain;border:1px solid #ccc;margin-top:4px}
.foot{font-size:7.5px;color:#555;margin-top:6px;border-top:1px solid #ccc;padding-top:3px}
.ne{page-break-before:always;font-family:'Nirmala UI','Noto Sans Devanagari',Mangal,sans-serif}
.disc{background:#fff6e5;border-left:3px solid #e69500;padding:3px 6px;font-size:9px;margin-top:5px}
"""


def build_html(summary: dict, map_png: Path | None) -> str:
    f = facts(summary)
    img = ""
    if map_png and map_png.exists():
        img = ("<img class=map src='data:image/png;base64," + base64.b64encode(map_png.read_bytes()).decode() + "'>")
    foot = ("<div class=foot>" + " ".join(html.escape(a) for a in config.attribution(int(summary["event_utc"][:4]))) +
            f" OSM snapshot: {f['osm']['snapshot']} (pre-event). Generated automatically from the system's maps; no value is "
            f"produced by a language model. {html.escape(config.DISCLAIMER)}</div>")
    return (f"<!doctype html><html lang=en><head><meta charset=utf-8><title>Situation report</title><style>{CSS}</style></head>"
            f"<body><div class=page>{english(f)}{img}<div class=disc>{html.escape(config.DISCLAIMER)}</div>{foot}"
            f"</div><div class='page ne'>{nepali(f)}{img}{foot}</div></body></html>")


def _browser() -> str | None:
    for p in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
              "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"):
        if Path(p).exists():
            return p
    return shutil.which("chrome") or shutil.which("chromium") or shutil.which("msedge")


def write_all(summary: dict, out: Path, log=print):
    html_text = build_html(summary, out / "map.png")
    (out / "sitrep.html").write_text(html_text, encoding="utf-8")
    out = Path(out).resolve()          # Edge resolves relative paths against its own cwd
    pdf = out / "sitrep.pdf"
    b = _browser()
    if not b:
        log("[sitrep] no Chrome/Edge found for PDF export; open sitrep.html and print to PDF")
        return
    import tempfile
    if pdf.exists():
        pdf.unlink()
    uri = (out / "sitrep.html").resolve().as_uri()
    # classic --headless is the reliable one for --print-to-pdf (--headless=new can exit 0 without writing)
    for mode in ("--headless", "--headless=new"):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as prof:   # private profile: works with the browser open
            try:
                subprocess.run([b, mode, "--disable-gpu", "--no-sandbox", f"--user-data-dir={prof}", "--no-pdf-header-footer",
                                f"--print-to-pdf={pdf}", uri], check=True, timeout=120, capture_output=True)
            except Exception as exc:
                log(f"[sitrep] PDF export attempt failed ({mode}): {exc}")
        for _ in range(10):                      # the file can appear a moment after the process exits
            if pdf.exists() and pdf.stat().st_size > 1000:
                break
            time.sleep(0.5)
        if pdf.exists() and pdf.stat().st_size > 1000:
            break
    if pdf.exists() and pdf.stat().st_size > 1000:
        log(f"[sitrep] wrote {pdf}")
    else:
        log("[sitrep] PDF was not produced; open sitrep.html and print to PDF")
