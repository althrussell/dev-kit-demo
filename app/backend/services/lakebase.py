"""
Lakebase service.

Persists work packages, agent recommendations, evidence and approvals.

- Production: connects to Lakebase (Postgres) via `LAKEBASE_DATABASE_URL`.
- Local dev:  uses SQLite at data/lakebase/gridlens.db. The schema is
              generated from the same DDL as Postgres via the seed script.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from app.backend.config import LAKEBASE_LOCAL_DB, settings


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def short_uuid() -> str:
    return uuid.uuid4().hex[:10]


class LakebaseService:
    _instance: "LakebaseService | None" = None
    _lock = threading.Lock()

    @classmethod
    def instance(cls) -> "LakebaseService":
        with cls._lock:
            if cls._instance is None:
                cls._instance = LakebaseService()
            return cls._instance

    def __init__(self) -> None:
        self.url = settings.lakebase_url
        self.is_sqlite = not self.url
        if self.is_sqlite:
            LAKEBASE_LOCAL_DB.parent.mkdir(parents=True, exist_ok=True)
            if not LAKEBASE_LOCAL_DB.exists():
                # Auto-seed for first run.
                from scripts.seed_lakebase_demo_state import main as seed_main
                print("[lakebase] local DB not found; auto-seeding...")
                # Best effort — if path import fails, just create empty.
                try:
                    seed_main()  # type: ignore[no-untyped-call]
                except Exception as exc:
                    print(f"[lakebase] auto-seed failed: {exc}")
        else:
            try:
                import psycopg  # type: ignore  # noqa: F401
            except ImportError as e:
                raise RuntimeError("psycopg not installed; pip install psycopg[binary]") from e

    @contextmanager
    def _conn(self) -> Iterator[Any]:
        if self.is_sqlite:
            conn = sqlite3.connect(LAKEBASE_LOCAL_DB)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()
        else:
            import psycopg  # type: ignore
            from psycopg.rows import dict_row  # type: ignore

            conn = psycopg.connect(self.url, autocommit=True, row_factory=dict_row)
            try:
                yield conn
            finally:
                conn.close()

    # ---- Work packages ---------------------------------------------------

    def list_work_packages(self) -> list[dict]:
        with self._conn() as c:
            cur = c.execute(
                "SELECT * FROM work_packages ORDER BY created_at DESC"
                if self.is_sqlite
                else "SELECT * FROM work_packages ORDER BY created_at DESC"
            )
            rows = cur.fetchall()
        return [self._wp_row_to_dict(r) for r in rows]

    def get_work_package(self, work_package_id: str) -> dict | None:
        with self._conn() as c:
            if self.is_sqlite:
                cur = c.execute("SELECT * FROM work_packages WHERE work_package_id = ?", (work_package_id,))
            else:
                cur = c.cursor()
                cur.execute("SELECT * FROM work_packages WHERE work_package_id = %s", (work_package_id,))
            row = cur.fetchone()
            if not row:
                return None
            wp = self._wp_row_to_dict(row)
            if self.is_sqlite:
                acur = c.execute(
                    "SELECT asset_id, role, notes FROM work_package_assets WHERE work_package_id = ?",
                    (work_package_id,),
                )
            else:
                acur = c.cursor()
                acur.execute(
                    "SELECT asset_id, role, notes FROM work_package_assets WHERE work_package_id = %s",
                    (work_package_id,),
                )
            wp["assets"] = [dict(a) for a in acur.fetchall()]
            return wp

    def create_work_package(self, payload: dict) -> dict:
        pkg_id = payload.get("work_package_id") or f"WP-{short_uuid()}"
        cols = (
            "work_package_id, title, region_id, feeder_id, scenario_type, priority, status, "
            "created_by, recommended_by_agent, evidence_summary, estimated_hours, estimated_cost_aud, "
            "estimated_customer_impact_reduction, suggested_depot_id, updated_at"
        )
        values = (
            pkg_id,
            payload["title"],
            payload["region_id"],
            payload.get("feeder_id"),
            payload.get("scenario_type"),
            payload.get("priority", "medium"),
            payload.get("status", "draft"),
            payload.get("created_by", "demo_user"),
            1 if payload.get("recommended_by_agent") else 0 if self.is_sqlite else bool(payload.get("recommended_by_agent")),
            payload.get("evidence_summary"),
            payload.get("estimated_hours"),
            payload.get("estimated_cost_aud"),
            payload.get("estimated_customer_impact_reduction"),
            payload.get("suggested_depot_id"),
            now_iso(),
        )
        with self._conn() as c:
            if self.is_sqlite:
                placeholders = ",".join(["?"] * len(values))
                c.execute(f"INSERT INTO work_packages ({cols}) VALUES ({placeholders})", values)
                for asset_id in payload.get("asset_ids", []):
                    c.execute(
                        "INSERT OR REPLACE INTO work_package_assets (work_package_id, asset_id, role) VALUES (?, ?, ?)",
                        (pkg_id, asset_id, "primary" if asset_id == payload.get("asset_ids", [None])[0] else "bundled"),
                    )
            else:
                placeholders = ",".join(["%s"] * len(values))
                cur = c.cursor()
                cur.execute(f"INSERT INTO work_packages ({cols}) VALUES ({placeholders})", values)
                for asset_id in payload.get("asset_ids", []):
                    cur.execute(
                        "INSERT INTO work_package_assets (work_package_id, asset_id, role) VALUES (%s, %s, %s) "
                        "ON CONFLICT DO NOTHING",
                        (pkg_id, asset_id, "primary" if asset_id == payload.get("asset_ids", [None])[0] else "bundled"),
                    )
        return self.get_work_package(pkg_id)  # type: ignore[return-value]

    def patch_work_package(self, work_package_id: str, patch: dict) -> dict | None:
        if not patch:
            return self.get_work_package(work_package_id)
        sets = []
        values: list[Any] = []
        for k, v in patch.items():
            if v is None:
                continue
            sets.append(f"{k} = " + ("?" if self.is_sqlite else "%s"))
            values.append(v)
        if not sets:
            return self.get_work_package(work_package_id)
        sets.append("updated_at = " + ("?" if self.is_sqlite else "%s"))
        values.append(now_iso())
        values.append(work_package_id)
        with self._conn() as c:
            if self.is_sqlite:
                c.execute(f"UPDATE work_packages SET {', '.join(sets)} WHERE work_package_id = ?", values)
            else:
                cur = c.cursor()
                cur.execute(f"UPDATE work_packages SET {', '.join(sets)} WHERE work_package_id = %s", values)
        return self.get_work_package(work_package_id)

    def _wp_row_to_dict(self, r) -> dict:
        d = dict(r)
        # SQLite stores BOOLEAN as 0/1.
        if isinstance(d.get("recommended_by_agent"), int):
            d["recommended_by_agent"] = bool(d["recommended_by_agent"])
        return {
            "work_package_id": d.get("work_package_id"),
            "title": d.get("title"),
            "region_id": d.get("region_id"),
            "feeder_id": d.get("feeder_id"),
            "scenario_type": d.get("scenario_type"),
            "priority": d.get("priority"),
            "status": d.get("status"),
            "created_by": d.get("created_by"),
            "created_at": str(d.get("created_at") or ""),
            "recommended_by_agent": d.get("recommended_by_agent", False),
            "evidence_summary": d.get("evidence_summary"),
            "estimated_hours": d.get("estimated_hours"),
            "estimated_cost_aud": d.get("estimated_cost_aud"),
            "estimated_customer_impact_reduction": d.get("estimated_customer_impact_reduction"),
            "suggested_depot_id": d.get("suggested_depot_id"),
            "assets": [],
        }

    # ---- Agent recommendations ------------------------------------------

    def save_recommendation(self, rec_id: str, prompt: str, body: str, confidence: float,
                            evidence: list[dict], work_package_id: str | None = None,
                            status: str = "proposed") -> None:
        with self._conn() as c:
            if self.is_sqlite:
                c.execute(
                    "INSERT OR REPLACE INTO agent_recommendations "
                    "(recommendation_id, work_package_id, user_prompt, agent_response, confidence_score, status) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (rec_id, work_package_id, prompt, body, confidence, status),
                )
                for ev in evidence:
                    c.execute(
                        "INSERT OR REPLACE INTO agent_recommendation_evidence "
                        "(evidence_id, recommendation_id, evidence_type, source_ref, source_title, excerpt, confidence) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (f"EV-{short_uuid()}", rec_id, ev["evidence_type"], ev["source_ref"],
                         ev["source_title"], ev["excerpt"], ev["confidence"]),
                    )
            else:
                cur = c.cursor()
                cur.execute(
                    "INSERT INTO agent_recommendations "
                    "(recommendation_id, work_package_id, user_prompt, agent_response, confidence_score, status) "
                    "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (recommendation_id) DO NOTHING",
                    (rec_id, work_package_id, prompt, body, confidence, status),
                )
                for ev in evidence:
                    cur.execute(
                        "INSERT INTO agent_recommendation_evidence "
                        "(evidence_id, recommendation_id, evidence_type, source_ref, source_title, excerpt, confidence) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                        (f"EV-{short_uuid()}", rec_id, ev["evidence_type"], ev["source_ref"],
                         ev["source_title"], ev["excerpt"], ev["confidence"]),
                    )

    def list_recommendations(self, limit: int = 50) -> list[dict]:
        with self._conn() as c:
            if self.is_sqlite:
                cur = c.execute(
                    "SELECT * FROM agent_recommendations ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                )
            else:
                cur = c.cursor()
                cur.execute(
                    "SELECT * FROM agent_recommendations ORDER BY created_at DESC LIMIT %s",
                    (limit,),
                )
            return [dict(r) for r in cur.fetchall()]

    def list_scenarios(self) -> list[dict]:
        with self._conn() as c:
            cur = c.execute("SELECT * FROM app_scenarios WHERE is_active = 1 ORDER BY scenario_name")
            return [dict(r) for r in cur.fetchall()]
