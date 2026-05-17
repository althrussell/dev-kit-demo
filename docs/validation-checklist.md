# GridLens Queensland — validation checklist

Run this before any demo. Everything should pass on a clean checkout.

## 1. Data checks

```bash
python scripts/generate_synthetic_energyq_data.py --seed 42 --output data/synthetic
python scripts/validate_referential_integrity.py --data data/synthetic
```

Expected output ends with:

```text
All integrity checks passed.
```

What this guarantees:

- [x] Synthetic data generation succeeds from a clean repo.
- [x] All 16 entity CSVs exist in `data/synthetic`.
- [x] Primary keys unique across every entity.
- [x] Foreign keys resolve in every table.
- [x] Asset region matches feeder region; asset substation matches feeder
      substation.
- [x] Defect → inspection → asset chain is consistent.
- [x] Vegetation span nearest asset belongs to the same feeder.
- [x] Outage end ≥ start; outage asset (if set) is on the outage feeder.
- [x] Work order completed date ≥ created; work order asset (if set) on the
      work order feeder; depot region matches work order region.
- [x] Critical customer belongs to a real feeder + region.
- [x] Mobile generation candidate belongs to a real feeder + region.
- [x] Coordinates are inside Queensland bounding box.
- [x] All percentage / score fields are in `[0, 100]`.
- [x] Health bands align with risk scores within tolerance.
- [x] Every target region has ≥ 30 high/critical risk assets in at least one
      demo cluster.

## 2. Document checks

```bash
python scripts/generate_asset_documents.py --data data/synthetic --out data/documents
```

Verify:

```bash
find data/documents -name '*.md' | wc -l   # ≥ 500
```

The `document_summary` field of `asset_documents.csv` is refreshed
in-place with the first paragraph of every generated document.

## 3. Lakebase seed

```bash
python scripts/seed_lakebase_demo_state.py
```

This creates `data/lakebase/gridlens.db` containing:

- 1+ `app_users`
- 3+ `saved_map_views`
- 5+ `app_scenarios` (mapped to demo scenarios A–E)
- 4 `work_packages` with associated assets, evidence and approvals
- 3+ `agent_recommendations` with `agent_recommendation_evidence`

When `LAKEBASE_DATABASE_URL` is set, the same script seeds Lakebase.

## 4. Backend

```bash
uvicorn app.backend.main:app --port 8765
curl http://localhost:8765/api/healthz
curl http://localhost:8765/api/regions | jq length      # expect 5
curl "http://localhost:8765/api/map/bundle?region=REG-MKY&scenario=storm_readiness&asset_limit=2000" | jq '.high_risk_asset_count + .critical_asset_count'
curl -X POST -H 'content-type: application/json' \
  http://localhost:8765/api/genie/ask \
  -d '{"question":"Which regions have the highest storm-season asset risk?"}' | jq '.rows | length'  # expect 5
curl -X POST -H 'content-type: application/json' \
  http://localhost:8765/api/agent/investigate \
  -d '{"prompt":"Why is REG-MKY high risk before storm season?","region_id":"REG-MKY","scenario_type":"storm_readiness"}' \
  | jq '.evidence | map(.evidence_type) | unique'
```

The last command should include `"delta_table"` and `"document"`.

## 5. Frontend

```bash
cd app/frontend
npm install
npm run build         # tsc --noEmit && vite build
```

The production bundle should build cleanly (≤ 2s of warnings is fine).

Run it:

```bash
npm run dev
```

Manual checks at <http://localhost:5173>:

- [x] Command Map renders.
- [x] Region selector lists all 5 regions.
- [x] Scenario selector switches risk surface (count changes when switching
      from *Normal operations* to *Storm readiness*).
- [x] Layer toggles enable/disable each map layer.
- [x] Asset click opens Asset 360 with full data.
- [x] "Ask AI about this asset" routes to AI Investigation with the asset
      seeded.
- [x] Create work package saves to Lakebase and routes to the new package.
- [x] AI Investigation returns headline + body + evidence + trace + next
      steps.
- [x] Evidence includes ≥ 1 delta_table and ≥ 1 document item.
- [x] Genie Explorer returns 5 trusted questions and renders SQL + cards +
      table + business definitions for each.
- [x] Executive Briefing renders for the selected region and prints cleanly.
- [x] Status pipeline on a work package flows `draft → pending_approval →
      approved → scheduled → completed`.

## 6. UX checks

- [x] Sidebar shows all six pages with active state.
- [x] Dark enterprise palette (`deep-navy / panel / electric-cyan`).
- [x] Loading states are panels, not bare spinners.
- [x] Empty states explain what's expected.
- [x] Tables have `row-hover` and right-aligned monospace metrics.
- [x] Map popups are styled (no white default MapLibre popup).
- [x] No browser console errors on a full demo flow.

## 7. Demo end-to-end

Walk the script in `docs/demo-script.md`:

- [x] Mackay storm-readiness scenario opens with critical cluster on screen.
- [x] Selected asset has ≥ 1 inspection document.
- [x] MAS recommendation cites ≥ 1 delta_table and ≥ 1 document.
- [x] Created work package appears in Lakebase-backed list with
      `recommended_by_agent = true`.
- [x] Genie question produces a regional ranking with 5 rows.
- [x] Demo can be reset via `rm data/lakebase/gridlens.db && python
      scripts/seed_lakebase_demo_state.py`.

## 8. Quality gates

If any of these are red, fix before showing the demo:

- [ ] `validate_referential_integrity.py` is not green
- [ ] Backend `/api/healthz` is not green
- [ ] Frontend has unhandled console errors
- [ ] An agent response is returned without evidence
- [ ] A Genie answer lacks `business_definitions`
- [ ] A work package was created but `work_package_assets` is empty
