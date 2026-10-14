# BeaconSpace — Q&A preparation — honest answers (for the team, not for submission)

Answer plainly; judges score "understanding in Q&A and honesty about limitations" (15 %). Numbers below are from `docs/results/` — re-check against your final run before the day.

**1. Why must pre/post radar images be on the same orbit track?**
Different tracks look at the terrain from different angles (layover, shadow, incidence angle), so pixel values aren't comparable. `plan_pairs` groups by relative orbit and never mixes tracks. For the case study: RO 85 (16→28 Aug) and RO 19 (24 Aug→5 Sep).

**2. How do you avoid radar shadow being called water?**
Water must be dark **and have dropped ≥ 3 dB** relative to the pre-event images; shadow is dark in both. Slope and height-above-drainage gates remove steep or high ground.

**3. What does the AI model actually add?** *(say this first — it is the weak spot)*
On the Trishuli case study almost nothing: with vs without the network, EMS-area IoU 0.483 vs 0.477, affected buildings found 56 % vs 56 %. The dominant class (debris/scour) comes from the change detector; EMS mapped no flood-water class the network could improve; our flood water is ~60 ha. The network's measured value is on open-water floods in Kuro Siwo: IoU 0.72 vs 0.50 for a threshold baseline — but 19 of 25 test-shard events also occur in training, so on the 6 truly unseen events the per-event IoU is 0.15–0.92 (patch-weighted mean 0.46). It is weak on steep terrain (IoU 0.35) and has 2.6 % false flood on flood-free patches.

**4. Then why include it?** The brief asks for it; it works well on typical open-water floods; it is gated by physics so it can't run wild; and we report its limits instead of hiding them.

**5. How accurate is the damage map?** Against EMSR927 inside its four areas: extent IoU 0.48 (precision 0.76, recall 0.57); with 30 m tolerance 0.82 / 0.76. 56 % of EMS-affected buildings found; 85 % of EMS-affected road length covered; road *precision* only 0.49 because OSM has many tracks EMS didn't assess. Building status is an estimate from 10–20 m pixels overlapping OSM footprints.

**6. You say you fixed false alarms — what happened?**
Our first detector flagged 670–2 620 ha of "debris" on pre-event pairs where nothing happened (rice terraces, monsoon-wet soils). We added (a) per-pixel natural variability from up to 5 pre-event images and (b) a rule that debris must lie within 150 m of the drainage network. Late-season false alarms fell to 42–71 ha vs 880–990 ha for the real event. Recall against EMS dropped from 0.65 to 0.57 — a deliberate trade. Early-July pairs still show 480–800 ha because their pre-event series ends before the monsoon.

**7. Did you tune on EMS? Is that allowed?**
No tuning on EMS. Thresholds were set from SAR physics, stable-terrain noise and null pairs. EMS was used for checking only (read three times: first detector, final detector, no-model ablation — all reported). One disclosure: we widened the study area west to include the Phosretar EMS area (coverage choice only).

**8. How do you prove no forbidden data was used?**
`provenance.json` lists sources and `forbidden_inputs_used: []`; the pipeline never reads `data/reference/`; the OSM request is dated before the event (RunConfig rejects otherwise). In one dense tile 15 % of buildings had been edited after the 27 July snapshot, which is why live OSM isn't acceptable.

**9. OpenStreetMap: why Overpass and not ohsome?**
The public ohsome *geometry* endpoint returned HTTP 403 from our network; the loader tries ohsome first and falls back to Overpass `[date:]` attic queries (verified date-dependent: 346 vs 1 418 buildings in a test tile for 2015 vs 2020). It is slow, so tiles are cached/bundled.

**10. How does "cut off" work, and what can go wrong?**
Road graph from pre-event OSM; roads intersecting the mask (≥ 10 m) are removed; multi-source Dijkstra from hospitals/clinics/towns gives each settlement's nearest destination before/after. Cut-off = route existed before, not after. Weaknesses: unmapped tracks/footpaths/helicopter access; routes leaving the area assumed intact; settlements = OSM places + building clusters; no population data (not an allowed input), so we report buildings, not people.

**11. What can't the system do?** Warn minutes ahead (satellites revisit every few days); see the situation *now*; separate mud/boulders/landslide or give depth/volume; map hill-slope landslides far from rivers; see through everything (wet snow, gorges); replace ground verification. It is an educational prototype.

**12. Why 20 m, not 10 m?** Speed for live use (4× fewer pixels; default 20 m, `--res 10` available). The network was trained with a random 2× downscale so it works at both; at 20 m the Kuro Siwo flood IoU is 0.71 vs 0.72.

**13. Is the Nepali report reliable?** It is template-based with numbers inserted from the maps (no language model, no invented numbers); wording needs review by a native speaker.

**14. What would you do with more time?** Sentinel-1 SLC coherence for debris; more pre-event seasons; a debris-flow-labelled training set; per-pixel uncertainty; population from allowed sources; faster OSM via ohsome access.

**15. What did go wrong during the build?** (honest anecdotes judges like) ohsome 403 → fallback; first detector's false alarms → null test and fix; Edge headless PDF export silently failing; Windows encoding; the mistaken "held-out" claim for Kuro Siwo test shards, corrected after checking event overlap.
