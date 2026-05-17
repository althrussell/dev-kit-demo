"""
Generate synthetic asset documents for GridLens Queensland.

For each row in data/synthetic/asset_documents.csv, write a corresponding
markdown file under data/documents/{region_id}/{document_type}/{document_id}.md
The markdown content references real asset_id / feeder_id / region_id values
from the synthetic dataset so the documents are useful for RAG retrieval.

The CSV is then re-emitted with `document_summary` filled in.

Usage:
    python scripts/generate_asset_documents.py --input data/synthetic --output data/documents
"""

from __future__ import annotations

import argparse
import csv
import random
from datetime import date, datetime, timedelta
from pathlib import Path


TEMPLATES = {
    "inspection_report": """# Inspection Report — {asset_id}

Region: {region_name}
Feeder: {feeder_id}
Substation: {substation_name}
Inspection type: {inspection_type}
Inspection date: {inspection_date}
Inspector team: {inspector_team}

## Findings

- {finding_1}
- {finding_2}
- {finding_3}

## Risk drivers

This asset is currently scored **{risk_band}** ({risk_score}/100). Primary
drivers: {risk_drivers}.

Recent outage history (12 months): {outage_count_12m} events linked to feeder {feeder_id}.

## Recommendation

{recommendation}

## Bundling opportunity

Adjacent assets on feeder {feeder_id} with similar drivers:
- {bundled_asset_1}
- {bundled_asset_2}

Crew should consider treating these together to reduce mobilisations.

---

Document classification: {classification}
Document id: {document_id}
""",
    "engineering_drawing": """# Engineering Drawing — {asset_id}

Region: {region_name}
Feeder: {feeder_id}
Drawing series: GLQ-DRWG-{region_id}-{drawing_num}

## Asset summary

- Asset id: {asset_id}
- Asset type: {asset_type}
- Manufacturer: {manufacturer}
- Material: {material}
- Voltage: {voltage_kv} kV
- Installed: {install_year}

## Notes

This drawing depicts the physical mounting configuration for asset {asset_id}
on feeder {feeder_id}. Refer to maintenance standard MS-{region_id}-{stdnum}
for clearance, earthing and condition assessment requirements.

Updated dimensions or material substitutions must be approved by the regional
engineering manager and reflected in the next inspection report.

Document id: {document_id}
""",
    "maintenance_standard": """# Maintenance Standard MS-{region_id}-{stdnum} — {region_name}

Effective date: {effective_date}
Document id: {document_id}
Classification: {classification}

## Scope

Applies to overhead distribution assets in the **{region_name}** operating
region. Covers crossarm inspection frequency, conductor sag, insulator
condition, and vegetation clearance thresholds.

## Key requirements

- Routine pole-top inspections every 36 months for assets with risk band
  *good* or *watch*.
- Pole-top inspections every 12 months for assets in *poor* or *critical*
  health band.
- Minimum vegetation clearance: 2.5m for 11/22 kV; 4.0m for 33 kV.
- Following storm events with peak gust above 90 km/h, perform a
  storm follow-up inspection on all flagged feeders.
- Crossarm corrosion observations rated severity high or above must
  trigger a planned replacement work order within 90 days.

## Approval

Document approved by Regional Asset Manager, {region_name}.
""",
    "vegetation_policy": """# Vegetation Management Policy — {region_name}

Document id: {document_id}
Effective date: {effective_date}
Classification: {classification}

## Treatment cycle

- High growth species (mango, eucalypt, casuarina): 8-12 month cycle.
- Moderate growth species: 12-18 month cycle.
- Slow growth species: 24 month cycle.

Cycle length must be reduced by 25% on any span where clearance has been
recorded below 1.5m more than once in the preceding 24 months.

## Outage correlation

Spans with three or more vegetation-related outages in the last 36 months
on feeder {feeder_id} or comparable feeders must be flagged for
extended-treatment-area assessment.

## Region-specific notes

In **{region_name}**, the dominant species drivers are tracked in the
vegetation_spans table. Tropical species in coastal corridors show
significantly higher growth rates during the wet season (Nov - Apr).
""",
    "storm_response_plan": """# Storm Response Plan — {region_name}

Document id: {document_id}
Effective date: {effective_date}
Classification: {classification}

## Pre-season activities

- Confirm mobile generation candidate sites are inspected and connection-ready.
- Validate critical customer backup power status.
- Audit storm response work orders for completeness.

## Activation

When the Bureau of Meteorology issues a cyclone watch within the
**{region_name}** operating area:

1. Pre-position mobile generation units at depots with highest customer
   exposure.
2. Run storm-follow-up inspection assignments on feeders with risk band
   *high* or *critical*.
3. Validate switching plans for the listed critical customer feeders.

## Restoration priorities

1. Hospitals, aged care, water pumping, emergency services.
2. Industrial critical load (refer to gold_storm_readiness).
3. Residential metro feeders by customer count.
4. Remote radial feeders by access difficulty.
""",
    "photo_pack": """# Photo Pack — {asset_id}

Region: {region_name}
Feeder: {feeder_id}
Captured: {inspection_date}
Photographer: {inspector_team}

This photo pack contains visual evidence supporting inspection findings on
asset {asset_id}. Each frame is captioned with timestamp, asset id and
observed condition.

- Frame 1: Crossarm condition view from western elevation.
- Frame 2: Insulator surface contamination.
- Frame 3: Vegetation clearance measurement.
- Frame 4: Access track condition.

Document id: {document_id}
Classification: {classification}
""",
    "work_order_pdf": """# Work Order — {asset_id}

Work order id: WO-EX-{document_id}
Region: {region_name}
Feeder: {feeder_id}
Priority: {priority}
Status: scheduled
Created: {effective_date}

## Scope

Carry out remediation works against asset {asset_id} as recommended in
inspection report linked to feeder {feeder_id}. Crew should bundle with
adjacent assets where possible to reduce mobilisations.

## Safety controls

- Pole top isolation per maintenance standard MS-{region_id}-{stdnum}
- Vegetation clearance check before climbing
- Two-person team for any work above 7m

## Estimated hours

Field hours: 6.5
Travel hours: 2.0
Total: 8.5

Document id: {document_id}
""",
    "risk_assessment": """# Risk Assessment — {asset_id}

Region: {region_name}
Feeder: {feeder_id}
Document id: {document_id}
Effective date: {effective_date}

## Asset risk profile

- Risk band: {risk_band}
- Risk score: {risk_score}/100
- Failure probability (12m): {fp12}
- Failure probability (36m): {fp36}
- Key drivers: {risk_drivers}

## Consequence assessment

Feeder {feeder_id} serves approximately {customer_count} customers, of which
{critical_customer_count} are classified as critical (hospital, aged care,
water pumping, emergency services, industrial).

A loss of supply event on this asset would likely interrupt {est_impact}
customers for {est_minutes} minutes given current restoration profiles for
{region_name}.

## Mitigation

Refer to the linked inspection report and gold_work_prioritisation
recommendation for the planned mitigation pathway.
""",
}


FINDINGS_BY_TYPE = {
    "pole": [
        "Crossarm corrosion observed on western side.",
        "Termite damage noted at ground line.",
        "Pole shows slight lean (8 degrees from vertical).",
        "Insulator surface contamination consistent with coastal salt deposition.",
        "Lightning damage marks on crossarm.",
        "Conductor binding showing wear at attachment point.",
    ],
    "transformer": [
        "Oil leak observed at gasket interface.",
        "Bushing arrester showing surface contamination.",
        "Tank earth connection corrosion noted.",
        "Acoustic noise above baseline for nameplate rating.",
        "Cooling fin damage on east side.",
    ],
    "switch": [
        "Air break operating mechanism slow to operate.",
        "Insulator surface contamination.",
        "Mechanism greasing overdue.",
        "Earth connection looseness.",
    ],
    "recloser": [
        "Counter reading unusually high for cycle.",
        "Battery age beyond recommended threshold.",
        "Surface contamination on housing.",
    ],
    "sectionaliser": [
        "Mechanism operation slow under test.",
        "Surface contamination on housing.",
    ],
    "conductor_span": [
        "Conductor sag observed during high temperature.",
        "Tie wire wear at attachment point.",
        "Vegetation clearance below threshold for span.",
    ],
    "ring_main_unit": [
        "Surface corrosion on enclosure.",
        "Locking mechanism sluggish.",
        "Cable termination joint requires inspection.",
    ],
}


RECOMMENDATIONS = [
    "Schedule crossarm replacement and bundle with vegetation treatment within 30 days.",
    "Plan replacement during next regional capex round; monitor monthly.",
    "Defer until storm-season pre-inspection; review in 90 days.",
    "Urgent inspection required; mobilise drone team to confirm condition.",
    "Bundle into upcoming feeder-wide reliability improvement work pack.",
    "Replace within 60 days; consider switching plan to limit customer impact during outage.",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/synthetic")
    parser.add_argument("--output", default="data/documents")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    inp = Path(args.input)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    def load(name: str) -> list[dict]:
        return list(csv.DictReader((inp / f"{name}.csv").open(newline="", encoding="utf-8")))

    docs = load("asset_documents")
    assets = {a["asset_id"]: a for a in load("assets")}
    feeders = {f["feeder_id"]: f for f in load("feeders")}
    substations = {s["substation_id"]: s for s in load("substations")}
    regions = {r["region_id"]: r for r in load("regions")}
    health = {h["asset_id"]: h for h in load("asset_health_scores")}
    inspections = load("inspection_events")
    insp_by_asset: dict[str, list[dict]] = {}
    for i in inspections:
        insp_by_asset.setdefault(i["asset_id"], []).append(i)
    outages = load("outage_events")
    outages_by_feeder: dict[str, int] = {}
    cutoff = date.today() - timedelta(days=365)
    for o in outages:
        try:
            start = datetime.fromisoformat(o["outage_start"]).date()
        except Exception:
            continue
        if start >= cutoff:
            outages_by_feeder[o["feeder_id"]] = outages_by_feeder.get(o["feeder_id"], 0) + 1

    feeder_assets: dict[str, list[str]] = {}
    for asset_id, a in assets.items():
        feeder_assets.setdefault(a["feeder_id"], []).append(asset_id)

    written = 0
    for d in docs:
        doc_type = d["document_type"]
        template = TEMPLATES.get(doc_type)
        if not template:
            continue

        region = regions.get(d["region_id"], {})
        region_name = region.get("region_name", d["region_id"])
        feeder = feeders.get(d["feeder_id"], {})
        asset = assets.get(d["asset_id"], {}) if d.get("asset_id") else {}
        substation = substations.get(asset.get("substation_id", ""), {}) if asset else {}
        h = health.get(d["asset_id"], {}) if d.get("asset_id") else {}
        insp = (insp_by_asset.get(d["asset_id"]) or [{}])[0] if d.get("asset_id") else {}

        ftype = asset.get("asset_type", "pole")
        finding_pool = FINDINGS_BY_TYPE.get(ftype, FINDINGS_BY_TYPE["pole"])
        if len(finding_pool) >= 3:
            picks = rng.sample(finding_pool, k=3)
        else:
            picks = (finding_pool * 3)[:3]
        finding_1, finding_2, finding_3 = picks

        # Bundling opportunity — two assets on the same feeder.
        bundled = []
        siblings = feeder_assets.get(asset.get("feeder_id", d["feeder_id"]), [])
        if siblings:
            bundled = rng.sample(siblings, k=min(2, len(siblings)))
        b1 = bundled[0] if bundled else "n/a"
        b2 = bundled[1] if len(bundled) > 1 else b1

        ctx = {
            "asset_id": d.get("asset_id") or "n/a",
            "asset_type": ftype,
            "manufacturer": asset.get("manufacturer", "Hardwood Co."),
            "material": asset.get("material", "hardwood"),
            "voltage_kv": asset.get("voltage_kv", "11.0"),
            "install_year": asset.get("install_year", "1995"),
            "region_id": d["region_id"],
            "region_name": region_name,
            "feeder_id": d.get("feeder_id") or "n/a",
            "substation_name": substation.get("substation_name", "Unknown"),
            "inspection_type": insp.get("inspection_type", "pole_test"),
            "inspection_date": insp.get("inspection_date", d.get("effective_date", "2025-01-01")[:10]),
            "inspector_team": insp.get("inspector_team", "Crew A"),
            "finding_1": finding_1,
            "finding_2": finding_2,
            "finding_3": finding_3,
            "risk_band": h.get("risk_band", "watch"),
            "risk_score": h.get("risk_score", "55.0"),
            "risk_drivers": h.get("risk_drivers", "age, criticality").replace("|", ", "),
            "outage_count_12m": outages_by_feeder.get(d.get("feeder_id"), 0),
            "recommendation": rng.choice(RECOMMENDATIONS),
            "bundled_asset_1": b1,
            "bundled_asset_2": b2,
            "drawing_num": f"{rng.randint(100, 999):03d}",
            "stdnum": f"{rng.randint(1, 50):02d}",
            "classification": d.get("sensitivity_classification", "internal"),
            "document_id": d["document_id"],
            "effective_date": d.get("effective_date", "2025-01-01")[:10],
            "priority": rng.choice(["medium", "high", "urgent"]),
            "customer_count": feeder.get("customer_count", "800"),
            "critical_customer_count": feeder.get("critical_customer_count", "5"),
            "est_impact": int(int(feeder.get("customer_count", "800") or "800") * 0.3),
            "est_minutes": rng.randint(60, 240),
            "fp12": h.get("failure_probability_12m", "0.04"),
            "fp36": h.get("failure_probability_36m", "0.10"),
        }
        try:
            body = template.format(**ctx)
        except KeyError as e:
            print(f"template error for {d['document_id']} type {doc_type}: missing {e}")
            continue

        path = out / d["region_id"] / d["document_type"] / f"{d['document_id']}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        # First two lines become the summary.
        summary_lines = [l for l in body.splitlines() if l.strip() and not l.startswith("#")][:2]
        d["document_summary"] = " ".join(summary_lines)[:500]
        written += 1

    # Re-write the asset_documents.csv with summaries filled in.
    target = inp / "asset_documents.csv"
    with target.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(docs[0].keys()))
        writer.writeheader()
        for row in docs:
            writer.writerow(row)

    print(f"Wrote {written} documents to {out}/<region>/<type>/<doc>.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
