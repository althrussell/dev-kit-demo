"""
GridLens Queensland — Databricks agent / data primitive provisioner.

Idempotent end-to-end provisioning for the four real Databricks resources the
demo depends on:

  1. Lakebase Autoscaling project `gridlens`           (Postgres OLTP store)
  2. Genie Space         `GridLens Queensland - Network Intelligence`
  3. Knowledge Assistant `gridlens-asset-docs`         (RAG over UC volume)
  4. Supervisor MAS      `gridlens-supervisor`         (routes Genie + KA)

Lakebase is provisioned headlessly via the Databricks Python SDK.

Genie / KA / MAS creation is exposed via Cursor MCP tools (`create_or_update_genie`,
`manage_ka`, `manage_mas`). This script writes their canonical configuration to
`scripts/.agent_bricks_state.json` and prints the exact MCP calls the operator
(or this repo's Cursor agent) needs to run; once they run, the file is updated
with the returned IDs so subsequent runs are idempotent.

Usage
-----
    # Provision Lakebase only
    python scripts/provision_databricks_agents.py --lakebase \\
        --profile servco

    # Apply Postgres DDL + seed
    python scripts/provision_databricks_agents.py --seed --profile servco

    # Print Genie / KA / MAS canonical config (no Databricks calls)
    python scripts/provision_databricks_agents.py --print-bricks

    # End-to-end
    python scripts/provision_databricks_agents.py --all --profile servco
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_SQL = ROOT / "scripts" / "create_lakebase_schema.sql"
STATE_FILE = ROOT / "scripts" / ".agent_bricks_state.json"

# ---------------------------------------------------------------------------
# Canonical configuration
# ---------------------------------------------------------------------------

APP_SP_CLIENT_ID = "f02e1450-0f82-453d-b95b-25aa6056200b"  # app-3fu42r gridlens

LAKEBASE_PROJECT_ID = "gridlens"
LAKEBASE_DISPLAY_NAME = "GridLens Queensland"
LAKEBASE_PG_VERSION = "17"
LAKEBASE_AUTOSCALE_MIN_CU = 0.5
LAKEBASE_AUTOSCALE_MAX_CU = 2.0
LAKEBASE_SCALE_TO_ZERO_SECONDS = 300
LAKEBASE_BRANCH_ID = "production"
LAKEBASE_ENDPOINT_ID = "primary"
LAKEBASE_DATABASE = "databricks_postgres"

CATALOG = "anzgt_may"
SCHEMA_SILVER = "energyq_silver"
SCHEMA_GOLD = "energyq_gold"
VOLUME_PATH = "/Volumes/anzgt_may/energyq/asset_docs"

GENIE_SPACE_NAME = "GridLens Queensland - Network Intelligence"
GENIE_DESCRIPTION = (
    "Natural-language analytics over Queensland's synthetic electricity "
    "distribution network. Use this to ask about regional risk, feeder "
    "outage history, vegetation backlog, asset health, customer exposure, "
    "storm readiness and work prioritisation."
)
GENIE_TABLES: list[str] = [
    # Gold (curated KPIs / personas)
    f"{CATALOG}.{SCHEMA_GOLD}.gold_asset_360",
    f"{CATALOG}.{SCHEMA_GOLD}.gold_feeder_risk_summary",
    f"{CATALOG}.{SCHEMA_GOLD}.gold_regional_risk_summary",
    f"{CATALOG}.{SCHEMA_GOLD}.gold_storm_readiness",
    f"{CATALOG}.{SCHEMA_GOLD}.gold_work_prioritisation",
    f"{CATALOG}.{SCHEMA_GOLD}.gold_genie_metrics",
    # Silver (entities)
    f"{CATALOG}.{SCHEMA_SILVER}.assets",
    f"{CATALOG}.{SCHEMA_SILVER}.feeders",
    f"{CATALOG}.{SCHEMA_SILVER}.regions",
    f"{CATALOG}.{SCHEMA_SILVER}.vegetation_spans",
    f"{CATALOG}.{SCHEMA_SILVER}.outage_events",
    f"{CATALOG}.{SCHEMA_SILVER}.hazard_exposure_zones",
    f"{CATALOG}.{SCHEMA_SILVER}.work_orders",
    f"{CATALOG}.{SCHEMA_SILVER}.critical_customers",
    f"{CATALOG}.{SCHEMA_SILVER}.depots",
    f"{CATALOG}.{SCHEMA_SILVER}.inspection_events",
]
GENIE_SAMPLE_QUESTIONS: list[str] = [
    "Which regions have the highest storm-season asset risk?",
    "Show me feeders with repeated vegetation-related outages in the last 12 months.",
    "Rank regions by vegetation backlog (spans overdue by more than 30 days).",
    "What is our planned remediation coverage by region?",
    "Which 10 feeders should we prioritise work on?",
    "How many critical customers are exposed to high-risk assets, by region?",
    "Which assets are within 5km of an active cyclone, storm or flood hazard zone?",
    "What is the failure probability profile by asset class in Far North Queensland?",
]
GENIE_INSTRUCTIONS = """\
You are the Network Intelligence analyst for Energy Queensland's distribution network.

When answering, ALWAYS:
- Use fully-qualified table names: `anzgt_may.energyq_gold.<table>` and `anzgt_may.energyq_silver.<table>`.
- Prefer the gold views for aggregated questions: gold_asset_360, gold_feeder_risk_summary, gold_regional_risk_summary, gold_storm_readiness, gold_vegetation_risk_index, gold_work_prioritisation.
- Group/order region names from the `regions` table (do not use raw region_id codes in user-facing output).

Personas:
- Spatial-risk: join hazard_zones to assets by region or distance; consider feeder length and customer count.
- Asset-health: use gold_asset_360 (risk_score, risk_band, risk_drivers, failure_probability_12m).
- Outage-impact: aggregate outage_events by feeder/region; surface customers_interrupted and critical_customers_interrupted.
- Vegetation: use vegetation_spans.overdue_days > 30 as the backlog threshold.
- Compliance: tie back to the work_orders table (status in approved/scheduled/in_progress).
- Hazard zones: join `hazard_exposure_zones` (not `hazard_zones`) to assets by region or distance; hazard_type filters: cyclone, storm, flood, bushfire.

Risk bands:
- low: 0-40, medium: 41-55, high: 56-75, critical: 76+.

Critical customers include: hospitals, aged care, emergency services, water pumping, telecom, airport, industrial and schools.
"""

KA_NAME = "gridlens-asset-docs"
KA_DESCRIPTION = (
    "Grounded Q&A over Queensland network asset documents: inspection reports, "
    "work orders, engineering drawings, vegetation surveys and maintenance standards."
)
KA_INSTRUCTIONS = """\
You answer grounded questions about Queensland network assets using inspection
reports, work orders, engineering drawings, vegetation surveys and regional
maintenance standards stored in the UC volume.

For every answer:
- Cite the document ID (e.g. DOC-000126) and the region ID (e.g. REG-MKY).
- Distinguish document types: inspection_report, work_order_pdf, engineering_drawing, vegetation_survey, maintenance_standard.
- Quote at most two short verbatim excerpts; otherwise summarise faithfully.
- If asked about specific assets, scan documents for asset IDs in the form AST-XXX-XXX-NNNNNN.
- If you can't find evidence in the documents, say so explicitly. Do NOT fabricate.
"""

MAS_NAME = "gridlens-supervisor"
MAS_DESCRIPTION = (
    "Operations supervisor that routes between the Network Intelligence Genie "
    "space (data) and the Asset Documents Knowledge Assistant (documents) to "
    "answer storm readiness, asset risk, vegetation, outage, work planning and "
    "compliance questions for Queensland's distribution network."
)
MAS_INSTRUCTIONS = """\
You are the GridLens operations supervisor for Energy Queensland.

You have two specialist agents:

1. `network_analytics` — Genie space that runs SQL on Delta tables. Use for any
   question that needs counts, rankings, distributions, time-series, or
   thresholds over assets, feeders, outages, vegetation, hazards, customers or
   work orders.

2. `document_intelligence` — Knowledge Assistant over the asset_docs UC volume.
   Use for any question that needs evidence from inspection reports, work
   orders, engineering drawings, vegetation surveys or maintenance standards.

Routing rules:
- Quantitative questions ("how many", "what %", "rank", "top N", "trend") -> network_analytics.
- Evidence questions ("why", "what did the last inspection say", "is there a standard for") -> document_intelligence.
- Investigation questions (the user has selected an asset / feeder / region and asks for a recommendation) -> call BOTH agents:
    a) network_analytics for risk, outage, customer-exposure context.
    b) document_intelligence for inspection / work order / vegetation evidence.
   Then synthesise a recommendation that cites both.

Output rules:
- Lead with a one-sentence headline.
- Then evidence as a bulleted list with explicit citations: SQL summary (with table) for network_analytics, doc IDs for document_intelligence.
- Then a confidence score (0.0-1.0) reflecting both agents' confidence.
- Then 3-5 next-step actions for an asset planner.

Never make up numbers or document IDs. If neither agent can answer, say so.
"""
MAS_EXAMPLES = [
    {
        "question": "Why is feeder FDR-MKY-0042 high risk and what should we do before storm season?",
        "guideline": (
            "Call network_analytics for risk profile, customer count and outage history on that feeder. "
            "Call document_intelligence for the latest inspection reports + work orders on assets on the feeder. "
            "Synthesise a bundled remediation recommendation with depot routing."
        ),
    },
    {
        "question": "Which regions have the highest storm-season asset risk?",
        "guideline": "Pure analytics question. Route to network_analytics only. Use gold_regional_risk_summary.",
    },
    {
        "question": "Show me feeders with repeated vegetation-related outages in the last 12 months.",
        "guideline": "Analytics over outage_events filtered by cause_category='vegetation'. Route to network_analytics.",
    },
    {
        "question": "What does the last inspection say about asset AST-MKY-CRA-001234?",
        "guideline": "Document retrieval only. Route to document_intelligence. Cite the document ID.",
    },
    {
        "question": "Are there compliance standards for vegetation clearance in REG-TSV?",
        "guideline": (
            "Document retrieval question. Route to document_intelligence to find the maintenance standard, "
            "then optionally summarise vegetation_spans backlog from network_analytics."
        ),
    },
]


# ---------------------------------------------------------------------------
# State file helpers
# ---------------------------------------------------------------------------

def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True))
    print(f"[state] wrote {STATE_FILE.relative_to(ROOT)}")


# ---------------------------------------------------------------------------
# Lakebase Autoscaling provisioner (Databricks SDK)
# ---------------------------------------------------------------------------

def _ws_client(profile: Optional[str]):
    from databricks.sdk import WorkspaceClient
    if profile:
        os.environ["DATABRICKS_CONFIG_PROFILE"] = profile
    return WorkspaceClient()


def provision_lakebase(profile: Optional[str]) -> dict:
    """Idempotently create the Lakebase Autoscaling project + endpoint."""
    print(f"[lakebase] using profile {profile or '(default)'}")
    w = _ws_client(profile)

    project_name = f"projects/{LAKEBASE_PROJECT_ID}"
    endpoint_name = f"{project_name}/branches/{LAKEBASE_BRANCH_ID}/endpoints/{LAKEBASE_ENDPOINT_ID}"

    # 1. Project
    try:
        proj = w.postgres.get_project(name=project_name)
        print(f"[lakebase] project {project_name} already exists (state={getattr(proj.status, 'state', '?')})")
    except Exception:
        from databricks.sdk.service.postgres import Project, ProjectSpec
        print(f"[lakebase] creating project {project_name} ...")
        op = w.postgres.create_project(
            project=Project(
                spec=ProjectSpec(
                    display_name=LAKEBASE_DISPLAY_NAME,
                    pg_version=LAKEBASE_PG_VERSION,
                )
            ),
            project_id=LAKEBASE_PROJECT_ID,
        )
        # SDK 0.108+ exposes wait() that returns the resource
        proj = op.wait()
        print(f"[lakebase] created {proj.name}")

    # 2. Endpoint — set autoscaling + scale-to-zero
    try:
        endpoint = w.postgres.get_endpoint(name=endpoint_name)
        print(f"[lakebase] endpoint {endpoint_name} exists")
    except Exception:
        print(f"[lakebase] endpoint {endpoint_name} not found; the SDK auto-creates ep-primary "
              "on the production branch. Trying again in 10s...")
        time.sleep(10)
        endpoint = w.postgres.get_endpoint(name=endpoint_name)

    from databricks.sdk.service.postgres import (
        Endpoint, EndpointSpec, EndpointType, FieldMask, Duration,
    )
    print(f"[lakebase] updating endpoint to autoscale {LAKEBASE_AUTOSCALE_MIN_CU}-{LAKEBASE_AUTOSCALE_MAX_CU} CU "
          f"with scale-to-zero {LAKEBASE_SCALE_TO_ZERO_SECONDS}s")
    suspend_duration = Duration()
    suspend_duration.seconds = LAKEBASE_SCALE_TO_ZERO_SECONDS
    update_op = w.postgres.update_endpoint(
        name=endpoint_name,
        endpoint=Endpoint(
            name=endpoint_name,
            spec=EndpointSpec(
                endpoint_type=EndpointType.ENDPOINT_TYPE_READ_WRITE,
                autoscaling_limit_min_cu=LAKEBASE_AUTOSCALE_MIN_CU,
                autoscaling_limit_max_cu=LAKEBASE_AUTOSCALE_MAX_CU,
                suspend_timeout_duration=suspend_duration,
            ),
        ),
        update_mask=FieldMask(field_mask=[
            "spec.autoscaling_limit_min_cu",
            "spec.autoscaling_limit_max_cu",
        ]),
    )
    try:
        update_op.wait()
    except Exception as e:
        # Non-fatal — endpoint exists, settings may already match.
        print(f"[lakebase] update_endpoint returned: {e}")

    host = w.postgres.get_endpoint(name=endpoint_name).status.hosts.host
    print(f"[lakebase] endpoint host: {host}")

    # 3. Ensure the app SP is a Postgres role with OAuth auth on this branch.
    branch_name = f"{project_name}/branches/{LAKEBASE_BRANCH_ID}"
    _ensure_sp_role(w, branch_name)

    state = _load_state()
    state.setdefault("lakebase", {}).update({
        "project_name": project_name,
        "branch_id": LAKEBASE_BRANCH_ID,
        "endpoint_name": endpoint_name,
        "host": host,
        "database": LAKEBASE_DATABASE,
        "autoscale_min_cu": LAKEBASE_AUTOSCALE_MIN_CU,
        "autoscale_max_cu": LAKEBASE_AUTOSCALE_MAX_CU,
        "scale_to_zero_seconds": LAKEBASE_SCALE_TO_ZERO_SECONDS,
    })
    _save_state(state)
    return state["lakebase"]


def _ensure_sp_role(w, branch_name: str) -> None:
    """Create the app service principal as a Postgres OAuth role on the branch."""
    from databricks.sdk.service.postgres import (
        Role, RoleRoleSpec, RoleIdentityType, RoleAuthMethod,
    )

    role_id = APP_SP_CLIENT_ID
    full_role_name = f"{branch_name}/roles/{role_id}"
    try:
        existing = w.postgres.get_role(name=full_role_name)
        print(f"[lakebase] SP role already exists: {existing.name}")
        return
    except Exception:
        pass

    print(f"[lakebase] creating SP Postgres role for {role_id} on {branch_name}")
    try:
        op = w.postgres.create_role(
            parent=branch_name,
            role=Role(
                spec=RoleRoleSpec(
                    identity_type=RoleIdentityType.SERVICE_PRINCIPAL,
                    auth_method=RoleAuthMethod.LAKEBASE_OAUTH_V1,
                    postgres_role=role_id,
                ),
            ),
            role_id=role_id,
        )
        role = op.wait()
        print(f"[lakebase] SP role ready: {role.name}")
    except Exception as e:
        print(f"[lakebase] SP role creation failed (non-fatal, app may still auth): {e}")


def mint_token(profile: Optional[str], endpoint_name: str) -> str:
    """Return a fresh OAuth token for the Lakebase endpoint."""
    w = _ws_client(profile)
    cred = w.postgres.generate_database_credential(endpoint=endpoint_name)
    return cred.token


def apply_schema_and_seed(profile: Optional[str]) -> None:
    """Connect via psycopg, apply DDL, seed deterministic demo data."""
    try:
        import psycopg
    except ImportError:
        print("psycopg not installed. pip install 'psycopg[binary]>=3.0'", file=sys.stderr)
        sys.exit(2)

    state = _load_state().get("lakebase") or {}
    if not state.get("host"):
        print("[lakebase] no host in state file. Run with --lakebase first.", file=sys.stderr)
        sys.exit(2)
    host = state["host"]
    endpoint_name = state["endpoint_name"]
    database = state["database"]

    w = _ws_client(profile)
    user = w.current_user.me().user_name
    token = mint_token(profile, endpoint_name)

    conn_str = (
        f"host={host} dbname={database} user={user} "
        f"password={token} sslmode=require"
    )
    print(f"[lakebase] connecting as {user} to {host}/{database}")
    with psycopg.connect(conn_str, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT version();")
            print(f"[lakebase] {cur.fetchone()[0]}")

            sql = SCHEMA_SQL.read_text()
            statements = _split_sql(sql)
            print(f"[lakebase] applying {len(statements)} DDL statements")
            for stmt in statements:
                try:
                    cur.execute(stmt)
                except Exception as e:
                    print(f"[lakebase] WARN ddl: {e}\n--statement--\n{stmt[:200]}")

            # Grant the app SP access. Role was pre-created via _ensure_sp_role,
            # so this should succeed. Granting USAGE + CREATE on the schema and
            # full CRUD on all tables; ALTER DEFAULT PRIVILEGES makes future
            # tables inherit the grant.
            sp_role = APP_SP_CLIENT_ID
            try:
                cur.execute(f'GRANT USAGE, CREATE ON SCHEMA gridlens TO "{sp_role}"')
                cur.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA gridlens TO "{sp_role}"')
                cur.execute(
                    f'ALTER DEFAULT PRIVILEGES IN SCHEMA gridlens GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "{sp_role}"'
                )
                print(f"[lakebase] granted SP {sp_role} CRUD on schema gridlens")
            except Exception as e:
                print(f"[lakebase] grant SP failed: {e}")

    # Seed via existing seed script's logic, but in Postgres mode.
    # Use the keyword-form conn string (not a URI) to avoid url-encoding the
    # email-shaped username.
    print("[lakebase] seeding demo data via scripts/seed_lakebase_demo_state.py")
    import subprocess
    db_url = f"host={host} port=5432 dbname={database} user={user} password={token} sslmode=require"
    res = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "seed_lakebase_demo_state.py"),
         "--database-url", db_url],
        cwd=str(ROOT),
        env={**os.environ, "LAKEBASE_DATABASE_URL": db_url},
    )
    if res.returncode != 0:
        print(f"[lakebase] seed exited with {res.returncode}")
        sys.exit(res.returncode)
    print("[lakebase] seed complete")


def _strip_sql_comments(sql: str) -> str:
    """Remove '-- ...' line comments so they don't confuse the splitter."""
    out_lines = []
    for line in sql.splitlines():
        idx = line.find("--")
        if idx >= 0:
            line = line[:idx]
        out_lines.append(line)
    return "\n".join(out_lines)


def _split_sql(sql: str) -> list[str]:
    """Split SQL on ';' boundaries while respecting single-quoted strings.

    Comments are stripped first so that ';' or "'" inside comments doesn't
    affect the parser.
    """
    sql = _strip_sql_comments(sql)
    out: list[str] = []
    buf: list[str] = []
    in_str = False
    for ch in sql:
        if ch == "'" and (not buf or buf[-1] != "\\"):
            in_str = not in_str
        if ch == ";" and not in_str:
            stmt = "".join(buf).strip()
            if stmt:
                out.append(stmt)
            buf = []
            continue
        buf.append(ch)
    final = "".join(buf).strip()
    if final:
        out.append(final)
    return out


# ---------------------------------------------------------------------------
# Agent Bricks config (Genie / KA / MAS)
# ---------------------------------------------------------------------------

def print_bricks_config() -> None:
    """Print canonical Agent Bricks configuration for MCP-driven creation."""
    state = _load_state()
    genie_state = state.get("genie", {})
    ka_state = state.get("ka", {})
    mas_state = state.get("mas", {})

    print("\n=== Genie Space ===")
    print(f"  name:        {GENIE_SPACE_NAME}")
    print(f"  description: {GENIE_DESCRIPTION}")
    print(f"  tables:      {len(GENIE_TABLES)} (gold + silver)")
    for t in GENIE_TABLES:
        print(f"    - {t}")
    print(f"  sample_questions: {len(GENIE_SAMPLE_QUESTIONS)}")
    print(f"  current_space_id: {genie_state.get('space_id', '(not provisioned)')}")
    print(f"\n  MCP call:")
    print(f"    create_or_update_genie(\n"
          f"      display_name={GENIE_SPACE_NAME!r},\n"
          f"      table_identifiers={GENIE_TABLES!r},\n"
          f"      description={GENIE_DESCRIPTION!r},\n"
          f"      sample_questions={GENIE_SAMPLE_QUESTIONS!r},\n"
          f"      instructions={GENIE_INSTRUCTIONS!r},\n"
          f"    )")

    print("\n=== Knowledge Assistant ===")
    print(f"  name:        {KA_NAME}")
    print(f"  volume_path: {VOLUME_PATH}")
    print(f"  current_tile_id: {ka_state.get('tile_id', '(not provisioned)')}")
    print(f"  current_endpoint: {ka_state.get('endpoint_name', '(not provisioned)')}")
    print(f"\n  MCP call:")
    print(f"    manage_ka(\n"
          f"      action='create_or_update',\n"
          f"      name={KA_NAME!r},\n"
          f"      volume_path={VOLUME_PATH!r},\n"
          f"      description={KA_DESCRIPTION!r},\n"
          f"      instructions={KA_INSTRUCTIONS!r},\n"
          f"      add_examples_from_volume=False,\n"
          f"    )")

    print("\n=== Supervisor MAS ===")
    print(f"  name:        {MAS_NAME}")
    print(f"  agents:      network_analytics (Genie), document_intelligence (KA)")
    print(f"  current_tile_id: {mas_state.get('tile_id', '(not provisioned)')}")
    print(f"  current_endpoint: {mas_state.get('endpoint_name', '(not provisioned)')}")
    print(f"\n  MCP call: (requires Genie space_id + KA tile_id from above)")
    print(f"    manage_mas(\n"
          f"      action='create_or_update',\n"
          f"      name={MAS_NAME!r},\n"
          f"      description={MAS_DESCRIPTION!r},\n"
          f"      instructions={MAS_INSTRUCTIONS!r},\n"
          f"      agents=[\n"
          f"        {{'name': 'network_analytics', 'genie_space_id': '<genie_space_id>',\n"
          f"          'description': 'Run SQL on UC Delta tables to answer questions about asset risk, "
          f"outages, vegetation, feeders, customer exposure and work prioritisation.'}},\n"
          f"        {{'name': 'document_intelligence', 'ka_tile_id': '<ka_tile_id>',\n"
          f"          'description': 'Search inspection reports, work orders, engineering drawings, "
          f"vegetation surveys and maintenance standards on the UC volume.'}},\n"
          f"      ],\n"
          f"      examples={MAS_EXAMPLES!r},\n"
          f"    )")
    print()


def record_genie(space_id: str) -> None:
    state = _load_state()
    state.setdefault("genie", {})["space_id"] = space_id
    state["genie"]["display_name"] = GENIE_SPACE_NAME
    _save_state(state)


def record_ka(tile_id: str, endpoint_name: str) -> None:
    state = _load_state()
    state.setdefault("ka", {}).update({
        "tile_id": tile_id,
        "endpoint_name": endpoint_name,
        "name": KA_NAME,
    })
    _save_state(state)


def record_mas(tile_id: str, endpoint_name: str) -> None:
    state = _load_state()
    state.setdefault("mas", {}).update({
        "tile_id": tile_id,
        "endpoint_name": endpoint_name,
        "name": MAS_NAME,
    })
    _save_state(state)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default=os.getenv("DATABRICKS_CONFIG_PROFILE"),
                        help="Databricks CLI profile (e.g. servco)")
    parser.add_argument("--lakebase", action="store_true",
                        help="Provision Lakebase Autoscaling project + endpoint")
    parser.add_argument("--seed", action="store_true",
                        help="Apply Postgres DDL + seed demo data")
    parser.add_argument("--print-bricks", action="store_true",
                        help="Print canonical Genie / KA / MAS config + MCP calls")
    parser.add_argument("--all", action="store_true",
                        help="Run --lakebase then --seed then --print-bricks")
    parser.add_argument("--state", action="store_true",
                        help="Print current state file contents")
    args = parser.parse_args()

    if args.state:
        print(json.dumps(_load_state(), indent=2, sort_keys=True))
        return 0
    if args.all:
        args.lakebase = args.seed = args.print_bricks = True

    if args.lakebase:
        provision_lakebase(args.profile)
    if args.seed:
        apply_schema_and_seed(args.profile)
    if args.print_bricks:
        print_bricks_config()
    if not (args.lakebase or args.seed or args.print_bricks):
        parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
