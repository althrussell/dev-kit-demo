"""
Load synthetic CSV data into Unity Catalog Delta tables.

Two modes:
  1. Databricks SQL Connector (default) — uses DATABRICKS_HOST/HTTP_PATH/TOKEN.
  2. Local CSV (--dry-run) — validates the load plan without touching Databricks.

Usage:
    python scripts/load_delta_tables.py --input data/synthetic --catalog anzgt_may
    python scripts/load_delta_tables.py --input data/synthetic --dry-run

Requires (for real load):
    pip install databricks-sql-connector
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

TABLE_SCHEMA = {
    "regions": ["region_id", "region_name", "region_type", "state",
                "population_density_band", "hazard_profile",
                "centre_lat", "centre_lon"],
    "depots": ["depot_id", "region_id", "depot_name", "lat", "lon",
               "crew_count", "specialist_crews", "mobile_generation_units"],
    "substations": ["substation_id", "region_id", "substation_name", "lat", "lon",
                    "voltage_level", "commissioned_year", "criticality_score",
                    "flood_exposure_score", "cyclone_exposure_score"],
    "feeders": ["feeder_id", "substation_id", "region_id", "feeder_name",
                "voltage_kv", "feeder_length_km", "customer_count",
                "critical_customer_count", "overhead_pct", "underground_pct",
                "radiality_score", "asset_density_score",
                "network_capacity_band", "export_capacity_band"],
    "assets": ["asset_id", "feeder_id", "substation_id", "region_id",
               "asset_type", "asset_name", "lat", "lon", "install_year",
               "manufacturer", "material", "voltage_kv", "status",
               "criticality_score", "access_difficulty_score",
               "coastal_corrosion_score", "flood_exposure_score",
               "cyclone_exposure_score", "bushfire_exposure_score"],
    "asset_health_scores": ["asset_id", "condition_score",
                            "failure_probability_12m", "failure_probability_36m",
                            "health_band", "risk_score", "risk_band",
                            "risk_drivers", "last_scored_at"],
    "inspection_events": ["inspection_id", "asset_id", "inspection_date",
                          "inspection_type", "inspector_team",
                          "condition_observed", "defect_count", "photo_count",
                          "document_id", "recommended_action"],
    "defects": ["defect_id", "inspection_id", "asset_id", "defect_type",
                "severity", "detected_date", "target_rectification_date",
                "status", "safety_risk_score", "reliability_risk_score"],
    "vegetation_spans": ["vegetation_span_id", "feeder_id", "region_id",
                         "nearest_asset_id", "lat", "lon", "species_group",
                         "clearance_m", "growth_rate_band",
                         "last_treatment_date", "next_due_date",
                         "overdue_days", "vegetation_risk_score",
                         "treatment_priority"],
    "outage_events": ["outage_id", "feeder_id", "region_id", "asset_id",
                      "outage_start", "outage_end", "duration_minutes",
                      "customers_interrupted", "critical_customers_interrupted",
                      "cause_category", "saidi_minutes", "saifi_count",
                      "crew_response_minutes", "restoration_notes"],
    "work_orders": ["work_order_id", "asset_id", "feeder_id", "region_id",
                    "work_type", "priority", "status", "created_date",
                    "scheduled_date", "completed_date", "estimated_hours",
                    "estimated_cost_aud", "crew_type", "depot_id"],
    "critical_customers": ["critical_customer_id", "feeder_id", "region_id",
                           "site_name", "site_type", "lat", "lon",
                           "backup_power_status", "priority_score"],
    "hazard_exposure_zones": ["hazard_zone_id", "region_id", "hazard_type",
                              "zone_name", "lat", "lon", "radius_km",
                              "severity_score", "seasonal_window"],
    "asset_documents": ["document_id", "asset_id", "feeder_id", "region_id",
                        "document_type", "document_title", "volume_path",
                        "created_date", "effective_date", "document_summary",
                        "sensitivity_classification"],
    "mobile_generation_candidates": ["candidate_id", "feeder_id", "region_id",
                                     "site_name", "lat", "lon",
                                     "connection_ready",
                                     "customer_impact_reduction_score",
                                     "access_difficulty_score",
                                     "recommended_unit_size_kva"],
    "scenario_runs": ["scenario_id", "scenario_name", "scenario_type",
                      "created_at", "region_id", "risk_threshold",
                      "selected_asset_count",
                      "recommended_work_package_count",
                      "estimated_customer_impact_reduction"],
}


def chunked(iterable, size):
    chunk = []
    for item in iterable:
        chunk.append(item)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def python_to_sql_literal(v: str, col: str, table: str) -> str:
    """Best-effort SQL literal conversion based on column heuristics."""
    if v == "" or v is None:
        return "NULL"
    lower = v.lower()
    # Booleans.
    if lower in ("true", "false"):
        return lower.upper()
    # Numeric.
    if col.endswith("_score") or col in (
        "lat", "lon", "voltage_kv", "feeder_length_km", "overhead_pct",
        "underground_pct", "radiality_score", "asset_density_score",
        "condition_score", "risk_score", "failure_probability_12m",
        "failure_probability_36m", "saidi_minutes", "saifi_count",
        "estimated_hours", "estimated_cost_aud", "clearance_m",
        "centre_lat", "centre_lon", "radius_km", "priority_score",
    ):
        try:
            float(v)
            return v
        except ValueError:
            pass
    if col in (
        "crew_count", "specialist_crews", "mobile_generation_units",
        "customer_count", "critical_customer_count", "commissioned_year",
        "install_year", "duration_minutes", "customers_interrupted",
        "critical_customers_interrupted", "crew_response_minutes",
        "defect_count", "photo_count", "overdue_days", "risk_threshold",
        "selected_asset_count", "recommended_work_package_count",
        "estimated_customer_impact_reduction", "recommended_unit_size_kva",
    ):
        try:
            int(v)
            return v
        except ValueError:
            pass
    # String — escape single quotes.
    return "'" + v.replace("'", "''") + "'"


def make_insert_statements(table: str, rows: list[dict], catalog: str, schema: str, batch: int = 200):
    cols = TABLE_SCHEMA[table]
    cols_sql = ", ".join(cols)
    for batch_rows in chunked(rows, batch):
        values = []
        for row in batch_rows:
            vals = [python_to_sql_literal(row.get(c, ""), c, table) for c in cols]
            values.append("(" + ", ".join(vals) + ")")
        yield f"INSERT INTO {catalog}.{schema}.{table} ({cols_sql}) VALUES " + ",\n".join(values)


def load_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/synthetic")
    parser.add_argument("--catalog", default=os.getenv("DATABRICKS_CATALOG", "anzgt_may"))
    parser.add_argument("--schema", default=os.getenv("DATABRICKS_SCHEMA_SILVER", "energyq_silver"))
    parser.add_argument("--http-path", default=os.getenv("DATABRICKS_HTTP_PATH"))
    parser.add_argument("--host", default=os.getenv("DATABRICKS_HOST"))
    parser.add_argument("--token", default=os.getenv("DATABRICKS_TOKEN"))
    parser.add_argument("--dry-run", action="store_true", help="Print INSERT statement counts only.")
    parser.add_argument("--batch-size", type=int, default=200)
    args = parser.parse_args()

    inp = Path(args.input)
    if not inp.exists():
        print(f"input not found: {inp}", file=sys.stderr)
        return 2

    print(f"\n  GridLens Queensland — Delta loader")
    print(f"  input={inp.resolve()}  catalog={args.catalog}.{args.schema}")

    plan = []
    for table in TABLE_SCHEMA:
        rows = load_csv(inp / f"{table}.csv")
        plan.append((table, rows))
        print(f"    {table:<35} rows={len(rows):>7}")

    if args.dry_run:
        print("\n  --dry-run mode: not connecting to Databricks.")
        total_statements = 0
        for table, rows in plan:
            n = (len(rows) + args.batch_size - 1) // args.batch_size
            total_statements += n
        print(f"  total INSERT statements planned: {total_statements}")
        return 0

    # Real load.
    try:
        from databricks import sql as dbsql  # type: ignore
    except ImportError:
        print("\n  databricks-sql-connector not installed. pip install databricks-sql-connector", file=sys.stderr)
        return 3

    if not (args.host and args.http_path and args.token):
        print("\n  Set DATABRICKS_HOST, DATABRICKS_HTTP_PATH and DATABRICKS_TOKEN.", file=sys.stderr)
        return 4

    host = args.host.replace("https://", "").replace("http://", "").rstrip("/")
    with dbsql.connect(server_hostname=host, http_path=args.http_path, access_token=args.token) as conn:
        with conn.cursor() as cur:
            for table, rows in plan:
                if not rows:
                    print(f"  - {table}: 0 rows, skipping")
                    continue
                target = f"{args.catalog}.{args.schema}.{table}"
                print(f"  loading {target} ({len(rows)} rows)")
                cur.execute(f"DELETE FROM {target}")
                for stmt in make_insert_statements(table, rows, args.catalog, args.schema, args.batch_size):
                    cur.execute(stmt)
    print("\n  Done loading.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
