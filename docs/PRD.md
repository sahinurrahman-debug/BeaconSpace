# BeaconSpace — product requirements

## Problem
After a mountain flood or glacial-lake outburst, ground sensors are swept away and roads, bridges and phone lines fail. Rescue coordinators need three answers quickly, from data that exists everywhere:
**where did the flood hit, what was damaged, and which villages are cut off?**

## Users
| User | Need |
|---|---|
| Rescue coordinator / duty officer | One map and a one-page report: which settlements to reach first, where the road is blocked |
| GIS / remote-sensing analyst | Reproducible products (GeoTIFF/GeoJSON), provenance, honest confidence |
| Hackathon judges | Run it on *their* area and date, see the AI and its limits, check data-rule compliance |

## Goals
1. Take **an area and a flood date** and run end-to-end from raw Sentinel data (no pre-baked results).
2. Map flooded and debris-covered areas (Sentinel-1 radar, Sentinel-2 where clear).
3. Overlay pre-event OpenStreetMap buildings, roads and bridges and estimate which were hit.
4. Find settlements that lost their road connection to the nearest hospital or town.
5. Include an AI component and show how well it works on unseen scenes.
6. Produce a map dashboard and a one-page situation report in English and Nepali, with every number computed from the maps.
7. Bonus: trace the flood path downstream from an upstream point and list the settlements along it.

## Non-goals
- Forecasting or early warning (satellites revisit every few days).
- Real-time feeds (rainfall, river gauges, drones) — not available in the allowed inputs.
- Population estimates (no allowed population dataset); we report buildings.
- Separating mud, boulders and landslides, or estimating depth/volume.

## Requirements and status
| # | Requirement (from the Track B brief) | Status |
|---|---|---|
| R1 | Flood + debris mapping from same-track pre/post Sentinel-1 (+ Sentinel-2 when clear) | Done |
| R2 | Buildings, roads, bridges from OSM **before** the event; estimate which were hit | Done |
| R3 | Cut-off settlements from the road network | Done |
| R4 | AI component: flood segmentation model (Kuro Siwo), evaluated on unseen scenes | Done (see honest results) |
| R5 | Map dashboard + one-page report (EN + NE) | Done |
| R6 | Bonus: flood path from any upstream point | Done |
| R7 | Case study vs Copernicus EMS EMSR927 (checking only) | Done |
| R8 | Report ≤ 6 pages with a limitations section; README; attributions and citations | Done |
| R9 | 3-minute demo video | Team task (script in `docs/DEMO_SCRIPT.md`) |

## Data rules (hard constraints)
Allowed inputs: Sentinel-1, Sentinel-2, Copernicus DEM, OpenStreetMap as it was before the event, the listed training datasets.
Not allowed as input: Copernicus EMS, UNOSAT or other damage maps, post-event OSM edits (they may only be used to check results).
Enforced in code and recorded per run in `provenance.json`.

## Success metrics
| Metric | Target | Result |
|---|---|---|
| End-to-end run on the case study | < 15 min with cached OSM | ≈ 3–10 min |
| Agreement with EMSR927 extent (IoU, inside EMS areas) | ≥ 0.4 | 0.48 |
| False alarms on pre-event "nothing happened" pairs (late season) | « real-event area | 42–71 ha vs 880–990 ha |
| Cut-off analysis reproducible from OSM snapshot | yes | yes (`summary.json`, `settlements.geojson`) |

## Risks
- Public OSM history servers are slow or blocked → provider chain + cached tiles.
- Monsoon cloud limits optical data → radar leads, optical only adds evidence.
- Farmland and monsoon soils create radar change → per-pixel variability + river-proximity rule.
- AI trained on low-relief floods → gated by terrain, reported with an ablation.
