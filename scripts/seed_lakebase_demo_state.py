"""
Seed GridLens Queensland Lakebase app state for the demo.

This creates a SQLite database at data/lakebase/gridlens.db (when running
locally without Postgres), or initialises a Postgres database when
LAKEBASE_DATABASE_URL is set.

Seed contents:
- 3 demo users
- 6 saved map views (one per region + state-wide)
- 5 app scenarios matching docs/demo-script.md
- 4 example work packages (2 agent-recommended, 1 approved, 1 draft)
- A handful of agent recommendations with evidence

Usage:
    python scripts/seed_lakebase_demo_state.py
    python scripts/seed_lakebase_demo_state.py --reset
    LAKEBASE_DATABASE_URL=postgres://... python scripts/seed_lakebase_demo_state.py
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_SQL = ROOT / "scripts" / "create_lakebase_schema.sql"
SYNTHETIC_DIR = ROOT / "data" / "synthetic"
LOCAL_DB_PATH = ROOT / "data" / "lakebase" / "gridlens.db"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def short_uuid() -> str:
    return uuid.uuid4().hex[:10]


def load_csv(name: str) -> list[dict]:
    p = SYNTHETIC_DIR / f"{name}.csv"
    if not p.exists():
        return []
    with p.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def adapt_pg_sql_for_sqlite(sql: str) -> str:
    """Translate the Postgres DDL into SQLite-compatible DDL.

    Only what we need to make the demo seed run locally. Postgres usage is
    unaffected.
    """
    out_lines = []
    skip_block = False
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("--") or not stripped:
            out_lines.append(line)
            continue
        if stripped.upper().startswith("SET SEARCH_PATH"):
            continue
        # Replace PG types.
        replaced = (
            line
            .replace("TIMESTAMPTZ", "TEXT")
            .replace("DOUBLE PRECISION", "REAL")
            .replace("DEFAULT now()", "DEFAULT CURRENT_TIMESTAMP")
            .replace("BOOLEAN", "INTEGER")
        )
        if stripped.upper().startswith("CREATE SCHEMA"):
            continue
        out_lines.append(replaced)
    return "\n".join(out_lines)


def _strip_sql_comments(sql: str) -> str:
    lines = []
    for line in sql.splitlines():
        idx = line.find("--")
        if idx >= 0:
            line = line[:idx]
        if line.strip():
            lines.append(line)
    return "\n".join(lines)


def execute_schema(cur, is_sqlite: bool) -> None:
    sql = SCHEMA_SQL.read_text()
    if is_sqlite:
        sql = adapt_pg_sql_for_sqlite(sql)
    sql = _strip_sql_comments(sql)
    statements = [s.strip() for s in sql.split(";") if s.strip()]
    for stmt in statements:
        cur.execute(stmt + ";")


def seed(cur, is_sqlite: bool) -> None:
    """Insert deterministic demo data."""
    users = [
        ("usr_amelia_seq", "Amelia Chen", "amelia.chen@energyq.example.com.au", "planner", "REG-SEQ"),
        ("usr_marcus_mky", "Marcus Tully", "marcus.tully@energyq.example.com.au", "approver", "REG-MKY"),
        ("usr_priya_cqi", "Priya Iyer", "priya.iyer@energyq.example.com.au", "admin", "REG-CQI"),
    ]
    for u in users:
        cur.execute(
            "INSERT OR REPLACE INTO app_users (user_id, display_name, email, role, region_id) VALUES (?, ?, ?, ?, ?)"
            if is_sqlite else
            "INSERT INTO app_users (user_id, display_name, email, role, region_id) VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (user_id) DO NOTHING",
            u,
        )

    saved_views = [
        ("view_state", "Queensland State Overview", "All regions overview at state zoom.",
         None, "normal", -22.6, 145.9, 5.6,
         json.dumps(["assets", "feeders", "outages", "hazards"]), 60, "usr_priya_cqi"),
        ("view_seq", "SEQ Storm Belt", "Brisbane metro storm readiness view.",
         "REG-SEQ", "storm_readiness", -27.47, 153.02, 9.0,
         json.dumps(["assets", "feeders", "outages", "critical_customers"]), 60, "usr_amelia_seq"),
        ("view_mky", "Mackay Demo Cluster", "Pre-storm Mackay corridor.",
         "REG-MKY", "storm_readiness", -21.14, 149.19, 9.5,
         json.dumps(["assets", "vegetation", "hazards", "critical_customers"]), 60, "usr_marcus_mky"),
        ("view_tsv", "Cairns Cyclone Watch", "Tropical cyclone exposure.",
         "REG-TSV", "storm_readiness", -16.92, 145.77, 9.0,
         json.dumps(["assets", "hazards", "vegetation"]), 65, "usr_priya_cqi"),
        ("view_cqi", "CQ Industrial Critical Load", "Gladstone industrial belt.",
         "REG-CQI", "capex_prioritisation", -23.84, 151.26, 9.0,
         json.dumps(["assets", "feeders", "critical_customers"]), 60, "usr_priya_cqi"),
        ("view_rw", "Remote West Mobile Gen", "Long radial feeder restoration.",
         "REG-RW", "field_inspection_review", -23.7, 144.5, 6.5,
         json.dumps(["assets", "feeders", "depots", "mobile_gen"]), 55, "usr_priya_cqi"),
    ]
    for v in saved_views:
        if is_sqlite:
            cur.execute(
                "INSERT OR REPLACE INTO saved_map_views "
                "(view_id, name, description, region_id, scenario_type, center_lat, center_lon, zoom, layers, risk_threshold, created_by) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                v,
            )
        else:
            cur.execute(
                "INSERT INTO saved_map_views "
                "(view_id, name, description, region_id, scenario_type, center_lat, center_lon, zoom, layers, risk_threshold, created_by) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (view_id) DO NOTHING",
                v,
            )

    scenarios = [
        ("scn_mky_storm", "Mackay Storm Readiness 2026", "storm_readiness", "REG-MKY",
         "Pre-cyclone-season readiness pack — high-risk crossarm cluster, vegetation backlog, mobile gen readiness."),
        ("scn_seq_reliability", "SEQ Feeder Reliability Improvement", "reliability_improvement", "REG-SEQ",
         "Recurring storm outages on suburban Brisbane / Logan feeders with high critical customer exposure."),
        ("scn_tsv_cyclone", "Cairns Cyclone & Flood Exposure", "storm_readiness", "REG-TSV",
         "Pre-season inspection coverage + mobile generation readiness for tropical cyclone exposure."),
        ("scn_cqi_capex", "Central Queensland Industrial Capex", "capex_prioritisation", "REG-CQI",
         "High-criticality industrial load with ageing distribution assets — capex round prioritisation."),
        ("scn_rw_mobgen", "Remote West Mobile Generation Plan", "field_inspection_review", "REG-RW",
         "Long radial feeders, sparse depots, plan pre-positioned spares and mobile gen siting."),
    ]
    for s in scenarios:
        s_full = (*s, 60, "usr_priya_cqi", 1 if is_sqlite else True)
        if is_sqlite:
            cur.execute(
                "INSERT OR REPLACE INTO app_scenarios "
                "(scenario_id, scenario_name, scenario_type, region_id, description, risk_threshold, created_by, is_active) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                s_full,
            )
        else:
            cur.execute(
                "INSERT INTO app_scenarios "
                "(scenario_id, scenario_name, scenario_type, region_id, description, risk_threshold, created_by, is_active) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (scenario_id) DO NOTHING",
                s_full,
            )

    # Pre-built work packages — pick a few high-risk assets per region.
    assets = load_csv("assets")
    health = {h["asset_id"]: h for h in load_csv("asset_health_scores")}
    depots = load_csv("depots")
    feeders = load_csv("feeders")
    feeder_index = {f["feeder_id"]: f for f in feeders}

    def pick_assets(region_id: str, n: int) -> list[dict]:
        candidates = [a for a in assets if a["region_id"] == region_id and a["asset_id"] in health]
        ranked = sorted(candidates, key=lambda a: -float(health[a["asset_id"]]["risk_score"]))
        return ranked[:n]

    def nearest_depot(region_id: str) -> str:
        for d in depots:
            if d["region_id"] == region_id:
                return d["depot_id"]
        return ""

    seed_packages = []
    for label, region_id, scenario_type, priority, status, recommended_by_agent in [
        ("Mackay storm crossarm cluster", "REG-MKY", "storm_readiness", "high", "approved", True),
        ("SEQ Brisbane feeder reliability targets", "REG-SEQ", "reliability_improvement", "high", "pending_approval", True),
        ("Cairns pre-cyclone pole hardening", "REG-TSV", "storm_readiness", "urgent", "draft", False),
        ("Gladstone industrial transformer review", "REG-CQI", "capex_prioritisation", "medium", "scheduled", False),
    ]:
        pkg_id = f"WP-{short_uuid()}"
        asset_set = pick_assets(region_id, 8)
        if not asset_set:
            continue
        feeder_id = asset_set[0]["feeder_id"]
        feeder = feeder_index.get(feeder_id, {})
        est_customer_impact = int(int(feeder.get("customer_count", "100")) * 0.30)
        est_hours = round(len(asset_set) * 4.5, 1)
        est_cost = round(est_hours * 285 + 8500, 2)
        evidence = (
            f"Bundles {len(asset_set)} high/critical assets on feeder {feeder_id}. "
            f"Risk drivers: ageing crossarms, vegetation exposure, storm season. "
            f"Estimated impact reduction: {est_customer_impact} customer-minutes."
        )
        if is_sqlite:
            cur.execute(
                "INSERT OR REPLACE INTO work_packages "
                "(work_package_id, title, region_id, feeder_id, scenario_type, priority, status, "
                " created_by, recommended_by_agent, evidence_summary, estimated_hours, estimated_cost_aud, "
                " estimated_customer_impact_reduction, suggested_depot_id, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (pkg_id, label, region_id, feeder_id, scenario_type, priority, status,
                 "usr_amelia_seq", 1 if recommended_by_agent else 0, evidence,
                 est_hours, est_cost, est_customer_impact, nearest_depot(region_id), now_iso()),
            )
        else:
            cur.execute(
                "INSERT INTO work_packages "
                "(work_package_id, title, region_id, feeder_id, scenario_type, priority, status, "
                " created_by, recommended_by_agent, evidence_summary, estimated_hours, estimated_cost_aud, "
                " estimated_customer_impact_reduction, suggested_depot_id, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (pkg_id, label, region_id, feeder_id, scenario_type, priority, status,
                 "usr_amelia_seq", recommended_by_agent, evidence,
                 est_hours, est_cost, est_customer_impact, nearest_depot(region_id), now_iso()),
            )
        for i, a in enumerate(asset_set):
            role = "primary" if i == 0 else "bundled"
            row = (pkg_id, a["asset_id"], role, f"Risk {health[a['asset_id']]['risk_score']}; band {health[a['asset_id']]['risk_band']}")
            if is_sqlite:
                cur.execute(
                    "INSERT OR REPLACE INTO work_package_assets (work_package_id, asset_id, role, notes) VALUES (?, ?, ?, ?)",
                    row,
                )
            else:
                cur.execute(
                    "INSERT INTO work_package_assets (work_package_id, asset_id, role, notes) VALUES (%s, %s, %s, %s) "
                    "ON CONFLICT DO NOTHING",
                    row,
                )

        seed_packages.append((pkg_id, label, region_id, asset_set))

    # Agent recommendations seed.
    for pkg_id, label, region_id, asset_set in seed_packages[:2]:
        rec_id = f"REC-{short_uuid()}"
        prompt = f"Why are the {region_id} assets in {label!r} high risk and what should we do before storm season?"
        body = (
            f"The {label} cluster shows the highest combination of asset age, "
            "coastal corrosion exposure and recent storm-driven outages on the feeder. "
            "Inspection reports flagged crossarm corrosion and reduced vegetation clearance. "
            "Recommend bundling crossarm replacement with vegetation treatment to reduce "
            "crew mobilisations and pre-storm customer impact."
        )
        if is_sqlite:
            cur.execute(
                "INSERT OR REPLACE INTO agent_recommendations "
                "(recommendation_id, work_package_id, user_prompt, agent_response, confidence_score, status) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (rec_id, pkg_id, prompt, body, 0.82, "accepted"),
            )
        else:
            cur.execute(
                "INSERT INTO agent_recommendations "
                "(recommendation_id, work_package_id, user_prompt, agent_response, confidence_score, status) "
                "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (recommendation_id) DO NOTHING",
                (rec_id, pkg_id, prompt, body, 0.82, "accepted"),
            )
        # Evidence
        evidence_rows = [
            (f"EV-{short_uuid()}", rec_id, "delta_table",
             "anzgt_may.energyq_gold.gold_asset_360",
             f"Gold asset 360 risk profile for {asset_set[0]['asset_id']}",
             f"Risk band: critical. Drivers: coastal_corrosion, age, criticality.", 0.88),
            (f"EV-{short_uuid()}", rec_id, "document",
             f"/Volumes/anzgt_may/energyq/asset_docs/{region_id}/inspection_report/INSPECTION_001.md",
             "Most recent inspection report",
             "Crossarm corrosion observed on western side. Vegetation clearance 1.2m vs 2.5m target.", 0.91),
            (f"EV-{short_uuid()}", rec_id, "genie_answer",
             "Genie / Energy Queensland Network Intelligence",
             "What % of high-risk assets have planned remediation?",
             f"Region {region_id}: 28% of high-risk assets currently have planned remediation.", 0.74),
        ]
        for ev in evidence_rows:
            if is_sqlite:
                cur.execute(
                    "INSERT OR REPLACE INTO agent_recommendation_evidence "
                    "(evidence_id, recommendation_id, evidence_type, source_ref, source_title, excerpt, confidence) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    ev,
                )
            else:
                cur.execute(
                    "INSERT INTO agent_recommendation_evidence "
                    "(evidence_id, recommendation_id, evidence_type, source_ref, source_title, excerpt, confidence) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (evidence_id) DO NOTHING",
                    ev,
                )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Drop and recreate the local SQLite database.")
    parser.add_argument("--database-url", default=os.getenv("LAKEBASE_DATABASE_URL"))
    args = parser.parse_args()

    url = args.database_url
    if url:
        try:
            import psycopg  # type: ignore
        except ImportError:
            print("psycopg not installed. pip install psycopg[binary]", file=sys.stderr)
            return 2
        print(f"connecting to {url.split('@')[-1]}")
        with psycopg.connect(url, autocommit=True) as conn:
            with conn.cursor() as cur:
                execute_schema(cur, is_sqlite=False)
                seed(cur, is_sqlite=False)
    else:
        LOCAL_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        if args.reset and LOCAL_DB_PATH.exists():
            LOCAL_DB_PATH.unlink()
        conn = sqlite3.connect(LOCAL_DB_PATH)
        try:
            cur = conn.cursor()
            execute_schema(cur, is_sqlite=True)
            seed(cur, is_sqlite=True)
            conn.commit()
            print(f"Seeded local SQLite Lakebase mock at {LOCAL_DB_PATH}")
        finally:
            conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
