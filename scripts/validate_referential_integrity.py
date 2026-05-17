"""
Validate referential integrity for synthetic GridLens Queensland data.

Reads every CSV produced by generate_synthetic_energyq_data.py and checks all
foreign keys, primary key uniqueness, value ranges and date sanity.

Usage:
    python scripts/validate_referential_integrity.py --input data/synthetic

Exits non-zero on any failure and prints a clear summary.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path


REQUIRED_TABLES = [
    "regions",
    "depots",
    "substations",
    "feeders",
    "assets",
    "asset_health_scores",
    "inspection_events",
    "defects",
    "vegetation_spans",
    "outage_events",
    "work_orders",
    "critical_customers",
    "hazard_exposure_zones",
    "asset_documents",
    "mobile_generation_candidates",
    "scenario_runs",
]


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def parse_date(value: str):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None


class Validator:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.passed: list[str] = []

    def check(self, name: str, ok: bool, msg: str = "") -> None:
        if ok:
            self.passed.append(name)
        else:
            self.errors.append(f"FAIL: {name} — {msg}")

    def report(self) -> bool:
        print()
        for p in self.passed:
            print(f"  PASS  {p}")
        for e in self.errors:
            print(f"  {e}")
        print()
        print(f"  Passed: {len(self.passed)}")
        print(f"  Failed: {len(self.errors)}")
        return not self.errors


def primary_keys_unique(v: Validator, name: str, rows: list[dict], key: str) -> set[str]:
    ids = [r[key] for r in rows]
    pk = set(ids)
    v.check(f"{name}.{key} unique", len(ids) == len(pk), f"{len(ids)} rows, {len(pk)} unique")
    return pk


def foreign_keys_present(
    v: Validator, name: str, rows: list[dict], fk: str, parent: set[str], allow_blank: bool = False
) -> None:
    bad = []
    for r in rows:
        val = r.get(fk, "")
        if not val:
            if allow_blank:
                continue
            bad.append((r, fk))
            continue
        if val not in parent:
            bad.append((r, fk))
        if len(bad) > 3:
            break
    v.check(
        f"{name}.{fk} -> parent",
        not bad,
        f"first offender: {bad[0]}" if bad else "",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/synthetic")
    args = parser.parse_args()

    inp = Path(args.input)
    print(f"\n  Validating {inp.resolve()}\n")
    v = Validator()

    # Load.
    tables = {name: load(inp / f"{name}.csv") for name in REQUIRED_TABLES}
    for name in REQUIRED_TABLES:
        v.check(f"table:{name} exists", bool(tables[name]), f"missing or empty {name}.csv")
    if v.errors:
        v.report()
        return 1

    # Primary keys.
    region_ids = primary_keys_unique(v, "regions", tables["regions"], "region_id")
    depot_ids = primary_keys_unique(v, "depots", tables["depots"], "depot_id")
    substation_ids = primary_keys_unique(v, "substations", tables["substations"], "substation_id")
    feeder_ids = primary_keys_unique(v, "feeders", tables["feeders"], "feeder_id")
    asset_ids = primary_keys_unique(v, "assets", tables["assets"], "asset_id")
    primary_keys_unique(v, "asset_health_scores", tables["asset_health_scores"], "asset_id")
    inspection_ids = primary_keys_unique(v, "inspection_events", tables["inspection_events"], "inspection_id")
    primary_keys_unique(v, "defects", tables["defects"], "defect_id")
    primary_keys_unique(v, "vegetation_spans", tables["vegetation_spans"], "vegetation_span_id")
    primary_keys_unique(v, "outage_events", tables["outage_events"], "outage_id")
    primary_keys_unique(v, "work_orders", tables["work_orders"], "work_order_id")
    primary_keys_unique(v, "critical_customers", tables["critical_customers"], "critical_customer_id")
    primary_keys_unique(v, "hazard_exposure_zones", tables["hazard_exposure_zones"], "hazard_zone_id")
    primary_keys_unique(v, "asset_documents", tables["asset_documents"], "document_id")
    primary_keys_unique(v, "mobile_generation_candidates", tables["mobile_generation_candidates"], "candidate_id")
    primary_keys_unique(v, "scenario_runs", tables["scenario_runs"], "scenario_id")

    # Foreign keys.
    foreign_keys_present(v, "depots", tables["depots"], "region_id", region_ids)
    foreign_keys_present(v, "substations", tables["substations"], "region_id", region_ids)
    foreign_keys_present(v, "feeders", tables["feeders"], "substation_id", substation_ids)
    foreign_keys_present(v, "feeders", tables["feeders"], "region_id", region_ids)

    feeder_to_region = {f["feeder_id"]: f["region_id"] for f in tables["feeders"]}
    feeder_to_substation = {f["feeder_id"]: f["substation_id"] for f in tables["feeders"]}
    asset_to_feeder = {a["asset_id"]: a["feeder_id"] for a in tables["assets"]}

    foreign_keys_present(v, "assets", tables["assets"], "feeder_id", feeder_ids)
    foreign_keys_present(v, "assets", tables["assets"], "substation_id", substation_ids)
    foreign_keys_present(v, "assets", tables["assets"], "region_id", region_ids)

    # Asset region must match feeder region.
    asset_region_consistent = sum(1 for a in tables["assets"] if a["region_id"] == feeder_to_region.get(a["feeder_id"]))
    v.check("assets.region matches feeder.region", asset_region_consistent == len(tables["assets"]),
            f"{len(tables['assets']) - asset_region_consistent} mismatches")
    asset_ss_consistent = sum(1 for a in tables["assets"] if a["substation_id"] == feeder_to_substation.get(a["feeder_id"]))
    v.check("assets.substation matches feeder.substation", asset_ss_consistent == len(tables["assets"]),
            f"{len(tables['assets']) - asset_ss_consistent} mismatches")

    foreign_keys_present(v, "asset_health_scores", tables["asset_health_scores"], "asset_id", asset_ids)
    foreign_keys_present(v, "inspection_events", tables["inspection_events"], "asset_id", asset_ids)
    foreign_keys_present(v, "defects", tables["defects"], "inspection_id", inspection_ids)
    foreign_keys_present(v, "defects", tables["defects"], "asset_id", asset_ids)

    inspection_to_asset = {i["inspection_id"]: i["asset_id"] for i in tables["inspection_events"]}
    bad = [d for d in tables["defects"] if inspection_to_asset.get(d["inspection_id"]) != d["asset_id"]]
    v.check("defects.asset matches inspection.asset", not bad, f"first offender: {bad[0] if bad else ''}")

    foreign_keys_present(v, "vegetation_spans", tables["vegetation_spans"], "feeder_id", feeder_ids)
    foreign_keys_present(v, "vegetation_spans", tables["vegetation_spans"], "region_id", region_ids)
    foreign_keys_present(v, "vegetation_spans", tables["vegetation_spans"], "nearest_asset_id", asset_ids)
    # Nearest asset's feeder should equal vegetation span's feeder.
    bad = [
        x for x in tables["vegetation_spans"]
        if asset_to_feeder.get(x["nearest_asset_id"]) != x["feeder_id"]
    ]
    v.check("vegetation.nearest_asset feeder matches span feeder", not bad,
            f"first offender: {bad[0] if bad else ''}")

    foreign_keys_present(v, "outage_events", tables["outage_events"], "feeder_id", feeder_ids)
    foreign_keys_present(v, "outage_events", tables["outage_events"], "region_id", region_ids)
    foreign_keys_present(v, "outage_events", tables["outage_events"], "asset_id", asset_ids, allow_blank=True)

    bad = [
        o for o in tables["outage_events"]
        if o.get("asset_id") and asset_to_feeder.get(o["asset_id"]) != o["feeder_id"]
    ]
    v.check("outages.asset belongs to outage feeder", not bad, f"first offender: {bad[0] if bad else ''}")

    foreign_keys_present(v, "work_orders", tables["work_orders"], "feeder_id", feeder_ids)
    foreign_keys_present(v, "work_orders", tables["work_orders"], "region_id", region_ids)
    foreign_keys_present(v, "work_orders", tables["work_orders"], "depot_id", depot_ids)
    foreign_keys_present(v, "work_orders", tables["work_orders"], "asset_id", asset_ids, allow_blank=True)

    depot_to_region = {d["depot_id"]: d["region_id"] for d in tables["depots"]}
    bad = [
        w for w in tables["work_orders"]
        if depot_to_region.get(w["depot_id"]) != w["region_id"]
    ]
    v.check("work_orders.depot in same region", not bad, f"first offender: {bad[0] if bad else ''}")

    bad = [
        w for w in tables["work_orders"]
        if w.get("asset_id") and asset_to_feeder.get(w["asset_id"]) != w["feeder_id"]
    ]
    v.check("work_orders.asset belongs to work feeder", not bad, f"first offender: {bad[0] if bad else ''}")

    foreign_keys_present(v, "critical_customers", tables["critical_customers"], "feeder_id", feeder_ids)
    foreign_keys_present(v, "critical_customers", tables["critical_customers"], "region_id", region_ids)

    foreign_keys_present(v, "asset_documents", tables["asset_documents"], "asset_id", asset_ids, allow_blank=True)
    foreign_keys_present(v, "asset_documents", tables["asset_documents"], "feeder_id", feeder_ids, allow_blank=True)
    foreign_keys_present(v, "asset_documents", tables["asset_documents"], "region_id", region_ids)
    # Document must reference asset or feeder.
    bad = [d for d in tables["asset_documents"] if not d.get("asset_id") and not d.get("feeder_id")]
    v.check("asset_documents must reference asset or feeder", not bad,
            f"{len(bad)} docs reference neither")

    foreign_keys_present(v, "mobile_generation_candidates", tables["mobile_generation_candidates"], "feeder_id", feeder_ids)
    foreign_keys_present(v, "mobile_generation_candidates", tables["mobile_generation_candidates"], "region_id", region_ids)

    # Coordinate sanity.
    bad = [a for a in tables["assets"] if not -45 < float(a["lat"]) < -8 or not 137 < float(a["lon"]) < 156]
    v.check("assets lat/lon within QLD-ish bbox", not bad, f"{len(bad)} outside expected QLD bounds")

    # Score ranges.
    range_checks = [
        ("assets.criticality_score", "assets", "criticality_score", 0, 100),
        ("assets.access_difficulty_score", "assets", "access_difficulty_score", 0, 100),
        ("assets.coastal_corrosion_score", "assets", "coastal_corrosion_score", 0, 100),
        ("assets.flood_exposure_score", "assets", "flood_exposure_score", 0, 100),
        ("assets.cyclone_exposure_score", "assets", "cyclone_exposure_score", 0, 100),
        ("assets.bushfire_exposure_score", "assets", "bushfire_exposure_score", 0, 100),
        ("asset_health.condition_score", "asset_health_scores", "condition_score", 0, 100),
        ("asset_health.risk_score", "asset_health_scores", "risk_score", 0, 100),
        ("feeders.overhead_pct", "feeders", "overhead_pct", 0, 100),
        ("feeders.underground_pct", "feeders", "underground_pct", 0, 100),
        ("hazards.severity_score", "hazard_exposure_zones", "severity_score", 0, 100),
        ("veg.vegetation_risk_score", "vegetation_spans", "vegetation_risk_score", 0, 100),
    ]
    for label, tbl, col, lo, hi in range_checks:
        bad = [r for r in tables[tbl] if not (lo <= float(r[col]) <= hi)]
        v.check(f"{label} in [{lo},{hi}]", not bad, f"{len(bad)} rows out of range")

    # Outage end > start.
    bad = []
    for o in tables["outage_events"]:
        try:
            s = datetime.fromisoformat(o["outage_start"])
            e = datetime.fromisoformat(o["outage_end"])
            if e < s:
                bad.append(o["outage_id"])
        except ValueError:
            bad.append(o["outage_id"])
    v.check("outage_events.outage_end >= outage_start", not bad, f"{len(bad)} outages bad")

    # Work order completed_date >= created_date when present.
    bad = []
    for w in tables["work_orders"]:
        if w.get("completed_date"):
            c = parse_date(w["created_date"])
            done = parse_date(w["completed_date"])
            if c and done and done < c:
                bad.append(w["work_order_id"])
    v.check("work_orders.completed_date >= created_date", not bad, f"{len(bad)} bad")

    # Health bands align broadly with risk scores.
    bad = []
    for h in tables["asset_health_scores"]:
        risk = float(h["risk_score"])
        if h["risk_band"] == "critical" and risk < 70:
            bad.append(h["asset_id"])
        if h["risk_band"] == "low" and risk > 40:
            bad.append(h["asset_id"])
    v.check("health risk band aligns with risk score", len(bad) < 50, f"{len(bad)} mild misalignments (tolerated <50)")

    # At least one high-risk demo cluster per target region.
    regions_with_critical: dict[str, int] = defaultdict(int)
    asset_region = {a["asset_id"]: a["region_id"] for a in tables["assets"]}
    for h in tables["asset_health_scores"]:
        if h["risk_band"] in ("high", "critical"):
            regions_with_critical[asset_region.get(h["asset_id"], "")] += 1
    for r in tables["regions"]:
        rid = r["region_id"]
        v.check(
            f"{rid} has >=30 high/critical assets",
            regions_with_critical.get(rid, 0) >= 30,
            f"only {regions_with_critical.get(rid, 0)} high/critical",
        )

    ok = v.report()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
