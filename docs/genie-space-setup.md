# Genie Space — Energy Queensland Network Intelligence

## 1. Create the Genie Space

In Databricks → **Genie** → **New Space**:

- Name: `Energy Queensland Network Intelligence`
- Description: *AI-powered geospatial asset intelligence for Queensland's
  electricity network. Curated metrics across asset health, vegetation,
  outages, hazard exposure and storm readiness.*

## 2. Add tables

Include only governed gold views (read-only):

| Table | Purpose |
| --- | --- |
| `anzgt_may.energyq_gold.gold_asset_360` | one row per asset with joined context |
| `anzgt_may.energyq_gold.gold_feeder_risk_summary` | per-feeder risk roll-up |
| `anzgt_may.energyq_gold.gold_regional_risk_summary` | per-region totals |
| `anzgt_may.energyq_gold.gold_work_prioritisation` | recommended opportunities |
| `anzgt_may.energyq_gold.gold_storm_readiness` | storm-cluster readiness |
| `anzgt_may.energyq_gold.gold_genie_metrics` | shared business metrics |

## 3. Business definitions

Paste the following into the Genie **Instructions** field (or attach as
trusted nouns):

- **Asset risk score** — weighted composite of age, condition, defect
  severity, vegetation proximity, outage recurrence, criticality and hazard
  exposure. Scored 0–100; banded `low ≤ 30 < medium ≤ 55 < high ≤ 75 < critical`.
- **Health band** — derived from `condition_score` only:
  `critical ≤ 30 < poor ≤ 55 < watch ≤ 75 < good`.
- **Vegetation backlog** — vegetation spans with `overdue_days > 0`. The
  count is regional unless filtered.
- **Storm readiness score** — composite of (a) % high/critical assets with a
  scheduled or approved work order, (b) mobile generation candidate readiness,
  and (c) inverse of vegetation backlog density.
- **Planned remediation coverage** — work_orders with `status in
  ('approved','scheduled','in_progress')` covering high/critical risk assets,
  divided by the total high/critical risk asset count, capped at 100%.
- **Critical customer impact** — sum of `critical_customer_count_exposed`
  per region (hospitals, aged care, water, telecom, emergency services,
  airports, industrial, schools).
- **Customer impact reduction** — modelled reduction in interrupted-customer
  count from completing the recommended remediation bundle, derived from
  feeder customer counts and historic SAIFI.

## 4. Suggested questions

Add these to **Sample questions** so they appear in the Genie UI:

1. Which regions have the highest storm-season asset risk?
2. Which feeders have repeated vegetation-related outages?
3. What percentage of high-risk assets have planned remediation?
4. Where should we prioritise work to reduce customer impact?
5. Which regions have the highest vegetation backlog?
6. Which regions have the highest critical customer impact exposure?

The same list is served by the app at `GET /api/genie/suggested-questions`.

## 5. Validation set

Use these closed-form questions to validate Genie behaviour. Run them first
in the Genie UI, then via the app at `/genie`. Numbers depend on your
generation seed; the *shape* must match.

| Question | Expected shape |
| --- | --- |
| "Which regions have the highest storm-season asset risk?" | 5 rows, columns include `Region`, `High-risk assets`, `Critical-risk assets`, `Vegetation backlog`, `Planned remediation coverage`, `Critical customers exposed`. Bar chart. |
| "What percentage of high-risk assets have planned remediation?" | 5 rows, region + coverage %. Cards show top/bottom region. |
| "Which regions have the highest vegetation backlog?" | 5 rows, region + overdue spans. Bar chart. |
| "Which feeders have repeated vegetation-related outages?" | Top N feeders by `outage_count_12m` with `cause_category = 'vegetation'`. |

The app ships a deterministic gold-table fallback (`GenieService`) when
`GENIE_SPACE_ID` is empty. It uses the same SQL shape and business
definitions.

## 6. `genie_questions.json`

A machine-readable copy of the suggested questions and their expected answer
shape lives at:

```json
{
  "questions": [
    {
      "id": "regions_storm_risk",
      "prompt": "Which regions have the highest storm-season asset risk?",
      "expected_columns": [
        "Region",
        "High-risk assets",
        "Critical-risk assets",
        "Vegetation backlog",
        "Planned remediation coverage",
        "Critical customers exposed"
      ],
      "expected_chart": "bar"
    },
    {
      "id": "planned_coverage",
      "prompt": "What percentage of high-risk assets have planned remediation?",
      "expected_columns": [
        "Region",
        "Planned remediation coverage"
      ],
      "expected_chart": "bar"
    }
  ]
}
```

Save it as `docs/genie_questions.json` and check it into the repo if you want
CI to validate Genie answers against the expected shape.

## 7. Refining Genie terminology

When users ask "Which feeders are most fragile?" or "Which transformers will
fail this summer?" the supervisor agent should accept the synonym and route
it. Add these synonyms in the Genie *Trusted Nouns* section:

- *fragile feeders* → feeders with `high + critical assets > 20` and
  `outage_count_12m > 5`
- *summer failure risk* → asset with `risk_band in ('high','critical')` and
  `cyclone_exposure_score > 60`
- *vegetation hotspots* → vegetation spans with
  `vegetation_risk_score > 70 and overdue_days > 0`
- *storm-season cluster* → contiguous high/critical assets within a 5km
  radius on a feeder with `outage_count_12m > 3`
