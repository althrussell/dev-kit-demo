"""
GridLens Queensland — one-shot Databricks deployer.

Steps:
  1. Pick a running serverless SQL warehouse on the active profile.
  2. Create UC schemas (energyq_bronze/silver/gold/energyq) and the
     asset_docs volume under the target catalog.
  3. Stage synthetic CSVs to /Volumes/<catalog>/energyq/asset_docs/_staging/.
  4. Materialise the 16 silver Delta tables with CTAS + read_files() so
     types are inferred from the CSV.
  5. Replay the gold-view block from scripts/create_uc_tables.sql.
  6. Upload markdown documents under data/documents to
     /Volumes/<catalog>/energyq/asset_docs/<region>/<doc_type>/<doc>.md.

Usage:
    DATABRICKS_CONFIG_PROFILE=servco python scripts/deploy_databricks.py
    python scripts/deploy_databricks.py --profile servco
    python scripts/deploy_databricks.py --profile servco --skip-docs
"""

from __future__ import annotations

import argparse
import io
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "synthetic"
DOCS_DIR = ROOT / "data" / "documents"
DDL_PATH = ROOT / "scripts" / "create_uc_tables.sql"

SILVER_TABLES = [
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


def _log(msg: str) -> None:
    print(msg, flush=True)


def _pick_warehouse(ws):
    from databricks.sdk.service.sql import EndpointInfoWarehouseType  # type: ignore

    running = []
    any_serverless = []
    for w in ws.warehouses.list():
        if getattr(w, "enable_serverless_compute", False):
            any_serverless.append(w)
        if str(getattr(w, "state", "")).endswith("RUNNING"):
            running.append(w)
    pool = running or any_serverless or list(ws.warehouses.list())
    if not pool:
        raise RuntimeError("no SQL warehouses available on this workspace")
    pool.sort(key=lambda w: 0 if str(getattr(w, "state", "")).endswith("RUNNING") else 1)
    chosen = pool[0]
    if not str(getattr(chosen, "state", "")).endswith("RUNNING"):
        _log(f"  starting warehouse {chosen.name} ({chosen.id}) ...")
        ws.warehouses.start(chosen.id).result()
    return chosen


def _exec(ws, warehouse_id: str, catalog: str, statement: str, *, wait_seconds: int = 600) -> None:
    from databricks.sdk.service.sql import StatementState  # type: ignore

    resp = ws.statement_execution.execute_statement(
        statement=statement,
        warehouse_id=warehouse_id,
        catalog=catalog,
        wait_timeout="50s",
    )
    statement_id = resp.statement_id
    deadline = time.time() + wait_seconds
    state = resp.status.state if resp.status else None
    while state in (StatementState.PENDING, StatementState.RUNNING) and time.time() < deadline:
        time.sleep(2)
        status = ws.statement_execution.get_statement(statement_id)
        state = status.status.state if status.status else None
        resp = status

    if state != StatementState.SUCCEEDED:
        err = ""
        try:
            err = resp.status.error.message if resp.status and resp.status.error else ""
        except Exception:
            err = ""
        snippet = statement.strip().splitlines()[0][:120]
        raise RuntimeError(f"SQL failed [{state}] ({err}): {snippet}")


_COMMENT_LINE = re.compile(r"^\s*--.*$", re.MULTILINE)


def _split_sql(blob: str) -> list[str]:
    """Split a SQL blob on `;`, but ignore semicolons inside single-quoted strings."""
    cleaned = _COMMENT_LINE.sub("", blob)
    statements: list[str] = []
    buf: list[str] = []
    in_str = False
    i = 0
    while i < len(cleaned):
        ch = cleaned[i]
        if ch == "'":
            # Single-quote handling — '' is an escape for a literal quote.
            if in_str and i + 1 < len(cleaned) and cleaned[i + 1] == "'":
                buf.append("''")
                i += 2
                continue
            in_str = not in_str
            buf.append(ch)
            i += 1
            continue
        if ch == ";" and not in_str:
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


def _extract_gold_block(ddl: str) -> str:
    marker = "-- Gold views"
    idx = ddl.find(marker)
    if idx == -1:
        return ""
    end_idx = ddl.find("-- Grants", idx)
    return ddl[idx:end_idx if end_idx != -1 else len(ddl)]


def run(args: argparse.Namespace) -> int:
    if args.profile:
        os.environ["DATABRICKS_CONFIG_PROFILE"] = args.profile

    try:
        from databricks.sdk import WorkspaceClient  # type: ignore
    except ImportError:
        _log("\n  databricks-sdk not installed. Run: pip install databricks-sdk")
        return 3

    ws = WorkspaceClient()
    me = ws.current_user.me()
    _log(f"\n=== GridLens deploy ===")
    _log(f"  workspace: {ws.config.host}")
    _log(f"  user:      {me.user_name}")
    _log(f"  catalog:   {args.catalog}")

    if args.warehouse_id:
        warehouse_id = args.warehouse_id
        _log(f"  warehouse: {warehouse_id} (forced)")
    else:
        wh = _pick_warehouse(ws)
        warehouse_id = wh.id
        _log(f"  warehouse: {wh.name} ({warehouse_id})")

    volume_path = f"/Volumes/{args.catalog}/energyq/asset_docs"
    staging_path = f"{volume_path}/_staging"

    # --- 1. Schemas + volume -------------------------------------------------
    _log("\n[1/5] Creating schemas and volume ...")
    _exec(ws, warehouse_id, args.catalog,
          f"CREATE SCHEMA IF NOT EXISTS {args.catalog}.energyq_bronze "
          "COMMENT 'Raw synthetic ingest landing for GridLens Queensland demo.'")
    _exec(ws, warehouse_id, args.catalog,
          f"CREATE SCHEMA IF NOT EXISTS {args.catalog}.energyq_silver "
          "COMMENT 'Curated synthetic operational tables for GridLens Queensland demo.'")
    _exec(ws, warehouse_id, args.catalog,
          f"CREATE SCHEMA IF NOT EXISTS {args.catalog}.energyq_gold "
          "COMMENT 'Consumption tables and views powering the app and Genie space.'")
    _exec(ws, warehouse_id, args.catalog,
          f"CREATE SCHEMA IF NOT EXISTS {args.catalog}.energyq "
          "COMMENT 'GridLens Queensland app + volume namespace.'")
    _exec(ws, warehouse_id, args.catalog,
          f"CREATE VOLUME IF NOT EXISTS {args.catalog}.energyq.asset_docs "
          "COMMENT 'Synthetic asset inspection reports, drawings, standards.'")
    _log("       schemas + volume ready")

    if args.only_schema:
        _log("\n  --only-schema set; stopping after DDL.")
        return 0

    # --- 2. Stage CSVs to volume --------------------------------------------
    _log(f"\n[2/5] Staging CSVs to {staging_path} ...")
    csvs = sorted(DATA_DIR.glob("*.csv"))
    if not csvs:
        _log(f"  no CSVs in {DATA_DIR}; aborting")
        return 4
    for csv_path in csvs:
        target = f"{staging_path}/{csv_path.name}"
        with csv_path.open("rb") as fh:
            ws.files.upload(target, fh, overwrite=True)
        _log(f"       uploaded {csv_path.name} ({csv_path.stat().st_size:,} B)")

    # --- 3. Materialise silver Delta tables via read_files -------------------
    _log(f"\n[3/5] Materialising {len(SILVER_TABLES)} silver Delta tables ...")
    for tbl in SILVER_TABLES:
        staged = f"{staging_path}/{tbl}.csv"
        target = f"{args.catalog}.energyq_silver.{tbl}"
        stmt = (
            f"CREATE OR REPLACE TABLE {target} USING DELTA AS "
            f"SELECT * FROM read_files('{staged}', "
            "format => 'csv', header => true, inferSchema => true, "
            "mode => 'PERMISSIVE')"
        )
        t0 = time.time()
        _exec(ws, warehouse_id, args.catalog, stmt, wait_seconds=600)
        _log(f"       {tbl:<35} OK ({time.time() - t0:.1f}s)")

    # --- 4. Gold views --------------------------------------------------------
    _log("\n[4/5] Creating gold views ...")
    ddl_text = DDL_PATH.read_text(encoding="utf-8")
    gold_block = _extract_gold_block(ddl_text)
    if not gold_block:
        _log("  WARNING: could not find gold block in create_uc_tables.sql")
    else:
        for stmt in _split_sql(gold_block):
            first = stmt.strip().splitlines()[0][:80]
            t0 = time.time()
            _exec(ws, warehouse_id, args.catalog, stmt, wait_seconds=600)
            _log(f"       {first} ({time.time() - t0:.1f}s)")

    # --- 5. Upload documents ------------------------------------------------
    if args.skip_docs:
        _log("\n[5/5] Skipping document upload (--skip-docs)")
    else:
        _log(f"\n[5/5] Uploading documents to {volume_path} ...")
        if not DOCS_DIR.exists():
            _log(f"  no docs dir at {DOCS_DIR}; skipping")
        else:
            files = sorted(DOCS_DIR.rglob("*.md"))
            for i, f in enumerate(files, 1):
                rel = f.relative_to(DOCS_DIR)
                target = f"{volume_path}/{rel.as_posix()}"
                with f.open("rb") as src:
                    ws.files.upload(target, src, overwrite=True)
                if i % 50 == 0 or i == len(files):
                    _log(f"       uploaded {i}/{len(files)} files")

    # --- Quick verification --------------------------------------------------
    _log("\n[verify] Row counts in silver:")
    counts_query = " UNION ALL ".join(
        f"SELECT '{t}' AS table_name, COUNT(*) AS rows FROM {args.catalog}.energyq_silver.{t}"
        for t in SILVER_TABLES
    )
    from databricks.sdk.service.sql import StatementState  # type: ignore
    resp = ws.statement_execution.execute_statement(
        statement=counts_query + " ORDER BY 1",
        warehouse_id=warehouse_id,
        catalog=args.catalog,
        wait_timeout="50s",
    )
    while resp.status and resp.status.state in (StatementState.PENDING, StatementState.RUNNING):
        time.sleep(1.5)
        resp = ws.statement_execution.get_statement(resp.statement_id)
    if resp.status and resp.status.state == StatementState.SUCCEEDED:
        data = resp.result.data_array or [] if resp.result else []
        for name, rows in data:
            _log(f"       {name:<35} {rows}")

    _log("\n=== deploy complete ===\n")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--profile", default=os.getenv("DATABRICKS_CONFIG_PROFILE"))
    p.add_argument("--catalog", default="anzgt_may")
    p.add_argument("--warehouse-id", default=None)
    p.add_argument("--only-schema", action="store_true")
    p.add_argument("--skip-docs", action="store_true")
    args = p.parse_args()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
