# BeaconSpace — roadmap

## Done
- [x] Same-track Sentinel-1 pair planner; radar change detection with terrain gates
- [x] Per-pixel pre-event variability + river-proximity rule (after the null-event test)
- [x] Sentinel-2 water evidence (cloud-masked, additive only)
- [x] OSM snapshot provider chain (ohsome → Overpass attic → local file) with resumable tile cache
- [x] Damage overlay for buildings, roads, bridges
- [x] Cut-off analysis with the blocked segment located
- [x] Flow-path bonus (D8) and HAND water-rise preview
- [x] U-Net trained on Kuro Siwo (Colab), ONNX inference, ablation and unseen-event evaluation
- [x] EN + NE situation report (templates), dashboard with top navigation, light/dark themes
- [x] Case study vs EMSR927 (checking only), null-event test, technical report (5 pages), tests

## Next (ranked by value)
1. **Same-season baselines.** Early-monsoon pairs still show 480–800 ha of false alarms because the pre-event series predates the monsoon. Add a warning and use last year's same-season images when available.
2. **Faster OSM.** Obtain ohsome access (or a regional extract) so a new area needs minutes, not an hour, for buildings.
3. **Debris labels for the AI.** Train on debris-flow / landslide-dam examples (none exist in Kuro Siwo) and evaluate event-by-event.
4. **Sentinel-1 SLC coherence** to separate scoured/deposited surfaces from field change.
5. **Uncertainty maps.** Per-pixel confidence from track agreement and variability, propagated into building and road counts.
6. **Native-speaker review** of the Nepali report and more languages.
7. **Hosted demo** with cached example runs (container image is ready).

## Known issues
- A first run on a new area is slow when only the public Overpass server is available.
- Hill-slope landslides far from rivers are intentionally out of scope.
- Farmland next to rivers can still produce false alarms.
- The AI model changes the Trishuli result by about 1 %; its measured benefit is on open-water floods.
