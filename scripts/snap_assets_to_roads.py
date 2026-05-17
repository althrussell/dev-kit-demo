"""Snap synthetic assets to real OpenStreetMap road centerlines.

After `snap_synthetic_to_land.py` clusters everything around real Queensland
town anchors, this script does the second pass: for each anchor we fetch real
road geometry from the OpenStreetMap Overpass API, then snap each asset's
lat/lon onto its nearest road segment.

  - **Poles, switches, reclosers, sectionalisers, ring main units, conductor
    spans** (the things that physically follow the roadside): snapped onto
    the centreline with 0–4 m perpendicular jitter.
  - **Transformers**: snapped onto road with 3–10 m offset (often pole-top or
    pad-mount slightly off the kerb).
  - **Critical customers, depots, substations, mobile-gen sites, vegetation
    spans**: snapped to nearest road with larger offset (10–80 m) since they
    are buildings/parcels near roads, not roadside infrastructure.

Road geometries are cached per anchor under
`data/synthetic/_road_cache/<anchor>.geojson` so re-running is fast (and
respectful to the public Overpass endpoint).
"""

from __future__ import annotations

import csv
import json
import math
import random
import sys
import time
from pathlib import Path
from typing import Iterable

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data" / "synthetic"
CACHE_DIR = DATA_DIR / "_road_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Reuse anchors from the land-snap script so we hit identical centroids.
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from snap_synthetic_to_land import REGION_ANCHORS  # noqa: E402

# Overpass API endpoints. Mirrors are tried in order; first one that returns
# 200 wins. The main endpoint frequently throttles unauthenticated requests
# (and rejects bare User-Agents), so the Kumi Systems mirror is a useful
# fallback.
OVERPASS_URLS = (
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)
USER_AGENT = (
    "GridLensDemo/0.1 (Databricks Apps demo; contact: al.thrussell@databricks.com)"
)

# Roughly 5km box (~0.045°) around each anchor; bigger for remote anchors.
DEFAULT_BBOX_DEG = 0.05
REMOTE_BBOX_DEG = 0.18

# Asset type → perpendicular offset (metres). Lower = closer to road
# centreline.  Roadside infrastructure hugs the line; buildings stand off.
ASSET_TYPE_OFFSET_M: dict[str, tuple[float, float]] = {
    "pole":           (0.0, 4.0),
    "conductor_span": (0.0, 4.0),
    "switch":         (0.0, 5.0),
    "recloser":       (0.0, 5.0),
    "sectionaliser":  (0.0, 5.0),
    "ring_main_unit": (3.0, 8.0),
    "transformer":    (3.0, 10.0),
}

# Highway tags worth snapping to (excludes paths/cycleways/footways).
HIGHWAY_TAGS = (
    "trunk", "trunk_link",
    "primary", "primary_link",
    "secondary", "secondary_link",
    "tertiary", "tertiary_link",
    "unclassified", "residential", "service",
    "motorway", "motorway_link",
)


# ---------------------------------------------------------------------------
# Geo helpers
# ---------------------------------------------------------------------------


def meters_to_deg_lat(m: float) -> float:
    return m / 111_320.0


def meters_to_deg_lon(m: float, at_lat: float) -> float:
    return m / (111_320.0 * max(math.cos(math.radians(at_lat)), 1e-6))


def bbox(lat: float, lon: float, span_deg: float) -> tuple[float, float, float, float]:
    """Return (south, west, north, east) bounding box in degrees."""
    return (lat - span_deg, lon - span_deg, lat + span_deg, lon + span_deg)


# ---------------------------------------------------------------------------
# Overpass fetch
# ---------------------------------------------------------------------------


def overpass_query_for_bbox(s: float, w: float, n: float, e: float) -> str:
    tags = "|".join(HIGHWAY_TAGS)
    return f"""
[out:json][timeout:60];
(
  way["highway"~"^({tags})$"]({s},{w},{n},{e});
);
out geom;
""".strip()


def fetch_roads_for_anchor(name: str, lat: float, lon: float, span_deg: float) -> list[list[tuple[float, float]]]:
    """Return a list of road segments as `[(lon, lat), ...]` for the bbox.

    Cached on disk per-anchor.
    """
    cache_path = CACHE_DIR / f"{name.replace(' ', '_').replace('/', '_')}.json"
    if cache_path.exists():
        try:
            payload = json.loads(cache_path.read_text())
            return payload.get("segments", [])
        except Exception:
            pass

    s, w, n, e = bbox(lat, lon, span_deg)
    query = overpass_query_for_bbox(s, w, n, e)
    print(f"  fetching OSM roads for {name} [{s:.3f},{w:.3f},{n:.3f},{e:.3f}]...")

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    last_err: Exception | None = None
    data = None
    for url in OVERPASS_URLS:
        for attempt in range(3):
            try:
                resp = requests.post(url, data={"data": query}, headers=headers, timeout=180)
                if resp.status_code in (429, 504):
                    print(f"    {url} -> {resp.status_code}, backing off {2 ** attempt}s")
                    time.sleep(2 ** attempt)
                    continue
                resp.raise_for_status()
                data = resp.json()
                break
            except Exception as ex:
                last_err = ex
                print(f"    {url} attempt {attempt + 1} failed: {ex}")
                time.sleep(2 ** attempt)
        if data is not None:
            break
    if data is None:
        raise RuntimeError(f"all Overpass mirrors failed for {name}: {last_err}")

    segments: list[list[tuple[float, float]]] = []
    for el in data.get("elements", []):
        if el.get("type") != "way":
            continue
        geom = el.get("geometry") or []
        # Convert to a polyline (lon, lat order matches GeoJSON).
        line = [(pt["lon"], pt["lat"]) for pt in geom if "lon" in pt and "lat" in pt]
        if len(line) >= 2:
            # Split a polyline into 2-point segments so nearest-segment search
            # is straightforward.
            for i in range(len(line) - 1):
                segments.append([line[i], line[i + 1]])

    cache_path.write_text(json.dumps({"segments": segments}))
    print(f"  cached {len(segments)} road segments for {name}")
    return segments


def fetch_all_anchor_roads() -> dict[str, list[list[tuple[float, float]]]]:
    """Fetch / load road segments for every region anchor."""
    out: dict[str, list[list[tuple[float, float]]]] = {}
    for region_id, anchors in REGION_ANCHORS.items():
        for (name, lat, lon) in anchors:
            span = REMOTE_BBOX_DEG if region_id == "REG-RW" else DEFAULT_BBOX_DEG
            try:
                segs = fetch_roads_for_anchor(name, lat, lon, span)
            except Exception as ex:
                print(f"  ERROR fetching {name}: {ex}")
                segs = []
            out[f"{region_id}|{name}"] = segs
            # Brief pause so we don't hammer Overpass.
            time.sleep(0.5)
    total = sum(len(v) for v in out.values())
    print(f"\n[roads] total cached segments across all anchors: {total}")
    return out


# ---------------------------------------------------------------------------
# Nearest-segment lookup
# ---------------------------------------------------------------------------


def project_point_to_segment(
    px: float, py: float,
    ax: float, ay: float,
    bx: float, by: float,
) -> tuple[float, float, float]:
    """Project (px, py) onto segment AB. Returns (proj_x, proj_y, dist_sq)."""
    dx = bx - ax
    dy = by - ay
    if dx == 0 and dy == 0:
        return ax, ay, (px - ax) ** 2 + (py - ay) ** 2
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    proj_x = ax + t * dx
    proj_y = ay + t * dy
    return proj_x, proj_y, (px - proj_x) ** 2 + (py - proj_y) ** 2


def assign_anchor_for_row(row: dict, region_id: str) -> str | None:
    """Pick the closest anchor inside the row's region. Returns anchor key
    (`<region_id>|<anchor_name>`) or None if region has no anchors."""
    anchors = REGION_ANCHORS.get(region_id)
    if not anchors:
        return None
    lat = float(row["lat"])
    lon = float(row["lon"])
    best_key = None
    best_d = math.inf
    for (name, alat, alon) in anchors:
        d = (alat - lat) ** 2 + (alon - lon) ** 2
        if d < best_d:
            best_d = d
            best_key = f"{region_id}|{name}"
    return best_key


def snap_to_roads(
    rows: list[dict],
    region_col: str,
    lat_col: str,
    lon_col: str,
    roads: dict[str, list[list[tuple[float, float]]]],
    rng: random.Random,
    offset_chooser,
) -> int:
    """Snap each row's lat/lon onto the nearest road segment in its anchor
    bucket. `offset_chooser(row) -> (min_m, max_m)` returns the perpendicular
    offset range in metres for the row (depends on asset type)."""
    moved = 0
    for r in rows:
        rid = r.get(region_col)
        if not rid:
            continue
        anchor_key = assign_anchor_for_row(r, rid)
        segs = roads.get(anchor_key or "", [])
        if not segs:
            continue

        try:
            lat = float(r[lat_col])
            lon = float(r[lon_col])
        except (KeyError, ValueError):
            continue

        # Find nearest segment.
        best_proj: tuple[float, float] | None = None
        best_d = math.inf
        best_seg: list[tuple[float, float]] | None = None
        for seg in segs:
            (ax, ay), (bx, by) = seg
            px, py, d = project_point_to_segment(lon, lat, ax, ay, bx, by)
            if d < best_d:
                best_d = d
                best_proj = (px, py)
                best_seg = seg
        if not best_proj or not best_seg:
            continue

        # Add small offset perpendicular to the chosen segment, scaled by
        # asset-type rule, so the points don't all stack on the exact line.
        min_m, max_m = offset_chooser(r)
        offset_m = rng.uniform(min_m, max_m) * rng.choice((-1.0, 1.0))
        (ax, ay), (bx, by) = best_seg
        sdx = bx - ax
        sdy = by - ay
        seg_len = math.hypot(sdx, sdy) or 1.0
        # Perpendicular unit vector in degree space (approximate).
        perp_x = -sdy / seg_len
        perp_y = sdx / seg_len
        # Convert metres to degrees at this latitude.
        proj_lat = best_proj[1]
        dx_deg = meters_to_deg_lon(offset_m, proj_lat) * perp_x
        dy_deg = meters_to_deg_lat(offset_m) * perp_y

        new_lon = round(best_proj[0] + dx_deg, 6)
        new_lat = round(best_proj[1] + dy_deg, 6)
        if (new_lat, new_lon) != (lat, lon):
            moved += 1
        r[lat_col] = f"{new_lat:.6f}"
        r[lon_col] = f"{new_lon:.6f}"
    return moved


def offset_for_asset(row: dict) -> tuple[float, float]:
    return ASSET_TYPE_OFFSET_M.get(row.get("asset_type", "pole"), (0.0, 5.0))


def offset_substation(_: dict) -> tuple[float, float]:
    return (20.0, 80.0)


def offset_critical_customer(_: dict) -> tuple[float, float]:
    return (15.0, 60.0)


def offset_depot(_: dict) -> tuple[float, float]:
    return (10.0, 50.0)


def offset_mobile_gen(_: dict) -> tuple[float, float]:
    return (8.0, 35.0)


def offset_vegetation(_: dict) -> tuple[float, float]:
    return (1.0, 8.0)


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    fields = list(rows[0].keys())
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def remap(
    path: Path,
    region_col: str,
    lat_col: str,
    lon_col: str,
    roads: dict[str, list[list[tuple[float, float]]]],
    offset_chooser,
    salt: str,
) -> None:
    if not path.exists():
        print(f"  skip (missing): {path.name}")
        return
    rows = read_csv(path)
    rng = random.Random(f"snap-roads-{salt}")
    moved = snap_to_roads(rows, region_col, lat_col, lon_col, roads, rng, offset_chooser)
    write_csv(path, rows)
    print(f"  road-snapped {moved}/{len(rows)} rows in {path.name}")


def main() -> None:
    print("Step 1/2: fetch OSM road geometries per anchor...")
    roads = fetch_all_anchor_roads()

    print("\nStep 2/2: snap entities to road centerlines...")
    targets = [
        ("substations.csv",                "region_id", "lat", "lon", offset_substation),
        ("assets.csv",                     "region_id", "lat", "lon", offset_for_asset),
        ("critical_customers.csv",         "region_id", "lat", "lon", offset_critical_customer),
        ("depots.csv",                     "region_id", "lat", "lon", offset_depot),
        ("mobile_generation_candidates.csv","region_id", "lat", "lon", offset_mobile_gen),
        ("vegetation_spans.csv",           "region_id", "lat", "lon", offset_vegetation),
    ]
    for fname, rcol, latc, lonc, off in targets:
        remap(DATA_DIR / fname, rcol, latc, lonc, roads, off, salt=fname)


if __name__ == "__main__":
    main()
