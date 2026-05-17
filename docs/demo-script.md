# GridLens Queensland — 12-minute demo script

> Walk-through for a senior Energy Queensland operational and executive audience.
> Total run time: ~12 minutes.

## Setup before the meeting

```bash
# In one terminal
source .venv/bin/activate
uvicorn app.backend.main:app --port 8765

# In another
cd app/frontend && npm run dev
```

Open <http://localhost:5173/command-map>.

Pre-load:
- Region selector: **Mackay / Whitsunday Corridor** (`REG-MKY`)
- Scenario selector: **Storm readiness**
- Layers on: Assets, Hazard zones, Critical customers, Depots, Mobile generation

---

## Opening (60s)

> "GridLens Queensland shows how Databricks can become the governed
> intelligence layer above GIS, EAM, outage, field inspection, vegetation and
> document systems. The user we have in mind today is the Mackay regional
> operations manager preparing for storm season."

Highlight what's on screen:
- Live demo backend
- Unity Catalog: `anzgt_may`
- Lakebase: `gridlens.*`

## Act 1 — Command Map (2 min)

1. Show the **Queensland-wide view** (Region: All Queensland).
2. Toggle layers off and on to demonstrate spatial composition.
3. Select **Mackay / Whitsunday Corridor**.
4. Switch the scenario to **Storm readiness**.
5. Point to the right panel:
   - Assets visible
   - **Critical-risk assets** — the demo cluster
   - **Critical customers exposed**
6. Point to the **Top recommendation** card. Click *Open Asset 360*.

> "Notice that what we're looking at is governed Unity Catalog data joined with
> hazard exposure, customer data and depot proximity. No spreadsheets, no
> shapefiles emailed around the team."

## Act 2 — Asset 360 (2 min)

On Asset 360:
1. Read out asset identity, risk score, condition score.
2. Show **Top risk drivers** — derived from health + outage + vegetation.
3. Scroll to **Inspections** and **Defects** — point out the recent
   critical defect.
4. Scroll to **Documents** — show that the volume already contains an
   inspection report referencing this asset and its feeder.
5. Click **Ask AI**.

> "These documents live in a Unity Catalog Volume. The same Volume holds
> standards, drawings, vegetation policies and storm response plans, so the
> agents can ground their answers against authoritative content rather than
> hallucinating."

## Act 3 — AI Investigation (3 min)

In the AI Investigation console:

1. The seeded prompt is already filled in. Press enter (or use the suggested
   prompt: "Show me the top 20 assets that should be remediated before storm
   season.").
2. While the response is rendering, point to the **Specialist agent trace** on
   the right.
3. Walk through the response:
   - Headline + confidence
   - Narrative body
   - **Next steps**
   - **Evidence**: at least one Delta table source, at least one document
     excerpt, a Genie answer, a policy reference.
4. Click **Convert to work package**.

> "Every answer is grounded. The supervisor agent — Grid Operations Advisor —
> orchestrates Spatial Risk, Asset Health, Document Intelligence, Outage
> Impact, Genie Analyst, Compliance and Work Planner specialists. Each
> specialist has a defined tool surface in Unity Catalog or the Volume."

## Act 4 — Work package (2 min)

You're now on `/work-packages/<id>`.

1. Show the new package: status `pending_approval`, priority `high`,
   `recommended_by_agent` badge.
2. Show **bundled assets** and **suggested depot**.
3. Show the **evidence summary**.
4. Click **Approve** → **Schedule** → demonstrate the status pipeline.

> "Lakebase holds the transactional state of the app — every approval,
> annotation, work package and agent recommendation. This is the operational
> system of record that lives next to the lakehouse."

## Act 5 — Genie Explorer (1.5 min)

1. Click **Genie Explorer** in the sidebar.
2. Click the suggested question
   *"Which regions have the highest storm-season asset risk?"*.
3. Walk through:
   - Cards (top 3 regions)
   - **Generated SQL** (gold tables)
   - **Business definitions** — what *vegetation backlog* and
     *planned remediation coverage* actually mean
4. Ask one more: *"What percentage of high-risk assets have planned
   remediation?"*.

> "Genie is grounded against the curated `energyq_gold.*` views. Same
> definitions, same numbers, whether you ask via the app, via SQL or via
> the supervisor agent."

## Act 6 — Executive Briefing (1 min)

1. Click **Executive Briefing**.
2. Select Mackay (or leave on *All Queensland*).
3. Walk through:
   - Headline
   - Top risk zones
   - Recommended actions
   - Open decisions
4. Click **Export** (browser print).

## Close (45s)

> "Databricks is not replacing GIS or work management. It is the governed data
> and AI intelligence layer that turns asset inventories, inspection
> documents, outage history and vegetation programs into explainable spatial
> action — for field crews, regional managers and executives."
>
> "The same architecture supports the next workloads: storm response
> activation, vegetation contractor performance, capex prioritisation,
> mobile generation pre-positioning, and reliability programs."

---

## Demo reset

```bash
rm data/lakebase/gridlens.db
python scripts/seed_lakebase_demo_state.py
```

This returns the Lakebase mock to the seeded state (4 demo work packages,
3 agent recommendations, the saved scenarios) without regenerating the silver
data.

To rebuild the synthetic dataset entirely:

```bash
rm -rf data/synthetic data/documents
python scripts/generate_synthetic_energyq_data.py --seed 42 --output data/synthetic
python scripts/generate_asset_documents.py --data data/synthetic --out data/documents
python scripts/validate_referential_integrity.py --data data/synthetic
python scripts/seed_lakebase_demo_state.py
```
