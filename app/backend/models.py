"""Pydantic models for GridLens Queensland API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


RiskBand = Literal["low", "medium", "high", "critical"]
HealthBand = Literal["good", "watch", "poor", "critical"]
ScenarioType = Literal[
    "normal",
    "storm_readiness",
    "vegetation_program",
    "reliability_improvement",
    "capex_prioritisation",
    "field_inspection_review",
]
WorkPackageStatus = Literal["draft", "pending_approval", "approved", "scheduled", "completed"]
WorkPackagePriority = Literal["low", "medium", "high", "urgent"]


class Region(BaseModel):
    region_id: str
    region_name: str
    region_type: str
    state: str
    population_density_band: str
    hazard_profile: str
    centre_lat: float
    centre_lon: float


class MapAsset(BaseModel):
    asset_id: str
    feeder_id: str
    region_id: str
    asset_type: str
    lat: float
    lon: float
    risk_score: float
    risk_band: RiskBand
    health_band: HealthBand
    status: str


class AssetDetail(BaseModel):
    asset_id: str
    asset_type: str
    asset_name: str
    status: str
    lat: float
    lon: float
    install_year: int
    manufacturer: str
    material: str
    voltage_kv: float
    region_id: str
    region_name: str
    feeder_id: str
    feeder_name: str
    feeder_length_km: float
    customer_count: int
    critical_customer_count: int
    substation_id: str
    substation_name: str
    criticality_score: float
    access_difficulty_score: float
    coastal_corrosion_score: float
    flood_exposure_score: float
    cyclone_exposure_score: float
    bushfire_exposure_score: float
    condition_score: float
    health_band: HealthBand
    risk_score: float
    risk_band: RiskBand
    risk_drivers: list[str]
    failure_probability_12m: float
    failure_probability_36m: float
    defect_count_total: int
    open_defects: int
    open_critical_defects: int
    outage_count_12m: int
    outage_count_24m: int
    outage_count_36m: int
    customers_impact_total: int
    vegetation_risk_score_max: float
    vegetation_min_clearance_m: float
    open_work_orders: int
    completed_work_orders: int
    recommended_action: str


class AssetDocument(BaseModel):
    document_id: str
    document_type: str
    document_title: str
    volume_path: str
    region_id: str
    feeder_id: Optional[str] = None
    asset_id: Optional[str] = None
    excerpt: Optional[str] = None
    sensitivity_classification: Optional[str] = None
    created_date: Optional[str] = None


class FeederSummary(BaseModel):
    feeder_id: str
    feeder_name: str
    region_id: str
    region_name: str
    customer_count: int
    critical_customer_count: int
    asset_count: int
    high_risk_assets: int
    critical_risk_assets: int
    avg_risk_score: float
    outage_count_12m: int
    saidi_minutes_12m: float
    saifi_count_12m: float
    avg_vegetation_risk_score: float
    planned_work_count: int


class RegionalSummary(BaseModel):
    region_id: str
    region_name: str
    total_assets: int
    high_risk_assets: int
    critical_risk_assets: int
    vegetation_backlog: int
    mobile_gen_ready_sites: int
    critical_customer_count_exposed: int
    planned_work_count: int
    avg_risk_score: float
    customers_at_risk: int


class HazardZone(BaseModel):
    hazard_zone_id: str
    region_id: str
    hazard_type: str
    zone_name: str
    lat: float
    lon: float
    radius_km: float
    severity_score: float
    seasonal_window: str


class CriticalCustomer(BaseModel):
    critical_customer_id: str
    feeder_id: str
    region_id: str
    site_name: str
    site_type: str
    lat: float
    lon: float
    backup_power_status: str
    priority_score: float


class Depot(BaseModel):
    depot_id: str
    region_id: str
    depot_name: str
    lat: float
    lon: float
    crew_count: int
    specialist_crews: int
    mobile_generation_units: int


class MobileGenSite(BaseModel):
    candidate_id: str
    feeder_id: str
    region_id: str
    site_name: str
    lat: float
    lon: float
    connection_ready: bool
    customer_impact_reduction_score: float
    access_difficulty_score: float
    recommended_unit_size_kva: int


class MapBundle(BaseModel):
    """Combined payload for the command map."""

    assets: list[MapAsset]
    hazards: list[HazardZone]
    critical_customers: list[CriticalCustomer]
    depots: list[Depot]
    mobile_gen_sites: list[MobileGenSite]
    feeders_count: int
    high_risk_asset_count: int
    critical_asset_count: int
    customers_exposed: int


# ---------------------------------------------------------------------------
# Lakebase / work package models
# ---------------------------------------------------------------------------


class WorkPackageAsset(BaseModel):
    asset_id: str
    role: Optional[str] = None
    notes: Optional[str] = None


class WorkPackage(BaseModel):
    work_package_id: str
    title: str
    region_id: str
    feeder_id: Optional[str] = None
    scenario_type: Optional[str] = None
    priority: WorkPackagePriority
    status: WorkPackageStatus
    created_by: Optional[str] = None
    created_at: str
    recommended_by_agent: bool = False
    evidence_summary: Optional[str] = None
    estimated_hours: Optional[float] = None
    estimated_cost_aud: Optional[float] = None
    estimated_customer_impact_reduction: Optional[int] = None
    suggested_depot_id: Optional[str] = None
    assets: list[WorkPackageAsset] = []


class WorkPackageCreate(BaseModel):
    title: str
    region_id: str
    feeder_id: Optional[str] = None
    scenario_type: Optional[str] = None
    priority: WorkPackagePriority = "medium"
    status: WorkPackageStatus = "draft"
    asset_ids: list[str] = Field(default_factory=list)
    evidence_summary: Optional[str] = None
    recommended_by_agent: bool = False
    estimated_hours: Optional[float] = None
    estimated_cost_aud: Optional[float] = None
    estimated_customer_impact_reduction: Optional[int] = None
    suggested_depot_id: Optional[str] = None


class WorkPackagePatch(BaseModel):
    status: Optional[WorkPackageStatus] = None
    priority: Optional[WorkPackagePriority] = None
    title: Optional[str] = None
    evidence_summary: Optional[str] = None


# ---------------------------------------------------------------------------
# Agent models
# ---------------------------------------------------------------------------


class AgentEvidence(BaseModel):
    evidence_type: Literal["delta_table", "document", "genie_answer", "map_selection", "policy"]
    source_ref: str
    source_title: str
    excerpt: str
    confidence: float


class AgentTraceStep(BaseModel):
    agent: str
    action: str
    inputs: Optional[dict] = None
    output_summary: str
    confidence: float


class AgentInvestigateRequest(BaseModel):
    prompt: str
    asset_id: Optional[str] = None
    feeder_id: Optional[str] = None
    region_id: Optional[str] = None
    scenario_type: Optional[ScenarioType] = None
    selected_asset_ids: list[str] = Field(default_factory=list)


class AgentInvestigateResponse(BaseModel):
    recommendation_id: str
    headline: str
    body: str
    confidence: float
    evidence: list[AgentEvidence]
    trace: list[AgentTraceStep]
    next_steps: list[str]


class AgentCreateWorkPackageRequest(BaseModel):
    recommendation_id: str
    title: Optional[str] = None
    priority: WorkPackagePriority = "high"
    region_id: str
    feeder_id: Optional[str] = None
    asset_ids: list[str]


# ---------------------------------------------------------------------------
# Genie models
# ---------------------------------------------------------------------------


class GenieAskRequest(BaseModel):
    question: str


class GenieAnswerCard(BaseModel):
    label: str
    value: str
    sub_label: Optional[str] = None


class GenieAnswer(BaseModel):
    question: str
    summary: str
    sql: str
    columns: list[str]
    rows: list[list]
    cards: list[GenieAnswerCard] = []
    chart_type: Optional[Literal["bar", "line", "pie", "table"]] = None
    business_definitions: list[str] = []


class ExecutiveBriefing(BaseModel):
    region_id: Optional[str] = None
    headline: str
    generated_at: str
    summary: str
    top_risk_zones: list[dict]
    top_recommended_actions: list[dict]
    estimated_customer_impact_reduction: int
    open_decisions: list[str]
