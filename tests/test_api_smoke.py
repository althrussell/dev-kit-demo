"""End-to-end API smoke tests against the FastAPI app."""

from __future__ import annotations


def test_healthz(app_client) -> None:
    r = app_client.get("/api/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"


def test_regions(app_client) -> None:
    r = app_client.get("/api/regions")
    assert r.status_code == 200
    regions = r.json()
    assert len(regions) == 5
    ids = {x["region_id"] for x in regions}
    assert ids == {"REG-SEQ", "REG-MKY", "REG-TSV", "REG-CQI", "REG-RW"}


def test_map_bundle(app_client) -> None:
    r = app_client.get(
        "/api/map/bundle",
        params={"region": "REG-MKY", "scenario": "storm_readiness", "asset_limit": 500},
    )
    assert r.status_code == 200
    b = r.json()
    assert b["assets"]
    assert b["high_risk_asset_count"] >= 0
    assert b["critical_asset_count"] >= 0
    assert b["depots"]


def test_asset_detail_and_documents(app_client) -> None:
    # find a critical asset to inspect
    bundle = app_client.get(
        "/api/map/bundle",
        params={"region": "REG-MKY", "scenario": "storm_readiness", "asset_limit": 2000},
    ).json()
    critical = next(
        (a for a in bundle["assets"] if a["risk_band"] == "critical"),
        bundle["assets"][0],
    )
    detail = app_client.get(f"/api/assets/{critical['asset_id']}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["asset_id"] == critical["asset_id"]
    assert body["region_id"] == critical["region_id"]
    docs = app_client.get(f"/api/assets/{critical['asset_id']}/documents")
    assert docs.status_code == 200


def test_genie_returns_grounded_answer(app_client) -> None:
    r = app_client.post(
        "/api/genie/ask",
        json={"question": "Which regions have the highest storm-season asset risk?"},
    )
    assert r.status_code == 200
    a = r.json()
    assert a["summary"]
    assert a["columns"]
    assert a["rows"]
    assert a["business_definitions"], "expected business definitions in Genie answer"
    assert a["sql"], "expected mock SQL in Genie answer"


def test_agent_investigate_returns_evidence(app_client) -> None:
    r = app_client.post(
        "/api/agent/investigate",
        json={
            "prompt": "Why is REG-MKY high risk before storm season?",
            "region_id": "REG-MKY",
            "scenario_type": "storm_readiness",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["recommendation_id"].startswith("REC-")
    assert body["evidence"]
    types = {e["evidence_type"] for e in body["evidence"]}
    assert "delta_table" in types
    assert "document" in types
    assert body["next_steps"]
    assert body["trace"]


def test_work_package_create_and_patch(app_client) -> None:
    bundle = app_client.get(
        "/api/map/bundle",
        params={"region": "REG-SEQ", "asset_limit": 200, "scenario": "reliability_improvement"},
    ).json()
    asset_ids = [a["asset_id"] for a in bundle["assets"][:3]]
    feeder_id = bundle["assets"][0]["feeder_id"]
    create = app_client.post(
        "/api/work-packages",
        json={
            "title": "Test SEQ reliability package",
            "region_id": "REG-SEQ",
            "feeder_id": feeder_id,
            "scenario_type": "reliability_improvement",
            "priority": "high",
            "status": "draft",
            "asset_ids": asset_ids,
            "evidence_summary": "Created by API smoke test",
        },
    )
    assert create.status_code == 200
    wp = create.json()
    assert wp["work_package_id"].startswith("WP-")
    assert wp["status"] == "draft"
    # Patch through the approval pipeline
    patched = app_client.patch(
        f"/api/work-packages/{wp['work_package_id']}",
        json={"status": "pending_approval"},
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "pending_approval"


def test_executive_briefing(app_client) -> None:
    r = app_client.get("/api/executive-briefing", params={"region": "REG-MKY"})
    assert r.status_code == 200
    b = r.json()
    assert b["headline"]
    assert b["top_risk_zones"]
    assert b["top_recommended_actions"]
    assert b["open_decisions"]
