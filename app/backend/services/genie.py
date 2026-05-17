"""
Genie service.

Two modes, picked at request time:

  1. **Real Genie Space** — when `GENIE_SPACE_ID` is configured, every
     `ask()` is sent to the Databricks Genie Conversation API
     (`WorkspaceClient.genie.start_conversation_and_wait`). The returned
     SQL + rows are shaped into the existing
     `{summary, sql, columns, rows, cards, chart_type, business_definitions}`
     contract so the frontend doesn't need to change. Errors fall back to
     the deterministic fallback below.

  2. **Local fallback** — when `GENIE_SPACE_ID` is unset (local dev
     without a Databricks profile, smoke tests), `GenieFallback` answers
     a small set of trusted questions deterministically from the
     in-memory DataStore.
"""

from __future__ import annotations

import datetime as _dt
import logging
import os
import re
import threading
from typing import Any, Callable, Optional

from app.backend.services.data_store import DataStore

logger = logging.getLogger(__name__)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).strip()


# ----------------------------------------------------------------------------
# Local fallback (used in dev and when Genie call fails)
# ----------------------------------------------------------------------------

class GenieFallback:
    """Deterministic, source-grounded answers for trusted questions."""

    def __init__(self) -> None:
        self.ds = DataStore.instance()
        self.handlers: list[tuple[str, str, Callable[[], dict]]] = [
            ("highest storm-season asset risk", "Storm-season high-risk assets by region",
             self._q_storm_risk),
            ("storm season asset risk", "Storm-season high-risk assets by region",
             self._q_storm_risk),
            ("repeated vegetation-related outages", "Feeders with repeated vegetation outages",
             self._q_veg_outages),
            ("vegetation backlog", "Vegetation backlog by region",
             self._q_veg_backlog),
            ("planned remediation", "Planned remediation coverage by region",
             self._q_planned_remediation),
            ("prioritise work", "Top regions to prioritise work",
             self._q_prioritise_work),
            ("highest vegetation backlog", "Highest vegetation backlog regions",
             self._q_veg_backlog),
            ("critical customer impact", "Critical customer exposure by region",
             self._q_critical_customers),
            ("regions have the highest", "Region risk ranking",
             self._q_storm_risk),
        ]

    def ask(self, question: str) -> dict:
        n = _norm(question)
        for key, label, fn in self.handlers:
            if key in n:
                resp = fn()
                resp["question"] = question
                return resp
        resp = self._q_storm_risk()
        resp["question"] = question
        resp["summary"] = (
            "I don't have a tuned answer for that question. Showing the regional "
            "risk overview as a starting point."
        )
        return resp

    def _q_storm_risk(self) -> dict:
        summary = self.ds.regional_summary()
        summary.sort(key=lambda r: -(r["critical_risk_assets"] * 5 + r["high_risk_assets"]))
        rows = []
        cards = []
        for r in summary:
            planned_coverage = 0.0
            risky = r["high_risk_assets"] + r["critical_risk_assets"]
            if risky:
                planned_coverage = round(100.0 * r["planned_work_count"] / risky, 1)
            rows.append([
                r["region_name"],
                r["high_risk_assets"],
                r["critical_risk_assets"],
                r["vegetation_backlog"],
                f"{planned_coverage}%",
                r["critical_customer_count_exposed"],
            ])
        for r in summary[:3]:
            cards.append({
                "label": r["region_name"],
                "value": str(r["high_risk_assets"] + r["critical_risk_assets"]),
                "sub_label": f"{r['high_risk_assets']} high / {r['critical_risk_assets']} critical",
            })
        return {
            "summary": "Region risk ranking by storm-season high + critical asset counts.",
            "sql": (
                "SELECT region_name, high_risk_assets, critical_risk_assets, vegetation_backlog, "
                "planned_work_count, critical_customer_count_exposed "
                "FROM anzgt_may.energyq_gold.gold_regional_risk_summary "
                "ORDER BY (high_risk_assets + critical_risk_assets) DESC;"
            ),
            "columns": [
                "Region", "High-risk assets", "Critical-risk assets",
                "Vegetation backlog", "Planned remediation coverage",
                "Critical customers exposed",
            ],
            "rows": rows,
            "cards": cards,
            "chart_type": "bar",
            "business_definitions": [
                "high_risk_assets: count of assets in 'high' risk band (56-75).",
                "critical_risk_assets: count of assets in 'critical' risk band (76+).",
                "vegetation_backlog: vegetation spans overdue by >30 days.",
                "planned remediation coverage: planned work count / risky assets.",
            ],
        }

    def _q_veg_outages(self) -> dict:
        cutoff = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=365)
        veg_count: dict[str, int] = {}
        for o in self.ds.outages:
            if o.get("cause_category") != "vegetation":
                continue
            try:
                start = _dt.datetime.fromisoformat(o["outage_start"].replace("Z", "+00:00"))
            except Exception:
                continue
            if start.tzinfo is None:
                start = start.replace(tzinfo=_dt.timezone.utc)
            if start < cutoff:
                continue
            veg_count[o["feeder_id"]] = veg_count.get(o["feeder_id"], 0) + 1
        ranked = sorted(veg_count.items(), key=lambda x: -x[1])[:10]
        rows = []
        for feeder_id, count in ranked:
            f = self.ds.feeders.get(feeder_id, {})
            r = self.ds.regions.get(f.get("region_id"), {})
            rows.append([f.get("feeder_name", feeder_id), r.get("region_name", ""), count])
        return {
            "summary": "Top feeders by vegetation-caused outages in the last 12 months.",
            "sql": (
                "SELECT f.feeder_name, r.region_name, COUNT(*) AS veg_outages_12m "
                "FROM anzgt_may.energyq_silver.outage_events o "
                "JOIN anzgt_may.energyq_silver.feeders f ON f.feeder_id = o.feeder_id "
                "JOIN anzgt_may.energyq_silver.regions r ON r.region_id = o.region_id "
                "WHERE o.cause_category = 'vegetation' "
                "  AND o.outage_start >= current_date() - INTERVAL 12 MONTHS "
                "GROUP BY f.feeder_name, r.region_name "
                "ORDER BY veg_outages_12m DESC LIMIT 10;"
            ),
            "columns": ["Feeder", "Region", "Vegetation outages (12m)"],
            "rows": rows,
            "cards": [],
            "chart_type": "bar",
            "business_definitions": [
                "Vegetation outage: outage_events.cause_category = 'vegetation'.",
            ],
        }

    def _q_veg_backlog(self) -> dict:
        backlog: dict[str, int] = {}
        for v in self.ds.vegetation:
            try:
                if int(float(v.get("overdue_days", 0))) > 30:
                    backlog[v["region_id"]] = backlog.get(v["region_id"], 0) + 1
            except ValueError:
                pass
        rows = []
        for region_id, count in sorted(backlog.items(), key=lambda x: -x[1]):
            r = self.ds.regions.get(region_id, {})
            rows.append([r.get("region_name", region_id), count])
        return {
            "summary": "Vegetation backlog by region (spans overdue by >30 days).",
            "sql": (
                "SELECT r.region_name, COUNT(*) AS backlog "
                "FROM anzgt_may.energyq_silver.vegetation_spans v "
                "JOIN anzgt_may.energyq_silver.regions r ON r.region_id = v.region_id "
                "WHERE v.overdue_days > 30 "
                "GROUP BY r.region_name ORDER BY backlog DESC;"
            ),
            "columns": ["Region", "Backlog (spans >30d overdue)"],
            "rows": rows,
            "cards": [],
            "chart_type": "bar",
            "business_definitions": ["overdue_days > 30 implies vegetation treatment past target."],
        }

    def _q_planned_remediation(self) -> dict:
        out = []
        for r in self.ds.regional_summary():
            risky = r["high_risk_assets"] + r["critical_risk_assets"]
            cov = (100.0 * r["planned_work_count"] / risky) if risky else 0.0
            out.append([r["region_name"], risky, r["planned_work_count"], f"{cov:.1f}%"])
        out.sort(key=lambda x: -float(x[3].rstrip("%")))
        return {
            "summary": "Planned remediation coverage by region.",
            "sql": (
                "SELECT region_name, (high_risk_assets + critical_risk_assets) AS risky_assets, "
                "planned_work_count, "
                "round(100.0 * planned_work_count / NULLIF(high_risk_assets + critical_risk_assets, 0), 1) AS coverage_pct "
                "FROM anzgt_may.energyq_gold.gold_regional_risk_summary;"
            ),
            "columns": ["Region", "Risky assets", "Planned work orders", "Coverage %"],
            "rows": out,
            "cards": [],
            "chart_type": "bar",
            "business_definitions": [
                "planned_work_count: work orders in status approved/scheduled/in_progress."
            ],
        }

    def _q_prioritise_work(self) -> dict:
        ranked = []
        summaries = self.ds.feeder_summary()
        for s in summaries:
            score = (s["critical_risk_assets"] * 8 + s["high_risk_assets"]) * (1 + s["customer_count"] / 5000.0)
            if score == 0:
                continue
            ranked.append((score, s))
        ranked.sort(key=lambda x: -x[0])
        rows = []
        for score, s in ranked[:10]:
            rows.append([
                s["feeder_name"], s["region_name"], s["critical_risk_assets"],
                s["high_risk_assets"], s["customer_count"], round(score, 1),
            ])
        return {
            "summary": "Top 10 feeders to prioritise work, ranked by risky assets weighted by customer exposure.",
            "sql": (
                "SELECT feeder_name, region_name, critical_risk_assets, high_risk_assets, customer_count "
                "FROM anzgt_may.energyq_gold.gold_feeder_risk_summary "
                "ORDER BY critical_risk_assets * 8 + high_risk_assets DESC LIMIT 10;"
            ),
            "columns": ["Feeder", "Region", "Critical", "High", "Customers", "Priority score"],
            "rows": rows,
            "cards": [],
            "chart_type": "bar",
            "business_definitions": [],
        }

    def _q_critical_customers(self) -> dict:
        rows = []
        for r in self.ds.regional_summary():
            rows.append([r["region_name"], r["critical_customer_count_exposed"]])
        rows.sort(key=lambda x: -x[1])
        return {
            "summary": "Critical customer exposure by region.",
            "sql": (
                "SELECT region_name, critical_customer_count_exposed "
                "FROM anzgt_may.energyq_gold.gold_regional_risk_summary "
                "ORDER BY critical_customer_count_exposed DESC;"
            ),
            "columns": ["Region", "Critical customer count"],
            "rows": rows,
            "cards": [],
            "chart_type": "bar",
            "business_definitions": [
                "critical customer: hospital, aged care, emergency services, water pumping, telecom, airport, industrial, school."
            ],
        }


# ----------------------------------------------------------------------------
# Real Genie Conversation API
# ----------------------------------------------------------------------------

class GenieService:
    """Routes questions to the real Genie space, with deterministic fallback."""

    _instance: "GenieService | None" = None
    _lock = threading.Lock()

    @classmethod
    def instance(cls) -> "GenieService":
        with cls._lock:
            if cls._instance is None:
                cls._instance = GenieService()
            return cls._instance

    def __init__(self) -> None:
        from app.backend.config import settings
        self.space_id = settings.genie_space_id or os.getenv("GENIE_SPACE_ID", "")
        self.fallback = GenieFallback()
        self._ws = None

    def _workspace_client(self):
        if self._ws is not None:
            return self._ws
        from databricks.sdk import WorkspaceClient
        self._ws = WorkspaceClient()
        return self._ws

    def ask(self, question: str) -> dict:
        if not self.space_id:
            logger.info("GENIE_SPACE_ID not set; using fallback for %r", question[:80])
            return self.fallback.ask(question)
        try:
            return self._ask_genie(question)
        except Exception as e:
            logger.warning("Genie call failed (%s); using fallback for %r", e, question[:80])
            resp = self.fallback.ask(question)
            resp["summary"] = (
                f"Genie call failed ({type(e).__name__}); returning a deterministic "
                f"fallback answer. Original summary: {resp.get('summary')}"
            )
            return resp

    def _ask_genie(self, question: str) -> dict:
        w = self._workspace_client()
        logger.info("Genie ask (space=%s): %r", self.space_id, question[:80])
        msg = w.genie.start_conversation_and_wait(
            space_id=self.space_id,
            content=question,
        )
        # The completed message has attachments; the SQL attachment carries
        # the query + (optionally) execution result.
        attachments = list(getattr(msg, "attachments", []) or [])
        text_summary = ""
        for a in attachments:
            text = getattr(a, "text", None)
            if text is not None:
                content = getattr(text, "content", "") or ""
                if content:
                    text_summary = content
                    break
        # Find a SQL/query attachment.
        sql_text = ""
        columns: list[str] = []
        rows: list[list[Any]] = []
        sql_attachment_id: Optional[str] = None
        for a in attachments:
            q = getattr(a, "query", None)
            if q is not None:
                sql_text = getattr(q, "query", "") or ""
                sql_attachment_id = getattr(a, "attachment_id", None)
                break
        # If we have a SQL attachment, fetch the executed result rows.
        if sql_attachment_id and msg.conversation_id and msg.id:
            try:
                qr = w.genie.get_message_query_result_by_attachment(
                    space_id=self.space_id,
                    conversation_id=msg.conversation_id,
                    message_id=msg.id,
                    attachment_id=sql_attachment_id,
                )
                stmt = getattr(qr, "statement_response", None)
                if stmt is not None:
                    manifest = getattr(stmt, "manifest", None)
                    if manifest is not None and getattr(manifest, "schema", None) is not None:
                        columns = [c.name for c in (manifest.schema.columns or [])]
                    result = getattr(stmt, "result", None)
                    if result is not None and getattr(result, "data_array", None):
                        rows = list(result.data_array)
            except Exception as e:
                logger.info("Genie result fetch failed (%s)", e)

        cards = []
        if rows and columns:
            # Best-effort: first column is label, second is numeric → top-3 cards.
            for r in rows[:3]:
                if len(r) >= 2:
                    cards.append({"label": str(r[0]), "value": str(r[1]), "sub_label": ""})

        return {
            "question": question,
            "summary": text_summary or f"Genie answered using {len(rows)} rows.",
            "sql": sql_text,
            "columns": columns,
            "rows": rows,
            "cards": cards,
            "chart_type": "bar" if (rows and columns and len(columns) >= 2) else "table",
            "business_definitions": [],
            "genie": {
                "space_id": self.space_id,
                "conversation_id": msg.conversation_id,
                "message_id": msg.id,
            },
        }
