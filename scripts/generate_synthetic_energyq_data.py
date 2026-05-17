"""
GridLens Queensland — synthetic data generator.

Generates a referentially consistent, scenario-driven synthetic dataset for an
Energy Queensland-style electricity distribution network. Output is written as
CSV files (Parquet optional) under data/synthetic/.

Usage:
    python scripts/generate_synthetic_energyq_data.py \\
        --assets 40000 \\
        --feeders 320 \\
        --documents 1200 \\
        --seed 42 \\
        --output data/synthetic

The generator is deterministic for a given seed.

Design principles:
- Each region has a distinct risk profile (storm, cyclone, vegetation, etc.).
- Assets inherit region/feeder context and accumulate risk drivers.
- Risk scores are computed from drivers, not random.
- Outages, defects, work orders, vegetation spans and critical customers are
  positively correlated with their risk drivers.
- A small number of deliberate "demo clusters" of high risk assets are seeded
  per region so the UI always has an obvious risky area to investigate.

This script does NOT need network access. It does not require databricks-sdk.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
from pathlib import Path
from typing import Iterable

# ---------------------------------------------------------------------------
# Region definitions
# ---------------------------------------------------------------------------

REGIONS = [
    {
        "region_id": "REG-SEQ",
        "region_name": "SEQ Metro Storm Belt",
        "region_type": "metro",
        "state": "QLD",
        "population_density_band": "very_high",
        "hazard_profile": "storm,flood,heat",
        "centre_lat": -27.4698,
        "centre_lon": 153.0251,
        "spread_lat": 1.1,
        "spread_lon": 1.0,
        "customer_density_factor": 1.8,
        "underground_pct_mean": 35.0,
        "storm_factor": 1.5,
        "cyclone_factor": 0.2,
        "vegetation_factor": 0.6,
        "flood_factor": 0.8,
        "bushfire_factor": 0.3,
        "corrosion_factor": 0.2,
        "access_factor": 0.3,
        "criticality_factor": 1.4,
        "critical_customer_density": 1.6,
        "feeder_length_mean": 14.0,
    },
    {
        "region_id": "REG-MKY",
        "region_name": "Mackay / Whitsunday Corridor",
        "region_type": "coastal_tropical",
        "state": "QLD",
        "population_density_band": "medium",
        "hazard_profile": "cyclone,storm,vegetation,corrosion",
        "centre_lat": -21.1430,
        "centre_lon": 149.1860,
        "spread_lat": 0.9,
        "spread_lon": 1.1,
        "customer_density_factor": 0.7,
        "underground_pct_mean": 14.0,
        "storm_factor": 1.1,
        "cyclone_factor": 1.6,
        "vegetation_factor": 1.4,
        "flood_factor": 1.0,
        "bushfire_factor": 0.5,
        "corrosion_factor": 1.4,
        "access_factor": 0.7,
        "criticality_factor": 0.9,
        "critical_customer_density": 0.7,
        "feeder_length_mean": 22.0,
    },
    {
        "region_id": "REG-TSV",
        "region_name": "Townsville / Cairns Coastal Corridor",
        "region_type": "coastal_tropical",
        "state": "QLD",
        "population_density_band": "medium",
        "hazard_profile": "cyclone,flood,vegetation,heat",
        "centre_lat": -17.7500,
        "centre_lon": 145.7600,
        "spread_lat": 2.4,
        "spread_lon": 1.2,
        "customer_density_factor": 0.8,
        "underground_pct_mean": 18.0,
        "storm_factor": 1.0,
        "cyclone_factor": 1.7,
        "vegetation_factor": 1.5,
        "flood_factor": 1.4,
        "bushfire_factor": 0.4,
        "corrosion_factor": 1.5,
        "access_factor": 0.8,
        "criticality_factor": 1.0,
        "critical_customer_density": 0.8,
        "feeder_length_mean": 25.0,
    },
    {
        "region_id": "REG-CQI",
        "region_name": "Central Queensland Industrial Belt",
        "region_type": "industrial_regional",
        "state": "QLD",
        "population_density_band": "medium",
        "hazard_profile": "storm,heat,industrial_load",
        "centre_lat": -23.3781,
        "centre_lon": 150.5100,
        "spread_lat": 1.6,
        "spread_lon": 2.2,
        "customer_density_factor": 0.6,
        "underground_pct_mean": 20.0,
        "storm_factor": 0.9,
        "cyclone_factor": 0.5,
        "vegetation_factor": 0.8,
        "flood_factor": 0.6,
        "bushfire_factor": 0.6,
        "corrosion_factor": 0.5,
        "access_factor": 0.6,
        "criticality_factor": 1.6,
        "critical_customer_density": 1.0,
        "feeder_length_mean": 28.0,
    },
    {
        "region_id": "REG-RW",
        "region_name": "Remote Western Queensland",
        "region_type": "remote_radial",
        "state": "QLD",
        "population_density_band": "very_low",
        "hazard_profile": "heat,storm,bushfire,access",
        "centre_lat": -23.7000,
        "centre_lon": 144.5000,
        "spread_lat": 3.5,
        "spread_lon": 4.0,
        "customer_density_factor": 0.2,
        "underground_pct_mean": 6.0,
        "storm_factor": 0.8,
        "cyclone_factor": 0.2,
        "vegetation_factor": 0.7,
        "flood_factor": 0.5,
        "bushfire_factor": 1.4,
        "corrosion_factor": 0.3,
        "access_factor": 1.7,
        "criticality_factor": 0.7,
        "critical_customer_density": 0.4,
        "feeder_length_mean": 65.0,
    },
]

REGION_INDEX = {r["region_id"]: r for r in REGIONS}

# Sub-anchors per region — give the map distinct named clusters.
REGION_ANCHORS = {
    "REG-SEQ": [
        ("Brisbane", -27.4698, 153.0251),
        ("Ipswich", -27.6171, 152.7613),
        ("Logan", -27.6390, 153.1090),
        ("Redcliffe", -27.2300, 153.1100),
        ("Sunshine Coast", -26.6500, 153.0660),
        ("Gold Coast", -28.0167, 153.4000),
    ],
    "REG-MKY": [
        ("Mackay", -21.1430, 149.1860),
        ("Proserpine", -20.4000, 148.5800),
        ("Airlie Beach", -20.2660, 148.7180),
        ("Bowen", -20.0167, 148.2333),
    ],
    "REG-TSV": [
        ("Townsville", -19.2589, 146.8169),
        ("Ingham", -18.6500, 146.1660),
        ("Innisfail", -17.5236, 146.0294),
        ("Cairns", -16.9203, 145.7710),
        ("Port Douglas", -16.4830, 145.4620),
    ],
    "REG-CQI": [
        ("Rockhampton", -23.3781, 150.5100),
        ("Gladstone", -23.8420, 151.2570),
        ("Emerald", -23.5230, 148.1610),
    ],
    "REG-RW": [
        ("Longreach", -23.4400, 144.2500),
        ("Charleville", -26.4080, 146.2420),
        ("Mount Isa", -20.7256, 139.4927),
        ("Roma", -26.5750, 148.7870),
        ("Winton", -22.3895, 143.0359),
    ],
}

ASSET_TYPES = [
    ("pole", 0.62),
    ("transformer", 0.14),
    ("switch", 0.06),
    ("recloser", 0.04),
    ("sectionaliser", 0.04),
    ("conductor_span", 0.07),
    ("ring_main_unit", 0.03),
]

MANUFACTURERS = {
    "pole": ["Hardwood Co.", "ConcreteWorks", "CompositePoleCo", "SteelPoleAU"],
    "transformer": ["ABB", "Siemens", "Wilson Transformer", "Schneider"],
    "switch": ["NOJA Power", "ABB", "Schneider"],
    "recloser": ["NOJA Power", "G&W Electric", "S&C"],
    "sectionaliser": ["NOJA Power", "S&C"],
    "conductor_span": ["Nexans", "Olex", "Prysmian"],
    "ring_main_unit": ["ABB", "Schneider", "Siemens"],
}

MATERIALS = {
    "pole": ["hardwood", "concrete", "composite", "steel"],
    "transformer": ["oil_filled", "dry_type"],
    "switch": ["sf6", "vacuum", "air"],
    "recloser": ["sf6", "vacuum"],
    "sectionaliser": ["vacuum", "air"],
    "conductor_span": ["aluminium", "acsr", "covered_conductor"],
    "ring_main_unit": ["sf6", "air"],
}

VOLTAGE_BY_TYPE = {
    "pole": [11.0, 22.0, 33.0],
    "transformer": [0.4, 11.0, 22.0, 33.0, 66.0],
    "switch": [11.0, 22.0, 33.0],
    "recloser": [11.0, 22.0],
    "sectionaliser": [11.0, 22.0],
    "conductor_span": [11.0, 22.0, 33.0, 66.0],
    "ring_main_unit": [11.0, 22.0],
}

DEFECT_TYPES = [
    "crossarm_corrosion",
    "insulator_damage",
    "vegetation_clearance",
    "leaning_pole",
    "termite_damage",
    "conductor_sag",
    "oil_leak",
    "access_blocked",
    "flood_damage",
    "lightning_damage",
]

INSPECTION_TYPES = [
    "routine",
    "storm_follow_up",
    "vegetation",
    "thermal",
    "drone",
    "pole_test",
]

OUTAGE_CAUSES = [
    "storm",
    "vegetation",
    "equipment_failure",
    "vehicle_impact",
    "planned",
    "unknown",
    "flood",
    "lightning",
]

WORK_TYPES = [
    "inspection",
    "vegetation_treatment",
    "repair",
    "replacement",
    "storm_response",
    "planned_maintenance",
    "access_remediation",
]

WORK_STATUS = ["draft", "approved", "scheduled", "in_progress", "completed", "cancelled"]

CRITICAL_SITE_TYPES = [
    ("hospital", 1.0),
    ("aged_care", 0.9),
    ("water_pumping", 0.6),
    ("telecom", 0.7),
    ("emergency_services", 0.95),
    ("airport", 0.85),
    ("industrial", 0.7),
    ("school", 0.5),
]

DOCUMENT_TYPES = [
    "inspection_report",
    "engineering_drawing",
    "maintenance_standard",
    "vegetation_policy",
    "storm_response_plan",
    "photo_pack",
    "work_order_pdf",
    "risk_assessment",
]

SENSITIVITY = ["internal", "restricted", "confidential"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def weighted_choice(rng: random.Random, choices: list[tuple[str, float]]) -> str:
    total = sum(w for _, w in choices)
    r = rng.uniform(0.0, total)
    upto = 0.0
    for name, w in choices:
        upto += w
        if r <= upto:
            return name
    return choices[-1][0]


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def jitter(rng: random.Random, base: float, spread: float) -> float:
    return base + rng.uniform(-spread, spread)


def risk_band(score: float) -> str:
    if score >= 76:
        return "critical"
    if score >= 56:
        return "high"
    if score >= 31:
        return "medium"
    return "low"


def health_band(condition: float) -> str:
    if condition >= 76:
        return "good"
    if condition >= 56:
        return "watch"
    if condition >= 31:
        return "poor"
    return "critical"


def to_iso(d: date | datetime) -> str:
    if isinstance(d, datetime):
        return d.isoformat(timespec="seconds")
    return d.isoformat()


# ---------------------------------------------------------------------------
# Output container
# ---------------------------------------------------------------------------


@dataclass
class Dataset:
    regions: list[dict] = field(default_factory=list)
    depots: list[dict] = field(default_factory=list)
    substations: list[dict] = field(default_factory=list)
    feeders: list[dict] = field(default_factory=list)
    assets: list[dict] = field(default_factory=list)
    asset_health_scores: list[dict] = field(default_factory=list)
    inspection_events: list[dict] = field(default_factory=list)
    defects: list[dict] = field(default_factory=list)
    vegetation_spans: list[dict] = field(default_factory=list)
    outage_events: list[dict] = field(default_factory=list)
    work_orders: list[dict] = field(default_factory=list)
    critical_customers: list[dict] = field(default_factory=list)
    hazard_exposure_zones: list[dict] = field(default_factory=list)
    asset_documents: list[dict] = field(default_factory=list)
    mobile_generation_candidates: list[dict] = field(default_factory=list)
    scenario_runs: list[dict] = field(default_factory=list)

    def write_csv(self, output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        for name, rows in self.as_dict().items():
            if not rows:
                continue
            path = output_dir / f"{name}.csv"
            fieldnames = list(rows[0].keys())
            with path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for row in rows:
                    writer.writerow(row)
            print(f"  wrote {len(rows):>7} rows  ->  {path}")

    def as_dict(self) -> dict[str, list[dict]]:
        return {
            "regions": self.regions,
            "depots": self.depots,
            "substations": self.substations,
            "feeders": self.feeders,
            "assets": self.assets,
            "asset_health_scores": self.asset_health_scores,
            "inspection_events": self.inspection_events,
            "defects": self.defects,
            "vegetation_spans": self.vegetation_spans,
            "outage_events": self.outage_events,
            "work_orders": self.work_orders,
            "critical_customers": self.critical_customers,
            "hazard_exposure_zones": self.hazard_exposure_zones,
            "asset_documents": self.asset_documents,
            "mobile_generation_candidates": self.mobile_generation_candidates,
            "scenario_runs": self.scenario_runs,
        }


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------


def gen_regions(ds: Dataset) -> None:
    for r in REGIONS:
        ds.regions.append({
            "region_id": r["region_id"],
            "region_name": r["region_name"],
            "region_type": r["region_type"],
            "state": r["state"],
            "population_density_band": r["population_density_band"],
            "hazard_profile": r["hazard_profile"],
            "centre_lat": round(r["centre_lat"], 6),
            "centre_lon": round(r["centre_lon"], 6),
        })


def gen_depots(ds: Dataset, rng: random.Random, target_depots: int) -> None:
    # Distribute proportional to anchors per region, with a floor of 2 per region.
    per_region = []
    total_anchors = sum(len(REGION_ANCHORS[r["region_id"]]) for r in REGIONS)
    for r in REGIONS:
        anchors = REGION_ANCHORS[r["region_id"]]
        share = max(2, round(target_depots * len(anchors) / total_anchors))
        per_region.append((r, share))

    counter = 1
    for r, count in per_region:
        anchors = REGION_ANCHORS[r["region_id"]]
        for i in range(count):
            anchor_name, alat, alon = anchors[i % len(anchors)]
            depot_id = f"DEP-{r['region_id'][-3:]}-{counter:04d}"
            counter += 1
            crew_count = rng.randint(8, 40)
            specialist_crews = rng.randint(1, 6)
            mobile_gen_units = rng.randint(0, 4)
            ds.depots.append({
                "depot_id": depot_id,
                "region_id": r["region_id"],
                "depot_name": f"{anchor_name} Depot {i + 1}",
                "lat": round(jitter(rng, alat, 0.05), 6),
                "lon": round(jitter(rng, alon, 0.05), 6),
                "crew_count": crew_count,
                "specialist_crews": specialist_crews,
                "mobile_generation_units": mobile_gen_units,
            })


def gen_substations(ds: Dataset, rng: random.Random, target_substations: int) -> None:
    total_anchors = sum(len(REGION_ANCHORS[r["region_id"]]) for r in REGIONS)
    counter = 1
    for r in REGIONS:
        anchors = REGION_ANCHORS[r["region_id"]]
        # Substations roughly proportional to customer density.
        share = max(2, round(target_substations * (len(anchors) / total_anchors) * (0.6 + r["customer_density_factor"]) / 2))
        for i in range(share):
            anchor_name, alat, alon = rng.choice(anchors)
            ss_id = f"SS-{r['region_id'][-3:]}-{counter:04d}"
            counter += 1
            voltage = rng.choice(["33/11", "66/11", "66/22", "110/33", "132/33"])
            commissioned = rng.randint(1965, 2024)
            criticality = clamp(rng.gauss(55 * r["criticality_factor"], 12), 5, 99)
            flood = clamp(rng.gauss(35 * r["flood_factor"], 15), 0, 99)
            cyclone = clamp(rng.gauss(35 * r["cyclone_factor"], 15), 0, 99)
            ds.substations.append({
                "substation_id": ss_id,
                "region_id": r["region_id"],
                "substation_name": f"{anchor_name} ZS{i + 1}",
                "lat": round(jitter(rng, alat, 0.08), 6),
                "lon": round(jitter(rng, alon, 0.08), 6),
                "voltage_level": voltage,
                "commissioned_year": commissioned,
                "criticality_score": round(criticality, 1),
                "flood_exposure_score": round(flood, 1),
                "cyclone_exposure_score": round(cyclone, 1),
            })


def gen_feeders(ds: Dataset, rng: random.Random, target_feeders: int) -> None:
    # Allocate feeders to substations proportional to region density.
    substations_by_region: dict[str, list[dict]] = {}
    for ss in ds.substations:
        substations_by_region.setdefault(ss["region_id"], []).append(ss)

    total_weight = sum(r["customer_density_factor"] + 0.5 for r in REGIONS)
    counter = 1
    for r in REGIONS:
        share = max(20, round(target_feeders * (r["customer_density_factor"] + 0.5) / total_weight))
        region_substations = substations_by_region.get(r["region_id"], [])
        if not region_substations:
            continue
        for i in range(share):
            ss = rng.choice(region_substations)
            feeder_id = f"FDR-{r['region_id'][-3:]}-{counter:04d}"
            counter += 1
            voltage_kv = rng.choice([11.0, 22.0, 33.0])
            length_km = max(2.0, rng.gauss(r["feeder_length_mean"], r["feeder_length_mean"] * 0.4))
            customer_count = max(20, int(rng.gauss(1200 * r["customer_density_factor"], 600 * r["customer_density_factor"])))
            critical_customers = max(0, int(customer_count * 0.02 * r["critical_customer_density"]))
            underground_pct = clamp(rng.gauss(r["underground_pct_mean"], 12), 0, 95)
            overhead_pct = round(100.0 - underground_pct, 1)
            radiality = clamp(rng.gauss(40 + 30 * (r["access_factor"] - 0.3), 12), 5, 99)
            asset_density = clamp(rng.gauss(50, 15), 5, 99)
            capacity_band = rng.choice(["low", "medium", "high"])
            export_capacity = rng.choice(["constrained", "moderate", "headroom"])
            ds.feeders.append({
                "feeder_id": feeder_id,
                "substation_id": ss["substation_id"],
                "region_id": r["region_id"],
                "feeder_name": f"{ss['substation_name']}-F{i + 1}",
                "voltage_kv": voltage_kv,
                "feeder_length_km": round(length_km, 2),
                "customer_count": customer_count,
                "critical_customer_count": critical_customers,
                "overhead_pct": overhead_pct,
                "underground_pct": round(underground_pct, 1),
                "radiality_score": round(radiality, 1),
                "asset_density_score": round(asset_density, 1),
                "network_capacity_band": capacity_band,
                "export_capacity_band": export_capacity,
            })


def gen_assets(ds: Dataset, rng: random.Random, target_assets: int) -> None:
    """Generate assets along feeders, with risk drivers correlated to region & feeder."""
    by_region_feeders: dict[str, list[dict]] = {}
    for f in ds.feeders:
        by_region_feeders.setdefault(f["region_id"], []).append(f)

    # Pre-pick "demo cluster" feeders per region so each region has at least one
    # very high-risk cluster the demo can land on.
    demo_clusters: dict[str, list[dict]] = {}
    for r in REGIONS:
        feeders = by_region_feeders.get(r["region_id"], [])
        if not feeders:
            continue
        # Pick the 3-5 longest feeders as demo clusters (scaled to region size).
        feeders_sorted = sorted(feeders, key=lambda f: -f["feeder_length_km"])
        cluster_n = max(3, min(6, len(feeders_sorted) // 8))
        demo_clusters[r["region_id"]] = feeders_sorted[:cluster_n]

    # Allocate asset count proportional to feeder length * customer count.
    total_weight = 0.0
    feeder_weights: dict[str, float] = {}
    for f in ds.feeders:
        w = (f["feeder_length_km"] ** 0.7) * (f["customer_count"] ** 0.3)
        feeder_weights[f["feeder_id"]] = w
        total_weight += w

    counter = 1
    for f in ds.feeders:
        region = REGION_INDEX[f["region_id"]]
        share = max(20, int(target_assets * feeder_weights[f["feeder_id"]] / total_weight))
        anchors = REGION_ANCHORS[f["region_id"]]
        anchor_name, alat, alon = rng.choice(anchors)
        is_demo = f["feeder_id"] in {df["feeder_id"] for df in demo_clusters.get(f["region_id"], [])}

        for _ in range(share):
            asset_type = weighted_choice(rng, ASSET_TYPES)
            voltage = rng.choice(VOLTAGE_BY_TYPE[asset_type])
            install_year = rng.randint(1962, 2024)
            material = rng.choice(MATERIALS[asset_type])
            manufacturer = rng.choice(MANUFACTURERS[asset_type])
            spread = 0.12 + (f["feeder_length_km"] / 800.0)
            lat = round(jitter(rng, alat, spread), 6)
            lon = round(jitter(rng, alon, spread), 6)

            # Drivers (all 0-100).
            age = clamp((2025 - install_year) * 1.4, 0, 100)
            access = clamp(rng.gauss(40 * region["access_factor"], 14), 0, 100)
            corrosion = clamp(rng.gauss(35 * region["corrosion_factor"], 14), 0, 100)
            flood = clamp(rng.gauss(25 * region["flood_factor"], 14), 0, 100)
            cyclone = clamp(rng.gauss(25 * region["cyclone_factor"], 14), 0, 100)
            bushfire = clamp(rng.gauss(25 * region["bushfire_factor"], 14), 0, 100)
            criticality = clamp(rng.gauss(45 * region["criticality_factor"], 14), 0, 100)

            if is_demo:
                # Deliberate demo cluster — push drivers into high/critical band.
                # We boost a basket of drivers so even regions with low natural
                # exposure (e.g. SEQ metro) still produce a believable risky cluster.
                age = clamp(age + 30, 0, 100)
                access = clamp(access + 22, 0, 100)
                corrosion = clamp(corrosion + 25, 0, 100)
                criticality = clamp(criticality + 30, 0, 100)
                flood = clamp(flood + 18, 0, 100)
                if region["cyclone_factor"] > 1.0:
                    cyclone = clamp(cyclone + 35, 0, 100)
                if region["vegetation_factor"] > 1.0:
                    corrosion = clamp(corrosion + 10, 0, 100)
                if region["bushfire_factor"] > 1.0:
                    bushfire = clamp(bushfire + 35, 0, 100)
                if region["flood_factor"] > 1.0:
                    flood = clamp(flood + 22, 0, 100)
                if region["storm_factor"] > 1.0:
                    # Storm-prone regions: inflate cyclone score (proxy for storm
                    # damage exposure) + criticality so high-density feeders show
                    # up as high risk during storm season.
                    cyclone = clamp(cyclone + 25, 0, 100)
                    criticality = clamp(criticality + 10, 0, 100)

            status = "in_service"
            if rng.random() < 0.02:
                status = "decommissioned"
            elif rng.random() < 0.05:
                status = "planned_replacement"
            elif rng.random() < 0.06:
                status = "under_monitoring"

            asset_id = f"AST-{f['region_id'][-3:]}-{asset_type[:3].upper()}-{counter:06d}"
            counter += 1
            ds.assets.append({
                "asset_id": asset_id,
                "feeder_id": f["feeder_id"],
                "substation_id": f["substation_id"],
                "region_id": f["region_id"],
                "asset_type": asset_type,
                "asset_name": f"{asset_type.upper()} {anchor_name} {counter:06d}",
                "lat": lat,
                "lon": lon,
                "install_year": install_year,
                "manufacturer": manufacturer,
                "material": material,
                "voltage_kv": voltage,
                "status": status,
                "criticality_score": round(criticality, 1),
                "access_difficulty_score": round(access, 1),
                "coastal_corrosion_score": round(corrosion, 1),
                "flood_exposure_score": round(flood, 1),
                "cyclone_exposure_score": round(cyclone, 1),
                "bushfire_exposure_score": round(bushfire, 1),
            })


def compute_asset_risk(asset: dict, region: dict, rng: random.Random) -> tuple[float, float, list[str]]:
    age = clamp((2025 - asset["install_year"]) * 1.4, 0, 100)
    drivers = []
    # Condition: older + more corrosion + more access difficulty -> lower condition.
    condition = clamp(
        100
        - 0.45 * age
        - 0.25 * asset["coastal_corrosion_score"]
        - 0.08 * asset["access_difficulty_score"]
        + rng.gauss(0, 6),
        2,
        99,
    )
    # Risk: blend of multiple drivers. Weights chosen so that strong individual
    # drivers can independently push an asset into high/critical, while assets
    # with consistently low drivers stay in low/medium.
    risk = clamp(
        0.22 * age
        + 0.18 * (100 - condition)
        + 0.16 * asset["criticality_score"]
        + 0.10 * asset["coastal_corrosion_score"]
        + 0.10 * asset["flood_exposure_score"]
        + 0.10 * asset["cyclone_exposure_score"]
        + 0.08 * asset["bushfire_exposure_score"]
        + 0.08 * asset["access_difficulty_score"]
        + rng.gauss(0, 4),
        1,
        99,
    )

    if age > 55:
        drivers.append("age")
    if condition < 45:
        drivers.append("condition")
    if asset["criticality_score"] > 65:
        drivers.append("criticality")
    if asset["coastal_corrosion_score"] > 60:
        drivers.append("coastal_corrosion")
    if asset["flood_exposure_score"] > 55:
        drivers.append("flood_exposure")
    if asset["cyclone_exposure_score"] > 55:
        drivers.append("cyclone_exposure")
    if asset["bushfire_exposure_score"] > 55:
        drivers.append("bushfire_exposure")
    if asset["access_difficulty_score"] > 60:
        drivers.append("access_difficulty")

    return condition, risk, drivers


def gen_asset_health(ds: Dataset, rng: random.Random, now: date) -> None:
    for a in ds.assets:
        region = REGION_INDEX[a["region_id"]]
        condition, risk, drivers = compute_asset_risk(a, region, rng)
        rb = risk_band(risk)
        if rb == "critical":
            prob_12 = round(rng.uniform(0.15, 0.35), 4)
        elif rb == "high":
            prob_12 = round(rng.uniform(0.06, 0.15), 4)
        elif rb == "medium":
            prob_12 = round(rng.uniform(0.02, 0.06), 4)
        else:
            prob_12 = round(rng.uniform(0.001, 0.02), 4)
        prob_36 = round(min(1.0, prob_12 * rng.uniform(2.0, 3.2)), 4)
        ds.asset_health_scores.append({
            "asset_id": a["asset_id"],
            "condition_score": round(condition, 1),
            "failure_probability_12m": prob_12,
            "failure_probability_36m": prob_36,
            "health_band": health_band(condition),
            "risk_score": round(risk, 1),
            "risk_band": rb,
            "risk_drivers": "|".join(drivers) if drivers else "",
            "last_scored_at": to_iso(now - timedelta(days=rng.randint(0, 14))),
        })


def gen_inspections_and_defects(
    ds: Dataset,
    rng: random.Random,
    now: date,
    target_inspections: int,
    target_defects: int,
) -> None:
    """Inspections cluster on higher-risk assets."""
    # Score assets to pick a biased sample for inspection.
    health_by_asset = {h["asset_id"]: h for h in ds.asset_health_scores}

    asset_weights: list[tuple[dict, float]] = []
    for a in ds.assets:
        h = health_by_asset.get(a["asset_id"])
        risk = h["risk_score"] if h else 30.0
        weight = 1.0 + (risk / 25.0) ** 1.6
        asset_weights.append((a, weight))
    total_w = sum(w for _, w in asset_weights)

    # Build a fast inverse-CDF sampler.
    cum: list[float] = []
    running = 0.0
    for _, w in asset_weights:
        running += w / total_w
        cum.append(running)

    def sample_asset() -> dict:
        r = rng.random()
        # Binary search.
        lo, hi = 0, len(cum) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if cum[mid] < r:
                lo = mid + 1
            else:
                hi = mid
        return asset_weights[lo][0]

    inspection_counter = 1
    defects_made = 0
    for _ in range(target_inspections):
        a = sample_asset()
        h = health_by_asset[a["asset_id"]]
        inspection_id = f"INS-{inspection_counter:07d}"
        inspection_counter += 1
        insp_date = now - timedelta(days=rng.randint(2, 540))
        # Older / damaged assets attract storm follow ups, vegetation, drone.
        if h["risk_band"] in ("high", "critical"):
            insp_type = weighted_choice(
                rng,
                [
                    ("storm_follow_up", 0.30),
                    ("vegetation", 0.20),
                    ("drone", 0.18),
                    ("pole_test", 0.14),
                    ("thermal", 0.10),
                    ("routine", 0.08),
                ],
            )
            defect_likelihood = 0.85
            defect_count_mean = 2.0
        else:
            insp_type = weighted_choice(
                rng,
                [
                    ("routine", 0.55),
                    ("drone", 0.15),
                    ("thermal", 0.10),
                    ("vegetation", 0.10),
                    ("storm_follow_up", 0.05),
                    ("pole_test", 0.05),
                ],
            )
            defect_likelihood = 0.30
            defect_count_mean = 0.7

        defect_count = 0
        recommended_action = "no_action"
        if rng.random() < defect_likelihood:
            defect_count = max(1, int(rng.gauss(defect_count_mean, 0.9)))
            recommended_action = rng.choice(["schedule_repair", "schedule_inspection", "monitor", "urgent_repair"])

        photo_count = rng.randint(0, 8)

        ds.inspection_events.append({
            "inspection_id": inspection_id,
            "asset_id": a["asset_id"],
            "inspection_date": insp_date.isoformat(),
            "inspection_type": insp_type,
            "inspector_team": rng.choice(["Crew A", "Crew B", "Crew C", "Drone Team 1", "Drone Team 2"]),
            "condition_observed": rng.choice(["good", "fair", "poor", "very_poor"]) if defect_count else rng.choice(["good", "fair"]),
            "defect_count": defect_count,
            "photo_count": photo_count,
            "document_id": "",  # filled later when generating documents
            "recommended_action": recommended_action,
        })

        # Spawn defects.
        for _ in range(defect_count):
            if defects_made >= target_defects:
                break
            defect_id = f"DEF-{defects_made + 1:08d}"
            defects_made += 1
            severity = weighted_choice(rng, [
                ("low", 0.40), ("medium", 0.35), ("high", 0.18), ("critical", 0.07),
            ]) if h["risk_band"] != "critical" else weighted_choice(rng, [
                ("low", 0.10), ("medium", 0.25), ("high", 0.40), ("critical", 0.25),
            ])
            target_date = insp_date + timedelta(days=rng.randint(7, 180))
            status = weighted_choice(rng, [
                ("open", 0.45), ("planned", 0.30), ("closed", 0.18), ("deferred", 0.07),
            ])
            safety = clamp(rng.gauss(45 if severity in ("high", "critical") else 25, 12), 1, 99)
            reliability = clamp(rng.gauss(50 if severity in ("high", "critical") else 25, 12), 1, 99)
            ds.defects.append({
                "defect_id": defect_id,
                "inspection_id": inspection_id,
                "asset_id": a["asset_id"],
                "defect_type": rng.choice(DEFECT_TYPES),
                "severity": severity,
                "detected_date": insp_date.isoformat(),
                "target_rectification_date": target_date.isoformat(),
                "status": status,
                "safety_risk_score": round(safety, 1),
                "reliability_risk_score": round(reliability, 1),
            })

    # Pad defects if we under-produced (low risk inspections suppress them).
    while defects_made < target_defects:
        if not ds.inspection_events:
            break
        ins = rng.choice(ds.inspection_events)
        defect_id = f"DEF-{defects_made + 1:08d}"
        defects_made += 1
        det_date = date.fromisoformat(ins["inspection_date"])
        ds.defects.append({
            "defect_id": defect_id,
            "inspection_id": ins["inspection_id"],
            "asset_id": ins["asset_id"],
            "defect_type": rng.choice(DEFECT_TYPES),
            "severity": rng.choice(["low", "medium", "high"]),
            "detected_date": det_date.isoformat(),
            "target_rectification_date": (det_date + timedelta(days=rng.randint(7, 180))).isoformat(),
            "status": rng.choice(["open", "planned", "closed", "deferred"]),
            "safety_risk_score": round(clamp(rng.gauss(30, 10), 1, 99), 1),
            "reliability_risk_score": round(clamp(rng.gauss(30, 10), 1, 99), 1),
        })
        # Update inspection defect_count.
        ins["defect_count"] = int(ins.get("defect_count", 0)) + 1


def gen_vegetation(ds: Dataset, rng: random.Random, now: date, target: int) -> None:
    feeders_by_region = {}
    assets_by_feeder: dict[str, list[dict]] = {}
    for a in ds.assets:
        assets_by_feeder.setdefault(a["feeder_id"], []).append(a)
    for f in ds.feeders:
        feeders_by_region.setdefault(f["region_id"], []).append(f)

    counter = 1
    # Weight veg by region veg factor.
    region_pool = []
    for r in REGIONS:
        weight = r["vegetation_factor"]
        region_pool.append((r["region_id"], weight))
    total_weight = sum(w for _, w in region_pool)

    for _ in range(target):
        # Pick region by weight.
        rnd = rng.uniform(0, total_weight)
        upto = 0.0
        region_id = REGIONS[0]["region_id"]
        for rid, w in region_pool:
            upto += w
            if rnd <= upto:
                region_id = rid
                break
        region = REGION_INDEX[region_id]
        feeders = feeders_by_region.get(region_id, [])
        if not feeders:
            continue
        f = rng.choice(feeders)
        feeder_assets = assets_by_feeder.get(f["feeder_id"], [])
        if not feeder_assets:
            continue
        nearest = rng.choice(feeder_assets)
        # Vegetation clusters on tropical / mountainous regions, lower clearances.
        clearance = clamp(rng.gauss(3.0 if region["vegetation_factor"] < 1.0 else 1.7, 0.8), 0.2, 6.0)
        growth_band = weighted_choice(rng, [("slow", 0.25), ("moderate", 0.45), ("fast", 0.30)]) if region["vegetation_factor"] < 1.0 else weighted_choice(rng, [("slow", 0.10), ("moderate", 0.35), ("fast", 0.55)])
        last_treatment = now - timedelta(days=rng.randint(30, 730))
        cycle = 365 if growth_band != "fast" else 240
        next_due = last_treatment + timedelta(days=cycle)
        overdue = max(0, (now - next_due).days)
        risk_score = clamp(
            (4.0 - clearance) * 18 + (overdue / 8) + (15 if growth_band == "fast" else 0) + rng.gauss(0, 4),
            1, 99,
        )
        priority = "urgent" if risk_score > 75 else ("high" if risk_score > 55 else ("medium" if risk_score > 30 else "low"))
        ds.vegetation_spans.append({
            "vegetation_span_id": f"VEG-{counter:07d}",
            "feeder_id": f["feeder_id"],
            "region_id": region_id,
            "nearest_asset_id": nearest["asset_id"],
            "lat": nearest["lat"],
            "lon": nearest["lon"],
            "species_group": rng.choice(["eucalypt", "mango", "rainforest_mixed", "callistemon", "acacia", "casuarina"]),
            "clearance_m": round(clearance, 2),
            "growth_rate_band": growth_band,
            "last_treatment_date": last_treatment.isoformat(),
            "next_due_date": next_due.isoformat(),
            "overdue_days": overdue,
            "vegetation_risk_score": round(risk_score, 1),
            "treatment_priority": priority,
        })
        counter += 1


def gen_critical_customers(ds: Dataset, rng: random.Random, target: int) -> None:
    feeders = ds.feeders
    counter = 1
    # Weight feeders by critical_customer_count (which already encodes region density).
    weights = [(f, f["critical_customer_count"] + 1) for f in feeders]
    total = sum(w for _, w in weights)
    for _ in range(target):
        r = rng.uniform(0, total)
        upto = 0.0
        f = feeders[-1]
        for fr, w in weights:
            upto += w
            if r <= upto:
                f = fr
                break
        site_type = weighted_choice(rng, CRITICAL_SITE_TYPES)
        # Pick coordinate around feeder's region anchor.
        region = REGION_INDEX[f["region_id"]]
        anchors = REGION_ANCHORS[f["region_id"]]
        _, alat, alon = rng.choice(anchors)
        ds.critical_customers.append({
            "critical_customer_id": f"CCX-{counter:06d}",
            "feeder_id": f["feeder_id"],
            "region_id": f["region_id"],
            "site_name": f"{site_type.replace('_', ' ').title()} Site {counter}",
            "site_type": site_type,
            "lat": round(jitter(rng, alat, 0.1), 6),
            "lon": round(jitter(rng, alon, 0.1), 6),
            "backup_power_status": rng.choice(["full", "partial", "none", "unknown"]),
            "priority_score": round(clamp(rng.gauss(70, 15), 1, 99), 1),
        })
        counter += 1


def gen_hazard_zones(ds: Dataset, rng: random.Random, target: int) -> None:
    counter = 1
    for r in REGIONS:
        n = max(20, target // len(REGIONS))
        anchors = REGION_ANCHORS[r["region_id"]]
        for i in range(n):
            anchor_name, alat, alon = rng.choice(anchors)
            hazard_type = weighted_choice(
                rng,
                [
                    ("cyclone", r["cyclone_factor"]),
                    ("flood", r["flood_factor"]),
                    ("bushfire", r["bushfire_factor"]),
                    ("heat", 0.4),
                    ("storm", r["storm_factor"]),
                    ("coastal_corrosion", r["corrosion_factor"]),
                ],
            )
            severity = clamp(rng.gauss(55, 18), 5, 99)
            ds.hazard_exposure_zones.append({
                "hazard_zone_id": f"HZN-{counter:06d}",
                "region_id": r["region_id"],
                "hazard_type": hazard_type,
                "zone_name": f"{anchor_name} {hazard_type} Zone {i + 1}",
                "lat": round(jitter(rng, alat, 0.45), 6),
                "lon": round(jitter(rng, alon, 0.45), 6),
                "radius_km": round(rng.uniform(3, 35), 1),
                "severity_score": round(severity, 1),
                "seasonal_window": rng.choice(["Nov-Apr", "Dec-Mar", "year_round", "Aug-Nov"]),
            })
            counter += 1


def gen_outages(ds: Dataset, rng: random.Random, now: date, target: int) -> None:
    feeders_by_id = {f["feeder_id"]: f for f in ds.feeders}
    health_by_asset = {h["asset_id"]: h for h in ds.asset_health_scores}
    veg_by_feeder: dict[str, float] = {}
    for v in ds.vegetation_spans:
        veg_by_feeder.setdefault(v["feeder_id"], 0.0)
        veg_by_feeder[v["feeder_id"]] += v["vegetation_risk_score"]

    # Weight outages towards risky feeders.
    weights = []
    for f in ds.feeders:
        region = REGION_INDEX[f["region_id"]]
        weight = (1.0 + region["storm_factor"]) * (1.0 + region["cyclone_factor"]) * (1.0 + veg_by_feeder.get(f["feeder_id"], 0) / 200.0)
        weights.append((f, weight))
    total = sum(w for _, w in weights)

    counter = 1
    for _ in range(target):
        r = rng.uniform(0, total)
        upto = 0.0
        f = weights[-1][0]
        for fr, w in weights:
            upto += w
            if r <= upto:
                f = fr
                break
        region = REGION_INDEX[f["region_id"]]
        start = datetime.combine(now - timedelta(days=rng.randint(0, 1095)), datetime.min.time()) + timedelta(hours=rng.randint(0, 23), minutes=rng.randint(0, 59))
        duration_minutes = max(5, int(rng.gauss(120 * (1.0 + region["access_factor"]), 80)))
        end = start + timedelta(minutes=duration_minutes)
        customers = max(1, int(rng.gauss(f["customer_count"] * 0.4, f["customer_count"] * 0.2)))
        critical_customers = max(0, int(min(customers, rng.gauss(f["critical_customer_count"] * 0.5, 2))))
        # Cause weighted by region.
        cause = weighted_choice(rng, [
            ("storm", region["storm_factor"]),
            ("vegetation", region["vegetation_factor"]),
            ("equipment_failure", 0.8),
            ("vehicle_impact", 0.3),
            ("planned", 0.3),
            ("unknown", 0.2),
            ("flood", region["flood_factor"]),
            ("lightning", region["storm_factor"] * 0.6),
        ])
        # Sometimes attach an asset (must be on the feeder).
        attached_asset_id = ""
        if rng.random() < 0.6:
            # Pick a random asset on this feeder.
            on_feeder = [a for a in ds.assets if a["feeder_id"] == f["feeder_id"]]
            if on_feeder:
                attached_asset_id = rng.choice(on_feeder)["asset_id"]
        saidi = round(duration_minutes * customers / max(1, f["customer_count"]), 2)
        saifi = round(customers / max(1, f["customer_count"]), 4)
        crew_response_minutes = max(5, int(rng.gauss(45 * (1.0 + region["access_factor"]), 20)))
        ds.outage_events.append({
            "outage_id": f"OUT-{counter:07d}",
            "feeder_id": f["feeder_id"],
            "region_id": f["region_id"],
            "asset_id": attached_asset_id,
            "outage_start": start.isoformat(timespec="minutes"),
            "outage_end": end.isoformat(timespec="minutes"),
            "duration_minutes": duration_minutes,
            "customers_interrupted": customers,
            "critical_customers_interrupted": critical_customers,
            "cause_category": cause,
            "saidi_minutes": saidi,
            "saifi_count": saifi,
            "crew_response_minutes": crew_response_minutes,
            "restoration_notes": rng.choice([
                "Crew rerouted via alternate access track.",
                "Helicopter inspection required.",
                "Storm cell passed through feeder.",
                "Vegetation contact confirmed at span.",
                "Restoration delayed by access issues.",
                "Switched to alternate feeder during restoration.",
                "Lightning strike at substation transformer.",
            ]),
        })
        counter += 1


def gen_work_orders(ds: Dataset, rng: random.Random, now: date, target: int) -> None:
    feeders_by_id = {f["feeder_id"]: f for f in ds.feeders}
    health_by_asset = {h["asset_id"]: h for h in ds.asset_health_scores}
    depots_by_region: dict[str, list[dict]] = {}
    for d in ds.depots:
        depots_by_region.setdefault(d["region_id"], []).append(d)

    # Bias work to higher risk feeders.
    feeder_weights = []
    for f in ds.feeders:
        feeder_assets = [a for a in ds.assets if a["feeder_id"] == f["feeder_id"]]
        if not feeder_assets:
            continue
        risk_total = 0.0
        for a in feeder_assets:
            h = health_by_asset.get(a["asset_id"])
            if h:
                risk_total += h["risk_score"]
        feeder_weights.append((f, feeder_assets, risk_total + 1))
    total = sum(w for *_, w in feeder_weights)

    counter = 1
    for _ in range(target):
        r = rng.uniform(0, total)
        upto = 0.0
        chosen = feeder_weights[-1]
        for fw in feeder_weights:
            upto += fw[2]
            if r <= upto:
                chosen = fw
                break
        f, feeder_assets, _ = chosen
        region_id = f["region_id"]
        depots = depots_by_region.get(region_id, [])
        if not depots:
            continue
        depot = rng.choice(depots)
        # Pick an asset 70% of the time.
        attached_asset_id = ""
        if rng.random() < 0.7:
            # Prefer higher-risk assets.
            asset_sample = rng.sample(feeder_assets, k=min(8, len(feeder_assets)))
            asset_sample.sort(key=lambda a: -health_by_asset[a["asset_id"]]["risk_score"])
            attached_asset_id = asset_sample[0]["asset_id"]
        work_type = weighted_choice(rng, [
            ("inspection", 0.20),
            ("vegetation_treatment", 0.20),
            ("repair", 0.20),
            ("replacement", 0.15),
            ("storm_response", 0.10),
            ("planned_maintenance", 0.10),
            ("access_remediation", 0.05),
        ])
        priority = weighted_choice(rng, [("low", 0.20), ("medium", 0.40), ("high", 0.30), ("urgent", 0.10)])
        status = weighted_choice(rng, [
            ("draft", 0.05),
            ("approved", 0.10),
            ("scheduled", 0.30),
            ("in_progress", 0.20),
            ("completed", 0.30),
            ("cancelled", 0.05),
        ])
        created = now - timedelta(days=rng.randint(2, 730))
        scheduled = created + timedelta(days=rng.randint(1, 90))
        completed = ""
        if status == "completed":
            completed = (scheduled + timedelta(days=rng.randint(0, 30))).isoformat()
        elif status == "in_progress":
            completed = ""
        estimated_hours = round(rng.uniform(2, 36), 1)
        estimated_cost = round(estimated_hours * rng.uniform(180, 320) + rng.uniform(500, 12000), 2)
        ds.work_orders.append({
            "work_order_id": f"WO-{counter:07d}",
            "asset_id": attached_asset_id,
            "feeder_id": f["feeder_id"],
            "region_id": region_id,
            "work_type": work_type,
            "priority": priority,
            "status": status,
            "created_date": created.isoformat(),
            "scheduled_date": scheduled.isoformat(),
            "completed_date": completed,
            "estimated_hours": estimated_hours,
            "estimated_cost_aud": estimated_cost,
            "crew_type": rng.choice(["line_crew", "vegetation_crew", "substation_crew", "drone_team"]),
            "depot_id": depot["depot_id"],
        })
        counter += 1


def gen_mobile_generation(ds: Dataset, rng: random.Random, target: int) -> None:
    by_region: dict[str, list[dict]] = {}
    for f in ds.feeders:
        by_region.setdefault(f["region_id"], []).append(f)
    counter = 1
    # More candidates in remote regions.
    region_weights = {r["region_id"]: r["access_factor"] for r in REGIONS}
    total = sum(region_weights.values())
    for _ in range(target):
        rnd = rng.uniform(0, total)
        upto = 0.0
        region_id = REGIONS[0]["region_id"]
        for rid, w in region_weights.items():
            upto += w
            if rnd <= upto:
                region_id = rid
                break
        feeders = by_region.get(region_id, [])
        if not feeders:
            continue
        f = rng.choice(feeders)
        anchors = REGION_ANCHORS[region_id]
        anchor_name, alat, alon = rng.choice(anchors)
        ds.mobile_generation_candidates.append({
            "candidate_id": f"MGC-{counter:05d}",
            "feeder_id": f["feeder_id"],
            "region_id": region_id,
            "site_name": f"{anchor_name} Mobile Gen Site {counter}",
            "lat": round(jitter(rng, alat, 0.3), 6),
            "lon": round(jitter(rng, alon, 0.3), 6),
            "connection_ready": rng.random() < 0.65,
            "customer_impact_reduction_score": round(clamp(rng.gauss(55, 18), 1, 99), 1),
            "access_difficulty_score": round(clamp(rng.gauss(45, 15), 1, 99), 1),
            "recommended_unit_size_kva": rng.choice([100, 250, 500, 750, 1000, 1500, 2000]),
        })
        counter += 1


def gen_asset_documents_metadata(ds: Dataset, rng: random.Random, target_meta: int) -> None:
    """Metadata rows only — actual document files generated by generate_asset_documents.py.

    We bias documents to high-risk assets so the RAG retrieval has signal.
    """
    health_by_asset = {h["asset_id"]: h for h in ds.asset_health_scores}
    # 80% per-asset documents, 20% per-feeder or per-region standards.
    counter = 1
    high_risk_assets = sorted(
        ds.assets,
        key=lambda a: -health_by_asset[a["asset_id"]]["risk_score"],
    )[: max(200, target_meta // 2)]

    base_volume = os.getenv("DATABRICKS_VOLUME_PATH", "/Volumes/anzgt_may/energyq/asset_docs")

    for _ in range(target_meta):
        kind_roll = rng.random()
        if kind_roll < 0.55 and high_risk_assets:
            a = rng.choice(high_risk_assets)
            doc_type = weighted_choice(rng, [
                ("inspection_report", 0.55),
                ("photo_pack", 0.15),
                ("work_order_pdf", 0.15),
                ("risk_assessment", 0.10),
                ("engineering_drawing", 0.05),
            ])
            title = f"{doc_type.replace('_', ' ').title()} — {a['asset_id']}"
            feeder_id = a["feeder_id"]
            region_id = a["region_id"]
            asset_id = a["asset_id"]
        elif kind_roll < 0.85:
            a = rng.choice(ds.assets)
            doc_type = rng.choice(["inspection_report", "engineering_drawing", "photo_pack", "work_order_pdf"])
            title = f"{doc_type.replace('_', ' ').title()} — {a['asset_id']}"
            feeder_id = a["feeder_id"]
            region_id = a["region_id"]
            asset_id = a["asset_id"]
        else:
            # Region/feeder-level standard.
            f = rng.choice(ds.feeders)
            doc_type = rng.choice(["maintenance_standard", "vegetation_policy", "storm_response_plan", "risk_assessment"])
            title = f"{doc_type.replace('_', ' ').title()} — {f['region_id']}"
            feeder_id = f["feeder_id"]
            region_id = f["region_id"]
            asset_id = ""

        document_id = f"DOC-{counter:06d}"
        counter += 1
        path = f"{base_volume}/{region_id}/{doc_type}/{document_id}.md"
        created = (_utcnow() - timedelta(days=rng.randint(0, 720))).isoformat(timespec="seconds")
        effective = (_utcnow() - timedelta(days=rng.randint(0, 365))).isoformat(timespec="seconds")
        ds.asset_documents.append({
            "document_id": document_id,
            "asset_id": asset_id,
            "feeder_id": feeder_id,
            "region_id": region_id,
            "document_type": doc_type,
            "document_title": title,
            "volume_path": path,
            "created_date": created,
            "effective_date": effective,
            "document_summary": "",  # filled by document generator
            "sensitivity_classification": weighted_choice(rng, [("internal", 0.6), ("restricted", 0.3), ("confidential", 0.1)]),
        })


def gen_scenario_runs(ds: Dataset, rng: random.Random) -> None:
    counter = 1
    scenarios = [
        ("Mackay Storm Readiness 2026", "storm_readiness", "REG-MKY"),
        ("SEQ Reliability Improvement", "reliability_improvement", "REG-SEQ"),
        ("Cairns Pre-Cyclone Pack", "storm_readiness", "REG-TSV"),
        ("Central Queensland Capex Round", "capex_prioritisation", "REG-CQI"),
        ("Remote West Mobile Gen Plan", "field_inspection_review", "REG-RW"),
        ("State Vegetation Program FY26", "vegetation_program", None),
    ]
    for name, type_, region in scenarios:
        ds.scenario_runs.append({
            "scenario_id": f"SCN-{counter:04d}",
            "scenario_name": name,
            "scenario_type": type_,
            "created_at": (_utcnow() - timedelta(days=rng.randint(0, 60))).isoformat(timespec="seconds"),
            "region_id": region or "",
            "risk_threshold": rng.choice([55, 60, 65, 70]),
            "selected_asset_count": rng.randint(50, 500),
            "recommended_work_package_count": rng.randint(3, 30),
            "estimated_customer_impact_reduction": rng.randint(500, 25000),
        })
        counter += 1


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic GridLens Queensland data.")
    parser.add_argument("--assets", type=int, default=40000)
    parser.add_argument("--feeders", type=int, default=320)
    parser.add_argument("--substations", type=int, default=40)
    parser.add_argument("--depots", type=int, default=12)
    parser.add_argument("--inspections", type=int, default=12000)
    parser.add_argument("--defects", type=int, default=22000)
    parser.add_argument("--vegetation", type=int, default=18000)
    parser.add_argument("--outages", type=int, default=9000)
    parser.add_argument("--work-orders", type=int, default=14000)
    parser.add_argument("--critical-customers", type=int, default=1400)
    parser.add_argument("--hazard-zones", type=int, default=350)
    parser.add_argument("--documents", type=int, default=2400, help="Metadata row count.")
    parser.add_argument("--mobile-gen", type=int, default=350)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default="data/synthetic", help="Output directory.")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    now = date.today()

    ds = Dataset()
    print(f"\n  GridLens Queensland — synthetic data generator")
    print(f"  seed={args.seed}  output={args.output}\n")

    print("[1/14] regions")
    gen_regions(ds)
    print("[2/14] depots")
    gen_depots(ds, rng, args.depots)
    print("[3/14] substations")
    gen_substations(ds, rng, args.substations)
    print("[4/14] feeders")
    gen_feeders(ds, rng, args.feeders)
    print("[5/14] assets")
    gen_assets(ds, rng, args.assets)
    print("[6/14] asset health scores")
    gen_asset_health(ds, rng, now)
    print("[7/14] inspections + defects")
    gen_inspections_and_defects(ds, rng, now, args.inspections, args.defects)
    print("[8/14] vegetation spans")
    gen_vegetation(ds, rng, now, args.vegetation)
    print("[9/14] critical customers")
    gen_critical_customers(ds, rng, args.critical_customers)
    print("[10/14] hazard exposure zones")
    gen_hazard_zones(ds, rng, args.hazard_zones)
    print("[11/14] outage events")
    gen_outages(ds, rng, now, args.outages)
    print("[12/14] work orders")
    gen_work_orders(ds, rng, now, args.work_orders)
    print("[13/14] mobile generation candidates")
    gen_mobile_generation(ds, rng, args.mobile_gen)
    print("[14/14] document metadata + scenarios")
    gen_asset_documents_metadata(ds, rng, args.documents)
    gen_scenario_runs(ds, rng)

    print("\nWriting CSV ->", args.output)
    ds.write_csv(Path(args.output))
    print("\nDone.\n")


if __name__ == "__main__":
    main()
