"""
Lakebase Autoscaling persistence layer for GridLens Queensland.

This module is the single persistence layer for transactional app state
(work packages, agent recommendations, evidence, saved map views, scenarios,
annotations and approvals). It is backed by a Databricks Lakebase Autoscaling
project (managed Postgres 17) — the same database in local development and in
the deployed Databricks App.

Connection model
----------------

We use psycopg3 with OAuth token authentication ("Lakebase OAuth v1"):

  - The username is the service principal client ID when the app runs in
    Databricks Apps (set via `DATABRICKS_CLIENT_ID`), or the workspace user's
    email when running locally with a personal Databricks profile.
  - The password is a short-lived OAuth token minted by
    `WorkspaceClient.postgres.generate_database_credential(endpoint=...)`,
    cached for ~50 minutes and refreshed on `OperationalError` from psycopg.
  - The `gridlens` Postgres schema is set as the search_path on every
    connection.

The first request after a scale-to-zero idle period will wake the endpoint;
we retry with exponential backoff up to 5 times to ride out the wake.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator, Optional

from app.backend.config import settings

# ---- Defaults ---------------------------------------------------------------

DEFAULT_PROJECT = "gridlens"
DEFAULT_BRANCH = "production"
DEFAULT_ENDPOINT = "primary"
DEFAULT_DATABASE = "databricks_postgres"
DEFAULT_SCHEMA = "gridlens"

TOKEN_TTL_SECONDS = 50 * 60  # Refresh before the 1h server-side token expiry.


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def short_uuid() -> str:
    return uuid.uuid4().hex[:10]


def _env(key: str, default: str = "") -> str:
    v = os.getenv(key)
    return v if v else default


class LakebaseService:
    """Singleton service over a single Lakebase Autoscaling endpoint."""

    _instance: "LakebaseService | None" = None
    _lock = threading.Lock()

    @classmethod
    def instance(cls) -> "LakebaseService":
        with cls._lock:
            if cls._instance is None:
                cls._instance = LakebaseService()
            return cls._instance

    def __init__(self) -> None:
        self.project = _env("LAKEBASE_PROJECT_NAME", DEFAULT_PROJECT)
        self.branch = _env("LAKEBASE_BRANCH", DEFAULT_BRANCH)
        self.endpoint = _env("LAKEBASE_ENDPOINT", DEFAULT_ENDPOINT)
        self.database = _env("LAKEBASE_DATABASE", DEFAULT_DATABASE)
        self.schema = _env("LAKEBASE_SCHEMA", DEFAULT_SCHEMA)

        # Optional: direct URL takes precedence (useful in CI / tests).
        self.direct_url = _env("LAKEBASE_DATABASE_URL", "")

        self._token: Optional[str] = None
        self._token_expiry: float = 0.0
        self._host: Optional[str] = None
        self._user: Optional[str] = None
        self._ws = None  # lazy-init WorkspaceClient

        try:
            import psycopg  # noqa: F401
        except ImportError as e:
            raise RuntimeError(
                "psycopg not installed. Install with: pip install 'psycopg[binary]>=3.0'"
            ) from e

    # ------------------------------------------------------------------
    # Auth + connection plumbing
    # ------------------------------------------------------------------

    def _endpoint_resource_name(self) -> str:
        return f"projects/{self.project}/branches/{self.branch}/endpoints/{self.endpoint}"

    def _workspace_client(self):
        if self._ws is not None:
            return self._ws
        from databricks.sdk import WorkspaceClient
        self._ws = WorkspaceClient()
        return self._ws

    def _resolve_host(self) -> str:
        if self._host:
            return self._host
        w = self._workspace_client()
        ep = w.postgres.get_endpoint(name=self._endpoint_resource_name())
        host = ep.status.hosts.host
        if not host:
            raise RuntimeError(f"Lakebase endpoint {self._endpoint_resource_name()} has no host")
        self._host = host
        return host

    def _resolve_user(self) -> str:
        if self._user:
            return self._user
        # In Databricks Apps the app SP authenticates with its client ID.
        sp_client_id = _env("DATABRICKS_CLIENT_ID")
        if sp_client_id:
            self._user = sp_client_id
            return self._user
        # Local dev: use the current Databricks workspace user.
        w = self._workspace_client()
        self._user = w.current_user.me().user_name
        return self._user

    def _mint_token(self) -> str:
        if self._token and time.time() < self._token_expiry:
            return self._token
        w = self._workspace_client()
        cred = w.postgres.generate_database_credential(endpoint=self._endpoint_resource_name())
        self._token = cred.token
        self._token_expiry = time.time() + TOKEN_TTL_SECONDS
        return self._token

    def _conn_string(self, *, force_refresh_token: bool = False) -> str:
        if self.direct_url:
            return self.direct_url
        if force_refresh_token:
            self._token = None
            self._token_expiry = 0.0
        host = self._resolve_host()
        user = self._resolve_user()
        token = self._mint_token()
        return (
            f"host={host} port=5432 dbname={self.database} "
            f"user={user} password={token} sslmode=require"
        )

    @contextmanager
    def _conn(self) -> Iterator[Any]:
        """Yield a psycopg connection with retries and search_path set."""
        import psycopg
        from psycopg import OperationalError
        from psycopg.rows import dict_row

        delays = [0.0, 1.0, 2.0, 4.0, 8.0]
        last_err: Optional[Exception] = None
        for attempt, delay in enumerate(delays):
            if delay:
                time.sleep(delay)
            try:
                refresh = attempt > 0
                conn = psycopg.connect(
                    self._conn_string(force_refresh_token=refresh),
                    autocommit=True,
                    row_factory=dict_row,
                )
                try:
                    with conn.cursor() as cur:
                        cur.execute(f'SET search_path TO "{self.schema}", public')
                    yield conn
                    return
                finally:
                    conn.close()
            except OperationalError as e:
                last_err = e
                # On wake-from-scale-to-zero, retry; on auth errors, refresh token.
                if attempt + 1 < len(delays):
                    print(f"[lakebase] connect attempt {attempt + 1} failed: {e}; retrying...")
                    continue
                raise
            except Exception as e:
                last_err = e
                raise
        if last_err:
            raise last_err

    # ------------------------------------------------------------------
    # Work packages
    # ------------------------------------------------------------------

    def list_work_packages(self) -> list[dict]:
        with self._conn() as c:
            with c.cursor() as cur:
                cur.execute("SELECT * FROM work_packages ORDER BY created_at DESC")
                rows = cur.fetchall()
        return [self._wp_row_to_dict(r) for r in rows]

    def get_work_package(self, work_package_id: str) -> dict | None:
        with self._conn() as c:
            with c.cursor() as cur:
                cur.execute(
                    "SELECT * FROM work_packages WHERE work_package_id = %s",
                    (work_package_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                wp = self._wp_row_to_dict(row)
                cur.execute(
                    "SELECT asset_id, role, notes FROM work_package_assets WHERE work_package_id = %s",
                    (work_package_id,),
                )
                wp["assets"] = [dict(a) for a in cur.fetchall()]
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
            bool(payload.get("recommended_by_agent")),
            payload.get("evidence_summary"),
            payload.get("estimated_hours"),
            payload.get("estimated_cost_aud"),
            payload.get("estimated_customer_impact_reduction"),
            payload.get("suggested_depot_id"),
            now_iso(),
        )
        with self._conn() as c:
            with c.cursor() as cur:
                placeholders = ",".join(["%s"] * len(values))
                cur.execute(
                    f"INSERT INTO work_packages ({cols}) VALUES ({placeholders}) "
                    f"ON CONFLICT (work_package_id) DO NOTHING",
                    values,
                )
                primary_id = (payload.get("asset_ids") or [None])[0]
                for asset_id in payload.get("asset_ids", []):
                    role = "primary" if asset_id == primary_id else "bundled"
                    cur.execute(
                        "INSERT INTO work_package_assets (work_package_id, asset_id, role) "
                        "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                        (pkg_id, asset_id, role),
                    )
        return self.get_work_package(pkg_id)  # type: ignore[return-value]

    def patch_work_package(self, work_package_id: str, patch: dict) -> dict | None:
        if not patch:
            return self.get_work_package(work_package_id)
        sets: list[str] = []
        values: list[Any] = []
        for k, v in patch.items():
            if v is None:
                continue
            sets.append(f"{k} = %s")
            values.append(v)
        if not sets:
            return self.get_work_package(work_package_id)
        sets.append("updated_at = %s")
        values.append(now_iso())
        values.append(work_package_id)
        with self._conn() as c:
            with c.cursor() as cur:
                cur.execute(
                    f"UPDATE work_packages SET {', '.join(sets)} WHERE work_package_id = %s",
                    values,
                )
        return self.get_work_package(work_package_id)

    @staticmethod
    def _wp_row_to_dict(r: dict) -> dict:
        return {
            "work_package_id": r.get("work_package_id"),
            "title": r.get("title"),
            "region_id": r.get("region_id"),
            "feeder_id": r.get("feeder_id"),
            "scenario_type": r.get("scenario_type"),
            "priority": r.get("priority"),
            "status": r.get("status"),
            "created_by": r.get("created_by"),
            "created_at": str(r.get("created_at") or ""),
            "recommended_by_agent": bool(r.get("recommended_by_agent")),
            "evidence_summary": r.get("evidence_summary"),
            "estimated_hours": r.get("estimated_hours"),
            "estimated_cost_aud": r.get("estimated_cost_aud"),
            "estimated_customer_impact_reduction": r.get("estimated_customer_impact_reduction"),
            "suggested_depot_id": r.get("suggested_depot_id"),
            "assets": [],
        }

    # ------------------------------------------------------------------
    # Agent recommendations
    # ------------------------------------------------------------------

    def save_recommendation(
        self,
        rec_id: str,
        prompt: str,
        body: str,
        confidence: float,
        evidence: list[dict],
        work_package_id: str | None = None,
        status: str = "proposed",
    ) -> None:
        with self._conn() as c:
            with c.cursor() as cur:
                cur.execute(
                    "INSERT INTO agent_recommendations "
                    "(recommendation_id, work_package_id, user_prompt, agent_response, confidence_score, status) "
                    "VALUES (%s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (recommendation_id) DO NOTHING",
                    (rec_id, work_package_id, prompt, body, confidence, status),
                )
                for ev in evidence:
                    cur.execute(
                        "INSERT INTO agent_recommendation_evidence "
                        "(evidence_id, recommendation_id, evidence_type, source_ref, source_title, excerpt, confidence) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                        "ON CONFLICT (evidence_id) DO NOTHING",
                        (
                            f"EV-{short_uuid()}",
                            rec_id,
                            ev["evidence_type"],
                            ev["source_ref"],
                            ev["source_title"],
                            ev["excerpt"],
                            ev["confidence"],
                        ),
                    )

    def list_recommendations(self, limit: int = 50) -> list[dict]:
        with self._conn() as c:
            with c.cursor() as cur:
                cur.execute(
                    "SELECT * FROM agent_recommendations ORDER BY created_at DESC LIMIT %s",
                    (limit,),
                )
                return [dict(r) for r in cur.fetchall()]

    def list_scenarios(self) -> list[dict]:
        with self._conn() as c:
            with c.cursor() as cur:
                cur.execute(
                    "SELECT * FROM app_scenarios WHERE is_active = TRUE ORDER BY scenario_name"
                )
                return [dict(r) for r in cur.fetchall()]
