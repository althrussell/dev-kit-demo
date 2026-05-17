# GridLens Queensland — data dictionary

All entities are synthetic but referentially valid. CSVs live in
`data/synthetic/*.csv` and load into `anzgt_may.energyq_silver.*`. Gold views
live in `anzgt_may.energyq_gold.*`.

Primary keys are uppercased identifiers, e.g. `REG-MKY`, `FDR-MKY-0007`,
`AST-MKY-POL-000482`.

## Silver entities

### `regions`

| column | type | notes |
| --- | --- | --- |
| `region_id` | string PK | e.g. `REG-MKY` |
| `region_name` | string | |
| `region_type` | string | `metro`, `coastal_tropical`, `industrial_belt`, `remote_radial` |
| `state` | string | `QLD` |
| `population_density_band` | string | `very_high`, `high`, `medium`, `low`, `very_low` |
| `hazard_profile` | string | comma-list of hazards |
| `centre_lat` / `centre_lon` | float | regional centroid |

### `depots`

| column | type | notes |
| --- | --- | --- |
| `depot_id` | string PK | |
| `region_id` | string FK→regions | |
| `depot_name` | string | |
| `lat` / `lon` | float | |
| `crew_count` | int | total crew |
| `specialist_crews` | int | high-voltage, vegetation, drone teams |
| `mobile_generation_units` | int | available mobile gensets |

### `substations`

| column | type | notes |
| --- | --- | --- |
| `substation_id` | string PK | |
| `region_id` | string FK→regions | |
| `substation_name` | string | |
| `lat` / `lon` | float | |
| `voltage_level` | string | `33kV/11kV`, `66kV/11kV`, `132kV/33kV` |
| `commissioned_year` | int | |
| `criticality_score` | float 0–100 | |
| `flood_exposure_score` | float 0–100 | |
| `cyclone_exposure_score` | float 0–100 | |

### `feeders`

| column | type | notes |
| --- | --- | --- |
| `feeder_id` | string PK | |
| `substation_id` | string FK→substations | |
| `region_id` | string FK→regions | matches substation region |
| `feeder_name` | string | |
| `voltage_kv` | float | |
| `feeder_length_km` | float | |
| `customer_count` | int | |
| `critical_customer_count` | int | |
| `overhead_pct` / `underground_pct` | float 0–100 | sum to 100 |
| `radiality_score` | float 0–100 | |
| `asset_density_score` | float 0–100 | |
| `network_capacity_band` | string | |
| `export_capacity_band` | string | |

### `assets`

| column | type | notes |
| --- | --- | --- |
| `asset_id` | string PK | |
| `feeder_id` | string FK→feeders | |
| `substation_id` | string FK→substations | matches feeder |
| `region_id` | string FK→regions | matches feeder |
| `asset_type` | enum | `pole`, `transformer`, `switch`, `recloser`, `sectionaliser`, `conductor_span`, `ring_main_unit` |
| `asset_name` | string | |
| `lat` / `lon` | float | |
| `install_year` | int | |
| `manufacturer` | string | |
| `material` | string | |
| `voltage_kv` | float | |
| `status` | enum | `in_service`, `planned_replacement`, `under_monitoring`, `decommissioned` |
| `criticality_score` | float 0–100 | |
| `access_difficulty_score` | float 0–100 | |
| `coastal_corrosion_score` | float 0–100 | |
| `flood_exposure_score` | float 0–100 | |
| `cyclone_exposure_score` | float 0–100 | |
| `bushfire_exposure_score` | float 0–100 | |

### `asset_health_scores`

| column | type | notes |
| --- | --- | --- |
| `asset_id` | string PK FK→assets | |
| `condition_score` | float 0–100 | higher = healthier |
| `failure_probability_12m` | float 0–1 | |
| `failure_probability_36m` | float 0–1 | |
| `health_band` | enum | `good`, `watch`, `poor`, `critical` |
| `risk_score` | float 0–100 | |
| `risk_band` | enum | `low`, `medium`, `high`, `critical` |
| `risk_drivers` | string | comma list |
| `last_scored_at` | timestamp | |

### `inspection_events`

| column | type | notes |
| --- | --- | --- |
| `inspection_id` | string PK | |
| `asset_id` | string FK→assets | |
| `inspection_date` | date | |
| `inspection_type` | enum | `routine`, `storm_follow_up`, `vegetation`, `thermal`, `drone`, `pole_test` |
| `inspector_team` | string | |
| `condition_observed` | string | |
| `defect_count` | int | |
| `photo_count` | int | |
| `document_id` | string FK→asset_documents nullable | |
| `recommended_action` | string | |

### `defects`

| column | type | notes |
| --- | --- | --- |
| `defect_id` | string PK | |
| `inspection_id` | string FK→inspection_events | |
| `asset_id` | string FK→assets | matches inspection |
| `defect_type` | enum | see brief |
| `severity` | enum | `low`, `medium`, `high`, `critical` |
| `detected_date` | date | |
| `target_rectification_date` | date | |
| `status` | enum | `open`, `planned`, `closed`, `deferred` |
| `safety_risk_score` | float 0–100 | |
| `reliability_risk_score` | float 0–100 | |

### `vegetation_spans`

| column | type | notes |
| --- | --- | --- |
| `vegetation_span_id` | string PK | |
| `feeder_id` | string FK→feeders | |
| `region_id` | string FK→regions | |
| `nearest_asset_id` | string FK→assets | |
| `lat` / `lon` | float | |
| `species_group` | string | |
| `clearance_m` | float | |
| `growth_rate_band` | enum | |
| `last_treatment_date` / `next_due_date` | date | |
| `overdue_days` | int | 0 if not overdue |
| `vegetation_risk_score` | float 0–100 | |
| `treatment_priority` | enum | `low`, `medium`, `high`, `critical` |

### `outage_events`

| column | type | notes |
| --- | --- | --- |
| `outage_id` | string PK | |
| `feeder_id` | string FK→feeders | |
| `region_id` | string FK→regions | |
| `asset_id` | string FK→assets nullable | |
| `outage_start` / `outage_end` | timestamp | end ≥ start |
| `duration_minutes` | int | |
| `customers_interrupted` | int | |
| `critical_customers_interrupted` | int | |
| `cause_category` | enum | see brief |
| `saidi_minutes` / `saifi_count` | float | |
| `crew_response_minutes` | int | |
| `restoration_notes` | string | |

### `work_orders`

| column | type | notes |
| --- | --- | --- |
| `work_order_id` | string PK | |
| `asset_id` | string FK→assets nullable | matches feeder when present |
| `feeder_id` | string FK→feeders | |
| `region_id` | string FK→regions | |
| `work_type` | enum | see brief |
| `priority` | enum | `low`, `medium`, `high`, `urgent` |
| `status` | enum | `draft`, `approved`, `scheduled`, `in_progress`, `completed`, `cancelled` |
| `created_date` | date | |
| `scheduled_date` | date | ≥ created |
| `completed_date` | date nullable | ≥ created when set |
| `estimated_hours` | float | |
| `estimated_cost_aud` | float | |
| `crew_type` | string | |
| `depot_id` | string FK→depots | matches region |

### `critical_customers`

| column | type | notes |
| --- | --- | --- |
| `critical_customer_id` | string PK | |
| `feeder_id` | string FK→feeders | |
| `region_id` | string FK→regions | |
| `site_name` | string | |
| `site_type` | enum | see brief |
| `lat` / `lon` | float | |
| `backup_power_status` | enum | `none`, `partial`, `full` |
| `priority_score` | float 0–100 | |

### `hazard_exposure_zones`

| column | type | notes |
| --- | --- | --- |
| `hazard_zone_id` | string PK | |
| `region_id` | string FK→regions | |
| `hazard_type` | enum | `cyclone`, `flood`, `bushfire`, `heat`, `storm`, `coastal_corrosion` |
| `zone_name` | string | |
| `lat` / `lon` | float | |
| `radius_km` | float | |
| `severity_score` | float 0–100 | |
| `seasonal_window` | string | |

### `asset_documents`

| column | type | notes |
| --- | --- | --- |
| `document_id` | string PK | |
| `asset_id` | string FK→assets nullable | |
| `feeder_id` | string FK→feeders nullable | |
| `region_id` | string FK→regions | |
| `document_type` | enum | see brief |
| `document_title` | string | |
| `volume_path` | string | `/Volumes/anzgt_may/energyq/asset_docs/...` |
| `created_date` / `effective_date` | date | |
| `document_summary` | string | embedded by Vector Search |
| `sensitivity_classification` | enum | `internal`, `restricted`, `confidential` |

### `mobile_generation_candidates`

| column | type | notes |
| --- | --- | --- |
| `candidate_id` | string PK | |
| `feeder_id` | string FK→feeders | |
| `region_id` | string FK→regions | |
| `site_name` | string | |
| `lat` / `lon` | float | |
| `connection_ready` | bool | |
| `customer_impact_reduction_score` | float 0–100 | |
| `access_difficulty_score` | float 0–100 | |
| `recommended_unit_size_kva` | int | |

### `scenario_runs`

Snapshot table for analytics (the live state is also kept in Lakebase
`app_scenarios`). Columns mirror the brief.

## Gold views

### `gold_asset_360`

One row per asset. Joins `assets`, `feeders`, `substations`, `regions`,
`asset_health_scores`, and aggregates the last 12/24/36 months of outage
counts, open defect counts (with critical roll-up), max vegetation risk on
the same feeder, work order coverage, customer impact, and computes a
`recommended_action` string.

### `gold_feeder_risk_summary`

One row per feeder. SAIDI/SAIFI 12-month, asset cluster risk, customer +
critical customer counts, planned work coverage, recommended priority.

### `gold_regional_risk_summary`

One row per region. Total/high/critical assets, vegetation backlog
(`overdue_days > 0`), planned work count, customer impact at risk, top
five risk drivers, mobile generation readiness.

### `gold_work_prioritisation`

One row per recommendation opportunity. Joined evidence and suggested depot.

### `gold_storm_readiness`

One row per region for the storm scenario. Assets in hazard zone, exposed
critical customers, mobile generation candidate count, vegetation backlog.

### `gold_genie_metrics`

Compact metric table keyed on `metric_name + region + month` for the trusted
Genie questions. Business definitions live in this table so they can be
edited without changing app code.

## Lakebase schema (app state only)

| table | purpose |
| --- | --- |
| `app_users` | user identity captured from OBO |
| `saved_map_views` | per-user named map state |
| `app_scenarios` | named "what-if" scenarios |
| `app_scenario_assets` | scenario ↔ asset binding |
| `work_packages` | core remediation package |
| `work_package_assets` | bundled assets per package |
| `agent_recommendations` | every MAS run, with prompt + body + confidence |
| `agent_recommendation_evidence` | evidence rows backing each recommendation |
| `asset_annotations` | crew-authored notes on an asset |
| `approval_events` | audit log for package status changes |
| `field_comments` | field-crew comments on a work package |
