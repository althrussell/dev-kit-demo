-- =====================================================================
-- GridLens Queensland — Lakebase / Postgres schema
--
-- The Databricks App uses Lakebase (managed Postgres) for transactional
-- app state: work packages, agent recommendations, annotations, approvals,
-- map view state, and field comments.
--
-- For local development the same DDL runs against any Postgres database
-- (or via sqlite-compat with minor types). The backend will auto-fallback
-- to a local SQLite file if LAKEBASE_DATABASE_URL is not set.
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS gridlens;
SET search_path TO gridlens, public;

-- ---------------------------------------------------------------------
-- Users
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS app_users (
    user_id              TEXT PRIMARY KEY,
    display_name         TEXT NOT NULL,
    email                TEXT,
    role                 TEXT NOT NULL CHECK (role IN ('viewer','planner','approver','admin')),
    region_id            TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- Saved map views
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS saved_map_views (
    view_id              TEXT PRIMARY KEY,
    name                 TEXT NOT NULL,
    description          TEXT,
    region_id            TEXT,
    scenario_type        TEXT,
    center_lat           DOUBLE PRECISION,
    center_lon           DOUBLE PRECISION,
    zoom                 DOUBLE PRECISION,
    layers               TEXT, -- JSON-encoded array of layer ids
    risk_threshold       INT,
    created_by           TEXT REFERENCES app_users(user_id),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- Scenarios (Lakebase copy of app-side scenarios; gold table is canonical)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS app_scenarios (
    scenario_id          TEXT PRIMARY KEY,
    scenario_name        TEXT NOT NULL,
    scenario_type        TEXT NOT NULL,
    region_id            TEXT,
    description          TEXT,
    risk_threshold       INT NOT NULL DEFAULT 60,
    created_by           TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_active            BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS app_scenario_assets (
    scenario_id          TEXT NOT NULL REFERENCES app_scenarios(scenario_id) ON DELETE CASCADE,
    asset_id             TEXT NOT NULL,
    included_reason      TEXT,
    PRIMARY KEY (scenario_id, asset_id)
);

-- ---------------------------------------------------------------------
-- Work packages
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS work_packages (
    work_package_id      TEXT PRIMARY KEY,
    title                TEXT NOT NULL,
    region_id            TEXT NOT NULL,
    feeder_id            TEXT,
    scenario_type        TEXT,
    priority             TEXT NOT NULL CHECK (priority IN ('low','medium','high','urgent')),
    status               TEXT NOT NULL CHECK (status IN ('draft','pending_approval','approved','scheduled','completed')),
    created_by           TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    recommended_by_agent BOOLEAN NOT NULL DEFAULT FALSE,
    evidence_summary     TEXT,
    estimated_hours      DOUBLE PRECISION,
    estimated_cost_aud   DOUBLE PRECISION,
    estimated_customer_impact_reduction INT,
    suggested_depot_id   TEXT,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS work_package_assets (
    work_package_id      TEXT NOT NULL REFERENCES work_packages(work_package_id) ON DELETE CASCADE,
    asset_id             TEXT NOT NULL,
    role                 TEXT, -- e.g. "primary", "bundled"
    notes                TEXT,
    PRIMARY KEY (work_package_id, asset_id)
);

CREATE INDEX IF NOT EXISTS work_packages_region_idx ON work_packages(region_id);
CREATE INDEX IF NOT EXISTS work_packages_status_idx ON work_packages(status);

-- ---------------------------------------------------------------------
-- Agent recommendations
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_recommendations (
    recommendation_id    TEXT PRIMARY KEY,
    work_package_id      TEXT REFERENCES work_packages(work_package_id) ON DELETE SET NULL,
    user_prompt          TEXT,
    agent_response       TEXT,
    confidence_score     DOUBLE PRECISION,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    status               TEXT NOT NULL CHECK (status IN ('proposed','accepted','rejected','superseded'))
);

CREATE TABLE IF NOT EXISTS agent_recommendation_evidence (
    evidence_id          TEXT PRIMARY KEY,
    recommendation_id    TEXT NOT NULL REFERENCES agent_recommendations(recommendation_id) ON DELETE CASCADE,
    evidence_type        TEXT NOT NULL CHECK (evidence_type IN ('delta_table','document','genie_answer','map_selection','policy')),
    source_ref           TEXT,
    source_title         TEXT,
    excerpt              TEXT,
    confidence           DOUBLE PRECISION
);

CREATE INDEX IF NOT EXISTS agent_evidence_rec_idx ON agent_recommendation_evidence(recommendation_id);

-- ---------------------------------------------------------------------
-- Asset annotations / field comments
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS asset_annotations (
    annotation_id        TEXT PRIMARY KEY,
    asset_id             TEXT NOT NULL,
    author               TEXT,
    body                 TEXT,
    tags                 TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS field_comments (
    comment_id           TEXT PRIMARY KEY,
    work_package_id      TEXT REFERENCES work_packages(work_package_id) ON DELETE CASCADE,
    author               TEXT,
    body                 TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- Approvals
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS approval_events (
    event_id             TEXT PRIMARY KEY,
    work_package_id      TEXT NOT NULL REFERENCES work_packages(work_package_id) ON DELETE CASCADE,
    approver             TEXT,
    action               TEXT NOT NULL CHECK (action IN ('submit_for_approval','approve','reject','request_changes','schedule')),
    notes                TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
