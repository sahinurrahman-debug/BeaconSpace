# BeaconSpace — 3-minute demo video — script and shot list

Record the screen (OBS / Win+G / Loom) with your voice. **No images of victims** (also no news footage). Keep the dashboard open and *pre-run*, so nothing waits on the network on camera. Replace `<N>` with the numbers shown in your final run (read them off the dashboard — never from memory).

| Time | On screen | Say (≈ words) |
|---|---|---|
| 0:00–0:20 | Title slide → dashboard home | "On 26 August 2026 a glacial-lake outburst sent a debris flood down the Bhote Koshi–Trishuli corridor. Roads, bridges and phone lines failed. BeaconSpace turns free Sentinel data into three answers for rescuers: where the flood hit, what was damaged, and who is cut off." |
| 0:20–0:50 | Sidebar: pick *Trishuli* preset, show bbox + date, press **Run** (or show the log of the pre-run) | "Give it any area and a flood date. It searches Sentinel-1 radar, finds same-orbit pairs twelve days apart, because different tracks cannot be compared pixel-by-pixel, and uses Sentinel-2 only where the monsoon sky is clear — here just <S2 clear %>." |
| 0:50–1:25 | Map: toggle flood / debris layers, zoom to the Syaphrubesi gorge, then to the lower valley; show *support* (two-track agreement) | "Orange is debris and scour, blue is flood water. Radar shadow is excluded because water must have *dropped* against the pre-event image; slope and height-above-drainage gates remove hillsides. A trained U-Net proposes the water — about 0.46 IoU on Kuro Siwo events it never saw, anywhere from 0.15 to 0.92 depending on the event, and weaker on mountains (about 0.35) — and the physics and terrain checks gate it." |
| 1:25–2:00 | Buildings / roads / bridges layers; metrics row | "Overlaying the OpenStreetMap snapshot from before the event: <B> buildings affected, <K> km of road hit, <br_hit> of <br_tot> bridges. Edits made after the event are never used — we request a snapshot dated 27 July." |
| 2:00–2:30 | *Who is cut off* tab: table, click a red settlement → popup with route before/after and the red marker where the road is cut | "We rebuild the road graph with and without the blocked segments. <C> settlements have lost their road route to the nearest hospital or town; <L> have a much longer route. The marker shows the exact cut a road crew would need to clear." |
| 2:30–2:45 | (Bonus) click upstream point → purple flow path + corridor + settlement list | "Pick any upstream point: we trace the flow path over the elevation model and list settlements in the corridor in downstream order." |
| 2:45–3:00 | *Situation report* tab (EN page, scroll to Nepali) → *Check vs EMSR927* tab | "A one-page report in English and Nepali — every number comes from the maps, nothing from a language model. Compared with the official Copernicus EMS map we reach <IoU_EMS> overlap; this is an educational prototype, and we list what it cannot do — it cannot warn minutes ahead, only describe the last satellite pass." |

## Checklist before recording
- [ ] `models/flood_unet.onnx` present, dashboard *Data & method* tab shows "AI model: flood_unet.onnx".
- [ ] `outputs/trishuli/` contains `sitrep.pdf`, `evaluation_emsr927.json`.
- [ ] Browser zoom 100 %, window 1920×1080, notifications off.
- [ ] Attributions visible in at least one frame (the map footer shows them).
- [ ] Audio checked; total length ≤ 3:00.
