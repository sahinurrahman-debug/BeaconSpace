"""Central configuration: endpoints, attribution strings, tunable parameters."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = Path(os.environ.get("FLOODSYS_CACHE", ROOT / "cache"))
OUTPUT_DIR = Path(os.environ.get("FLOODSYS_OUT", ROOT / "outputs"))
MODEL_PATH = Path(os.environ.get("FLOODSYS_MODEL", ROOT / "models" / "flood_unet.onnx"))

PC_STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
AWS_STAC = "https://earth-search.aws.element84.com/v1"
OHSOME = "https://api.ohsome.org/v1"
DEM_URL = ("https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_{ns}{lat:02d}_00_{ew}{lon:03d}_00_DEM/"
           "Copernicus_DSM_COG_10_{ns}{lat:02d}_00_{ew}{lon:03d}_00_DEM.tif")

ATTRIBUTION = [
    "Contains modified Copernicus Sentinel data 2026.",
    "Produced using Copernicus WorldDEM-30 © DLR e.V. 2010–2014 and © Airbus Defence and Space GmbH "
    "2014–2018 provided under COPERNICUS by the European Union and ESA; all rights reserved.",
    "© OpenStreetMap contributors.",
    "Training data: Kuro Siwo – Bountos et al., NeurIPS 2024 Datasets & Benchmarks (CC BY).",
]
def attribution(year: int = 2026) -> list:
    """Required attribution lines; the Sentinel line carries the year of the data actually used."""
    return [a.replace("data 2026.", f"data {year}.") for a in ATTRIBUTION]


EMS_CREDIT = "European Union, Copernicus Emergency Management Service data"
DISCLAIMER = ("Educational prototype – not an operational tool. Satellite-derived estimates carry uncertainty; "
              "verify on the ground before acting.")

# OpenStreetMap queries -------------------------------------------------------
ROAD_CLASSES = ("motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential",
                "service", "track", "motorway_link", "trunk_link", "primary_link", "secondary_link",
                "tertiary_link", "living_street")
PLACE_CLASSES = ("city", "town", "village", "hamlet", "suburb", "neighbourhood", "isolated_dwelling")
TOWN_CLASSES = ("city", "town")


@dataclass
class DetectParams:
    """Flood / debris detection parameters.

    Set a-priori from SAR physics and checked on *pre-event null pairs* and the
    Kuro Siwo held-out events. They were NOT tuned on the EMSR927 reference maps.
    """
    water_vv_db: float = -17.0        # open water is specular -> very dark in VV
    water_vh_db: float = -24.0
    water_drop_db: float = 3.0        # must also drop >= 3 dB w.r.t. pre-event
    change_low_k: float = 2.5         # hysteresis low: x robust sigma of stable terrain
    change_high_k: float = 4.0        # hysteresis high (seed)
    min_change_db: float = 2.5        # and never below this many dB (smoothed VV or VH)
    max_chan_dist_m: float = 150.0    # debris/scour must hug the drainage network (rivers with catchment >= chan_upa_km2)
    chan_upa_km2: float = 5.0
    variability_gain: float = 1.0     # scale of each pixel's own pre-event variability (std over the pre series)
    max_slope_water: float = 12.0     # deg: still water does not rest on steep slopes
    max_slope_debris: float = 35.0
    max_hand_water: float = 40.0      # m above nearest drainage
    max_hand_debris: float = 60.0
    min_area_ha: float = 0.3          # drop speckle-sized blobs
    s2_water_mndwi: float = 0.15
    s2_ndvi_drop: float = 0.25
    model_prob: float = 0.5


@dataclass
class DamageParams:
    building_buffer_m: float = 10.0       # raster/footprint uncertainty
    severe_overlap: float = 0.5           # >= 50 % of footprint inside the mask
    exposed_buffer_m: float = 40.0        # near the mask but not touching it
    road_min_overlap_m: float = 10.0      # metres of road inside the mask to count as hit
    bridge_buffer_m: float = 25.0


@dataclass
class AccessParams:
    snap_m: float = 400.0                 # max distance settlement -> road network
    detour_ratio: float = 1.5             # "degraded access" if route becomes this much longer
    cluster_eps_m: float = 120.0
    cluster_min_buildings: int = 4
    osm_buffer_km: float = 6.0            # fetch OSM beyond the AOI so routes can leave it


@dataclass
class Settings:
    detect: DetectParams = field(default_factory=DetectParams)
    damage: DamageParams = field(default_factory=DamageParams)
    access: AccessParams = field(default_factory=AccessParams)


def apply_gdal_env() -> None:
    """Retry-friendly remote COG access (Planetary Computer / AWS)."""
    os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "8")
    os.environ.setdefault("GDAL_HTTP_RETRY_DELAY", "2")
    os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
    os.environ.setdefault("VSI_CACHE", "TRUE")
    os.environ.setdefault("GDAL_HTTP_MULTIPLEX", "YES")
    os.environ.setdefault("GDAL_HTTP_VERSION", "2")
    os.environ.setdefault("GDAL_HTTP_TIMEOUT", "60")
    os.environ.setdefault("CPL_VSIL_CURL_USE_HEAD", "NO")


apply_gdal_env()
CACHE_DIR.mkdir(parents=True, exist_ok=True)
