"""Bootstrap PostGIS spatial schema on the GridLens Lakebase instance.

This script:
  1. Connects to the `gridlens` Lakebase Autoscale project / production branch.
  2. Installs the PostGIS extension if not already present.
  3. Creates a `gridlens_geo` schema with `assets_geom`, `hazard_zones_geom`,
     and `critical_customers_geom` tables containing real PostGIS geometry
     columns (geography/Point and geography/Polygon for hazard radii).
  4. Bulk-loads the synthetic CSVs into those tables.
  5. Adds GIST spatial indexes so ST_DWithin / ST_Intersects queries are fast.

It is idempotent — re-running drops + reloads the data rows but leaves
extensions and schemas in place.

Environment:
  DATABRICKS_CONFIG_PROFILE   — Databricks workspace profile (default: DEFAULT)
  LAKEBASE_PROJECT            — Lakebase project id (default: gridlens)
  LAKEBASE_BRANCH             — Branch id (default: production)
  LAKEBASE_ENDPOINT           — Endpoint id (default: primary)
  LAKEBASE_DATABASE           — Postgres database (default: databricks_postgres)
"""

from __future__ import annotations

import csv
import io
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import psycopg
from databricks.sdk import WorkspaceClient

DATA_DIR = REPO_ROOT / "data" / "synthetic"

PROJECT = os.environ.get("LAKEBASE_PROJECT", "gridlens")
BRANCH = os.environ.get("LAKEBASE_BRANCH", "production")
ENDPOINT = os.environ.get("LAKEBASE_ENDPOINT", "primary")
DATABASE = os.environ.get("LAKEBASE_DATABASE", "databricks_postgres")

SCHEMA = "gridlens_geo"


def get_connection() -> psycopg.Connection:
    w = WorkspaceClient()
    ep_name = f"projects/{PROJECT}/branches/{BRANCH}/endpoints/{ENDPOINT}"
    ep = w.postgres.get_endpoint(name=ep_name)
    host = ep.status.hosts.host
    cred = w.postgres.generate_database_credential(endpoint=ep_name)
    user = w.current_user.me().user_name
    conn_string = (
        f"host={host} dbname={DATABASE} user={user} "
        f"password={cred.token} sslmode=require"
    )
    print(f"[lakebase] connecting to {host} db={DATABASE} as {user}")
    return psycopg.connect(conn_string)


def install_postgis(cur: psycopg.Cursor) -> None:
    print("[lakebase] ensuring postgis extension...")
    cur.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    cur.execute("SELECT postgis_full_version()")
    print(f"  -> {cur.fetchone()[0]}")


def create_schema(cur: psycopg.Cursor) -> None:
    cur.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.assets_geom (
            asset_id        TEXT PRIMARY KEY,
            feeder_id       TEXT NOT NULL,
            substation_id   TEXT,
            region_id       TEXT NOT NULL,
            asset_type      TEXT NOT NULL,
            install_year    INT,
            voltage_kv      DOUBLE PRECISION,
            criticality     DOUBLE PRECISION,
            cyclone_score   DOUBLE PRECISION,
            flood_score     DOUBLE PRECISION,
            bushfire_score  DOUBLE PRECISION,
            corrosion_score DOUBLE PRECISION,
            risk_score      DOUBLE PRECISION,
            risk_band       TEXT,
            geom            geography(Point, 4326) NOT NULL
        )
        """
    )
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.hazard_zones_geom (
            hazard_zone_id  TEXT PRIMARY KEY,
            region_id       TEXT NOT NULL,
            hazard_type     TEXT NOT NULL,
            zone_name       TEXT,
            radius_km       DOUBLE PRECISION,
            severity_score  DOUBLE PRECISION,
            seasonal_window TEXT,
            geom            geography(Polygon, 4326) NOT NULL,
            center          geography(Point, 4326) NOT NULL
        )
        """
    )
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.critical_customers_geom (
            critical_customer_id TEXT PRIMARY KEY,
            region_id            TEXT NOT NULL,
            feeder_id            TEXT,
            site_name            TEXT,
            site_type            TEXT,
            backup_power_status  TEXT,
            priority_score       DOUBLE PRECISION,
            geom                 geography(Point, 4326) NOT NULL
        )
        """
    )
    # Spatial indexes.
    cur.execute(f"CREATE INDEX IF NOT EXISTS assets_geom_gix ON {SCHEMA}.assets_geom USING GIST(geom)")
    cur.execute(f"CREATE INDEX IF NOT EXISTS hazards_geom_gix ON {SCHEMA}.hazard_zones_geom USING GIST(geom)")
    cur.execute(f"CREATE INDEX IF NOT EXISTS hazards_center_gix ON {SCHEMA}.hazard_zones_geom USING GIST(center)")
    cur.execute(f"CREATE INDEX IF NOT EXISTS cc_geom_gix ON {SCHEMA}.critical_customers_geom USING GIST(geom)")
    print("[lakebase] schema/tables/indexes ready")


def _float(v, default=0.0):
    if v in (None, ""):
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _int(v, default=None):
    if v in (None, ""):
        return default
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def load_assets(cur: psycopg.Cursor) -> None:
    print("[lakebase] loading assets...")
    cur.execute(f"TRUNCATE {SCHEMA}.assets_geom")
    asset_rows = list(csv.DictReader(open(DATA_DIR / "assets.csv")))
    health_rows = {r["asset_id"]: r for r in csv.DictReader(open(DATA_DIR / "asset_health_scores.csv"))}

    rows = []
    for a in asset_rows:
        h = health_rows.get(a["asset_id"], {})
        rows.append((
            a["asset_id"],
            a["feeder_id"],
            a.get("substation_id"),
            a["region_id"],
            a["asset_type"],
            _int(a.get("install_year")),
            _float(a.get("voltage_kv")),
            _float(a.get("criticality_score")),
            _float(a.get("cyclone_exposure_score")),
            _float(a.get("flood_exposure_score")),
            _float(a.get("bushfire_exposure_score")),
            _float(a.get("coastal_corrosion_score")),
            _float(h.get("risk_score")),
            h.get("risk_band"),
            float(a["lon"]),
            float(a["lat"]),
        ))

    with cur.copy(
        f"COPY {SCHEMA}.assets_geom "
        "(asset_id, feeder_id, substation_id, region_id, asset_type, install_year, voltage_kv, "
        "criticality, cyclone_score, flood_score, bushfire_score, corrosion_score, risk_score, risk_band, geom) "
        "FROM STDIN WITH (FORMAT csv)"
    ) as copy:
        buf = io.StringIO()
        writer = csv.writer(buf)
        for r in rows:
            # geom as well-known text POINT(lon lat).
            writer.writerow(list(r[:-2]) + [f"SRID=4326;POINT({r[-2]} {r[-1]})"])
        copy.write(buf.getvalue())
    print(f"  -> {len(rows)} asset geometries loaded")


def load_hazards(cur: psycopg.Cursor) -> None:
    print("[lakebase] loading hazard zones (as buffered polygons)...")
    cur.execute(f"TRUNCATE {SCHEMA}.hazard_zones_geom")
    rows = list(csv.DictReader(open(DATA_DIR / "hazard_exposure_zones.csv")))
    for h in rows:
        lat = float(h["lat"])
        lon = float(h["lon"])
        radius_m = float(h["radius_km"]) * 1000.0
        # Build a buffered point as the polygon footprint (geography buffers
        # are returned in meters).
        cur.execute(
            f"""
            INSERT INTO {SCHEMA}.hazard_zones_geom
                (hazard_zone_id, region_id, hazard_type, zone_name, radius_km,
                 severity_score, seasonal_window, geom, center)
            VALUES (
                %s, %s, %s, %s, %s, %s, %s,
                ST_Buffer(ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)::geography,
                ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
            )
            """,
            (
                h["hazard_zone_id"], h["region_id"], h["hazard_type"], h.get("zone_name"),
                float(h["radius_km"]), _float(h.get("severity_score")), h.get("seasonal_window"),
                lon, lat, radius_m,
                lon, lat,
            ),
        )
    print(f"  -> {len(rows)} hazard polygons loaded")


def load_critical_customers(cur: psycopg.Cursor) -> None:
    print("[lakebase] loading critical customers...")
    cur.execute(f"TRUNCATE {SCHEMA}.critical_customers_geom")
    rows = list(csv.DictReader(open(DATA_DIR / "critical_customers.csv")))
    payload = []
    for c in rows:
        payload.append((
            c["critical_customer_id"], c["region_id"], c.get("feeder_id"),
            c.get("site_name"), c.get("site_type"), c.get("backup_power_status"),
            _float(c.get("priority_score")),
            float(c["lon"]), float(c["lat"]),
        ))
    with cur.copy(
        f"COPY {SCHEMA}.critical_customers_geom "
        "(critical_customer_id, region_id, feeder_id, site_name, site_type, "
        "backup_power_status, priority_score, geom) FROM STDIN WITH (FORMAT csv)"
    ) as copy:
        buf = io.StringIO()
        writer = csv.writer(buf)
        for r in payload:
            writer.writerow(list(r[:-2]) + [f"SRID=4326;POINT({r[-2]} {r[-1]})"])
        copy.write(buf.getvalue())
    print(f"  -> {len(payload)} critical customer geometries loaded")


def smoke_test(cur: psycopg.Cursor) -> None:
    print("\n[lakebase] sanity queries:")
    cur.execute(f"SELECT COUNT(*) FROM {SCHEMA}.assets_geom")
    print(f"  assets_geom rows: {cur.fetchone()[0]}")
    cur.execute(f"SELECT COUNT(*) FROM {SCHEMA}.hazard_zones_geom")
    print(f"  hazard_zones_geom rows: {cur.fetchone()[0]}")
    cur.execute(f"SELECT COUNT(*) FROM {SCHEMA}.critical_customers_geom")
    print(f"  critical_customers_geom rows: {cur.fetchone()[0]}")

    # Real spatial query: how many assets within 25km of a high-severity cyclone hazard?
    cur.execute(
        f"""
        SELECT COUNT(DISTINCT a.asset_id)
        FROM {SCHEMA}.assets_geom a
        JOIN {SCHEMA}.hazard_zones_geom h
          ON ST_DWithin(a.geom, h.center, 25000)
        WHERE h.hazard_type = 'cyclone' AND h.severity_score >= 60
        """
    )
    print(f"  assets within 25km of severe cyclone hazards: {cur.fetchone()[0]}")


def main() -> None:
    t0 = time.time()
    with get_connection() as conn:
        with conn.cursor() as cur:
            install_postgis(cur)
            create_schema(cur)
            load_assets(cur)
            load_hazards(cur)
            load_critical_customers(cur)
            conn.commit()
            smoke_test(cur)
    print(f"\n[lakebase] done in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
