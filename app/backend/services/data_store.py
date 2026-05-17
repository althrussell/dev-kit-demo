"""
In-memory analytics store for GridLens Queensland.

When running locally without Databricks credentials, this loads the synthetic
CSV files produced by `scripts/generate_synthetic_energyq_data.py` and serves
all of the analytics surfaces from memory. Indexes by region / feeder / asset
are built once at startup so the command map renders quickly.

When `DATABRICKS_HOST` etc. are configured, the equivalent Spark/SQL queries
should be issued against the Delta tables (see `databricks_store.py` for the
adapter and `scripts/load_delta_tables.py` for the load path). The shape of
returned dicts is identical so the API layer is unchanged.
"""

from __future__ import annotations

import csv
import math
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from app.backend.config import DATA_DIR


def _to_float(v, default: float = 0.0) -> float:
    if v in (None, ""):
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _to_int(v, default: int = 0) -> int:
    if v in (None, ""):
        return default
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _to_bool(v) -> bool:
    if v in (True, "True", "true", 1, "1"):
        return True
    return False


class DataStore:
    """Read-only synthetic analytics store."""

    _instance: "DataStore | None" = None
    _lock = threading.Lock()

    @classmethod
    def instance(cls) -> "DataStore":
        with cls._lock:
            if cls._instance is None:
                cls._instance = DataStore()
            return cls._instance

    def __init__(self) -> None:
        print(f"[data_store] loading synthetic data from {DATA_DIR}")
        self.regions: dict[str, dict] = self._load_map("regions.csv", "region_id")
        self.depots: list[dict] = self._load("depots.csv")
        self.substations: dict[str, dict] = self._load_map("substations.csv", "substation_id")
        self.feeders: dict[str, dict] = self._load_map("feeders.csv", "feeder_id")
        self.assets: dict[str, dict] = self._load_map("assets.csv", "asset_id")
        self.health: dict[str, dict] = self._load_map("asset_health_scores.csv", "asset_id")
        self.inspections: list[dict] = self._load("inspection_events.csv")
        self.defects: list[dict] = self._load("defects.csv")
        self.vegetation: list[dict] = self._load("vegetation_spans.csv")
        self.outages: list[dict] = self._load("outage_events.csv")
        self.work_orders: list[dict] = self._load("work_orders.csv")
        self.critical_customers: list[dict] = self._load("critical_customers.csv")
        self.hazard_zones: list[dict] = self._load("hazard_exposure_zones.csv")
        self.documents: list[dict] = self._load("asset_documents.csv")
        self.mobile_gen: list[dict] = self._load("mobile_generation_candidates.csv")
        self.scenarios: list[dict] = self._load("scenario_runs.csv")

        self._index()

    # ---- loaders ---------------------------------------------------------

    def _load(self, name: str) -> list[dict]:
        path = DATA_DIR / name
        if not path.exists():
            print(f"[data_store] WARNING: missing {path}")
            return []
        with path.open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def _load_map(self, name: str, key: str) -> dict[str, dict]:
        return {row[key]: row for row in self._load(name)}

    def _index(self) -> None:
        self.assets_by_feeder: dict[str, list[dict]] = {}
        for a in self.assets.values():
            self.assets_by_feeder.setdefault(a["feeder_id"], []).append(a)

        self.assets_by_region: dict[str, list[dict]] = {}
        for a in self.assets.values():
            self.assets_by_region.setdefault(a["region_id"], []).append(a)

        self.inspections_by_asset: dict[str, list[dict]] = {}
        for i in self.inspections:
            self.inspections_by_asset.setdefault(i["asset_id"], []).append(i)

        self.defects_by_asset: dict[str, list[dict]] = {}
        for d in self.defects:
            self.defects_by_asset.setdefault(d["asset_id"], []).append(d)

        self.outages_by_asset: dict[str, list[dict]] = {}
        self.outages_by_feeder: dict[str, list[dict]] = {}
        for o in self.outages:
            if o.get("asset_id"):
                self.outages_by_asset.setdefault(o["asset_id"], []).append(o)
            self.outages_by_feeder.setdefault(o["feeder_id"], []).append(o)

        self.work_by_asset: dict[str, list[dict]] = {}
        self.work_by_feeder: dict[str, list[dict]] = {}
        for w in self.work_orders:
            if w.get("asset_id"):
                self.work_by_asset.setdefault(w["asset_id"], []).append(w)
            self.work_by_feeder.setdefault(w["feeder_id"], []).append(w)

        self.veg_by_feeder: dict[str, list[dict]] = {}
        self.veg_by_asset: dict[str, list[dict]] = {}
        for v in self.vegetation:
            self.veg_by_feeder.setdefault(v["feeder_id"], []).append(v)
            self.veg_by_asset.setdefault(v["nearest_asset_id"], []).append(v)

        self.docs_by_asset: dict[str, list[dict]] = {}
        self.docs_by_feeder: dict[str, list[dict]] = {}
        self.docs_by_region: dict[str, list[dict]] = {}
        for d in self.documents:
            if d.get("asset_id"):
                self.docs_by_asset.setdefault(d["asset_id"], []).append(d)
            if d.get("feeder_id"):
                self.docs_by_feeder.setdefault(d["feeder_id"], []).append(d)
            self.docs_by_region.setdefault(d["region_id"], []).append(d)

        self.depots_by_region: dict[str, list[dict]] = {}
        for dp in self.depots:
            self.depots_by_region.setdefault(dp["region_id"], []).append(dp)

        self.hazards_by_region: dict[str, list[dict]] = {}
        for h in self.hazard_zones:
            self.hazards_by_region.setdefault(h["region_id"], []).append(h)

        self.cc_by_region: dict[str, list[dict]] = {}
        for c in self.critical_customers:
            self.cc_by_region.setdefault(c["region_id"], []).append(c)

        self.mobgen_by_region: dict[str, list[dict]] = {}
        for m in self.mobile_gen:
            self.mobgen_by_region.setdefault(m["region_id"], []).append(m)

        print(
            f"[data_store] loaded "
            f"regions={len(self.regions)} feeders={len(self.feeders)} "
            f"assets={len(self.assets)} health={len(self.health)} "
            f"inspections={len(self.inspections)} defects={len(self.defects)} "
            f"outages={len(self.outages)} work={len(self.work_orders)} "
            f"docs={len(self.documents)}"
        )

    # ---- query helpers ---------------------------------------------------

    def list_regions(self) -> list[dict]:
        return list(self.regions.values())

    def list_assets_for_map(
        self,
        bbox: Optional[tuple[float, float, float, float]] = None,
        region_id: Optional[str] = None,
        risk_band: Optional[str] = None,
        asset_type: Optional[str] = None,
        scenario: Optional[str] = None,
        limit: int = 8000,
    ) -> list[dict]:
        """Return assets enriched with risk info for the map.

        `bbox` is (south_lat, west_lon, north_lat, east_lon).
        """
        candidates: list[dict] = []
        if region_id:
            pool = self.assets_by_region.get(region_id, [])
        else:
            pool = list(self.assets.values())

        for a in pool:
            if asset_type and a["asset_type"] != asset_type:
                continue
            h = self.health.get(a["asset_id"])
            if not h:
                continue
            if risk_band and h["risk_band"] != risk_band:
                continue
            lat = _to_float(a["lat"])
            lon = _to_float(a["lon"])
            if bbox:
                s, w, n, e = bbox
                if not (s <= lat <= n and w <= lon <= e):
                    continue
            candidates.append({
                "asset_id": a["asset_id"],
                "feeder_id": a["feeder_id"],
                "region_id": a["region_id"],
                "asset_type": a["asset_type"],
                "lat": lat,
                "lon": lon,
                "risk_score": _to_float(h["risk_score"]),
                "risk_band": h["risk_band"],
                "health_band": h["health_band"],
                "status": a["status"],
            })

        # If a scenario is supplied, prefer high-risk/critical assets first.
        if scenario in (
            "storm_readiness",
            "vegetation_program",
            "reliability_improvement",
            "capex_prioritisation",
        ):
            band_priority = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            candidates.sort(key=lambda x: (band_priority.get(x["risk_band"], 9), -x["risk_score"]))
        else:
            candidates.sort(key=lambda x: -x["risk_score"])

        return candidates[:limit]

    def asset_detail(self, asset_id: str) -> Optional[dict]:
        a = self.assets.get(asset_id)
        if not a:
            return None
        h = self.health.get(asset_id, {})
        f = self.feeders.get(a["feeder_id"], {})
        ss = self.substations.get(a["substation_id"], {})
        r = self.regions.get(a["region_id"], {})

        defects = self.defects_by_asset.get(asset_id, [])
        open_defects = sum(1 for d in defects if d["status"] == "open")
        open_critical = sum(1 for d in defects if d["status"] == "open" and d["severity"] in ("high", "critical"))
        outages = self.outages_by_asset.get(asset_id, [])

        def _within(o, months: int) -> bool:
            try:
                start = datetime.fromisoformat(o["outage_start"])
            except Exception:
                return False
            cutoff = datetime.utcnow()
            return (cutoff - start).days <= months * 30

        out_12 = sum(1 for o in outages if _within(o, 12))
        out_24 = sum(1 for o in outages if _within(o, 24))
        out_36 = sum(1 for o in outages if _within(o, 36))
        cust_impact = sum(_to_int(o["customers_interrupted"]) for o in outages)
        veg = self.veg_by_asset.get(asset_id, [])
        veg_max = max((_to_float(v["vegetation_risk_score"]) for v in veg), default=0.0)
        veg_min_clear = min((_to_float(v["clearance_m"]) for v in veg), default=9.99)
        work = self.work_by_asset.get(asset_id, [])
        open_work = sum(1 for w in work if w["status"] in ("draft", "approved", "scheduled", "in_progress"))
        completed_work = sum(1 for w in work if w["status"] == "completed")

        risk_band = h.get("risk_band", "medium")
        coastal = _to_float(a.get("coastal_corrosion_score"))
        if risk_band == "critical" and open_work == 0:
            rec = "Plan immediate remediation; no open work order detected."
        elif risk_band == "high" and veg_max > 60:
            rec = "Bundle vegetation treatment with asset inspection."
        elif risk_band in ("high", "critical") and coastal > 60:
            rec = "Schedule crossarm + insulator replacement before storm season."
        elif risk_band in ("high", "critical"):
            rec = "Add to next regional capex review."
        else:
            rec = "Monitor — risk within acceptable band."

        return {
            "asset_id": asset_id,
            "asset_type": a["asset_type"],
            "asset_name": a.get("asset_name", asset_id),
            "status": a["status"],
            "lat": _to_float(a["lat"]),
            "lon": _to_float(a["lon"]),
            "install_year": _to_int(a["install_year"]),
            "manufacturer": a["manufacturer"],
            "material": a["material"],
            "voltage_kv": _to_float(a["voltage_kv"]),
            "region_id": a["region_id"],
            "region_name": r.get("region_name", a["region_id"]),
            "feeder_id": a["feeder_id"],
            "feeder_name": f.get("feeder_name", a["feeder_id"]),
            "feeder_length_km": _to_float(f.get("feeder_length_km")),
            "customer_count": _to_int(f.get("customer_count")),
            "critical_customer_count": _to_int(f.get("critical_customer_count")),
            "substation_id": a["substation_id"],
            "substation_name": ss.get("substation_name", a["substation_id"]),
            "criticality_score": _to_float(a["criticality_score"]),
            "access_difficulty_score": _to_float(a["access_difficulty_score"]),
            "coastal_corrosion_score": _to_float(a["coastal_corrosion_score"]),
            "flood_exposure_score": _to_float(a["flood_exposure_score"]),
            "cyclone_exposure_score": _to_float(a["cyclone_exposure_score"]),
            "bushfire_exposure_score": _to_float(a["bushfire_exposure_score"]),
            "condition_score": _to_float(h.get("condition_score")),
            "health_band": h.get("health_band", "watch"),
            "risk_score": _to_float(h.get("risk_score")),
            "risk_band": h.get("risk_band", "medium"),
            "risk_drivers": [d for d in (h.get("risk_drivers") or "").split("|") if d],
            "failure_probability_12m": _to_float(h.get("failure_probability_12m")),
            "failure_probability_36m": _to_float(h.get("failure_probability_36m")),
            "defect_count_total": len(defects),
            "open_defects": open_defects,
            "open_critical_defects": open_critical,
            "outage_count_12m": out_12,
            "outage_count_24m": out_24,
            "outage_count_36m": out_36,
            "customers_impact_total": cust_impact,
            "vegetation_risk_score_max": veg_max,
            "vegetation_min_clearance_m": veg_min_clear,
            "open_work_orders": open_work,
            "completed_work_orders": completed_work,
            "recommended_action": rec,
        }

    def asset_inspection_history(self, asset_id: str) -> list[dict]:
        return sorted(
            self.inspections_by_asset.get(asset_id, []),
            key=lambda x: x["inspection_date"],
            reverse=True,
        )

    def asset_defects(self, asset_id: str) -> list[dict]:
        return sorted(
            self.defects_by_asset.get(asset_id, []),
            key=lambda x: x["detected_date"],
            reverse=True,
        )

    def asset_outages(self, asset_id: str) -> list[dict]:
        return sorted(
            self.outages_by_asset.get(asset_id, []),
            key=lambda x: x["outage_start"],
            reverse=True,
        )[:25]

    def asset_work_orders(self, asset_id: str) -> list[dict]:
        return self.work_by_asset.get(asset_id, [])

    def regional_summary(self) -> list[dict]:
        out = []
        for r in self.regions.values():
            assets = self.assets_by_region.get(r["region_id"], [])
            high = critical = 0
            risk_total = 0.0
            risk_n = 0
            customers_at_risk = 0
            for a in assets:
                h = self.health.get(a["asset_id"])
                if not h:
                    continue
                if h["risk_band"] == "high":
                    high += 1
                elif h["risk_band"] == "critical":
                    critical += 1
                    f = self.feeders.get(a["feeder_id"], {})
                    customers_at_risk += _to_int(f.get("customer_count", 0))
                risk_total += _to_float(h["risk_score"])
                risk_n += 1
            vegetation_backlog = sum(1 for v in self.vegetation
                                    if v["region_id"] == r["region_id"] and _to_int(v["overdue_days"]) > 30)
            mobile_gen_ready = sum(1 for m in self.mobile_gen
                                  if m["region_id"] == r["region_id"] and _to_bool(m["connection_ready"]))
            critical_customer_count = sum(_to_int(f["critical_customer_count"]) for f in self.feeders.values() if f["region_id"] == r["region_id"])
            planned_work = sum(1 for w in self.work_orders
                              if w["region_id"] == r["region_id"]
                              and w["status"] in ("approved", "scheduled", "in_progress"))
            out.append({
                "region_id": r["region_id"],
                "region_name": r["region_name"],
                "total_assets": len(assets),
                "high_risk_assets": high,
                "critical_risk_assets": critical,
                "vegetation_backlog": vegetation_backlog,
                "mobile_gen_ready_sites": mobile_gen_ready,
                "critical_customer_count_exposed": critical_customer_count,
                "planned_work_count": planned_work,
                "avg_risk_score": (risk_total / risk_n) if risk_n else 0.0,
                "customers_at_risk": customers_at_risk,
            })
        return out

    def feeder_summary(self, region_id: Optional[str] = None, limit: int = 200) -> list[dict]:
        out = []
        for f in self.feeders.values():
            if region_id and f["region_id"] != region_id:
                continue
            assets = self.assets_by_feeder.get(f["feeder_id"], [])
            high = critical = 0
            risk_total = 0.0
            risk_n = 0
            for a in assets:
                h = self.health.get(a["asset_id"])
                if not h:
                    continue
                if h["risk_band"] == "high":
                    high += 1
                elif h["risk_band"] == "critical":
                    critical += 1
                risk_total += _to_float(h["risk_score"])
                risk_n += 1
            outages_12 = sum(1 for o in self.outages_by_feeder.get(f["feeder_id"], [])
                            if (datetime.utcnow() - datetime.fromisoformat(o["outage_start"])).days <= 365)
            saidi = sum(_to_float(o["saidi_minutes"]) for o in self.outages_by_feeder.get(f["feeder_id"], [])
                        if (datetime.utcnow() - datetime.fromisoformat(o["outage_start"])).days <= 365)
            saifi = sum(_to_float(o["saifi_count"]) for o in self.outages_by_feeder.get(f["feeder_id"], [])
                        if (datetime.utcnow() - datetime.fromisoformat(o["outage_start"])).days <= 365)
            veg_scores = [_to_float(v["vegetation_risk_score"]) for v in self.veg_by_feeder.get(f["feeder_id"], [])]
            avg_veg = sum(veg_scores) / len(veg_scores) if veg_scores else 0.0
            planned = sum(1 for w in self.work_by_feeder.get(f["feeder_id"], [])
                          if w["status"] in ("approved", "scheduled", "in_progress"))
            out.append({
                "feeder_id": f["feeder_id"],
                "feeder_name": f["feeder_name"],
                "region_id": f["region_id"],
                "region_name": self.regions.get(f["region_id"], {}).get("region_name", f["region_id"]),
                "customer_count": _to_int(f["customer_count"]),
                "critical_customer_count": _to_int(f["critical_customer_count"]),
                "asset_count": len(assets),
                "high_risk_assets": high,
                "critical_risk_assets": critical,
                "avg_risk_score": (risk_total / risk_n) if risk_n else 0.0,
                "outage_count_12m": outages_12,
                "saidi_minutes_12m": round(saidi, 2),
                "saifi_count_12m": round(saifi, 4),
                "avg_vegetation_risk_score": round(avg_veg, 1),
                "planned_work_count": planned,
            })
        out.sort(key=lambda x: -(x["critical_risk_assets"] * 10 + x["high_risk_assets"]))
        return out[:limit]

    def documents_for_asset(self, asset_id: str) -> list[dict]:
        a = self.assets.get(asset_id)
        if not a:
            return []
        out = list(self.docs_by_asset.get(asset_id, []))
        # Add feeder-/region-level standards relevant to the asset.
        for d in self.docs_by_feeder.get(a["feeder_id"], []):
            if d not in out:
                out.append(d)
        # Add region-level policies (cap).
        for d in self.docs_by_region.get(a["region_id"], [])[:10]:
            if d["document_type"] in ("maintenance_standard", "vegetation_policy", "storm_response_plan") and d not in out:
                out.append(d)
        return out[:25]

    def hazards(self, region_id: Optional[str] = None, hazard_type: Optional[str] = None) -> list[dict]:
        if region_id:
            pool = self.hazards_by_region.get(region_id, [])
        else:
            pool = self.hazard_zones
        if hazard_type:
            pool = [h for h in pool if h["hazard_type"] == hazard_type]
        return pool

    # ---- scenario-aware bundle ------------------------------------------

    # Per-scenario configuration that drives which hazards / extra layers
    # are returned, and which preset the frontend should apply.
    SCENARIO_CONFIG: dict = {
        "normal": {
            "hazard_types": None,  # all
            "asset_filter": None,
            "headline": "Normal operations",
            "narrative": "Baseline view across all hazards and asset health bands.",
            "primary_layers": ["assets", "hazards", "critical_customers", "depots"],
            "extras": [],
        },
        "storm_readiness": {
            "hazard_types": {"cyclone", "storm", "flood"},
            "asset_filter": "storm_exposed",
            "headline": "Storm-season readiness",
            "narrative": "Cyclone / storm / flood hazard rings overlay on assets with high coastal exposure. Mobile generation and critical customers prioritised.",
            "primary_layers": ["assets", "hazards", "critical_customers", "mobile_gen"],
            "extras": ["risk_extrusions"],
        },
        "vegetation_program": {
            "hazard_types": {"bushfire", "heat"},
            "asset_filter": "vegetation_exposed",
            "headline": "Vegetation treatment program",
            "narrative": "Backlog of vegetation spans (treatment overdue) rendered as risk-graded lines. Bushfire hazards retained; storm/flood hidden.",
            "primary_layers": ["vegetation_lines", "assets", "hazards"],
            "extras": ["vegetation_lines"],
        },
        "reliability_improvement": {
            "hazard_types": set(),  # no hazards
            "asset_filter": "reliability",
            "headline": "Reliability improvement",
            "narrative": "Top outage-prone feeders highlighted as connecting lines. Outage hot-spots dominate the view.",
            "primary_layers": ["outage_lines", "assets", "critical_customers"],
            "extras": ["outage_lines"],
        },
        "capex_prioritisation": {
            "hazard_types": set(),
            "asset_filter": "capex",
            "headline": "Capex prioritisation",
            "narrative": "Ageing assets (install_year < 1985) and high-criticality replacement candidates raised as 3D risk extrusions.",
            "primary_layers": ["risk_extrusions", "assets", "critical_customers"],
            "extras": ["risk_extrusions"],
        },
        "field_inspection_review": {
            "hazard_types": set(),
            "asset_filter": "inspection",
            "headline": "Field inspection review",
            "narrative": "Assets whose last inspection is overdue, weighted by access difficulty.",
            "primary_layers": ["assets", "depots"],
            "extras": [],
        },
    }

    def _apply_scenario_asset_filter(self, candidates: list[dict], scenario: Optional[str]) -> list[dict]:
        """Filter the asset candidate list with scenario-specific logic.

        Inputs are the enriched dicts produced by `list_assets_for_map` (which
        contain risk_score / risk_band) but we re-pull source columns from
        `self.assets` for richer filters (install_year, cyclone_exposure, etc.).
        """
        if not scenario or scenario == "normal":
            return candidates
        cfg = self.SCENARIO_CONFIG.get(scenario, {})
        flt = cfg.get("asset_filter")
        if not flt:
            return candidates

        # Pre-compute lookups we will need.
        veg_feeders = {fid for fid in self.veg_by_feeder.keys()}
        # Outage counts per feeder for reliability scenario.
        outage_counts = {fid: len(events) for fid, events in self.outages_by_feeder.items()}
        # Top 30 feeders by outage count (a feeder is "reliability hot" if it's here).
        reliability_feeders = {
            fid for fid, _ in sorted(outage_counts.items(), key=lambda kv: -kv[1])[:30]
        }
        # Cache of last inspection date per asset for inspection scenario.
        last_inspection: dict[str, str] = {}
        for ins in self.inspections:
            aid = ins.get("asset_id")
            d = ins.get("inspection_date")
            if not aid or not d:
                continue
            prev = last_inspection.get(aid)
            if prev is None or d > prev:
                last_inspection[aid] = d

        kept: list[dict] = []
        for a in candidates:
            src = self.assets.get(a["asset_id"], {})
            if flt == "storm_exposed":
                if (
                    _to_float(src.get("cyclone_exposure_score")) > 45
                    or _to_float(src.get("coastal_corrosion_score")) > 45
                    or _to_float(src.get("flood_exposure_score")) > 50
                    or a["risk_band"] in ("high", "critical")
                ):
                    kept.append(a)
            elif flt == "vegetation_exposed":
                if a["feeder_id"] in veg_feeders and (
                    a["risk_band"] in ("medium", "high", "critical")
                    or _to_float(src.get("bushfire_exposure_score")) > 35
                ):
                    kept.append(a)
            elif flt == "reliability":
                if a["feeder_id"] in reliability_feeders:
                    kept.append(a)
            elif flt == "capex":
                yr = _to_int(src.get("install_year"))
                if (yr and yr < 1985) or a["risk_score"] >= 70 or _to_float(src.get("criticality_score")) >= 70:
                    kept.append(a)
            elif flt == "inspection":
                d = last_inspection.get(a["asset_id"])
                # Stale if no inspection on record or older than 24 months.
                stale = True
                if d:
                    try:
                        ins_date = datetime.fromisoformat(d)
                        stale = (datetime.utcnow() - ins_date).days > 730
                    except Exception:
                        stale = True
                if stale and (_to_float(src.get("access_difficulty_score")) > 40 or a["risk_band"] in ("medium", "high", "critical")):
                    kept.append(a)
            else:
                kept.append(a)
        return kept

    def vegetation_lines(self, region_id: Optional[str] = None, limit: int = 600) -> list[dict]:
        """Vegetation spans rendered as line segments (span → nearest asset).

        Returns the highest-risk overdue spans first so the visible set is the
        treatment backlog.
        """
        rows: list[dict] = []
        for v in self.vegetation:
            if region_id and v.get("region_id") != region_id:
                continue
            asset = self.assets.get(v.get("nearest_asset_id"))
            if not asset:
                continue
            risk = _to_float(v.get("vegetation_risk_score"))
            overdue = _to_int(v.get("overdue_days"))
            # Only include spans that are either overdue or above medium risk.
            if overdue <= 0 and risk < 40:
                continue
            rows.append({
                "vegetation_span_id": v.get("vegetation_span_id"),
                "feeder_id": v.get("feeder_id"),
                "region_id": v.get("region_id"),
                "from_lat": _to_float(v.get("lat")),
                "from_lon": _to_float(v.get("lon")),
                "to_lat": _to_float(asset.get("lat")),
                "to_lon": _to_float(asset.get("lon")),
                "risk_score": risk,
                "overdue_days": overdue,
                "treatment_priority": v.get("treatment_priority"),
            })
        rows.sort(key=lambda r: (-r["overdue_days"], -r["risk_score"]))
        return rows[:limit]

    def outage_lines(self, region_id: Optional[str] = None, limit: int = 40) -> list[dict]:
        """Top outage-prone feeders rendered as lines.

        Each feeder line connects the substation centroid to the average asset
        location for that feeder — gives the map a directed "feeder span" feel
        even though we don't have true feeder geometry.
        """
        feeder_summaries: list[dict] = []
        for fid, events in self.outages_by_feeder.items():
            feeder = self.feeders.get(fid)
            if not feeder:
                continue
            if region_id and feeder.get("region_id") != region_id:
                continue
            assets = self.assets_by_feeder.get(fid, [])
            if not assets:
                continue
            substation = self.substations.get(feeder.get("substation_id"))
            if not substation:
                continue
            avg_asset_lat = sum(_to_float(a["lat"]) for a in assets) / len(assets)
            avg_asset_lon = sum(_to_float(a["lon"]) for a in assets) / len(assets)
            outage_count = len(events)
            saidi = sum(_to_float(e.get("saidi_minutes")) for e in events)
            customers_interrupted = sum(_to_int(e.get("customers_interrupted")) for e in events)
            feeder_summaries.append({
                "feeder_id": fid,
                "feeder_name": feeder.get("feeder_name"),
                "region_id": feeder.get("region_id"),
                "from_lat": _to_float(substation.get("lat")),
                "from_lon": _to_float(substation.get("lon")),
                "to_lat": avg_asset_lat,
                "to_lon": avg_asset_lon,
                "outage_count": outage_count,
                "saidi_minutes": round(saidi, 1),
                "customers_interrupted": customers_interrupted,
            })
        feeder_summaries.sort(key=lambda r: -r["outage_count"])
        return feeder_summaries[:limit]

    def risk_extrusions(self, candidates: list[dict], limit: int = 80) -> list[dict]:
        """Top-N assets as 3D extrusion data (lat, lon, height_m).

        Height is proportional to risk_score so the SEQ metro view in storm /
        capex scenarios shows visible 3D bars where things really matter.
        """
        # Already arrives sorted by risk band/score in scenario mode.
        out = []
        for a in candidates[:limit]:
            src = self.assets.get(a["asset_id"], {})
            criticality = _to_float(src.get("criticality_score"))
            base_h = 200 + (a["risk_score"] * 30) + (criticality * 12)
            out.append({
                "asset_id": a["asset_id"],
                "lat": a["lat"],
                "lon": a["lon"],
                "risk_score": a["risk_score"],
                "risk_band": a["risk_band"],
                "height_m": round(base_h, 1),
                "feeder_id": a["feeder_id"],
            })
        return out

    def get_map_bundle(
        self,
        scenario: Optional[str] = None,
        region_id: Optional[str] = None,
        risk_band: Optional[str] = None,
        asset_type: Optional[str] = None,
        asset_limit: int = 4000,
    ) -> dict:
        """Build the full scenario-aware map bundle."""
        scenario_key = scenario or "normal"
        cfg = self.SCENARIO_CONFIG.get(scenario_key, self.SCENARIO_CONFIG["normal"])

        # Start with the unfiltered candidate list (sort applied for scenario).
        # We oversample so that after scenario-specific filtering we still hit
        # a useful asset count.
        raw_assets = self.list_assets_for_map(
            region_id=region_id,
            risk_band=risk_band,
            asset_type=asset_type,
            scenario=scenario_key,
            limit=max(asset_limit * 2, 8000),
        )
        scenario_assets = self._apply_scenario_asset_filter(raw_assets, scenario_key)
        scenario_assets = scenario_assets[:asset_limit]

        # Filter hazards by scenario-allowed types.
        all_hazards = self.hazards(region_id=region_id)
        hz_types = cfg.get("hazard_types")
        if hz_types is None:
            hazards = all_hazards
        elif not hz_types:
            hazards = []
        else:
            hazards = [h for h in all_hazards if h.get("hazard_type") in hz_types]

        critical_customers = self.critical_customers_for_region(region_id=region_id)
        depots = self.depots_for_region(region_id=region_id)
        mobgen = self.mobile_gen_for_region(region_id=region_id)

        extras: dict = {}
        if "vegetation_lines" in cfg.get("extras", []):
            extras["vegetation_lines"] = self.vegetation_lines(region_id=region_id, limit=600)
        else:
            extras["vegetation_lines"] = []
        if "outage_lines" in cfg.get("extras", []):
            extras["outage_lines"] = self.outage_lines(region_id=region_id, limit=40)
        else:
            extras["outage_lines"] = []
        if "risk_extrusions" in cfg.get("extras", []):
            extras["risk_extrusions"] = self.risk_extrusions(scenario_assets, limit=80)
        else:
            extras["risk_extrusions"] = []

        # KPIs from the (potentially filtered) asset set.
        high = sum(1 for a in scenario_assets if a["risk_band"] == "high")
        critical = sum(1 for a in scenario_assets if a["risk_band"] == "critical")
        customers_exposed = sum(
            _to_int(self.feeders.get(a["feeder_id"], {}).get("customer_count"))
            for a in scenario_assets if a["risk_band"] in ("high", "critical")
        )
        feeders_count = len({a["feeder_id"] for a in scenario_assets})

        scenario_summary = {
            "scenario_id": scenario_key,
            "headline": cfg.get("headline"),
            "narrative": cfg.get("narrative"),
            "primary_layers": cfg.get("primary_layers", []),
            "counts": {
                "assets_shown": len(scenario_assets),
                "hazards_shown": len(hazards),
                "vegetation_lines": len(extras["vegetation_lines"]),
                "outage_lines": len(extras["outage_lines"]),
                "risk_extrusions": len(extras["risk_extrusions"]),
            },
        }

        return {
            "assets": scenario_assets,
            "hazards": hazards,
            "critical_customers": critical_customers,
            "depots": depots,
            "mobile_gen_sites": mobgen,
            "vegetation_lines": extras["vegetation_lines"],
            "outage_lines": extras["outage_lines"],
            "risk_extrusions": extras["risk_extrusions"],
            "scenario_summary": scenario_summary,
            "feeders_count": feeders_count,
            "high_risk_asset_count": high,
            "critical_asset_count": critical,
            "customers_exposed": customers_exposed,
        }

    def critical_customers_for_region(self, region_id: Optional[str] = None) -> list[dict]:
        if region_id:
            return self.cc_by_region.get(region_id, [])
        return self.critical_customers

    def depots_for_region(self, region_id: Optional[str] = None) -> list[dict]:
        if region_id:
            return self.depots_by_region.get(region_id, [])
        return self.depots

    def mobile_gen_for_region(self, region_id: Optional[str] = None) -> list[dict]:
        if region_id:
            return self.mobgen_by_region.get(region_id, [])
        return self.mobile_gen

    def feeder_by_id(self, feeder_id: str) -> Optional[dict]:
        return self.feeders.get(feeder_id)

    def region_by_id(self, region_id: str) -> Optional[dict]:
        return self.regions.get(region_id)

    def assets_in_region(self, region_id: str) -> list[dict]:
        return self.assets_by_region.get(region_id, [])

    def assets_in_feeder(self, feeder_id: str) -> list[dict]:
        return self.assets_by_feeder.get(feeder_id, [])

    def health_for(self, asset_id: str) -> dict:
        return self.health.get(asset_id, {})

    def closest_depot(self, region_id: str, lat: float, lon: float) -> Optional[dict]:
        candidates = self.depots_by_region.get(region_id, [])
        if not candidates:
            return None
        best = None
        best_d = math.inf
        for d in candidates:
            dlat = _to_float(d["lat"]) - lat
            dlon = _to_float(d["lon"]) - lon
            dist = dlat ** 2 + dlon ** 2
            if dist < best_d:
                best_d = dist
                best = d
        return best
