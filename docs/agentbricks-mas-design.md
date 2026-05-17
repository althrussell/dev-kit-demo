# GridLens Queensland — Agent Bricks Multi-Agent System design

> Supervisor: **Grid Operations Advisor**.
> Six specialists. Every answer must include grounded evidence (Delta tables,
> UC volume documents, Genie answers, or policy citations).

## Why a supervisor?

The questions Energy Queensland operations actually asks ("Why is this
cluster high risk?", "What should we do before storm season?") are
*multi-modal*: they touch spatial reasoning, asset health, recurrence,
documents, customer impact and compliance. A supervisor + specialist design
keeps each specialist focused on one tool surface and lets the supervisor
synthesise a coherent recommendation with named evidence.

## Supervisor — Grid Operations Advisor

**Role.** Plans an investigation, delegates to specialists in a deterministic
order, and assembles the narrative + evidence + next steps.

**Inputs.**

- User prompt
- Optional: `asset_id`, `feeder_id`, `region_id`, `scenario_type`,
  selected map asset IDs

**Outputs.**

```json
{
  "recommendation_id": "REC-...",
  "headline": "Critical risk cluster on FDR-MKY-0062 ...",
  "body": "...",
  "confidence": 0.78,
  "evidence": [
    {"evidence_type": "delta_table", "source_ref": "energyq_gold.gold_asset_360",
     "source_title": "Cluster risk pack", "excerpt": "...", "confidence": 0.86},
    {"evidence_type": "document", "source_ref": "/Volumes/.../INSP-...",
     "source_title": "Inspection report — POLE-MKY-...", "excerpt": "...",
     "confidence": 0.81},
    ...
  ],
  "trace": [
    {"agent": "Spatial Risk", "action": "query gold_asset_360", "confidence": 0.9,
     "output_summary": "..."}
    ...
  ],
  "next_steps": ["Bundle 8 assets on feeder ...", "Assign depot ...", ...]
}
```

**Invariants the supervisor enforces.**

1. At least one `delta_table` evidence row.
2. At least one `document` evidence row whenever assets are in scope.
3. At least one `policy` evidence row whenever a recommendation involves a
   field crew action.
4. The `next_steps` list is no longer than 5 and includes a depot
   assignment.

## Specialist agents

### 1. Spatial Risk Agent

| Aspect | Detail |
| --- | --- |
| Goal | Cluster the high-risk surface in the selected region or selection. |
| Tools | SQL: `energyq_gold.gold_asset_360`, `gold_storm_readiness`, `hazard_exposure_zones`. Map selection state. |
| Trigger | All investigations involving a region or feeder. |
| Output | "8 assets within 1.2km on FDR-MKY-0062, all in cyclone hazard zone HZ-MKY-..." |

### 2. Asset Health Agent

| Aspect | Detail |
| --- | --- |
| Goal | Explain *why* this asset/cluster is high risk. |
| Tools | SQL: `asset_health_scores`, `defects`, `inspection_events`, `outage_events`. |
| Trigger | All investigations. |
| Output | Ranked risk drivers + cohort comparison. |

### 3. Document Intelligence Agent

| Aspect | Detail |
| --- | --- |
| Goal | Retrieve relevant inspection reports, standards, vegetation policies. |
| Tools | Vector Search on UC volume `/Volumes/anzgt_may/energyq/asset_docs/`, plus `asset_documents` metadata. |
| Trigger | Whenever asset / feeder / region is in scope. |
| Output | 2–4 document excerpts with `volume_path` references. |

### 4. Work Planner Agent

| Aspect | Detail |
| --- | --- |
| Goal | Bundle assets into a draft work package, suggest depot + crew + cost. |
| Tools | SQL: `work_orders`, `depots`, `gold_work_prioritisation`. Lakebase: `work_packages`. |
| Trigger | "Create a work package" intent, or supervisor decides bundling is warranted. |
| Output | Draft package with assets, depot, hours, cost, customer impact reduction. |

### 5. Outage Impact Agent

| Aspect | Detail |
| --- | --- |
| Goal | Quantify customer + critical customer impact and recurrence. |
| Tools | SQL: `outage_events`, `gold_feeder_risk_summary`, `critical_customers`. |
| Trigger | Whenever a feeder is in scope. |
| Output | "Feeder FDR-MKY-0062: 12-month outages 8, customers 6,300, criticals 4." |

### 6. Genie Analyst Agent

| Aspect | Detail |
| --- | --- |
| Goal | Answer the business / executive analytics layer. |
| Tools | Genie Space via `genie_space_id`, with deterministic fallback against `gold_*` views. |
| Trigger | Executive briefings, regional ranking, planned coverage. |
| Output | Trusted question + cards + SQL + business definitions. |

### 7. Compliance Agent

| Aspect | Detail |
| --- | --- |
| Goal | Confirm the recommendation aligns with maintenance standards, vegetation policy and storm response plan. Flag where human approval is required. |
| Tools | Vector Search on standard / policy documents (sensitivity_classification ∈ {`internal`, `restricted`}). |
| Trigger | Whenever a recommendation produces a draft work package or capex spend. |
| Output | Policy excerpts + an explicit *human-approval-required* flag. |

## Specialist invocation order

```text
prompt + context
     │
     ▼
 Spatial Risk ─►  Asset Health ─►  Outage Impact ─► Document Intelligence
                                                       │
                                                       ▼
                              Genie Analyst ◄─── (trusted question, if needed)
                                                       │
                                                       ▼
                                            Work Planner (if remediation)
                                                       │
                                                       ▼
                                                 Compliance
                                                       │
                                                       ▼
                                              Supervisor merges
```

## Required demo prompts (UI buttons)

These render in `app/frontend/src/pages/AIInvestigation.tsx` and as suggested
chips:

1. "Show me the top 20 assets that should be remediated before storm season."
2. "Which feeders have the highest combination of vegetation exposure and outage history?"
3. "Create a work package for the Mackay high-risk cluster and avoid duplicate planned works."
4. "Explain why this selected asset is high risk using inspection documents."
5. "What is the customer impact if we defer this work by six months?"
6. "Prepare a regional manager briefing for the selected risk zone."

## Adapter interface

`app/backend/services/agent.py` defines the interface the app calls:

```python
class GridOperationsAdvisor:
    def investigate(
        self,
        *,
        prompt: str,
        asset_id: Optional[str] = None,
        feeder_id: Optional[str] = None,
        region_id: Optional[str] = None,
        scenario_type: Optional[str] = None,
        selected_asset_ids: Optional[list[str]] = None,
    ) -> dict: ...  # returns the JSON shape above
```

For local demo, the implementation pulls evidence from `DataStore`,
`DocumentSearchService`, and `GenieService`. To swap to Agent Bricks, set
`AGENTBRICKS_SUPERVISOR_ENDPOINT` and forward the request body — the response
contract is identical.

## Persistence

Every successful call writes to Lakebase via `LakebaseService.save_recommendation`:

- `agent_recommendations` — id, prompt, body, confidence, status (`proposed`)
- `agent_recommendation_evidence` — one row per evidence item

When the user converts a recommendation into a work package via
`POST /api/agent/create-work-package`, the recommendation row is linked via
`work_package_id` and its status flips to `accepted`.

## Guardrails

- Never produce a recommendation without at least one Delta table evidence
  row.
- Always show specialist trace in the right panel — including the action
  invoked and its output summary.
- Surface a *human approval required* badge whenever Compliance flags it.
- The supervisor must include the suggested depot for every remediation
  recommendation; if no depot can be assigned, the package is flagged
  *needs depot manual selection*.
