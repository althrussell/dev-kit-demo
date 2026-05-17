export type RiskBand = 'low' | 'medium' | 'high' | 'critical';
export type HealthBand = 'good' | 'watch' | 'poor' | 'critical';

export type ScenarioId =
  | 'normal'
  | 'storm_readiness'
  | 'vegetation_program'
  | 'reliability_improvement'
  | 'capex_prioritisation'
  | 'field_inspection_review';

export interface Region {
  region_id: string;
  region_name: string;
  region_type: string;
  state: string;
  population_density_band: string;
  hazard_profile: string;
  centre_lat: number;
  centre_lon: number;
}

export interface MapAsset {
  asset_id: string;
  feeder_id: string;
  region_id: string;
  asset_type: string;
  lat: number;
  lon: number;
  risk_score: number;
  risk_band: RiskBand;
  health_band: HealthBand;
  status: string;
}

export interface VegetationLine {
  vegetation_span_id: string;
  feeder_id: string;
  region_id: string;
  from_lat: number;
  from_lon: number;
  to_lat: number;
  to_lon: number;
  risk_score: number;
  overdue_days: number;
  treatment_priority?: string;
}

export interface OutageLine {
  feeder_id: string;
  feeder_name: string;
  region_id: string;
  from_lat: number;
  from_lon: number;
  to_lat: number;
  to_lon: number;
  outage_count: number;
  saidi_minutes: number;
  customers_interrupted: number;
}

export interface RiskExtrusion {
  asset_id: string;
  lat: number;
  lon: number;
  risk_score: number;
  risk_band: RiskBand;
  height_m: number;
  feeder_id: string;
}

export interface InspectionStaleAsset {
  asset_id: string;
  lat: number;
  lon: number;
  feeder_id: string;
  region_id: string;
  risk_band: RiskBand;
  overdue_days: number;
  last_inspection_date: string | null;
  access_difficulty_score: number;
}

export interface ScenarioSummary {
  scenario_id: ScenarioId;
  headline: string;
  narrative: string;
  primary_layers: string[];
  accent_color?: string;
  counts: {
    assets_shown: number;
    hazards_shown: number;
    critical_customers?: number;
    vegetation_lines: number;
    outage_lines: number;
    risk_extrusions: number;
    inspection_stale?: number;
    postgis_impact_assets?: number;
    postgis_hazard_polygons?: number;
  };
}

export interface HazardImpactAsset {
  asset_id: string;
  feeder_id: string;
  region_id: string;
  asset_type: string;
  risk_score: number;
  risk_band: RiskBand;
  lat: number;
  lon: number;
  distance_m: number;
  hazard_severity: number;
  hazard_types: string[];
}

export interface HazardPolygon {
  hazard_zone_id: string;
  region_id: string;
  hazard_type: string;
  zone_name: string;
  radius_km: number;
  severity_score: number;
  seasonal_window: string;
  polygon: GeoJSON.Polygon | null;
  center_lat: number;
  center_lon: number;
}

export interface MapBundle {
  assets: MapAsset[];
  hazards: HazardZone[];
  critical_customers: CriticalCustomer[];
  depots: Depot[];
  mobile_gen_sites: MobileGenSite[];
  vegetation_lines?: VegetationLine[];
  outage_lines?: OutageLine[];
  risk_extrusions?: RiskExtrusion[];
  inspection_stale_assets?: InspectionStaleAsset[];
  hazard_impact_assets?: HazardImpactAsset[];
  hazard_polygons?: HazardPolygon[];
  scenario_summary?: ScenarioSummary;
  feeders_count: number;
  high_risk_asset_count: number;
  critical_asset_count: number;
  customers_exposed: number;
}

export interface HazardZone {
  hazard_zone_id: string;
  region_id: string;
  hazard_type: string;
  zone_name: string;
  lat: number;
  lon: number;
  radius_km: number;
  severity_score: number;
  seasonal_window: string;
}

export interface CriticalCustomer {
  critical_customer_id: string;
  feeder_id: string;
  region_id: string;
  site_name: string;
  site_type: string;
  lat: number;
  lon: number;
  backup_power_status: string;
  priority_score: number;
}

export interface Depot {
  depot_id: string;
  region_id: string;
  depot_name: string;
  lat: number;
  lon: number;
  crew_count: number;
  specialist_crews: number;
  mobile_generation_units: number;
}

export interface MobileGenSite {
  candidate_id: string;
  feeder_id: string;
  region_id: string;
  site_name: string;
  lat: number;
  lon: number;
  connection_ready: boolean;
  customer_impact_reduction_score: number;
  access_difficulty_score: number;
  recommended_unit_size_kva: number;
}

export interface AssetDetail {
  asset_id: string;
  asset_type: string;
  asset_name: string;
  status: string;
  lat: number;
  lon: number;
  install_year: number;
  manufacturer: string;
  material: string;
  voltage_kv: number;
  region_id: string;
  region_name: string;
  feeder_id: string;
  feeder_name: string;
  feeder_length_km: number;
  customer_count: number;
  critical_customer_count: number;
  substation_id: string;
  substation_name: string;
  criticality_score: number;
  access_difficulty_score: number;
  coastal_corrosion_score: number;
  flood_exposure_score: number;
  cyclone_exposure_score: number;
  bushfire_exposure_score: number;
  condition_score: number;
  health_band: HealthBand;
  risk_score: number;
  risk_band: RiskBand;
  risk_drivers: string[];
  failure_probability_12m: number;
  failure_probability_36m: number;
  defect_count_total: number;
  open_defects: number;
  open_critical_defects: number;
  outage_count_12m: number;
  outage_count_24m: number;
  outage_count_36m: number;
  customers_impact_total: number;
  vegetation_risk_score_max: number;
  vegetation_min_clearance_m: number;
  open_work_orders: number;
  completed_work_orders: number;
  recommended_action: string;
}

export interface AssetDocument {
  document_id: string;
  document_type: string;
  document_title: string;
  volume_path: string;
  region_id: string;
  feeder_id?: string;
  asset_id?: string;
  excerpt?: string;
  sensitivity_classification?: string;
  created_date?: string;
}

export interface RegionalSummary {
  region_id: string;
  region_name: string;
  total_assets: number;
  high_risk_assets: number;
  critical_risk_assets: number;
  vegetation_backlog: number;
  mobile_gen_ready_sites: number;
  critical_customer_count_exposed: number;
  planned_work_count: number;
  avg_risk_score: number;
  customers_at_risk: number;
}

export interface WorkPackage {
  work_package_id: string;
  title: string;
  region_id: string;
  feeder_id?: string;
  scenario_type?: string;
  priority: 'low' | 'medium' | 'high' | 'urgent';
  status: 'draft' | 'pending_approval' | 'approved' | 'scheduled' | 'completed';
  created_by?: string;
  created_at: string;
  recommended_by_agent: boolean;
  evidence_summary?: string;
  estimated_hours?: number;
  estimated_cost_aud?: number;
  estimated_customer_impact_reduction?: number;
  suggested_depot_id?: string;
  assets?: { asset_id: string; role?: string; notes?: string }[];
}

export interface AgentEvidence {
  evidence_type: 'delta_table' | 'document' | 'genie_answer' | 'map_selection' | 'policy';
  source_ref: string;
  source_title: string;
  excerpt: string;
  confidence: number;
}

export interface AgentTraceStep {
  agent: string;
  action: string;
  inputs?: Record<string, unknown> | null;
  output_summary: string;
  confidence: number;
}

export interface AgentResponse {
  recommendation_id: string;
  headline: string;
  body: string;
  confidence: number;
  evidence: AgentEvidence[];
  trace: AgentTraceStep[];
  next_steps: string[];
}

export interface GenieAnswer {
  question: string;
  summary: string;
  sql: string;
  columns: string[];
  rows: (string | number)[][];
  cards: { label: string; value: string; sub_label?: string }[];
  chart_type?: 'bar' | 'line' | 'pie' | 'table';
  business_definitions: string[];
}

export interface ExecutiveBriefing {
  region_id?: string | null;
  headline: string;
  generated_at: string;
  summary: string;
  top_risk_zones: RegionalSummary[];
  top_recommended_actions: {
    region_id: string;
    region_name: string;
    headline: string;
    estimated_customer_impact_reduction: number;
    recommended_action: string;
  }[];
  estimated_customer_impact_reduction: number;
  open_decisions: string[];
}
