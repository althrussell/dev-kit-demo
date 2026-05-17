# GridLens Queensland — architecture

## High-level diagram

```text
                          ┌─────────────────────────┐
                          │   Energy Queensland     │
                          │   user (Operations,     │
                          │   Vegetation, Exec)     │
                          └────────────┬────────────┘
                                       │ HTTPS / OBO token
                                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│                       Databricks App (GridLens)                     │
│  React + TS + MapLibre  ───►  FastAPI backend (uvicorn, python 3.13) │
└──────────────────────────────────────────────────────────────────────┘
       │           │              │              │            │
       ▼           ▼              ▼              ▼            ▼
   Lakebase   Unity Catalog   UC Volume     Vector       Genie Space  Agent Bricks MAS
   (Postgres) Delta tables    asset_docs    Search       energyq_*    Grid Operations Advisor
   work_pkg   energyq_silver  inspection    over docs    gold tables  + 6 specialists
   approvals  energyq_gold    drawings
   scenarios                  standards
```

## Components

### Frontend (`app/frontend`)

- React 18 + TypeScript + Vite.
- **Mapping engine selected at build time on `VITE_MAPBOX_TOKEN`.**
  - With Mapbox token: `mapbox-gl` with globe projection, atmospheric fog,
    `mapbox-dem` terrain at exaggeration 1.4, hillshade, animated cyclone
    storm rings, high-risk asset heatmap (fades into circle markers as you
    zoom in), 3D building extrusions in metro at zoom > 13, and cinematic
    `flyTo` transitions.
  - Without token: `maplibre-gl` with CartoDB dark raster tiles — same layer
    semantics, no terrain or globe.
- Code-split: only the chosen mapping bundle ships to the browser.
- Tailwind CSS with a custom enterprise dark palette and shadcn-style
  primitives.
- Recharts for analytics.
- Pages mirror the demo flow: `CommandMap`, `AssetDetail`, `RegionalRisk`,
  `WorkPackages`, `AIInvestigation`, `GenieExplorer`, `ExecutiveBriefing`.

### Backend (`app/backend`)

FastAPI exposes `/api/*`. Services are dependency-injected singletons:

| Service | Local mode | Production mode |
| --- | --- | --- |
| `DataStore` | reads `data/synthetic/*.csv` | Databricks SQL connector against `anzgt_may.energyq_silver/gold.*` |
| `LakebaseService` | SQLite at `data/lakebase/gridlens.db` | `LAKEBASE_DATABASE_URL` (Postgres) |
| `DocumentSearchService` | keyword search over `data/documents/*.md` | Databricks Vector Search index `energyq_docs` |
| `GenieService` | grounded fallback against `DataStore` | Genie REST API (`GENIE_SPACE_ID`) |
| `GridOperationsAdvisor` | grounded local simulation | Agent Bricks supervisor endpoint |

Adapter interfaces are deliberately narrow so each service can be swapped to
its production implementation without touching the route layer or the
frontend.

### Data layers (Unity Catalog)

```text
anzgt_may.energyq_bronze.*      raw ingest landing zone (unused in demo)
anzgt_may.energyq_silver.*      conformed, deduped, schema-stable entities
anzgt_may.energyq_gold.*        curated views for app + Genie
```

Silver tables (one per entity from `scripts/generate_synthetic_energyq_data.py`):

`regions`, `depots`, `substations`, `feeders`, `assets`, `asset_health_scores`,
`inspection_events`, `defects`, `vegetation_spans`, `outage_events`,
`work_orders`, `critical_customers`, `hazard_exposure_zones`,
`asset_documents`, `mobile_generation_candidates`, `scenario_runs`.

Gold views (joined and aggregated):

| View | Purpose |
| --- | --- |
| `gold_asset_360` | Asset row with feeder, substation, region, health, recent defect/outage/customer/vegetation context, recommended action |
| `gold_feeder_risk_summary` | Per-feeder reliability + risk roll-up |
| `gold_regional_risk_summary` | Per-region totals (high/critical, vegetation backlog, customer impact, planned coverage) |
| `gold_work_prioritisation` | Recommended remediation opportunities |
| `gold_storm_readiness` | Storm-season cluster readiness per region |
| `gold_genie_metrics` | Compact metric table with shared business definitions |

### Lakebase schema (`scripts/create_lakebase_schema.sql`)

App-state-only tables (no analytics):

`app_users`, `saved_map_views`, `app_scenarios`, `app_scenario_assets`,
`work_packages`, `work_package_assets`, `agent_recommendations`,
`agent_recommendation_evidence`, `asset_annotations`, `approval_events`,
`field_comments`.

### Unity Catalog Volume

```text
/Volumes/anzgt_may/energyq/asset_docs/
  ├── REG-SEQ/<doc-id>.md
  ├── REG-MKY/<doc-id>.md
  ├── REG-TSV/<doc-id>.md
  ├── REG-CQI/<doc-id>.md
  └── REG-RW/<doc-id>.md
```

Documents are markdown for the demo; the same volume holds inspection PDFs,
drawings, standards and storm response plans in production.

### Vector Search

Index `energyq_docs` over `anzgt_may.energyq_silver.asset_documents`,
embedding the `document_summary` column with `databricks-gte-large-en`. See
`scripts/create_vector_index.md`.

### Agent Bricks MAS

Supervisor: **Grid Operations Advisor**. Specialists:

1. Spatial Risk Agent — `gold_asset_360`, `gold_storm_readiness`, map state.
2. Asset Health Agent — `asset_health_scores`, defects, inspections,
   outages.
3. Document Intelligence Agent — Vector Search on UC volume documents.
4. Work Planner Agent — `work_orders`, writes drafts to Lakebase.
5. Outage Impact Agent — `outage_events`, `gold_feeder_risk_summary`,
   `critical_customers`.
6. Genie Analyst Agent — Genie Space proxy.
7. Compliance Agent — policy/standard documents in the UC volume.

Full design in `docs/agentbricks-mas-design.md`.

## Data flow examples

### "Why is this cluster high risk?"

```text
User → AIInvestigation.tsx
     → POST /api/agent/investigate
     → GridOperationsAdvisor.investigate()
         ├─ Spatial Risk: gold_asset_360 (region + cluster)
         ├─ Asset Health: defects + inspections (silver)
         ├─ Outage Impact: outage_events (silver)
         ├─ Document Intelligence: Vector Search → UC Volume excerpts
         ├─ Genie Analyst: trusted question → gold_regional_risk_summary
         └─ Compliance: storm response plan excerpts
     → assemble narrative + evidence + next steps
     → persist agent_recommendations + agent_recommendation_evidence to Lakebase
     → return
```

### "Create a work package"

```text
User → AgentInvestigation → Convert to work package
     → POST /api/agent/create-work-package
     → derive depot, estimate hours/cost, asset bundle
     → LakebaseService.create_work_package → work_packages + work_package_assets
     → navigate to /work-packages/<id>
```

### "Show me storm-season risk per region" (Genie)

```text
User → GenieExplorer → suggested question
     → POST /api/genie/ask
     → GenieService.ask(question)
         ├─ if GENIE_SPACE_ID: forward to Genie REST API
         └─ else fallback: DataStore.regional_summary() → cards + chart + SQL
     → return GenieAnswer
```

## Security and identity

- Databricks Apps injects the OBO token; `databricks-sql-connector` uses it
  for warehouse queries.
- Lakebase auth: short-lived OAuth tokens via the Databricks SDK
  (`generate_database_credential`). The local mock skips auth.
- The UC volume access is governed by Unity Catalog grants.

## Deployment

- **Single-process** deployment is the default for Databricks Apps:
  `npm run build` (frontend) → `dist/` → mounted by FastAPI at `/`.
- The dev experience uses Vite (`:5173`) + uvicorn (`:8765`) with a proxy.

## Integration with real Energy Queensland systems

| External system | Integration pattern |
| --- | --- |
| GIS / asset register | Bronze CDC ingestion → silver entity tables |
| EAM / work management | Bidirectional: pull work orders, push approved work packages |
| Outage Management (OMS) | Streaming ingestion to `outage_events` |
| Vegetation contractor systems | Daily file drop → bronze → silver `vegetation_spans` |
| Weather / hazard feeds (BoM) | Streaming ingestion to `hazard_exposure_zones` |
| Standards / SharePoint | Sync to UC volume; recompute vector index |
| Identity (Azure AD) | Databricks Apps SSO |
