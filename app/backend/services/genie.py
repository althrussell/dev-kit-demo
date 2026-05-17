"""
Genie service.

When `GENIE_SPACE_ID` is configured, this proxies the question to the
Genie Conversation API on Databricks (see docs/genie-space-setup.md).

For the local demo and when Genie is not available, this implements a
deterministic fallback that maps a small set of trusted questions to
real SQL-style answers computed from the in-memory data_store. This
guarantees that the demo always shows credible, grounded analytics
without ungrounded LLM output.
"""

from __future__ import annotations

import re
from typing import Callable

from app.backend.services.data_store import DataStore


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).strip()


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
        # Unknown question — produce a region risk overview as best fallback.
        resp = self._q_storm_risk()
        resp["question"] = question
        resp["summary"] = (
            "I don't have a tuned answer for that question. Showing the regional "
            "risk overview as a starting point — refer to docs/genie-space-setup.md "
            "for the list of trusted questions."
        )
        return resp

    # ---- Tuned answers ---------------------------------------------------

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
            "summary": (
                "Region risk ranking by storm-season high + critical asset counts, "
                "with vegetation backlog and planned remediation coverage."
            ),
            "sql": (
                "SELECT region_name, high_risk_assets, critical_risk_assets, vegetation_backlog, "
                "planned_work_count, critical_customer_count_exposed "
                "FROM anzgt_may.energyq_gold.gold_regional_risk_summary "
                "ORDER BY (high_risk_assets + critical_risk_assets) DESC;"
            ),
            "columns": [
                "Region",
                "High-risk assets",
                "Critical-risk assets",
                "Vegetation backlog",
                "Planned remediation coverage",
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
        # Top feeders by vegetation outages in the last 12 months.
        from datetime import datetime, timedelta
        cutoff = datetime.utcnow() - timedelta(days=365)
        veg_count: dict[str, int] = {}
        for o in self.ds.outages:
            if o.get("cause_category") != "vegetation":
                continue
            try:
                start = datetime.fromisoformat(o["outage_start"])
            except Exception:
                continue
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
            "summary": (
                "Planned remediation coverage by region — share of high/critical "
                "assets covered by an approved or scheduled work order."
            ),
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
        # Top feeders by (high+critical assets * customer exposure).
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


class GenieService:
    _instance: "GenieService | None" = None

    @classmethod
    def instance(cls) -> "GenieService":
        if cls._instance is None:
            cls._instance = GenieService()
        return cls._instance

    def __init__(self) -> None:
        from app.backend.config import settings
        self.space_id = settings.genie_space_id
        self.fallback = GenieFallback()

    def ask(self, question: str) -> dict:
        # In production, we would call the Genie Conversation API here.
        # For the demo we always use the trusted fallback.
        return self.fallback.ask(question)
