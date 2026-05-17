"""Smoke-level checks on the generated synthetic data."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parents[1] / "data" / "synthetic"


def _load(name: str) -> list[dict]:
    path = DATA / f"{name}.csv"
    if not path.exists():
        pytest.skip(f"{path} not present; run scripts/generate_synthetic_energyq_data.py")
    with path.open() as f:
        return list(csv.DictReader(f))


def test_regions_have_five_qld_regions() -> None:
    rows = _load("regions")
    assert len(rows) == 5
    assert {r["region_id"] for r in rows} == {
        "REG-SEQ", "REG-MKY", "REG-TSV", "REG-CQI", "REG-RW",
    }


def test_feeders_have_valid_region_and_substation() -> None:
    regions = {r["region_id"] for r in _load("regions")}
    substations = {s["substation_id"]: s["region_id"] for s in _load("substations")}
    feeders = _load("feeders")
    assert feeders
    for f in feeders:
        assert f["region_id"] in regions
        assert f["substation_id"] in substations
        assert substations[f["substation_id"]] == f["region_id"], (
            f"feeder {f['feeder_id']} region mismatch with substation"
        )


def test_assets_match_their_feeder_region() -> None:
    feeder_region = {f["feeder_id"]: f["region_id"] for f in _load("feeders")}
    feeder_sub = {f["feeder_id"]: f["substation_id"] for f in _load("feeders")}
    bad = []
    for a in _load("assets"):
        if feeder_region.get(a["feeder_id"]) != a["region_id"]:
            bad.append(a["asset_id"])
        if feeder_sub.get(a["feeder_id"]) != a["substation_id"]:
            bad.append(a["asset_id"])
    assert not bad, f"{len(bad)} assets mis-aligned with feeder; first {bad[:5]}"


def test_risk_scores_in_range() -> None:
    for h in _load("asset_health_scores"):
        risk = float(h["risk_score"])
        assert 0.0 <= risk <= 100.0
        assert h["risk_band"] in {"low", "medium", "high", "critical"}


def test_each_region_has_high_risk_demo_cluster() -> None:
    health = {h["asset_id"]: h for h in _load("asset_health_scores")}
    counts: dict[str, int] = {}
    for a in _load("assets"):
        h = health.get(a["asset_id"])
        if h and h["risk_band"] in ("high", "critical"):
            counts[a["region_id"]] = counts.get(a["region_id"], 0) + 1
    for region in ("REG-SEQ", "REG-MKY", "REG-TSV", "REG-CQI", "REG-RW"):
        assert counts.get(region, 0) >= 30, (
            f"{region} has only {counts.get(region, 0)} high/critical risk assets"
        )


def test_documents_reference_valid_assets_or_feeders() -> None:
    asset_ids = {a["asset_id"] for a in _load("assets")}
    feeder_ids = {f["feeder_id"] for f in _load("feeders")}
    region_ids = {r["region_id"] for r in _load("regions")}
    for d in _load("asset_documents"):
        assert d["region_id"] in region_ids
        if d.get("asset_id"):
            assert d["asset_id"] in asset_ids
        if d.get("feeder_id"):
            assert d["feeder_id"] in feeder_ids
        assert d.get("asset_id") or d.get("feeder_id"), (
            f"document {d['document_id']} references neither asset nor feeder"
        )
