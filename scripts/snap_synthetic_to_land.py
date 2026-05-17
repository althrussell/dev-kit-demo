"""Re-anchor synthetic Queensland data to land.

The original generator placed assets with a `spread = 0.12 + length/800` degree
jitter around region anchors. For some regions that pushes assets up to 100+ km
offshore (Whitsundays, Cairns, Bowen, Gladstone, Gold Coast).

This script re-snaps every lat/lon-bearing entity to its region's nearest town
anchor with a small jitter, and applies an inland (negative-lon) bias for
coastal anchors so the demo stops rendering pins in the sea.

It is idempotent: re-running clamps things again to the same anchors.
"""

from __future__ import annotations

import csv
import math
import random
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "synthetic"

REGION_ANCHORS: dict[str, list[tuple[str, float, float]]] = {
    "REG-SEQ": [
        ("Brisbane", -27.4698, 152.9851),
        ("Ipswich", -27.6171, 152.7613),
        ("Logan", -27.6390, 153.0790),
        ("Caboolture", -27.0840, 152.9510),
        ("Sunshine Coast (Nambour)", -26.6260, 152.9590),
        ("Gold Coast (Nerang)", -28.0000, 153.3300),
    ],
    "REG-MKY": [
        ("Mackay", -21.1430, 149.1500),
        ("Proserpine", -20.4000, 148.5800),
        ("Bowen", -20.0167, 148.2200),
        ("Sarina", -21.4170, 149.2150),
        ("Moranbah", -22.0006, 148.0470),
    ],
    "REG-TSV": [
        ("Townsville", -19.2589, 146.7800),
        ("Ingham", -18.6500, 146.1660),
        ("Innisfail", -17.5236, 145.9994),
        ("Cairns", -16.9203, 145.7300),
        ("Mareeba", -16.9920, 145.4220),
        ("Atherton", -17.2670, 145.4760),
    ],
    "REG-CQI": [
        ("Rockhampton", -23.3781, 150.4800),
        ("Gladstone", -23.8420, 151.2200),
        ("Emerald", -23.5230, 148.1610),
        ("Biloela", -24.4060, 150.5160),
        ("Yeppoon", -23.1280, 150.7200),
    ],
    "REG-RW": [
        ("Longreach", -23.4400, 144.2500),
        ("Charleville", -26.4080, 146.2420),
        ("Mount Isa", -20.7256, 139.4927),
        ("Roma", -26.5750, 148.7870),
        ("Winton", -22.3895, 143.0359),
        ("Cloncurry", -20.7090, 140.5050),
    ],
}

COASTAL_ANCHOR_KEYWORDS = {
    "Bowen", "Mackay", "Proserpine", "Townsville", "Cairns", "Innisfail",
    "Ingham", "Gladstone", "Yeppoon", "Gold Coast", "Sunshine Coast",
    "Caboolture", "Rockhampton",
}


def euclid_sq(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return (lat1 - lat2) ** 2 + (lon1 - lon2) ** 2


def pick_anchor(region_id: str, current_lat: float, current_lon: float):
    anchors = REGION_ANCHORS.get(region_id)
    if not anchors:
        return None
    return min(anchors, key=lambda a: euclid_sq(current_lat, current_lon, a[1], a[2]))


def is_coastal(name: str) -> bool:
    return any(kw in name for kw in COASTAL_ANCHOR_KEYWORDS)


def jitter(rng: random.Random, base: float, spread: float, bias: float = 0.0) -> float:
    return round(base + rng.uniform(-spread, spread) + bias, 6)


def snap_row(rng: random.Random, region_id: str, lat: float, lon: float,
             spread: float, coastal_inland_bias_lon: float = 0.0) -> tuple[float, float]:
    """Snap (lat, lon) to the closest anchor of region_id with given jitter spread.

    If the chosen anchor is coastal, apply an additional negative-lon (inland)
    bias to keep the placement on land.
    """
    anchor = pick_anchor(region_id, lat, lon)
    if not anchor:
        return lat, lon
    name, alat, alon = anchor
    lon_bias = 0.0
    if is_coastal(name):
        # Pull westward (inland for east-coast Queensland) by 0.5-1.5x spread.
        lon_bias = -abs(rng.uniform(0.3, 1.2)) * spread + coastal_inland_bias_lon
    new_lat = jitter(rng, alat, spread)
    new_lon = jitter(rng, alon, spread, bias=lon_bias)
    return new_lat, new_lon


def remap_file(path: Path, region_col: str, lat_col: str, lon_col: str,
               spread: float, seed_salt: str) -> None:
    if not path.exists():
        print(f"  skip (missing): {path.name}")
        return
    rng = random.Random(f"snap-{seed_salt}")
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
        fieldnames = list(rows[0].keys()) if rows else []
    moved = 0
    for r in rows:
        try:
            lat = float(r[lat_col])
            lon = float(r[lon_col])
        except (KeyError, ValueError):
            continue
        rid = r.get(region_col)
        new_lat, new_lon = snap_row(rng, rid, lat, lon, spread)
        if (new_lat, new_lon) != (lat, lon):
            moved += 1
        r[lat_col] = f"{new_lat:.6f}"
        r[lon_col] = f"{new_lon:.6f}"
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)
    print(f"  snapped {moved}/{len(rows)} rows in {path.name}")


def main() -> None:
    print("Snapping synthetic Queensland data to land anchors...")
    targets = [
        ("substations.csv",                "region_id", "lat", "lon", 0.05),
        ("assets.csv",                     "region_id", "lat", "lon", 0.04),
        ("critical_customers.csv",         "region_id", "lat", "lon", 0.06),
        ("depots.csv",                     "region_id", "lat", "lon", 0.03),
        ("mobile_generation_candidates.csv","region_id", "lat", "lon", 0.05),
        ("vegetation_spans.csv",           "region_id", "lat", "lon", 0.05),
        ("hazard_exposure_zones.csv",      "region_id", "lat", "lon", 0.18),
    ]
    for fname, rcol, latc, lonc, spread in targets:
        remap_file(DATA_DIR / fname, rcol, latc, lonc, spread, seed_salt=fname)


if __name__ == "__main__":
    main()
