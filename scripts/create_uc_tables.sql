-- =====================================================================
-- GridLens Queensland — Unity Catalog DDL
--
-- Catalog: anzgt_may  (override with $CATALOG below)
-- Schemas:
--   anzgt_may.energyq_bronze   raw synthetic data
--   anzgt_may.energyq_silver   curated relational tables
--   anzgt_may.energyq_gold     consumption tables/views for app + Genie
--   anzgt_may.energyq.asset_docs volume for raw asset documents
--
-- Run with the Databricks SQL editor or:
--   databricks sql query --file scripts/create_uc_tables.sql --warehouse-id $WAREHOUSE_ID
--
-- The python loader (scripts/load_delta_tables.py) writes the synthetic
-- CSVs into the silver schema, then we materialise the gold views below.
-- =====================================================================

USE CATALOG anzgt_may;

CREATE SCHEMA IF NOT EXISTS energyq_bronze
  COMMENT 'Raw synthetic ingest landing zone for GridLens Queensland demo.';

CREATE SCHEMA IF NOT EXISTS energyq_silver
  COMMENT 'Curated synthetic operational tables for GridLens Queensland demo.';

CREATE SCHEMA IF NOT EXISTS energyq_gold
  COMMENT 'Consumption tables and views powering the app and Genie space.';

CREATE SCHEMA IF NOT EXISTS energyq
  COMMENT 'GridLens Queensland app + volume namespace.';

-- ---------------------------------------------------------------------
-- Volume for asset documents
-- ---------------------------------------------------------------------
CREATE VOLUME IF NOT EXISTS anzgt_may.energyq.asset_docs
  COMMENT 'Synthetic asset inspection reports, drawings, standards and photo manifests.';

-- =====================================================================
-- Silver tables
-- =====================================================================
USE SCHEMA energyq_silver;

CREATE OR REPLACE TABLE regions (
    region_id STRING NOT NULL,
    region_name STRING,
    region_type STRING,
    state STRING,
    population_density_band STRING,
    hazard_profile STRING,
    centre_lat DOUBLE,
    centre_lon DOUBLE
) USING DELTA;

CREATE OR REPLACE TABLE depots (
    depot_id STRING NOT NULL,
    region_id STRING,
    depot_name STRING,
    lat DOUBLE,
    lon DOUBLE,
    crew_count INT,
    specialist_crews INT,
    mobile_generation_units INT
) USING DELTA;

CREATE OR REPLACE TABLE substations (
    substation_id STRING NOT NULL,
    region_id STRING,
    substation_name STRING,
    lat DOUBLE,
    lon DOUBLE,
    voltage_level STRING,
    commissioned_year INT,
    criticality_score DOUBLE,
    flood_exposure_score DOUBLE,
    cyclone_exposure_score DOUBLE
) USING DELTA;

CREATE OR REPLACE TABLE feeders (
    feeder_id STRING NOT NULL,
    substation_id STRING,
    region_id STRING,
    feeder_name STRING,
    voltage_kv DOUBLE,
    feeder_length_km DOUBLE,
    customer_count INT,
    critical_customer_count INT,
    overhead_pct DOUBLE,
    underground_pct DOUBLE,
    radiality_score DOUBLE,
    asset_density_score DOUBLE,
    network_capacity_band STRING,
    export_capacity_band STRING
) USING DELTA;

CREATE OR REPLACE TABLE assets (
    asset_id STRING NOT NULL,
    feeder_id STRING,
    substation_id STRING,
    region_id STRING,
    asset_type STRING,
    asset_name STRING,
    lat DOUBLE,
    lon DOUBLE,
    install_year INT,
    manufacturer STRING,
    material STRING,
    voltage_kv DOUBLE,
    status STRING,
    criticality_score DOUBLE,
    access_difficulty_score DOUBLE,
    coastal_corrosion_score DOUBLE,
    flood_exposure_score DOUBLE,
    cyclone_exposure_score DOUBLE,
    bushfire_exposure_score DOUBLE
) USING DELTA;

CREATE OR REPLACE TABLE asset_health_scores (
    asset_id STRING NOT NULL,
    condition_score DOUBLE,
    failure_probability_12m DOUBLE,
    failure_probability_36m DOUBLE,
    health_band STRING,
    risk_score DOUBLE,
    risk_band STRING,
    risk_drivers STRING,
    last_scored_at TIMESTAMP
) USING DELTA;

CREATE OR REPLACE TABLE inspection_events (
    inspection_id STRING NOT NULL,
    asset_id STRING,
    inspection_date DATE,
    inspection_type STRING,
    inspector_team STRING,
    condition_observed STRING,
    defect_count INT,
    photo_count INT,
    document_id STRING,
    recommended_action STRING
) USING DELTA;

CREATE OR REPLACE TABLE defects (
    defect_id STRING NOT NULL,
    inspection_id STRING,
    asset_id STRING,
    defect_type STRING,
    severity STRING,
    detected_date DATE,
    target_rectification_date DATE,
    status STRING,
    safety_risk_score DOUBLE,
    reliability_risk_score DOUBLE
) USING DELTA;

CREATE OR REPLACE TABLE vegetation_spans (
    vegetation_span_id STRING NOT NULL,
    feeder_id STRING,
    region_id STRING,
    nearest_asset_id STRING,
    lat DOUBLE,
    lon DOUBLE,
    species_group STRING,
    clearance_m DOUBLE,
    growth_rate_band STRING,
    last_treatment_date DATE,
    next_due_date DATE,
    overdue_days INT,
    vegetation_risk_score DOUBLE,
    treatment_priority STRING
) USING DELTA;

CREATE OR REPLACE TABLE outage_events (
    outage_id STRING NOT NULL,
    feeder_id STRING,
    region_id STRING,
    asset_id STRING,
    outage_start TIMESTAMP,
    outage_end TIMESTAMP,
    duration_minutes INT,
    customers_interrupted INT,
    critical_customers_interrupted INT,
    cause_category STRING,
    saidi_minutes DOUBLE,
    saifi_count DOUBLE,
    crew_response_minutes INT,
    restoration_notes STRING
) USING DELTA;

CREATE OR REPLACE TABLE work_orders (
    work_order_id STRING NOT NULL,
    asset_id STRING,
    feeder_id STRING,
    region_id STRING,
    work_type STRING,
    priority STRING,
    status STRING,
    created_date DATE,
    scheduled_date DATE,
    completed_date DATE,
    estimated_hours DOUBLE,
    estimated_cost_aud DOUBLE,
    crew_type STRING,
    depot_id STRING
) USING DELTA;

CREATE OR REPLACE TABLE critical_customers (
    critical_customer_id STRING NOT NULL,
    feeder_id STRING,
    region_id STRING,
    site_name STRING,
    site_type STRING,
    lat DOUBLE,
    lon DOUBLE,
    backup_power_status STRING,
    priority_score DOUBLE
) USING DELTA;

CREATE OR REPLACE TABLE hazard_exposure_zones (
    hazard_zone_id STRING NOT NULL,
    region_id STRING,
    hazard_type STRING,
    zone_name STRING,
    lat DOUBLE,
    lon DOUBLE,
    radius_km DOUBLE,
    severity_score DOUBLE,
    seasonal_window STRING
) USING DELTA;

CREATE OR REPLACE TABLE asset_documents (
    document_id STRING NOT NULL,
    asset_id STRING,
    feeder_id STRING,
    region_id STRING,
    document_type STRING,
    document_title STRING,
    volume_path STRING,
    created_date TIMESTAMP,
    effective_date TIMESTAMP,
    document_summary STRING,
    sensitivity_classification STRING
) USING DELTA;

CREATE OR REPLACE TABLE mobile_generation_candidates (
    candidate_id STRING NOT NULL,
    feeder_id STRING,
    region_id STRING,
    site_name STRING,
    lat DOUBLE,
    lon DOUBLE,
    connection_ready BOOLEAN,
    customer_impact_reduction_score DOUBLE,
    access_difficulty_score DOUBLE,
    recommended_unit_size_kva INT
) USING DELTA;

CREATE OR REPLACE TABLE scenario_runs (
    scenario_id STRING NOT NULL,
    scenario_name STRING,
    scenario_type STRING,
    created_at TIMESTAMP,
    region_id STRING,
    risk_threshold INT,
    selected_asset_count INT,
    recommended_work_package_count INT,
    estimated_customer_impact_reduction INT
) USING DELTA;

-- =====================================================================
-- Gold views
-- =====================================================================
USE SCHEMA energyq_gold;

CREATE OR REPLACE VIEW gold_asset_360 AS
WITH defect_summary AS (
  SELECT
    asset_id,
    COUNT(*) AS defect_count_total,
    SUM(CASE WHEN status = 'open' AND severity IN ('high','critical') THEN 1 ELSE 0 END) AS open_critical_defects,
    SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) AS open_defects
  FROM anzgt_may.energyq_silver.defects
  GROUP BY asset_id
),
outage_summary AS (
  SELECT
    asset_id,
    COUNT(*) AS outage_count_total,
    SUM(CASE WHEN outage_start >= current_date() - INTERVAL 12 MONTHS THEN 1 ELSE 0 END) AS outage_count_12m,
    SUM(CASE WHEN outage_start >= current_date() - INTERVAL 24 MONTHS THEN 1 ELSE 0 END) AS outage_count_24m,
    SUM(CASE WHEN outage_start >= current_date() - INTERVAL 36 MONTHS THEN 1 ELSE 0 END) AS outage_count_36m,
    SUM(customers_interrupted) AS customers_impact_total
  FROM anzgt_may.energyq_silver.outage_events
  WHERE asset_id IS NOT NULL AND asset_id <> ''
  GROUP BY asset_id
),
veg_summary AS (
  SELECT
    nearest_asset_id AS asset_id,
    AVG(vegetation_risk_score) AS vegetation_risk_score_avg,
    MAX(vegetation_risk_score) AS vegetation_risk_score_max,
    MIN(clearance_m) AS vegetation_min_clearance_m
  FROM anzgt_may.energyq_silver.vegetation_spans
  GROUP BY nearest_asset_id
),
work_summary AS (
  SELECT
    asset_id,
    SUM(CASE WHEN status IN ('draft','approved','scheduled','in_progress') THEN 1 ELSE 0 END) AS open_work_orders,
    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed_work_orders,
    MAX(scheduled_date) AS last_scheduled_date
  FROM anzgt_may.energyq_silver.work_orders
  WHERE asset_id IS NOT NULL AND asset_id <> ''
  GROUP BY asset_id
)
SELECT
  a.asset_id,
  a.asset_type,
  a.asset_name,
  a.status,
  a.lat,
  a.lon,
  a.install_year,
  a.manufacturer,
  a.material,
  a.voltage_kv,
  a.criticality_score,
  a.access_difficulty_score,
  a.coastal_corrosion_score,
  a.flood_exposure_score,
  a.cyclone_exposure_score,
  a.bushfire_exposure_score,
  f.feeder_id,
  f.feeder_name,
  f.feeder_length_km,
  f.customer_count,
  f.critical_customer_count,
  f.overhead_pct,
  f.underground_pct,
  f.radiality_score,
  f.network_capacity_band,
  s.substation_id,
  s.substation_name,
  s.voltage_level,
  s.criticality_score AS substation_criticality_score,
  r.region_id,
  r.region_name,
  r.hazard_profile,
  h.condition_score,
  h.health_band,
  h.risk_score,
  h.risk_band,
  h.risk_drivers,
  h.failure_probability_12m,
  h.failure_probability_36m,
  COALESCE(d.defect_count_total, 0) AS defect_count_total,
  COALESCE(d.open_defects, 0) AS open_defects,
  COALESCE(d.open_critical_defects, 0) AS open_critical_defects,
  COALESCE(o.outage_count_12m, 0) AS outage_count_12m,
  COALESCE(o.outage_count_24m, 0) AS outage_count_24m,
  COALESCE(o.outage_count_36m, 0) AS outage_count_36m,
  COALESCE(o.customers_impact_total, 0) AS customers_impact_total,
  COALESCE(v.vegetation_risk_score_max, 0) AS vegetation_risk_score_max,
  COALESCE(v.vegetation_min_clearance_m, 9.99) AS vegetation_min_clearance_m,
  COALESCE(w.open_work_orders, 0) AS open_work_orders,
  COALESCE(w.completed_work_orders, 0) AS completed_work_orders,
  w.last_scheduled_date AS last_scheduled_work_date,
  CASE
    WHEN h.risk_band = 'critical' AND COALESCE(w.open_work_orders, 0) = 0
      THEN 'Plan immediate remediation; no open work order detected.'
    WHEN h.risk_band = 'high' AND COALESCE(v.vegetation_risk_score_max, 0) > 60
      THEN 'Bundle vegetation treatment with asset inspection.'
    WHEN h.risk_band IN ('high','critical') AND a.coastal_corrosion_score > 60
      THEN 'Schedule crossarm + insulator replacement before storm season.'
    WHEN h.risk_band IN ('high','critical')
      THEN 'Add to next regional capex review.'
    ELSE 'Monitor — risk within acceptable band.'
  END AS recommended_action
FROM anzgt_may.energyq_silver.assets a
JOIN anzgt_may.energyq_silver.feeders f ON a.feeder_id = f.feeder_id
JOIN anzgt_may.energyq_silver.substations s ON a.substation_id = s.substation_id
JOIN anzgt_may.energyq_silver.regions r ON a.region_id = r.region_id
LEFT JOIN anzgt_may.energyq_silver.asset_health_scores h ON h.asset_id = a.asset_id
LEFT JOIN defect_summary d ON d.asset_id = a.asset_id
LEFT JOIN outage_summary o ON o.asset_id = a.asset_id
LEFT JOIN veg_summary v ON v.asset_id = a.asset_id
LEFT JOIN work_summary w ON w.asset_id = a.asset_id;

CREATE OR REPLACE VIEW gold_feeder_risk_summary AS
SELECT
  f.feeder_id,
  f.feeder_name,
  f.region_id,
  r.region_name,
  f.substation_id,
  f.voltage_kv,
  f.feeder_length_km,
  f.customer_count,
  f.critical_customer_count,
  COUNT(a.asset_id) AS asset_count,
  SUM(CASE WHEN h.risk_band = 'high' THEN 1 ELSE 0 END) AS high_risk_assets,
  SUM(CASE WHEN h.risk_band = 'critical' THEN 1 ELSE 0 END) AS critical_risk_assets,
  AVG(h.risk_score) AS avg_risk_score,
  (SELECT COUNT(*) FROM anzgt_may.energyq_silver.outage_events o
    WHERE o.feeder_id = f.feeder_id
      AND o.outage_start >= current_date() - INTERVAL 12 MONTHS) AS outage_count_12m,
  (SELECT COUNT(*) FROM anzgt_may.energyq_silver.outage_events o
    WHERE o.feeder_id = f.feeder_id
      AND o.outage_start >= current_date() - INTERVAL 36 MONTHS) AS outage_count_36m,
  COALESCE((SELECT AVG(vegetation_risk_score) FROM anzgt_may.energyq_silver.vegetation_spans v
    WHERE v.feeder_id = f.feeder_id), 0) AS avg_vegetation_risk_score,
  (SELECT SUM(saidi_minutes) FROM anzgt_may.energyq_silver.outage_events o
    WHERE o.feeder_id = f.feeder_id
      AND o.outage_start >= current_date() - INTERVAL 12 MONTHS) AS saidi_minutes_12m,
  (SELECT SUM(saifi_count) FROM anzgt_may.energyq_silver.outage_events o
    WHERE o.feeder_id = f.feeder_id
      AND o.outage_start >= current_date() - INTERVAL 12 MONTHS) AS saifi_count_12m,
  (SELECT COUNT(*) FROM anzgt_may.energyq_silver.work_orders w
    WHERE w.feeder_id = f.feeder_id
      AND w.status IN ('approved','scheduled','in_progress')) AS planned_work_count
FROM anzgt_may.energyq_silver.feeders f
JOIN anzgt_may.energyq_silver.regions r ON f.region_id = r.region_id
LEFT JOIN anzgt_may.energyq_silver.assets a ON a.feeder_id = f.feeder_id
LEFT JOIN anzgt_may.energyq_silver.asset_health_scores h ON h.asset_id = a.asset_id
GROUP BY f.feeder_id, f.feeder_name, f.region_id, r.region_name, f.substation_id,
         f.voltage_kv, f.feeder_length_km, f.customer_count, f.critical_customer_count;

CREATE OR REPLACE VIEW gold_regional_risk_summary AS
SELECT
  r.region_id,
  r.region_name,
  COUNT(DISTINCT a.asset_id) AS total_assets,
  SUM(CASE WHEN h.risk_band = 'high' THEN 1 ELSE 0 END) AS high_risk_assets,
  SUM(CASE WHEN h.risk_band = 'critical' THEN 1 ELSE 0 END) AS critical_risk_assets,
  (SELECT COUNT(*) FROM anzgt_may.energyq_silver.feeders f2
    JOIN anzgt_may.energyq_silver.outage_events o2
      ON f2.feeder_id = o2.feeder_id
    WHERE f2.region_id = r.region_id
      AND o2.outage_start >= current_date() - INTERVAL 12 MONTHS
    GROUP BY f2.feeder_id HAVING COUNT(*) >= 3) AS feeders_with_repeat_outages,
  (SELECT COUNT(*) FROM anzgt_may.energyq_silver.vegetation_spans v
    WHERE v.region_id = r.region_id AND v.overdue_days > 30) AS vegetation_backlog,
  (SELECT COUNT(*) FROM anzgt_may.energyq_silver.mobile_generation_candidates m
    WHERE m.region_id = r.region_id AND m.connection_ready = TRUE) AS mobile_gen_ready_sites,
  (SELECT SUM(critical_customer_count) FROM anzgt_may.energyq_silver.feeders f3
    WHERE f3.region_id = r.region_id) AS critical_customer_count_exposed,
  (SELECT COUNT(*) FROM anzgt_may.energyq_silver.work_orders w
    WHERE w.region_id = r.region_id
      AND w.status IN ('approved','scheduled','in_progress')) AS planned_work_count
FROM anzgt_may.energyq_silver.regions r
LEFT JOIN anzgt_may.energyq_silver.assets a ON a.region_id = r.region_id
LEFT JOIN anzgt_may.energyq_silver.asset_health_scores h ON h.asset_id = a.asset_id
GROUP BY r.region_id, r.region_name;

CREATE OR REPLACE VIEW gold_work_prioritisation AS
SELECT
  CONCAT('REC-', f.feeder_id, '-', LPAD(CAST(ROW_NUMBER() OVER (ORDER BY h.risk_score DESC) AS STRING), 6, '0')) AS recommendation_id,
  a.region_id,
  f.feeder_id,
  a.asset_id,
  CASE
    WHEN h.risk_band = 'critical' AND a.coastal_corrosion_score > 60 THEN 'crossarm_replacement'
    WHEN h.risk_band = 'critical' AND a.cyclone_exposure_score > 60 THEN 'storm_hardening'
    WHEN h.risk_band IN ('high','critical') AND a.bushfire_exposure_score > 60 THEN 'bushfire_pole_swap'
    WHEN h.risk_band IN ('high','critical') AND a.flood_exposure_score > 60 THEN 'flood_mitigation'
    ELSE 'asset_inspection'
  END AS opportunity_type,
  h.risk_score AS priority_score,
  ROUND(f.customer_count * h.failure_probability_12m, 0) AS estimated_customer_impact_reduction,
  ROUND(GREATEST(2500, h.risk_score * 200), 2) AS estimated_cost_aud,
  CASE WHEN h.risk_score > 60 THEN TRUE ELSE FALSE END AS work_bundle_candidate,
  (SELECT depot_id FROM anzgt_may.energyq_silver.depots d
    WHERE d.region_id = a.region_id
    ORDER BY (POW(d.lat - a.lat, 2) + POW(d.lon - a.lon, 2)) ASC LIMIT 1) AS suggested_depot_id,
  CONCAT('Asset ', a.asset_id, ' risk=', CAST(ROUND(h.risk_score, 1) AS STRING),
         ' drivers=', h.risk_drivers) AS evidence_summary,
  CASE
    WHEN h.risk_band = 'critical' THEN 'Schedule within 30 days'
    WHEN h.risk_band = 'high' THEN 'Schedule within 90 days'
    ELSE 'Plan within FY'
  END AS recommended_next_step
FROM anzgt_may.energyq_silver.assets a
JOIN anzgt_may.energyq_silver.feeders f ON a.feeder_id = f.feeder_id
JOIN anzgt_may.energyq_silver.asset_health_scores h ON h.asset_id = a.asset_id
WHERE h.risk_band IN ('high','critical');

CREATE OR REPLACE VIEW gold_storm_readiness AS
SELECT
  r.region_id,
  r.region_name,
  COUNT(DISTINCT a.asset_id) AS assets_in_hazard_zone,
  SUM(CASE WHEN h.risk_band IN ('high','critical') THEN 1 ELSE 0 END) AS high_risk_in_hazard,
  COUNT(DISTINCT a.feeder_id) AS feeders_exposed,
  (SELECT COUNT(*) FROM anzgt_may.energyq_silver.vegetation_spans v
    WHERE v.region_id = r.region_id AND v.overdue_days > 30) AS vegetation_backlog,
  (SELECT COUNT(*) FROM anzgt_may.energyq_silver.mobile_generation_candidates m
    WHERE m.region_id = r.region_id) AS mobile_gen_candidate_sites,
  (SELECT COUNT(*) FROM anzgt_may.energyq_silver.critical_customers c
    WHERE c.region_id = r.region_id) AS critical_customers_exposed,
  (SELECT COUNT(*) FROM anzgt_may.energyq_silver.work_orders w
    WHERE w.region_id = r.region_id
      AND w.status IN ('approved','scheduled','in_progress')
      AND w.work_type IN ('storm_response','vegetation_treatment','replacement')) AS recommended_storm_packages
FROM anzgt_may.energyq_silver.regions r
JOIN anzgt_may.energyq_silver.hazard_exposure_zones z ON z.region_id = r.region_id
JOIN anzgt_may.energyq_silver.assets a ON a.region_id = r.region_id
JOIN anzgt_may.energyq_silver.asset_health_scores h ON h.asset_id = a.asset_id
WHERE z.hazard_type IN ('cyclone','storm','flood')
GROUP BY r.region_id, r.region_name;

CREATE OR REPLACE VIEW gold_genie_metrics AS
SELECT
  'High-risk assets' AS metric_name,
  CAST(COUNT(*) AS DOUBLE) AS metric_value,
  r.region_name,
  date_format(current_date(), 'yyyy-MM') AS month,
  'Count of assets where risk_band is high or critical.' AS business_definition
FROM anzgt_may.energyq_silver.asset_health_scores h
JOIN anzgt_may.energyq_silver.assets a ON a.asset_id = h.asset_id
JOIN anzgt_may.energyq_silver.regions r ON r.region_id = a.region_id
WHERE h.risk_band IN ('high','critical')
GROUP BY r.region_name
UNION ALL
SELECT
  'Vegetation backlog (overdue >30d)' AS metric_name,
  CAST(COUNT(*) AS DOUBLE) AS metric_value,
  r.region_name,
  date_format(current_date(), 'yyyy-MM') AS month,
  'Count of vegetation spans more than 30 days overdue for treatment.' AS business_definition
FROM anzgt_may.energyq_silver.vegetation_spans v
JOIN anzgt_may.energyq_silver.regions r ON r.region_id = v.region_id
WHERE v.overdue_days > 30
GROUP BY r.region_name
UNION ALL
SELECT
  'Critical customers exposed' AS metric_name,
  CAST(SUM(critical_customer_count) AS DOUBLE) AS metric_value,
  r.region_name,
  date_format(current_date(), 'yyyy-MM') AS month,
  'Sum of critical customers connected to feeders in the region.' AS business_definition
FROM anzgt_may.energyq_silver.feeders f
JOIN anzgt_may.energyq_silver.regions r ON r.region_id = f.region_id
GROUP BY r.region_name;

-- =====================================================================
-- Grants (optional — adjust to your environment)
-- =====================================================================
-- GRANT USAGE ON CATALOG anzgt_may TO `account users`;
-- GRANT USAGE ON SCHEMA anzgt_may.energyq_silver TO `account users`;
-- GRANT USAGE ON SCHEMA anzgt_may.energyq_gold TO `account users`;
-- GRANT SELECT ON ALL TABLES IN SCHEMA anzgt_may.energyq_silver TO `account users`;
-- GRANT SELECT ON ALL TABLES IN SCHEMA anzgt_may.energyq_gold TO `account users`;
