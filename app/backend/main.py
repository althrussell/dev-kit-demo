"""
GridLens Queensland — FastAPI backend.

Run locally:
    DATABRICKS_VOLUME_PATH=/Volumes/anzgt_may/energyq/asset_docs \
        uvicorn app.backend.main:app --reload --port 8000

The frontend Vite dev server proxies /api/* to this backend.
In production (Databricks Apps), uvicorn binds to DATABRICKS_APP_PORT.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from app.backend import models
from app.backend.services.data_store import DataStore
from app.backend.services.documents import DocumentSearchService
from app.backend.services.genie import GenieService
from app.backend.services.agent import GridOperationsAdvisor
from app.backend.services.lakebase import LakebaseService


app = FastAPI(
    title="GridLens Queensland API",
    version="0.1.0",
    description="Geospatial asset intelligence backend for Energy Queensland demo.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://localhost:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Services (singletons)
# ---------------------------------------------------------------------------
data_store: DataStore | None = None
docs_service: DocumentSearchService | None = None
genie_service: GenieService | None = None
agent_advisor: GridOperationsAdvisor | None = None
lakebase_service: LakebaseService | None = None


@app.on_event("startup")
def _startup() -> None:
    global data_store, docs_service, genie_service, agent_advisor, lakebase_service
    t0 = time.time()
    data_store = DataStore.instance()
    docs_service = DocumentSearchService.instance()
    genie_service = GenieService.instance()
    agent_advisor = GridOperationsAdvisor()
    lakebase_service = LakebaseService.instance()
    print(f"[startup] services ready in {time.time() - t0:.2f}s")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/api/healthz")
def healthz() -> dict:
    return {"status": "ok", "service": "gridlens-queensland", "mode": "local-synthetic"}


# ---------------------------------------------------------------------------
# Regions / scenarios
# ---------------------------------------------------------------------------


@app.get("/api/regions", response_model=list[models.Region])
def list_regions():
    return [models.Region(**r) for r in data_store.list_regions()]  # type: ignore[union-attr]


@app.get("/api/scenarios")
def list_scenarios():
    # Built-in scenarios + Lakebase-stored scenarios.
    built_in = [
        {"scenario_id": "normal", "scenario_name": "Normal operations", "scenario_type": "normal", "region_id": None},
        {"scenario_id": "storm_readiness", "scenario_name": "Storm readiness", "scenario_type": "storm_readiness", "region_id": None},
        {"scenario_id": "vegetation_program", "scenario_name": "Vegetation program", "scenario_type": "vegetation_program", "region_id": None},
        {"scenario_id": "reliability_improvement", "scenario_name": "Reliability improvement", "scenario_type": "reliability_improvement", "region_id": None},
        {"scenario_id": "capex_prioritisation", "scenario_name": "Capex prioritisation", "scenario_type": "capex_prioritisation", "region_id": None},
        {"scenario_id": "field_inspection_review", "scenario_name": "Field inspection review", "scenario_type": "field_inspection_review", "region_id": None},
    ]
    try:
        lb_scenarios = lakebase_service.list_scenarios()  # type: ignore[union-attr]
    except Exception as e:
        print(f"[scenarios] lakebase fetch failed: {e}")
        lb_scenarios = []
    return {"built_in": built_in, "saved": lb_scenarios}


# ---------------------------------------------------------------------------
# Map bundle
# ---------------------------------------------------------------------------


def _parse_bbox(bbox: Optional[str]) -> Optional[tuple[float, float, float, float]]:
    if not bbox:
        return None
    parts = [p.strip() for p in bbox.split(",")]
    if len(parts) != 4:
        raise HTTPException(400, detail="bbox must be 'south,west,north,east'")
    try:
        return tuple(float(p) for p in parts)  # type: ignore[return-value]
    except ValueError:
        raise HTTPException(400, detail="bbox must contain numbers")


@app.get("/api/map/assets")
def map_assets(
    bbox: Optional[str] = None,
    region: Optional[str] = None,
    risk_band: Optional[str] = None,
    asset_type: Optional[str] = None,
    scenario: Optional[str] = None,
    limit: int = 6000,
):
    return data_store.list_assets_for_map(  # type: ignore[union-attr]
        bbox=_parse_bbox(bbox),
        region_id=region,
        risk_band=risk_band,
        asset_type=asset_type,
        scenario=scenario,
        limit=limit,
    )


@app.get("/api/map/feeders")
def map_feeders(region: Optional[str] = None, scenario: Optional[str] = None):
    return data_store.feeder_summary(region_id=region, limit=300)  # type: ignore[union-attr]


@app.get("/api/map/hazards")
def map_hazards(region: Optional[str] = None, hazard_type: Optional[str] = None):
    return data_store.hazards(region_id=region, hazard_type=hazard_type)  # type: ignore[union-attr]


@app.get("/api/map/critical-customers")
def map_critical_customers(region: Optional[str] = None):
    return data_store.critical_customers_for_region(region_id=region)  # type: ignore[union-attr]


@app.get("/api/map/depots")
def map_depots(region: Optional[str] = None):
    return data_store.depots_for_region(region_id=region)  # type: ignore[union-attr]


@app.get("/api/map/mobile-gen")
def map_mobile_gen(region: Optional[str] = None):
    return data_store.mobile_gen_for_region(region_id=region)  # type: ignore[union-attr]


@app.get("/api/map/bundle")
def map_bundle(
    region: Optional[str] = None,
    scenario: Optional[str] = None,
    risk_band: Optional[str] = None,
    asset_type: Optional[str] = None,
    asset_limit: int = 4000,
):
    """Scenario-aware bundle endpoint.

    Returns a fully tailored payload per scenario (different hazards filtered,
    different asset subset, and optional `vegetation_lines` / `outage_lines` /
    `risk_extrusions` extras) so the map visibly transforms when the user
    switches scenarios in the sidebar.

    Also enriches the payload with real PostGIS spatial joins when the
    Lakebase `gridlens_geo` schema is available — adding `hazard_impact_assets`
    (assets within 20km of severe hazards, computed via ST_DWithin on
    geography columns) and `hazard_polygons` (true PostGIS-buffered polygons
    rather than circle approximations).
    """
    bundle = data_store.get_map_bundle(  # type: ignore[union-attr]
        scenario=scenario,
        region_id=region,
        risk_band=risk_band,
        asset_type=asset_type,
        asset_limit=asset_limit,
    )

    # Opportunistically enrich with Lakebase PostGIS spatial queries.
    bundle["hazard_impact_assets"] = []
    bundle["hazard_polygons"] = []
    if lakebase_service and scenario in ("storm_readiness", "normal", "vegetation_program"):
        try:
            if lakebase_service.has_postgis():
                hazard_filter = None
                if scenario == "storm_readiness":
                    hazard_filter = ["cyclone", "storm", "flood"]
                elif scenario == "vegetation_program":
                    hazard_filter = ["bushfire", "heat"]
                # Distance-based asset risk: real ST_DWithin against geography.
                bundle["hazard_impact_assets"] = lakebase_service.assets_within_hazard(
                    hazard_types=hazard_filter,
                    min_severity=55.0,
                    distance_m=20_000.0,
                    region_id=region,
                    limit=1200,
                )
                # PostGIS-buffered polygon footprints for hazard zones.
                bundle["hazard_polygons"] = lakebase_service.hazard_polygons(
                    hazard_types=hazard_filter,
                    region_id=region,
                    limit=120,
                )
                # Surface PostGIS usage in the scenario summary counts.
                if "scenario_summary" in bundle:
                    bundle["scenario_summary"]["counts"]["postgis_impact_assets"] = len(
                        bundle["hazard_impact_assets"]
                    )
                    bundle["scenario_summary"]["counts"]["postgis_hazard_polygons"] = len(
                        bundle["hazard_polygons"]
                    )
        except Exception as e:
            print(f"[map/bundle] PostGIS enrichment skipped: {e}")
    return bundle


# ---------------------------------------------------------------------------
# Asset detail
# ---------------------------------------------------------------------------


@app.get("/api/assets/{asset_id}")
def asset_detail(asset_id: str):
    a = data_store.asset_detail(asset_id)  # type: ignore[union-attr]
    if not a:
        raise HTTPException(404, detail=f"asset {asset_id} not found")
    return a


@app.get("/api/assets/{asset_id}/inspections")
def asset_inspections(asset_id: str):
    return data_store.asset_inspection_history(asset_id)  # type: ignore[union-attr]


@app.get("/api/assets/{asset_id}/defects")
def asset_defects(asset_id: str):
    return data_store.asset_defects(asset_id)  # type: ignore[union-attr]


@app.get("/api/assets/{asset_id}/outages")
def asset_outages(asset_id: str):
    return data_store.asset_outages(asset_id)  # type: ignore[union-attr]


@app.get("/api/assets/{asset_id}/work-orders")
def asset_work_orders(asset_id: str):
    return data_store.asset_work_orders(asset_id)  # type: ignore[union-attr]


@app.get("/api/assets/{asset_id}/documents")
def asset_documents(asset_id: str):
    docs = data_store.documents_for_asset(asset_id)  # type: ignore[union-attr]
    # Enrich with excerpt from the local document index when available.
    out = []
    for d in docs:
        excerpt = ""
        full = docs_service.read_full(d["document_id"])  # type: ignore[union-attr]
        if full:
            excerpt = " ".join(
                line.strip() for line in full["content"].splitlines()
                if line.strip() and not line.startswith("#")
            )[:300]
        out.append({
            "document_id": d["document_id"],
            "document_type": d["document_type"],
            "document_title": d["document_title"],
            "volume_path": d["volume_path"],
            "region_id": d["region_id"],
            "feeder_id": d.get("feeder_id"),
            "asset_id": d.get("asset_id"),
            "excerpt": excerpt or d.get("document_summary"),
            "sensitivity_classification": d.get("sensitivity_classification"),
            "created_date": d.get("created_date"),
        })
    return out


@app.get("/api/documents/search")
def documents_search(
    q: str,
    region_id: str | None = None,
    top_k: int = 6,
):
    """Knowledge-Assistant-backed document search.

    Falls back to local keyword search when the KA endpoint env var is unset
    or the KA call fails (see DocumentSearchService.semantic_search).
    """
    if not q or not q.strip():
        raise HTTPException(400, detail="query parameter `q` is required")
    return docs_service.semantic_search(  # type: ignore[union-attr]
        q.strip(), region_id=region_id, top_k=top_k
    )


@app.get("/api/documents/{document_id}")
def document_full(document_id: str):
    full = docs_service.read_full(document_id)  # type: ignore[union-attr]
    if not full:
        raise HTTPException(404, detail=f"document {document_id} not found")
    return full


# ---------------------------------------------------------------------------
# Regional analytics
# ---------------------------------------------------------------------------


@app.get("/api/regional-risk")
def regional_risk():
    return data_store.regional_summary()  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Work packages
# ---------------------------------------------------------------------------


@app.get("/api/work-packages")
def list_work_packages():
    return lakebase_service.list_work_packages()  # type: ignore[union-attr]


@app.get("/api/work-packages/{work_package_id}")
def get_work_package(work_package_id: str):
    wp = lakebase_service.get_work_package(work_package_id)  # type: ignore[union-attr]
    if not wp:
        raise HTTPException(404, detail=f"work package {work_package_id} not found")
    return wp


@app.post("/api/work-packages")
def create_work_package(body: models.WorkPackageCreate):
    payload = body.model_dump()
    return lakebase_service.create_work_package(payload)  # type: ignore[union-attr]


@app.patch("/api/work-packages/{work_package_id}")
def patch_work_package(work_package_id: str, body: models.WorkPackagePatch):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    wp = lakebase_service.patch_work_package(work_package_id, patch)  # type: ignore[union-attr]
    if not wp:
        raise HTTPException(404, detail=f"work package {work_package_id} not found")
    return wp


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


@app.post("/api/agent/investigate")
def agent_investigate(req: models.AgentInvestigateRequest):
    result = agent_advisor.investigate(  # type: ignore[union-attr]
        prompt=req.prompt,
        asset_id=req.asset_id,
        feeder_id=req.feeder_id,
        region_id=req.region_id,
        scenario_type=req.scenario_type,
        selected_asset_ids=req.selected_asset_ids,
    )
    # Persist recommendation to Lakebase.
    try:
        lakebase_service.save_recommendation(  # type: ignore[union-attr]
            rec_id=result["recommendation_id"],
            prompt=req.prompt,
            body=result["body"],
            confidence=result["confidence"],
            evidence=result["evidence"],
        )
    except Exception as e:
        print(f"[agent_investigate] failed to persist: {e}")
    return result


@app.post("/api/agent/create-work-package")
def agent_create_work_package(req: models.AgentCreateWorkPackageRequest):
    region_id = req.region_id
    feeder_id = req.feeder_id
    title = req.title or f"AI recommendation {req.recommendation_id}"
    asset_ids = req.asset_ids or []
    # Derive cost / hours estimates.
    est_hours = round(len(asset_ids) * 4.5, 1) if asset_ids else 8.0
    est_cost = round(est_hours * 285 + 6500, 2)
    # Suggested depot.
    depot_id = ""
    if asset_ids:
        a = data_store.assets.get(asset_ids[0])  # type: ignore[union-attr]
        if a:
            d = data_store.closest_depot(region_id, float(a["lat"]), float(a["lon"]))  # type: ignore[union-attr]
            if d:
                depot_id = d["depot_id"]
    payload = {
        "title": title,
        "region_id": region_id,
        "feeder_id": feeder_id,
        "scenario_type": "storm_readiness",
        "priority": req.priority,
        "status": "pending_approval",
        "asset_ids": asset_ids,
        "evidence_summary": f"Generated from agent recommendation {req.recommendation_id}",
        "recommended_by_agent": True,
        "estimated_hours": est_hours,
        "estimated_cost_aud": est_cost,
        "estimated_customer_impact_reduction": len(asset_ids) * 120,
        "suggested_depot_id": depot_id,
    }
    return lakebase_service.create_work_package(payload)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Genie
# ---------------------------------------------------------------------------


@app.post("/api/genie/ask")
def genie_ask(req: models.GenieAskRequest):
    return genie_service.ask(req.question)  # type: ignore[union-attr]


@app.get("/api/genie/suggested-questions")
def genie_suggested():
    # Verified live against the gridlens-network-intel Genie space. Each
    # question is known to generate valid SQL over the energyq_gold /
    # energyq_silver tables and return non-empty rows.
    return [
        "Rank regions by total high and critical risk assets.",
        "Show me feeders with repeated vegetation-related outages in the last 12 months.",
        "Rank regions by vegetation backlog (spans overdue by more than 30 days).",
        "Which 10 feeders should we prioritise work on?",
        "How many critical customers are exposed to high-risk assets, by region?",
        "How many work orders are approved, scheduled or in progress by region?",
        "Which assets are in cyclone, storm or flood hazard zones?",
        "Top 10 assets by risk score for storm-season prioritisation.",
    ]


# ---------------------------------------------------------------------------
# Executive briefing
# ---------------------------------------------------------------------------


@app.get("/api/executive-briefing")
def executive_briefing(region: Optional[str] = None):
    ds = data_store  # type: ignore[assignment]
    summary = ds.regional_summary()  # type: ignore[union-attr]
    if region:
        summary = [r for r in summary if r["region_id"] == region]
    summary.sort(key=lambda r: -(r["critical_risk_assets"] * 5 + r["high_risk_assets"]))
    top_zones = summary[:5]

    total_high = sum(r["high_risk_assets"] for r in summary)
    total_critical = sum(r["critical_risk_assets"] for r in summary)
    total_planned = sum(r["planned_work_count"] for r in summary)
    coverage = 0.0
    if total_high + total_critical > 0:
        coverage = min(100.0, round(100.0 * total_planned / (total_high + total_critical), 1))

    headline = (
        f"{total_critical} critical and {total_high} high-risk assets identified across "
        f"{len(summary)} regions. Planned remediation coverage: {coverage}%."
    )

    summary_text = (
        "GridLens has aggregated asset health, outage history, vegetation backlog and "
        "hazard exposure for the selected regions. The top risk zones below are ranked "
        "by combined high + critical asset count. Recommended actions focus on reducing "
        "customer impact via bundled remediation prior to storm season."
    )

    top_recs = []
    for r in top_zones:
        risky = r["high_risk_assets"] + r["critical_risk_assets"]
        cov = min(100.0, round(100.0 * r["planned_work_count"] / risky, 1)) if risky else 0.0
        top_recs.append({
            "region_id": r["region_id"],
            "region_name": r["region_name"],
            "headline": (
                f"{r['critical_risk_assets']} critical + {r['high_risk_assets']} high-risk assets, "
                f"{r['vegetation_backlog']} vegetation spans overdue, {cov}% planned coverage."
            ),
            "estimated_customer_impact_reduction": int(r["customers_at_risk"] * 0.25),
            "recommended_action": "Bundle remediation and pre-season inspection.",
        })

    estimated_impact = sum(rec["estimated_customer_impact_reduction"] for rec in top_recs)

    open_decisions = [
        "Approve Mackay storm readiness bundle (REG-MKY).",
        "Confirm mobile generation pre-positioning for Townsville / Cairns.",
        "Sign off Central Queensland industrial capex bundle.",
        "Approve Remote West pre-positioned spares allocation.",
    ]

    from datetime import datetime, timezone
    return {
        "region_id": region,
        "headline": headline,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "summary": summary_text,
        "top_risk_zones": top_zones,
        "top_recommended_actions": top_recs,
        "estimated_customer_impact_reduction": estimated_impact,
        "open_decisions": open_decisions,
    }


# ---------------------------------------------------------------------------
# Static frontend (built UI)
# ---------------------------------------------------------------------------

# The frontend builds into app/frontend/dist when running `npm run build`.
DIST_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if DIST_DIR.exists():
    assets_dir = DIST_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/", include_in_schema=False)
    def root_index() -> FileResponse:
        return FileResponse(DIST_DIR / "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404)
        target = DIST_DIR / full_path
        if target.exists() and target.is_file():
            return FileResponse(target)
        return FileResponse(DIST_DIR / "index.html")
else:
    @app.get("/", include_in_schema=False)
    def dev_root() -> JSONResponse:
        return JSONResponse({
            "message": "GridLens Queensland API running. Frontend dist/ not built; run npm run build or use Vite dev server on :5173.",
        })
