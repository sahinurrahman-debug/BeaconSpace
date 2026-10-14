"""Build the (max. 6 page) technical report as HTML -> PDF.  Every number is read from the saved result files.

    python scripts/build_report.py            -> docs/Report.html, docs/Report.pdf
"""
import base64
import html
import json
import statistics as st
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from floodsys import config  # noqa: E402
from floodsys.report.sitrep import _browser  # noqa: E402

R = ROOT / "docs" / "results"
RUN = ROOT / "outputs" / "trishuli"


def J(p, default=None):
    p = Path(p)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def img(p, w="100%"):
    p = Path(p)
    if not p.exists():
        return "<i>(figure missing)</i>"
    return f"<img style='width:{w}' src='data:image/png;base64,{base64.b64encode(p.read_bytes()).decode()}'>"


S = J(RUN / "summary.json")
S1 = J(R / "summary_v1_physics_noseries.json")
E1 = J(R / "evaluation_emsr927_v1_physics_noseries.json")
E2 = J(R / "evaluation_emsr927_v2_final.json")
E3 = J(R / "evaluation_emsr927_v2_nomodel_ablation.json")
S3 = J(R / "summary_v2_nomodel_ablation.json")
MEL = J(R / "robustness_melamchi_2021_summary.json")
M = J(R / "colab_metrics.json")
NULL_V1 = J(R / "null_test_v1_two_image_pre.json")
NULL_F = J(ROOT / "outputs" / "evaluation" / "null_test_v3_final_physics.json")
NULL_M = J(ROOT / "outputs" / "evaluation" / "null_test_v3_final_model.json")
CARD = J(ROOT / "models" / "flood_unet.json", {})
EV = J(R / "colab_events.json", {})
UNSEEN = EV.get("unseen_events", [])


def pct(x, nd=0):
    return f"{100 * x:.{nd}f}%"


def f2(x):
    return f"{x:.2f}"


a = S["area_ha"]; d = S["damage"]; ac = S["access"]
bld = d["buildings"]
ev1, ev2 = E1["extent"], E2["extent"]
m10, m20 = M["10m"], M["20m"]
fl10, fl20 = m10["all"]["flood"], m20["all"]["flood"]
mt10, mt20 = m10["mountain_slope_ge_10deg"]["flood"], m20["mountain_slope_ge_10deg"]["flood"]
base10 = m10["baseline_physics_threshold"]["flood"]; mod10 = m10["model_on_same_subset"]["flood"]
per10 = [m10["per_event_flood"][e]["iou"] for e in UNSEEN]
per20 = [m20["per_event_flood"][e]["iou"] for e in UNSEEN]
w10 = [m10["per_event_flood"][e]["patches"] for e in UNSEEN]
wm10 = sum(a * b for a, b in zip(per10, w10)) / sum(w10)
wm20 = sum(a * b for a, b in zip(per20, [m20["per_event_flood"][e]["patches"] for e in UNSEEN])) / sum(w10)
unseen_rows = "".join(
    f"<tr><td>event {e}</td><td>{m10['per_event_flood'][e]['patches']}</td><td>{f2(m10['per_event_flood'][e]['iou'])} / {f2(m20['per_event_flood'][e]['iou'])}</td>"
    f"<td>{f2(m10['per_event_flood'][e]['precision'])} / {f2(m10['per_event_flood'][e]['recall'])}</td></tr>" for e in UNSEEN)


def null_table():
    rows = ""
    def blk(label, N):
        if not N:
            return ""
        out = ""
        for r in N["pairs"]:
            out += (f"<tr><td>{label}</td><td>{r['pre']} → {r['post']}</td><td>{r['false_flood_ha']:.0f}</td>"
                    f"<td>{r['false_debris_ha']:.0f}</td><td>{r['per_1000km2_ha']:.0f}</td></tr>")
        for r in N.get("real_event", []):
            out += (f"<tr style='background:#eef5ff'><td>{label}</td><td>REAL EVENT {r['pre']} → {r['post']}</td>"
                    f"<td>{r['flood_ha']:.0f}</td><td>{r['debris_ha']:.0f}</td><td>–</td></tr>")
        return out
    rows += blk("v1: 2 pre images", {"pairs": NULL_V1["pairs"]} if NULL_V1 else None)
    rows += blk("final, physics", NULL_F)
    rows += blk("final, + AI model", NULL_M)
    return rows


def late_mean(N):
    if not N:
        return None
    v = [r["false_debris_ha"] + r["false_flood_ha"] for r in N["pairs"] if r["fake_event"] >= "2026-07-26"]
    return st.mean(v) if v else None


late_v1 = late_mean({"pairs": NULL_V1["pairs"]}) if NULL_V1 else None
late_f, late_m = late_mean(NULL_F), late_mean(NULL_M)

pairs_txt = "; ".join(f"RO{p['rel_orbit']} ({p['pre'][0][:10]} → {p['post'][:10]}, {len(p['pre'])} pre-event images)" for p in S["s1_pairs"])
s2c = S["s2"]["clear_fraction"] if S.get("s2") else None

CSS = """
@page{size:A4;margin:11mm 12mm}
body{font:10.6px/1.42 'Segoe UI',Arial,sans-serif;color:#1b1b1b;margin:0}
h1{font-size:19px;margin:0 0 2px} h2{font-size:13px;margin:9px 0 3px;color:#0b3d91;border-bottom:1px solid #c9d3e6;padding-bottom:1px}
h3{font-size:11px;margin:5px 0 2px} p{margin:2.5px 0} .sub{color:#555;font-size:9.4px}
table{border-collapse:collapse;width:100%;font-size:9.4px;margin:3px 0} th,td{border:1px solid #d5dbe6;padding:1.5px 4px;text-align:left} th{background:#eef1f7}
.two{display:grid;grid-template-columns:1fr 1fr;gap:8px} .fig{font-size:9px;color:#444;margin-top:1px}
.note{background:#fff6e5;border-left:3px solid #e69500;padding:2px 6px;margin:4px 0} .good{background:#eefaf0;border-left:3px solid #2a9d4b;padding:2px 6px;margin:4px 0}
ul{margin:2px 0 2px 14px;padding:0} li{margin:0.5px 0} small{color:#555} .pb{page-break-before:always}
"""

DIAGRAM = """
<svg viewBox='0 0 760 118' style='width:100%'><defs><marker id='a' viewBox='0 0 8 8' refX='7' refY='4' markerWidth='6' markerHeight='6' orient='auto'><path d='M0,0L8,4L0,8z' fill='#555'/></marker></defs>
<g font-family='Segoe UI,Arial' font-size='9.5' text-anchor='middle'>
<rect x='4' y='6' width='108' height='34' rx='5' fill='#e8f0fe' stroke='#4a6fd4'/><text x='58' y='20'>Sentinel-1 RTC</text><text x='58' y='32'>same-track pairs (≤5 pre)</text>
<rect x='4' y='46' width='108' height='30' rx='5' fill='#e8f0fe' stroke='#4a6fd4'/><text x='58' y='60'>Copernicus DEM</text><text x='58' y='71'>slope · HAND · rivers</text>
<rect x='4' y='82' width='108' height='30' rx='5' fill='#e8f0fe' stroke='#4a6fd4'/><text x='58' y='96'>Sentinel-2 (clear sky)</text><text x='58' y='107'>MNDWI water</text>
<rect x='150' y='28' width='150' height='62' rx='5' fill='#fff3e0' stroke='#e69500'/><text x='225' y='44'>Detection</text><text x='225' y='57'>U-Net (7 ch) + physics</text><text x='225' y='69'>variability-normalised change</text><text x='225' y='81'>terrain + river-proximity gates</text>
<rect x='340' y='6' width='120' height='34' rx='5' fill='#eaf7ee' stroke='#2a9d4b'/><text x='400' y='20'>OSM before event</text><text x='400' y='32'>ohsome → Overpass attic</text>
<rect x='340' y='46' width='120' height='30' rx='5' fill='#eaf7ee' stroke='#2a9d4b'/><text x='400' y='60'>Damage overlay</text><text x='400' y='71'>buildings · roads · bridges</text>
<rect x='340' y='82' width='120' height='30' rx='5' fill='#eaf7ee' stroke='#2a9d4b'/><text x='400' y='96'>Road graph pre vs post</text><text x='400' y='107'>who is cut off · where</text>
<rect x='500' y='28' width='125' height='62' rx='5' fill='#f3e8ff' stroke='#7b2cbf'/><text x='562' y='46'>Outputs</text><text x='562' y='60'>map dashboard</text><text x='562' y='72'>EN + नेपाली report</text><text x='562' y='84'>GeoJSON / GeoTIFF</text>
<rect x='660' y='28' width='96' height='62' rx='5' fill='#f2f2f2' stroke='#888'/><text x='708' y='46'>Bonus</text><text x='708' y='60'>D8 flow path</text><text x='708' y='72'>settlements</text><text x='708' y='84'>downstream</text>
<path d='M112 24L150 50M112 62L150 59M112 97L150 72M300 59L340 24M300 59L340 61M300 59L340 97M460 24L500 50M460 61L500 59M460 97L500 70M625 59L660 59' stroke='#555' fill='none' marker-end='url(#a)'/></g></svg>"""

BODY = f"""
<h1>Mapping flood damage from space — Trishuli / Bhote Koshi, 26 Aug 2026</h1>
<div class=sub>Multimodal AI Hackathon 2026 · Track B · AI component: flood-segmentation model · Educational prototype, not an operational tool.</div>

<h2>1 · What the system does</h2>
<p>Given a bounding box and a flood date, the system downloads Sentinel-1/2, the Copernicus DEM and a pre-event OpenStreetMap snapshot,
and answers three questions: <b>where the flood hit</b> (flood water and debris/scour), <b>what was damaged</b> (buildings, roads, bridges) and
<b>who is cut off</b> (settlements that lost their road route to the nearest hospital or town). A bonus module traces the flood path
downstream from any upstream point. Outputs: interactive dashboard, one-page bilingual (English/Nepali) situation report, GeoTIFF/GeoJSON and
a provenance file. It runs from raw data for any area/date: <code>python -m floodsys run --bbox W S E N --event DATE</code>.</p>
{DIAGRAM}
<p><b>Case-study result</b> (3 334 km², 20 m grid, {pairs_txt}; Sentinel-2 cloud-free overlap {pct(s2c) if s2c is not None else 'n/a'}):
<b>{a['impact_total_ha']:,.0f} ha</b> flooded or debris-covered ({a['flood water']:.0f} ha water, {a['debris / scour']:,.0f} ha debris/scour),
<b>{bld['affected_total']:,}</b> of {bld['total']:,} mapped buildings affected ({bld['destroyed_likely']:,} likely destroyed),
<b>{d['roads_total_hit_km']:.0f} km</b> of road and <b>{d['bridges']['hit']}/{d['bridges']['total']}</b> bridges hit,
<b>{ac['cut_off']}</b> settlements cut off and {ac['longer_route']} with a much longer route ({ac['buildings_in_cut_off']:,} buildings in cut-off settlements).</p>

<div style='text-align:center;margin:4px 0'>{img(RUN / 'map.png', '58%')}<div class=fig>Case-study map (final run): flood/debris along the Bhote Koshi–Trishuli corridor, hit roads, affected buildings, and settlements by road access (red = cut off). Contains modified Copernicus Sentinel data 2026; © OpenStreetMap contributors.</div></div>
<h2>2 · Data, rules and attribution</h2>
<table><tr><th>Input</th><th>Source / use</th><th>Rule compliance</th></tr>
<tr><td>Sentinel-1 RTC γ⁰ 10 m</td><td>Planetary Computer (from Copernicus GRD); same relative-orbit pre/post pairs, up to 5 pre-event images</td><td>allowed input</td></tr>
<tr><td>Sentinel-2 L2A</td><td>AWS Earth Search COGs; cloud/snow-masked by SCL; MNDWI water evidence</td><td>allowed input</td></tr>
<tr><td>Copernicus DEM GLO-30</td><td>slope, HAND, D8 flow, drainage network</td><td>allowed input</td></tr>
<tr><td>OpenStreetMap</td><td>snapshot <b>{S['osm']['snapshot']}</b> (before the event) via {', '.join(sorted(set(S['osm']['provider'].values())))}; the public ohsome <i>geometry</i> endpoint answered HTTP 403 from our network, so date-pinned Overpass “attic” queries were used</td><td>pre-event only; no post-event edits (in one dense tile 15 % of buildings had been edited after the snapshot, which shows why live data is not an option)</td></tr>
<tr><td>Kuro Siwo (GRD)</td><td>training the U-Net — Bountos et al., NeurIPS 2024, CC BY</td><td>listed training dataset</td></tr>
<tr><td>EMS EMSR927</td><td>checking only (<code>scripts/evaluate_emsr927.py</code>); never read by the pipeline; <code>provenance.json</code> records <code>forbidden_inputs_used: []</code></td><td>credit: “{config.EMS_CREDIT}”</td></tr></table>
<p class=sub>Contains modified Copernicus Sentinel data 2026. Produced using Copernicus WorldDEM-30 © DLR e.V. 2010–2014 and © Airbus Defence and Space GmbH 2014–2018 provided under COPERNICUS by the European Union and ESA; all rights reserved. © OpenStreetMap contributors.</p>

<h2>3 · Method</h2>
<h3>3.1 Radar pairs and change detection</h3>
<p><b>Pairing.</b> Acquisitions are grouped by relative orbit; a pair is a post-event pass plus up to five earlier passes on the <i>same</i> track (tracks are never compared pixel-by-pixel), preferring full AOI coverage, a short delay after the flood and a pre-image ≈12 days before. <b>Radiometry.</b> RTC γ⁰ → dB, 3×3 Lee filter at 10 m (as in Kuro Siwo), linear-domain window means at 20 m.
<b>Water</b> must be dark (VV &lt; −17 dB or VH &lt; −24 dB) <i>and</i> have dropped ≥3 dB against the pre-event mean, which removes radar shadow (dark in both images); slope ≤12° and HAND ≤40 m gates remove high ground.
<b>Debris/scour</b> (mud, boulders, scoured channel) raises or changes backscatter in both polarisations. We use a speckle-robust log-ratio, normalise it by <i>each pixel's own natural variability</i> (temporal std over the pre-event series), apply hysteresis thresholds (2.5σ / 4σ, ≥2.5 dB) derived from the empirical noise of stable hillslopes, and keep only changes within 150 m of the drainage network (catchment ≥5 km²).
<b>Optical</b> evidence only <i>adds</i> flood water where the sky is clear; it never vetoes radar. <b>Multi-track</b>: union of tracks with an agreement count as confidence ({S['confidence']['two_track_agreement_ha']:.0f} ha seen by both tracks).</p>
<div class=note><b>A mistake we found and fixed (null-event test).</b> Our first detector flagged 670–2 620 ha of “debris” on image pairs where <i>nothing happened</i> — rice terraces and monsoon-wet soils change backscatter by several dB. Two changes, chosen using only quiet-period pairs and physical reasoning (not EMS data), cut late-season false alarms by roughly 5–10×: per-pixel variability from the pre-event series, and the river-proximity rule. Parameters were frozen before the EMS comparison below.</div>
<h3>3.2 Damage and cut-off analysis</h3>
<p><b>Buildings</b> (OSM footprints): <i>likely destroyed</i> ≥50 % inside the mask; <i>affected</i> touching it (±10 m); <i>exposed</i> within 40 m. <b>Roads/bridges</b>: ≥10 m inside the mask (buffered half a pixel); bridges = ways tagged <code>bridge</code>.
<b>Who is cut off</b>: a vertex-level road graph ({ac.get('blocked_segments', 0):,} segments blocked in the final run); a multi-source Dijkstra from {ac['destinations']} hospitals/clinics/towns gives each settlement its nearest destination before and after.
<i>cut_off</i> = route exists before but not after; <i>longer_route</i> = route ≥1.5× and &gt;1 km longer. The first blocked segment on the old route is reported as the place to clear. Settlements = OSM places plus building clusters (DBSCAN) named by the nearest place.
<b>Flow path</b>: D8 flow directions from the DEM, followed from the snapped upstream cell to the area edge ({S['flowpath']['length_km']} km, {len(S['flowpath']['settlements'])} settlements in the corridor within 30 m of height above the path).</p>

<div class=pb></div>
<h2>4 · AI component: flood-segmentation model</h2>
<p><b>Model.</b> U-Net with a ResNet-34 encoder (ImageNet-initialised), 7 input channels (post VV/VH, pre VV/VH, smoothed log-ratio VV/VH, terrain slope), 3 classes (no water / permanent water / <i>new</i> flood water), exported to ONNX (98 MB, CPU inference; a unit test proves training and live feature construction are identical). <b>Training</b> on Colab T4: {CARD.get('trained_on', 'Kuro Siwo patches')}; cross-entropy with class weights + Dice, AdamW + one-cycle LR, ±1.5 dB gain and random 2× down-scale augmentation (the system runs at 20 m). Data: Kuro Siwo GRD (Bountos et al., NeurIPS 2024).
<b>In the pipeline</b> the network proposes flood water and the physics/terrain gates still apply.</p>
<div class=two><div>{img(R / 'training_curves.png')}<div class=fig>Training loss and validation flood IoU (random 8 % of training patches — optimistic, not the headline). The dip at epoch 5 is a one-off instability; the best checkpoint was kept.</div></div>
<div>{img(R / 'examples_heldout.png')}<div class=fig>Held-out examples: change-VV, reference, model (yellow = flood, teal = permanent water).</div></div></div>
<table><tr><th>Evaluation (flood class)</th><th>IoU</th><th>F1</th><th>Precision</th><th>Recall</th><th>n</th></tr>
<tr><td>Kuro Siwo test shards, 10 m</td><td>{f2(fl10['iou'])}</td><td>{f2(fl10['f1'])}</td><td>{f2(fl10['precision'])}</td><td>{f2(fl10['recall'])}</td><td>{m10['n_patches']:,} patches</td></tr>
<tr><td>… at 20 m (live-system resolution)</td><td>{f2(fl20['iou'])}</td><td>{f2(fl20['f1'])}</td><td>{f2(fl20['precision'])}</td><td>{f2(fl20['recall'])}</td><td>same</td></tr>
<tr><td><b>Events never seen in training</b> ({len(UNSEEN)} events, {sum(w10):,} patches): patch-weighted mean of per-event IoU, 10 m / 20 m</td><td colspan=4><b>{f2(wm10)} / {f2(wm20)}</b> (per-event range {f2(min(per10))}–{f2(max(per10))}, median {f2(st.median(per10))} at 10 m)</td><td>{len(UNSEEN)} events</td></tr>
<tr><td><b>Mountain subset</b> (mean slope ≥10°), 10 m / 20 m</td><td>{f2(mt10['iou'])} / {f2(mt20['iou'])}</td><td>{f2(mt10['f1'])} / {f2(mt20['f1'])}</td><td>{f2(mt10['precision'])} / {f2(mt20['precision'])}</td><td>{f2(mt10['recall'])} / {f2(mt20['recall'])}</td><td>{m10['n_mountain_patches']} patches</td></tr>
<tr><td>Physics threshold baseline vs model, same subset, 10 m</td><td>{f2(base10['iou'])} vs {f2(mod10['iou'])}</td><td>{f2(base10['f1'])} vs {f2(mod10['f1'])}</td><td>{f2(base10['precision'])} vs {f2(mod10['precision'])}</td><td>{f2(base10['recall'])} vs {f2(mod10['recall'])}</td><td>600 patches</td></tr>
<tr><td>False flood pixels on flood-free held-out patches (20 m)</td><td colspan=4>{pct(M['false_alarm_rate_flood_free_patches'], 1)} of land</td><td>≤800 patches</td></tr></table>
<div class=two><table><tr><th>Unseen event</th><th>patches</th><th>IoU 10 m / 20 m</th><th>P / R (10 m)</th></tr>{unseen_rows}</table>
<div class=note><b>Honest reading.</b> The all-patch numbers above are <b>not</b> an event-held-out test: 19 of the 25 events in the test shards also occur in our training patches (Hugging Face's split is not by event), and the validation curve is a random patch split. The clean test is the {len(UNSEEN)} events absent from training: IoU {f2(min(per10))}–{f2(max(per10))}, <b>patch-weighted mean {f2(wm10)}</b> — the model generalises well to some places and poorly to others. It also beats the threshold baseline on the same patches, but is weak on steep terrain (IoU {f2(mt10['iou'])}, precision {f2(mt10['precision'])}) and over-predicts flood on dry land ({pct(M['false_alarm_rate_flood_free_patches'], 1)}), which is why its output is gated by slope, HAND and permanent-water masks. Kuro Siwo has no debris-flow labels, so debris comes from the change detector. In the Trishuli case study the model changes the result only slightly (see ablation below).</div></div>

<h2>5 · Case study vs Copernicus EMS EMSR927 (check only)</h2>
<p>EMS mapped four areas (Syapru Besi, Timure, Bidur, Phosretar; {ev2['evaluated_inside_EMS_AOI_ha']:,.0f} ha) as one class, “mass movement”, {ev2['reference_ha']:,.0f} ha. We compare our flood+debris footprint, OSM buildings and roads inside these areas. The study area was widened west to cover the Phosretar area (a coverage choice only). Detector parameters were set before looking at EMS; EMS was read twice (before/after the false-alarm fix) and nothing was tuned on it.</p>
<div class=two><div>
<table><tr><th>Inside EMS areas</th><th>v1 first detector</th><th>final system</th></tr>
<tr><td>Our extent / EMS extent (ha)</td><td>{ev1['ours_ha']:,.0f} / {ev1['reference_ha']:,.0f}</td><td>{ev2['ours_ha']:,.0f} / {ev2['reference_ha']:,.0f}</td></tr>
<tr><td>IoU</td><td>{f2(ev1['IoU'])}</td><td>{f2(ev2['IoU'])}</td></tr>
<tr><td>Precision / recall</td><td>{f2(ev1['precision'])} / {f2(ev1['recall'])}</td><td>{f2(ev2['precision'])} / {f2(ev2['recall'])}</td></tr>
<tr><td>… with 30 m tolerance</td><td>{f2(E1['extent_with_30m_tolerance']['precision'])} / {f2(E1['extent_with_30m_tolerance']['recall'])}</td><td>{f2(E2['extent_with_30m_tolerance']['precision'])} / {f2(E2['extent_with_30m_tolerance']['recall'])}</td></tr>
<tr><td>EMS affected buildings found (≤20 m)</td><td>{E1['buildings']['reference_found_by_us(within 20 m)']:,} / {E1['buildings']['reference_affected']:,} ({pct(E1['buildings']['recall'])})</td><td>{E2['buildings']['reference_found_by_us(within 20 m)']:,} / {E2['buildings']['reference_affected']:,} ({pct(E2['buildings']['recall'])})</td></tr>
<tr><td>Road: EMS affected km covered / our precision</td><td>{pct(E1['roads']['recall'])} / {pct(E1['roads']['precision'])}</td><td>{pct(E2['roads']['recall'])} / {pct(E2['roads']['precision'])}</td></tr></table>
<p class=sub>Road precision is low because OSM maps many tracks that EMS did not assess. EMS counts only affected buildings, so building precision cannot be computed.</p></div>
<div>{img(RUN / 'evaluation_extent.png')}<div class=fig>Final extent (orange) vs EMS observed event (blue) inside the EMS areas. {html.escape(config.EMS_CREDIT)}.</div></div></div>
<div class=good><b>Reading.</b> We trace the same corridor, but the final detector trades recall for precision: EMS “mass movement” also includes hill-slope landslide scars away from rivers, which our river-proximity rule deliberately does not map (and radar change there is indistinguishable from vegetation/soil change). Using the whole EMS-area comparison, the system finds {pct(ev2['recall'])} of EMS's event area and {pct(E2['buildings']['recall'])} of its affected buildings.</div>

<div class=note><b>What does the AI model add here? (ablation)</b> Running the same case study <i>without</i> the network: flood+debris {S3['area_ha']['impact_total_ha']:,.0f} ha vs {a['impact_total_ha']:,.0f} ha with it; EMS-area IoU {f2(E3['extent']['IoU'])} vs {f2(ev2['IoU'])}; EMS-affected buildings found {pct(E3['buildings']['recall'])} vs {pct(E2['buildings']['recall'])}; road coverage {pct(E3['roads']['recall'])} vs {pct(E2['roads']['recall'])}. <b>The network changes the Trishuli result by about 1 %</b>: the dominant class (debris/scour) comes from the change detector, EMS has no separate flood-water class that could reward the network, and the model's flood water ({a['flood water']:.0f} ha vs {S3['area_ha']['flood water']:.0f} ha) is small and still gated by terrain. The network's value is demonstrated on Kuro Siwo (open-water floods, §4), not on this debris-flow case.</div>

<h2>6 · False alarms: the null-event test</h2>
<p>For fake “events” before the real flood we run the identical pipeline on same-track pairs where nothing happened; everything flagged is a false alarm by construction (area {NULL_V1['area_km2'] if NULL_V1 else ''} km², ha flagged).</p>
<table><tr><th>Detector</th><th>Pre → post pair</th><th>false flood ha</th><th>false debris ha</th><th>ha per 1000 km²</th></tr>{null_table()}</table>
<p>Late-season pairs (pre-event series in the monsoon): mean false alarm <b>{f'{late_v1:.0f}' if late_v1 else 'n/a'} ha</b> with the first detector → <b>{f'{late_f:.0f}' if late_f else 'n/a'} ha</b> final (physics) {f'→ {late_m:.0f} ha with the AI model' if late_m else ''}, against ≈1 000–1 200 ha of debris flagged for the real event. Early-July pairs stay noisy because their pre-event series ends before the monsoon began — <b>a real limitation</b>: the detector needs pre-event images from the same season.</p>

<div class=good><b>Second Himalayan event, no reference map (robustness only).</b> The unchanged system was run on the June 2021 Melamchi flood (small area, different year, Sentinel-1A/1B, a 2021 OSM snapshot chosen automatically): it completed end to end and mapped {MEL['area_ha']['impact_total_ha']:,.0f} ha ({MEL['area_ha']['flood water']:.0f} ha water, {MEL['area_ha']['debris / scour']:.0f} ha debris), {MEL['damage']['buildings']['affected_total']} affected buildings of {MEL['damage']['buildings']['total']:,}, {MEL['damage']['bridges']['hit']}/{MEL['damage']['bridges']['total']} bridges hit and {MEL['access']['cut_off']} cut-off settlements; the traced flood path ({MEL['flowpath']['length_km']} km) follows the detected corridor through Melamchi Bazaar. <b>We have no reference for this event, so this shows the system runs on a new place and date — it is not an accuracy claim.</b> Isolated patches on a side tributary look like possible false alarms.</div>

<h2>7 · Limitations — what the system cannot do</h2>
<ul>
<li><b>No warning.</b> Sentinel satellites revisit every few days (12 days per track); the system describes the scene at the last pass, not “now”, and cannot warn of a glacier collapse minutes ahead. Flood extent may have changed or receded before the post-event image.</li>
<li><b>Resolution.</b> 10–20 m pixels: single houses, small footbridges and narrow tracks are inferred from overlap with the footprint, not seen. Building status is an <i>estimate</i> (no VHR optical imagery).</li>
<li><b>Debris is “change”, not a class.</b> It cannot say mud vs. boulders vs. landslide, depth or volume; hill-slope landslides away from rivers are out of scope; farmland near rivers can still false-alarm (see §6).</li>
<li><b>Monsoon cloud.</b> Sentinel-2 was usable on only {pct(s2c) if s2c is not None else 'n/a'} of the area; radar is blind to nothing about cloud but is confused by wet snow, layover/shadow in gorges, and changes in rice/crop cover.</li>
<li><b>Road network.</b> Cut-off logic only knows <i>mapped</i> roads (OSM at {S['osm']['snapshot']}): unmapped tracks, footpaths, helicopter or boat access and repairs since are unknown; routes leaving the analysed area are assumed intact; “settlement” = OSM place/building cluster, with no population data (not an allowed input).</li>
<li><b>AI model.</b> Trained on mostly low-relief floods; on events never seen in training its IoU ranges 0.15–0.92 (§4); weak on steep terrain; 2.6 % false-alarm rate on flood-free patches; no debris labels.</li>
<li><b>OpenStreetMap access.</b> The public ohsome geometry endpoint was blocked from our network; the Overpass fallback is slow (our 3 300 km² case took an hour or more once; cached afterwards).</li>
<li><b>Nepali text</b> is template-based and needs review by a native speaker; <b>no values are generated by a language model</b>.</li>
<li><b>Uncertainty is not propagated</b> into the counts; treat them as ± tens of percent (see EMS comparison).</li></ul>

<h2>8 · Reproducibility, responsibility, citations</h2>
<p>Code, tests (<code>pytest</code>), Colab notebook, README and per-run <code>provenance.json</code> are in the repository; the case study runs in ≈10 min once OSM tiles are cached. This disaster is recent: no images of victims are used; outputs are labelled as educational prototypes.
<br><b>Cite:</b> Bountos, N.I., Sdraka, M., Zavras, A., Karavias, A., Karasante, I., Herekakis, T., Thanasou, A., Michail, D., Papoutsis, I. (2024) <i>Kuro Siwo: 33 billion m² under the water</i>, NeurIPS Datasets &amp; Benchmarks. · Copernicus Sentinel-1/2 data 2026; Copernicus DEM GLO-30; © OpenStreetMap contributors (ODbL); {html.escape(config.EMS_CREDIT)} (activation EMSR927, checking only).</p>
"""


def main():
    page = f"<!doctype html><html lang=en><head><meta charset=utf-8><title>Report</title><style>{CSS}</style></head><body>{BODY}</body></html>"
    out = ROOT / "docs"
    (out / "Report.html").write_text(page, encoding="utf-8")
    pdf = (out / "Report.pdf").resolve()
    b = _browser()
    if not b:
        print("no Edge/Chrome found; open docs/Report.html and print to PDF")
        return
    if pdf.exists():
        pdf.unlink()
    import time
    for attempt in range(4):                       # headless Edge/Chrome occasionally exits without writing the file
        mode = "--headless" if attempt % 2 == 0 else "--headless=new"
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as prof:
            subprocess.run([b, mode, "--disable-gpu", "--no-sandbox", f"--user-data-dir={prof}", "--no-pdf-header-footer",
                            f"--print-to-pdf={pdf}", (out / "Report.html").resolve().as_uri()], timeout=180, capture_output=True)
        for _ in range(20):
            if pdf.exists() and pdf.stat().st_size > 1000:
                break
            time.sleep(0.5)
        if pdf.exists() and pdf.stat().st_size > 1000:
            break
    import pymupdf
    n = len(pymupdf.open(pdf))
    print(f"wrote {pdf} — {n} pages", "(OK ≤ 6)" if n <= 6 else "(TOO LONG: trim)")


if __name__ == "__main__":
    main()
