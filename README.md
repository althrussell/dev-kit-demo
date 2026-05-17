# GridLens Queensland

> **AI-powered geospatial asset intelligence for Queensland's electricity network.**
>
> A fully runnable enterprise-grade Databricks App demo that shows how an
> electricity distribution utility can move from static GIS + fragmented asset
> documents + reactive work planning to a governed, AI-assisted spatial
> operating layer.

GridLens Queensland combines:

| Layer | Technology |
| --- | --- |
| Hosted UI | **Databricks Apps** (React / TypeScript + MapLibre) |
| Transactional / app state | **Lakebase** (Postgres) with local SQLite mock |
| Governed analytics | **Delta tables in Unity Catalog** (`anzgt_may.energyq_silver/gold`) |
| Asset documents | **Unity Catalog Volumes** (`/Volumes/anzgt_may/energyq/asset_docs`) |
| Document intelligence | **Vector Search / RAG** with local keyword fallback |
| Natural-language analytics | **Genie Space** over curated gold tables with grounded fallback |
| Operational recommendations | **Agent Bricks Multi-Agent System** with local grounded simulation |
| Map | **Mapbox GL JS** (globe projection, terrain, hillshading, sky/atmosphere, heatmap, animated cyclone rings, 3D buildings) when `VITE_MAPBOX_TOKEN` is set, with MapLibre + CartoDB fallback |

Every AI answer is grounded in Delta tables, UC Volume documents, Genie answers,
or policy excerpts — there is no ungrounded chatbot anywhere in the app.

---

## Repository layout

```text
.
├── README.md                              # this file
├── .env.example                           # full environment variable surface
├── app/
│   ├── backend/                           # FastAPI backend (uvicorn entry: app.backend.main:app)
│   │   ├── main.py                        # API endpoints
│   │   ├── models.py                      # Pydantic models
│   │   └── services/                      # DataStore, Lakebase, Documents, Genie, Agent
│   └── frontend/                          # React + TypeScript + Vite + Tailwind + MapLibre
│       ├── src/pages/                     # CommandMap, AssetDetail, RegionalRisk,
│       │                                  # WorkPackages, AIInvestigation, GenieExplorer,
│       │                                  # ExecutiveBriefing
│       ├── src/components/                # MapView, AppShell, RiskPill
│       └── src/lib/                       # api.ts, AppState.tsx
├── data/
│   ├── synthetic/                         # generated CSV tables (regions, assets, …)
│   ├── documents/                         # generated markdown asset documents per region
│   └── lakebase/gridlens.db               # local SQLite seed of the Lakebase schema
├── docs/
│   ├── demo-script.md
│   ├── demo-architecture.md
│   ├── data-dictionary.md
│   ├── genie-space-setup.md
│   ├── agentbricks-mas-design.md
│   └── validation-checklist.md
├── scripts/
│   ├── generate_synthetic_energyq_data.py
│   ├── validate_referential_integrity.py
│   ├── create_uc_tables.sql
│   ├── load_delta_tables.py
│   ├── create_lakebase_schema.sql
│   ├── seed_lakebase_demo_state.py
│   ├── generate_asset_documents.py
│   ├── upload_documents_to_volume.py
│   └── create_vector_index.md
└── tests/                                 # data integrity + API smoke tests
```

---

## Quickstart — local synthetic demo

The fastest path: everything runs locally against synthetic CSVs and a SQLite
mock of Lakebase. No Databricks credentials required.

### 1. Python environment

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install --upgrade uv
uv pip install -r app/backend/requirements.txt
```

### 2. Generate synthetic data (idempotent, deterministic with `--seed`)

```bash
python scripts/generate_synthetic_energyq_data.py \
  --assets 40000 \
  --feeders 320 \
  --documents 1200 \
  --seed 42 \
  --output data/synthetic
```

Then validate referential integrity:

```bash
python scripts/validate_referential_integrity.py --data data/synthetic
```

### 3. Generate synthetic asset documents

```bash
python scripts/generate_asset_documents.py --data data/synthetic --out data/documents
```

### 4. Seed the local Lakebase mock (SQLite)

```bash
python scripts/seed_lakebase_demo_state.py
```

This creates `data/lakebase/gridlens.db` with the same schema as Lakebase and
the demo work packages, agent recommendations and scenarios pre-loaded.

### 5. Run the backend (FastAPI on :8765)

```bash
uvicorn app.backend.main:app --port 8765 --reload
```

### 6. Run the frontend (Vite dev server on :5173 with `/api` proxy)

```bash
cd app/frontend
npm install

# Cinematic Mapbox experience (recommended for live demos):
# Drop your Mapbox public token (pk.*) into app/frontend/.env.local
echo 'VITE_MAPBOX_TOKEN=pk.your-token-here' > .env.local

npm run dev
```

If `VITE_MAPBOX_TOKEN` is omitted the app gracefully falls back to MapLibre +
CartoDB tiles. With Mapbox you get globe projection on the opening view, a
cinematic fly-to Queensland with terrain + hillshading, animated cyclone
storm rings, a high-risk asset heatmap, and 3D building footprints in SEQ
metro.

Open <http://localhost:5173/command-map>.

> **Single-process production layout.** `npm run build` writes
> `app/frontend/dist`; the FastAPI app auto-mounts it. Running just
> `uvicorn app.backend.main:app` will then serve both the API and SPA from one
> process — this is the Databricks Apps layout.

---

## Connecting to Databricks (anzgt_may)

The demo is designed to flip from local mocks to a live Databricks workspace by
adding environment variables. Nothing else changes in the app.

### 1. Create UC tables + volume

In a SQL warehouse (or the workspace SQL editor), run:

```bash
scripts/create_uc_tables.sql
```

This creates the schemas `anzgt_may.energyq_bronze/silver/gold` and the volume
`/Volumes/anzgt_may/energyq/asset_docs`.

### 2. Load Delta tables from generated CSVs

```bash
export DATABRICKS_HOST=https://<workspace>
export DATABRICKS_TOKEN=...
export DATABRICKS_HTTP_PATH=/sql/1.0/warehouses/<warehouse-id>

python scripts/load_delta_tables.py --data data/synthetic
```

A `--dry-run` flag is provided to preview the generated `INSERT` statements.

### 3. Upload documents to UC Volume

```bash
python scripts/upload_documents_to_volume.py \
  --local data/documents \
  --volume /Volumes/anzgt_may/energyq/asset_docs
```

### 4. Vector Search index

Follow the instructions in `scripts/create_vector_index.md` to create the
`energyq_docs` endpoint and index on
`anzgt_may.energyq_silver.asset_documents`.

### 5. Lakebase

Create a Lakebase instance, then run `scripts/create_lakebase_schema.sql`
against it and set:

```bash
export LAKEBASE_DATABASE_URL=postgresql://<user>:<pwd>@<host>:<port>/gridlens
python scripts/seed_lakebase_demo_state.py
```

### 6. Genie Space

Follow `docs/genie-space-setup.md` to create the Genie Space
"Energy Queensland Network Intelligence" backed by the six curated gold tables
and set `GENIE_SPACE_ID`.

### 7. Agent Bricks MAS

Follow `docs/agentbricks-mas-design.md` to deploy the Grid Operations Advisor
supervisor + six specialist agents and set
`AGENTBRICKS_SUPERVISOR_ENDPOINT`.

---

## Running the demo

`docs/demo-script.md` walks through the 12-minute demo flow:

1. **Command Map** — toggle layers, switch to *Storm readiness*, focus
   `Mackay / Whitsunday Corridor`.
2. **Asset 360** — click a critical asset, review evidence (defects,
   vegetation, documents).
3. **AI Investigation** — "Why is this cluster high risk?" → grounded
   evidence from Delta tables + UC volume documents.
4. **Work package** — convert the recommendation into a Lakebase-backed
   work package, follow it through `pending_approval → approved → scheduled`.
5. **Genie Explorer** — ask trusted business questions, see SQL +
   visualisation + business definitions.
6. **Executive Briefing** — generate the AI briefing for a regional manager.

Run `scripts/validate_referential_integrity.py` to confirm a clean demo state
before walkthroughs.

---

## Known limitations & TODOs

- **Vector Search** runs as a local keyword + region-aware fallback over
  generated markdown until the UC index is materialised. The interface is
  drop-in — replace `DocumentSearchService` in
  `app/backend/services/documents.py` with a Vector Search client.
- **Genie** uses a deterministic gold-table fallback for six trusted questions.
  When `GENIE_SPACE_ID` is set, the service should proxy the Genie REST API and
  preserve `cards / columns / rows / business_definitions` shape.
- **Agent Bricks MAS** is a grounded local simulation. The actual MAS endpoint
  (when set) will return the same `{recommendation_id, headline, body, evidence,
  trace, next_steps}` envelope; only the implementation in
  `app/backend/services/agent.py` swaps.
- **Asset photos** are referenced by metadata only — no binary images are
  generated.
- **Lasso selection** is implemented as "select all visible high-risk assets"
  in the current viewport for simplicity; a draw-rectangle tool can be added in
  `MapView`.
- **Authentication** is intentionally not wired; Databricks Apps will inject
  the OBO token at the platform layer.
- **Real Energy Queensland systems** (GIS, EAM, OMS, vegetation contractor
  systems, weather feeds, billing) are not connected. Integration patterns are
  documented in `docs/demo-architecture.md`.

---

## What's in here for the AE / SA team

- **Repeatable** demo from a clean repo: data generation, validation, app and
  docs in one place.
- **Coherent synthetic data**: regional risk profiles, correlated outages,
  document references that all join.
- **Grounded** AI: every agent response cites Delta tables and Volume
  documents.
- **Drop-in** Databricks integration points: each service is a single class
  with a clean adapter interface.
