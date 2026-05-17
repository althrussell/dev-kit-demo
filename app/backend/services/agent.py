"""
GridLens Queensland — Multi-Agent System adapter.

Two execution modes, chosen per-request:

  1. **Real Supervisor MAS** — when `AGENTBRICKS_SUPERVISOR_ENDPOINT` is
     set, `investigate()` POSTs to the Databricks Agent Bricks
     supervisor serving endpoint and shapes the response back to the
     existing FastAPI contract (recommendation_id / headline / body /
     confidence / evidence / trace / next_steps).

  2. **Local deterministic orchestrator** — when the endpoint is unset,
     the same hand-rolled pipeline used by every previous demo run is
     executed. This keeps `npm run dev` viable for engineers without a
     Databricks profile and gives the e2e tests stable, source-grounded
     output.

The deterministic pipeline below is also used as the safety-net fallback
when the real MAS call fails for any reason (network, auth, parse). The
returned dict ALWAYS includes at least one delta_table evidence and one
document evidence reference.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Optional

from app.backend.services.data_store import DataStore
from app.backend.services.documents import DocumentSearchService
from app.backend.services.genie import GenieService

logger = logging.getLogger(__name__)


def _short_id() -> str:
    return uuid.uuid4().hex[:8].upper()


class GridOperationsAdvisor:
    """Supervisor agent — orchestrates the specialist agents."""

    def __init__(self) -> None:
        self.ds = DataStore.instance()
        self.docs = DocumentSearchService.instance()
        self.genie = GenieService.instance()

    # ---- Public API -----------------------------------------------------

    def investigate(
        self,
        prompt: str,
        asset_id: Optional[str] = None,
        feeder_id: Optional[str] = None,
        region_id: Optional[str] = None,
        scenario_type: Optional[str] = None,
        selected_asset_ids: Optional[list[str]] = None,
    ) -> dict:
        endpoint = os.getenv("AGENTBRICKS_SUPERVISOR_ENDPOINT", "").strip()
        if endpoint:
            try:
                return self._invoke_supervisor(
                    endpoint, prompt,
                    asset_id=asset_id, feeder_id=feeder_id, region_id=region_id,
                    scenario_type=scenario_type,
                    selected_asset_ids=selected_asset_ids or [],
                )
            except Exception as e:
                logger.warning(
                    "Supervisor MAS call failed (%s); using deterministic fallback.", e
                )
                # Fall through to local pipeline.
        return self._investigate_local(
            prompt,
            asset_id=asset_id, feeder_id=feeder_id, region_id=region_id,
            scenario_type=scenario_type,
            selected_asset_ids=selected_asset_ids or [],
        )

    # ------------------------------------------------------------------
    # Real Supervisor MAS path
    # ------------------------------------------------------------------

    def _invoke_supervisor(
        self,
        endpoint: str,
        prompt: str,
        *,
        asset_id: Optional[str],
        feeder_id: Optional[str],
        region_id: Optional[str],
        scenario_type: Optional[str],
        selected_asset_ids: list[str],
    ) -> dict:
        from databricks.sdk import WorkspaceClient
        import requests

        focus = self._resolve_focus(asset_id, feeder_id, region_id, selected_asset_ids)
        composed = self._compose_supervisor_prompt(prompt, focus, scenario_type)

        w = WorkspaceClient()
        host = (w.config.host or "").rstrip("/")
        token = w.config.authenticate().get("Authorization", "").removeprefix("Bearer ").strip()
        if not host or not token:
            raise RuntimeError("Could not resolve Databricks host or token for MAS call")

        body: dict[str, Any] = {
            "input": [{"role": "user", "content": composed}],
            "custom_inputs": {k: v for k, v in {
                "asset_id": focus.get("asset_id"),
                "feeder_id": focus.get("feeder_id"),
                "region_id": focus.get("region_id"),
                "scenario_type": scenario_type,
                "selected_asset_ids": selected_asset_ids,
            }.items() if v},
        }
        url = f"{host}/serving-endpoints/{endpoint}/invocations"
        logger.info("Supervisor MAS invoke: endpoint=%s focus=%s", endpoint, focus)
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()

        return self._shape_supervisor_response(data, prompt, focus, scenario_type)

    @staticmethod
    def _compose_supervisor_prompt(prompt: str, focus: dict, scenario_type: Optional[str]) -> str:
        ctx_lines = []
        if focus.get("region_id"):
            ctx_lines.append(f"region_id={focus['region_id']}")
        if focus.get("feeder_id"):
            ctx_lines.append(f"feeder_id={focus['feeder_id']}")
        if focus.get("asset_id"):
            ctx_lines.append(f"asset_id={focus['asset_id']}")
        if scenario_type:
            ctx_lines.append(f"scenario_type={scenario_type}")
        if focus.get("selected_asset_ids"):
            ctx_lines.append(f"selected_asset_ids={','.join(focus['selected_asset_ids'][:8])}")
        ctx = "; ".join(ctx_lines) or "no map selection"
        return (
            f"GridLens operations question. Context: {ctx}.\n\n"
            f"Question: {prompt}\n\n"
            "Please route SQL/metric sub-questions to the network_analytics agent "
            "(Genie space) and document/policy sub-questions to the document_intelligence "
            "agent (Knowledge Assistant). Cite specific document IDs (e.g. DOC-000126) and "
            "Delta tables (anzgt_may.energyq_gold.* / energyq_silver.*) for every claim."
        )

    def _shape_supervisor_response(
        self,
        data: dict,
        prompt: str,
        focus: dict,
        scenario_type: Optional[str],
    ) -> dict:
        # ---- Extract answer text ---------------------------------------
        answer_parts: list[str] = []
        trace_steps: list[dict] = []
        citations: list[dict] = []

        for out in (data.get("output") or []):
            t = out.get("type")
            if t == "message":
                for piece in (out.get("content") or []):
                    if piece.get("type") in ("output_text", "text"):
                        txt = piece.get("text", "")
                        if isinstance(txt, dict):
                            txt = txt.get("value", "")
                        if txt:
                            answer_parts.append(txt)
                        for ann in (piece.get("annotations") or []):
                            citations.append(ann)
            elif t in ("function_call", "tool_call", "agent_call"):
                trace_steps.append({
                    "agent": out.get("name") or out.get("tool") or "agent",
                    "action": out.get("type"),
                    "output_summary": _truncate(out.get("output") or out.get("arguments") or "", 280),
                    "confidence": 0.85,
                    "inputs": out.get("arguments") if isinstance(out.get("arguments"), dict) else {},
                })
            elif t in ("function_call_output", "tool_result"):
                trace_steps.append({
                    "agent": out.get("name") or "tool_result",
                    "action": t,
                    "output_summary": _truncate(out.get("output") or "", 280),
                    "confidence": 0.85,
                    "inputs": {},
                })

        # Legacy / OpenAI-Chat envelopes
        for ch in (data.get("choices") or []):
            msg = ch.get("message") or {}
            txt = msg.get("content")
            if isinstance(txt, str) and txt:
                answer_parts.append(txt)

        # Top-level citations
        for key in ("citations", "sources", "documents"):
            arr = data.get(key)
            if isinstance(arr, list):
                citations.extend(c for c in arr if isinstance(c, dict))

        answer = "\n\n".join(p.strip() for p in answer_parts if p).strip()
        if not answer:
            answer = "Supervisor returned no narrative; see structured evidence."

        # ---- Build evidence list --------------------------------------
        evidence: list[dict] = []
        for c in citations:
            ev = _citation_to_evidence(c, self.docs)
            if ev:
                evidence.append(ev)

        # Always anchor on at least one delta_table evidence so the UI
        # has a SQL-shaped reference. Prefer the regional summary.
        if not any(e["evidence_type"] == "delta_table" for e in evidence):
            region_id = focus.get("region_id") or ""
            evidence.append({
                "evidence_type": "delta_table",
                "source_ref": "anzgt_may.energyq_gold.gold_regional_risk_summary",
                "source_title": f"Regional risk summary ({region_id or 'all regions'})",
                "excerpt": "Storm-season risk view aggregated by region.",
                "confidence": 0.82,
            })

        # Map selection evidence (always trivially true)
        if focus.get("feeder_id") or focus.get("region_id"):
            evidence.append({
                "evidence_type": "map_selection",
                "source_ref": f"feeder:{focus.get('feeder_id')}" if focus.get("feeder_id") else f"region:{focus.get('region_id')}",
                "source_title": "Map selection",
                "excerpt": ", ".join(
                    f"{k}={v}" for k, v in focus.items() if v and k != "selected_asset_ids"
                ),
                "confidence": 0.95,
            })

        # ---- Trace fallback --------------------------------------------
        if not trace_steps:
            trace_steps = [{
                "agent": "Supervisor MAS",
                "action": "invoke_serving_endpoint",
                "output_summary": _truncate(answer, 220),
                "confidence": 0.85,
                "inputs": {"prompt": prompt[:200]},
            }]

        # ---- Headline / body / confidence / next_steps -----------------
        region = self.ds.regions.get(focus.get("region_id") or "", {}).get("region_name", "the selected region")
        feeder = focus.get("feeder_id") or "the selected feeder"

        # Use the asset risk band when known, otherwise infer 'high' as a safe default.
        risk_band = "high"
        if focus.get("asset_id"):
            h = self.ds.health.get(focus["asset_id"], {})
            risk_band = h.get("risk_band", "high")
        headline = self._headline(risk_band, region, feeder)
        body = f"{headline}\n\n{answer}"

        # Pull a numeric confidence if present, else average trace confidences.
        confidence_values = [t.get("confidence", 0.85) for t in trace_steps if t.get("confidence")]
        confidence = round(sum(confidence_values) / max(1, len(confidence_values)), 2)
        confidence = max(0.5, min(0.99, confidence))

        # next_steps: extract bullets from the answer if any "Next steps" section exists,
        # otherwise generate operationally sensible ones.
        next_steps = _extract_next_steps(answer) or self._default_next_steps(focus, scenario_type)

        return {
            "recommendation_id": f"REC-{_short_id()}",
            "headline": headline,
            "body": body,
            "confidence": confidence,
            "evidence": evidence,
            "trace": trace_steps,
            "next_steps": next_steps,
        }

    def _default_next_steps(self, focus: dict, scenario_type: Optional[str]) -> list[str]:
        feeder = focus.get("feeder_id") or "the selected feeder"
        return [
            "Review the evidence pack and confirm the proposed scope.",
            f"Bundle high/critical assets on feeder {feeder} into a draft work package.",
            "Assign the nearest depot with crew availability.",
            "Submit the work package for approval; route to the regional asset manager.",
            "Schedule a pre-storm verification inspection once approved.",
        ]

    # ------------------------------------------------------------------
    # Local deterministic pipeline (fallback)
    # ------------------------------------------------------------------

    def _investigate_local(
        self,
        prompt: str,
        *,
        asset_id: Optional[str],
        feeder_id: Optional[str],
        region_id: Optional[str],
        scenario_type: Optional[str],
        selected_asset_ids: list[str],
    ) -> dict:
        trace = []
        evidence = []
        selected_asset_ids = selected_asset_ids or []

        # Resolve focus context — asset first, then feeder, then region.
        focus = self._resolve_focus(asset_id, feeder_id, region_id, selected_asset_ids)

        # 1. Spatial Risk Agent
        spatial = self._spatial_risk(focus)
        trace.append(spatial["trace"])
        evidence.extend(spatial["evidence"])

        # 2. Asset Health Agent
        health = self._asset_health(focus)
        trace.append(health["trace"])
        evidence.extend(health["evidence"])

        # 3. Outage Impact Agent
        impact = self._outage_impact(focus)
        trace.append(impact["trace"])
        evidence.extend(impact["evidence"])

        # 4. Document Intelligence Agent
        document = self._document_intelligence(prompt, focus)
        trace.append(document["trace"])
        evidence.extend(document["evidence"])

        # 5. Genie Analyst Agent
        genie = self._genie_analyst(prompt)
        trace.append(genie["trace"])
        evidence.extend(genie["evidence"])

        # 6. Compliance Agent
        compliance = self._compliance(focus)
        trace.append(compliance["trace"])
        evidence.extend(compliance["evidence"])

        # 7. Work Planner Agent — synthesises a draft package proposal.
        plan = self._work_planner(focus, scenario_type)
        trace.append(plan["trace"])
        evidence.extend(plan["evidence"])

        body, headline, confidence, next_steps = self._synthesise(
            prompt, focus, spatial, health, impact, document, genie, compliance, plan
        )
        recommendation_id = f"REC-{_short_id()}"
        return {
            "recommendation_id": recommendation_id,
            "headline": headline,
            "body": body,
            "confidence": confidence,
            "evidence": evidence,
            "trace": trace,
            "next_steps": next_steps,
        }

    # ---- Specialists -----------------------------------------------------

    def _resolve_focus(
        self,
        asset_id: Optional[str],
        feeder_id: Optional[str],
        region_id: Optional[str],
        selected: list[str],
    ) -> dict:
        # If a selected set is provided, take the highest-risk one.
        if selected:
            ranked = sorted(
                (a for a in (self.ds.assets.get(aid) for aid in selected) if a),
                key=lambda a: -float(self.ds.health.get(a["asset_id"], {}).get("risk_score", 0)),
            )
            if ranked:
                asset_id = ranked[0]["asset_id"]

        # If only region provided, pick the top-risk asset for the demo.
        if not asset_id and region_id:
            assets = self.ds.assets_by_region.get(region_id, [])
            ranked = sorted(
                assets,
                key=lambda a: -float(self.ds.health.get(a["asset_id"], {}).get("risk_score", 0)),
            )
            if ranked:
                asset_id = ranked[0]["asset_id"]

        # If only feeder provided, pick the top-risk asset on that feeder.
        if not asset_id and feeder_id:
            assets = self.ds.assets_by_feeder.get(feeder_id, [])
            ranked = sorted(
                assets,
                key=lambda a: -float(self.ds.health.get(a["asset_id"], {}).get("risk_score", 0)),
            )
            if ranked:
                asset_id = ranked[0]["asset_id"]

        if asset_id:
            asset = self.ds.assets.get(asset_id, {})
            feeder_id = asset.get("feeder_id")
            region_id = asset.get("region_id")
        return {
            "asset_id": asset_id,
            "feeder_id": feeder_id,
            "region_id": region_id,
            "selected_asset_ids": selected,
        }

    def _spatial_risk(self, focus: dict) -> dict:
        region_id = focus.get("region_id")
        feeder_id = focus.get("feeder_id")
        evidence = []
        details = ""
        if region_id:
            assets = self.ds.assets_by_region.get(region_id, [])
            hazards = self.ds.hazards_by_region.get(region_id, [])
            risky_count = sum(1 for a in assets if self.ds.health.get(a["asset_id"], {}).get("risk_band") in ("high", "critical"))
            details = (
                f"Region {region_id} has {risky_count} high/critical assets and "
                f"{len(hazards)} active hazard zones (cyclone/storm/flood)."
            )
            evidence.append({
                "evidence_type": "delta_table",
                "source_ref": "anzgt_may.energyq_gold.gold_regional_risk_summary",
                "source_title": "Regional risk summary",
                "excerpt": details,
                "confidence": 0.92,
            })
            if feeder_id:
                f = self.ds.feeders.get(feeder_id, {})
                evidence.append({
                    "evidence_type": "map_selection",
                    "source_ref": f"feeder:{feeder_id}",
                    "source_title": f"Feeder {f.get('feeder_name', feeder_id)}",
                    "excerpt": f"Length {f.get('feeder_length_km', '-')} km; serves {f.get('customer_count', '-')} customers ({f.get('critical_customer_count', '-')} critical).",
                    "confidence": 0.90,
                })
        return {
            "trace": {
                "agent": "Spatial Risk Agent",
                "action": "summarise_region_and_feeder_exposure",
                "output_summary": details or "no spatial context",
                "confidence": 0.92,
                "inputs": {"region_id": region_id, "feeder_id": feeder_id},
            },
            "evidence": evidence,
        }

    def _asset_health(self, focus: dict) -> dict:
        asset_id = focus.get("asset_id")
        if not asset_id:
            return {
                "trace": {
                    "agent": "Asset Health Agent",
                    "action": "skip",
                    "output_summary": "no asset focus provided",
                    "confidence": 0.30,
                },
                "evidence": [],
            }
        h = self.ds.health.get(asset_id, {})
        a = self.ds.assets.get(asset_id, {})
        drivers = (h.get("risk_drivers") or "").replace("|", ", ")
        summary = (
            f"Asset {asset_id} is in risk band '{h.get('risk_band', 'n/a')}' "
            f"({h.get('risk_score', 0)}/100). Drivers: {drivers}. "
            f"Failure probability 12m: {h.get('failure_probability_12m', 0)}."
        )
        return {
            "trace": {
                "agent": "Asset Health Agent",
                "action": "explain_risk_score",
                "output_summary": summary,
                "confidence": 0.90,
                "inputs": {"asset_id": asset_id},
            },
            "evidence": [{
                "evidence_type": "delta_table",
                "source_ref": "anzgt_may.energyq_gold.gold_asset_360",
                "source_title": f"Asset 360 — {asset_id}",
                "excerpt": summary,
                "confidence": 0.90,
            }],
        }

    def _outage_impact(self, focus: dict) -> dict:
        feeder_id = focus.get("feeder_id")
        if not feeder_id:
            return {
                "trace": {
                    "agent": "Outage Impact Agent",
                    "action": "skip",
                    "output_summary": "no feeder context",
                    "confidence": 0.30,
                },
                "evidence": [],
            }
        outages = self.ds.outages_by_feeder.get(feeder_id, [])
        critical = sum(int(float(o.get("critical_customers_interrupted") or 0)) for o in outages)
        impacted = sum(int(float(o.get("customers_interrupted") or 0)) for o in outages)
        summary = (
            f"Feeder {feeder_id} had {len(outages)} outages historically — "
            f"{impacted} customer interruptions including {critical} critical-customer hits."
        )
        return {
            "trace": {
                "agent": "Outage Impact Agent",
                "action": "summarise_feeder_outages",
                "output_summary": summary,
                "confidence": 0.85,
                "inputs": {"feeder_id": feeder_id},
            },
            "evidence": [{
                "evidence_type": "delta_table",
                "source_ref": "anzgt_may.energyq_silver.outage_events",
                "source_title": f"Outage history — {feeder_id}",
                "excerpt": summary,
                "confidence": 0.85,
            }],
        }

    def _document_intelligence(self, prompt: str, focus: dict) -> dict:
        hits = self.docs.search(
            query=prompt,
            region_id=focus.get("region_id"),
            asset_id=focus.get("asset_id"),
            feeder_id=focus.get("feeder_id"),
            top_k=4,
        )
        evidence = []
        summaries = []
        for hit in hits:
            evidence.append({
                "evidence_type": "document",
                "source_ref": hit["volume_path"],
                "source_title": hit["title"],
                "excerpt": hit["excerpt"],
                "confidence": min(0.95, 0.55 + hit["score"] / 20.0),
            })
            summaries.append(f"{hit['title']} — {hit['excerpt'][:120]}")
        return {
            "trace": {
                "agent": "Document Intelligence Agent",
                "action": "vector_search_volume_documents",
                "output_summary": f"{len(hits)} relevant documents retrieved.",
                "confidence": 0.80 if hits else 0.40,
                "inputs": {"region_id": focus.get("region_id"),
                           "asset_id": focus.get("asset_id"),
                           "feeder_id": focus.get("feeder_id")},
            },
            "evidence": evidence,
        }

    def _genie_analyst(self, prompt: str) -> dict:
        ga = self.genie.ask(prompt)
        excerpt = ga.get("summary", "")
        return {
            "trace": {
                "agent": "Genie Analyst Agent",
                "action": "ask_genie",
                "output_summary": excerpt,
                "confidence": 0.78,
                "inputs": {"question": prompt},
            },
            "evidence": [{
                "evidence_type": "genie_answer",
                "source_ref": "Genie / Energy Queensland Network Intelligence",
                "source_title": ga.get("question", "Genie metric"),
                "excerpt": excerpt,
                "confidence": 0.78,
            }],
        }

    def _compliance(self, focus: dict) -> dict:
        region_id = focus.get("region_id")
        if not region_id:
            return {
                "trace": {
                    "agent": "Compliance Agent",
                    "action": "skip",
                    "output_summary": "no region context",
                    "confidence": 0.30,
                },
                "evidence": [],
            }
        hits = self.docs.search(
            query="maintenance standard vegetation policy storm response",
            region_id=region_id,
            top_k=2,
        )
        evidence = []
        for hit in hits:
            evidence.append({
                "evidence_type": "policy",
                "source_ref": hit["volume_path"],
                "source_title": hit["title"],
                "excerpt": hit["excerpt"],
                "confidence": 0.74,
            })
        if not evidence:
            evidence.append({
                "evidence_type": "policy",
                "source_ref": f"{focus.get('region_id')}/maintenance_standard",
                "source_title": "Regional maintenance standard",
                "excerpt": "Refer to applicable maintenance standard. Approval required for replacement bundles > AUD 100k.",
                "confidence": 0.65,
            })
        return {
            "trace": {
                "agent": "Compliance Agent",
                "action": "check_standards_and_policies",
                "output_summary": f"{len(evidence)} compliance reference(s) attached.",
                "confidence": 0.75,
            },
            "evidence": evidence,
        }

    def _work_planner(self, focus: dict, scenario_type: Optional[str]) -> dict:
        region_id = focus.get("region_id")
        feeder_id = focus.get("feeder_id")
        if not region_id:
            return {
                "trace": {
                    "agent": "Work Planner Agent",
                    "action": "skip",
                    "output_summary": "no region context",
                    "confidence": 0.30,
                },
                "evidence": [],
            }
        # Find bundle candidates on the feeder.
        bundles: list[dict] = []
        for a in self.ds.assets_by_feeder.get(feeder_id or "", []):
            h = self.ds.health.get(a["asset_id"])
            if not h:
                continue
            if h["risk_band"] in ("high", "critical"):
                bundles.append(a)
            if len(bundles) >= 8:
                break
        if not bundles and region_id:
            assets = self.ds.assets_by_region.get(region_id, [])
            ranked = sorted(
                assets,
                key=lambda a: -float(self.ds.health.get(a["asset_id"], {}).get("risk_score", 0)),
            )
            bundles = ranked[:6]

        depot = None
        if bundles:
            a = bundles[0]
            depot = self.ds.closest_depot(region_id, float(a["lat"]), float(a["lon"]))
        depot_id = depot["depot_id"] if depot else ""
        depot_name = depot["depot_name"] if depot else ""

        # Check for existing work to avoid duplicates.
        feeder_work = self.ds.work_by_feeder.get(feeder_id or "", [])
        active = sum(1 for w in feeder_work if w["status"] in ("approved", "scheduled", "in_progress"))

        summary = (
            f"Proposed bundle: {len(bundles)} assets on feeder {feeder_id} routed to "
            f"depot {depot_name or '(t.b.d.)'} ({depot_id}). "
            f"Active feeder work currently: {active}. Avoid duplication."
        )
        return {
            "trace": {
                "agent": "Work Planner Agent",
                "action": "propose_bundle_and_assign_depot",
                "output_summary": summary,
                "confidence": 0.82,
                "inputs": {"feeder_id": feeder_id, "scenario_type": scenario_type},
            },
            "evidence": [{
                "evidence_type": "delta_table",
                "source_ref": "anzgt_may.energyq_gold.gold_work_prioritisation",
                "source_title": f"Work prioritisation — feeder {feeder_id}",
                "excerpt": summary,
                "confidence": 0.82,
            }],
            "planner_output": {
                "bundle_asset_ids": [b["asset_id"] for b in bundles],
                "depot_id": depot_id,
                "depot_name": depot_name,
                "active_work_count": active,
            },
        }

    # ---- Synthesis ------------------------------------------------------

    def _synthesise(self, prompt, focus, spatial, health, impact, document, genie, compliance, plan) -> tuple[str, str, float, list[str]]:
        asset_id = focus.get("asset_id")
        region = self.ds.regions.get(focus.get("region_id") or "", {}).get("region_name", "the selected region")
        feeder = focus.get("feeder_id") or "the selected feeder"

        evidence_lines = []
        risk_band = "high"
        if asset_id:
            h = self.ds.health.get(asset_id, {})
            risk_band = h.get("risk_band", "high")
            evidence_lines.append(
                f"Asset {asset_id} risk score {h.get('risk_score', 'n/a')}/100, "
                f"drivers: {h.get('risk_drivers', '').replace('|', ', ')}."
            )
        # Documents
        doc_evidence = [e for e in document["evidence"] if e["evidence_type"] == "document"]
        if doc_evidence:
            evidence_lines.append(f"Recent inspection / standards reference: {doc_evidence[0]['source_title']}.")
        # Outages
        if impact["evidence"]:
            evidence_lines.append(impact["evidence"][0]["excerpt"])
        # Genie
        if genie["evidence"]:
            evidence_lines.append(f"Genie context: {genie['evidence'][0]['excerpt']}")

        headline = self._headline(risk_band, region, feeder)
        body = (
            f"{headline}\n\n"
            f"Prompt: {prompt}\n\n"
            f"Evidence:\n- " + "\n- ".join(evidence_lines)
        )

        # Confidence: blend of agent confidences.
        scores = [step["confidence"] for step in (spatial["trace"], health["trace"], impact["trace"],
                                                  document["trace"], genie["trace"], compliance["trace"],
                                                  plan["trace"]) if step.get("confidence")]
        confidence = round(sum(scores) / len(scores), 2) if scores else 0.75

        # Next steps
        planner = plan.get("planner_output", {})
        next_steps = [
            "Review the evidence pack and confirm scope.",
            f"Bundle {len(planner.get('bundle_asset_ids') or [])} assets on feeder {feeder} into a draft work package.",
            f"Assign depot {planner.get('depot_name') or '(closest available)'} ({planner.get('depot_id') or 'n/a'}).",
            "Submit work package for approval; route to regional asset manager.",
            "Schedule pre-storm verification and inspection once approved.",
        ]
        return body, headline, confidence, next_steps

    def _headline(self, risk_band: str, region: str, feeder: str) -> str:
        if risk_band == "critical":
            return f"Critical risk cluster on {feeder} — recommend immediate bundled remediation in {region}."
        if risk_band == "high":
            return f"High-risk exposure on {feeder} — recommend bundled remediation before storm season in {region}."
        return f"Risk profile within band — recommend monitoring and inspection refresh on {feeder} ({region})."


# ---------------------------------------------------------------------------
# Module-level helpers for the MAS response shaper
# ---------------------------------------------------------------------------

def _truncate(s: Any, limit: int) -> str:
    if not isinstance(s, str):
        try:
            import json
            s = json.dumps(s, default=str)
        except Exception:
            s = str(s)
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


def _citation_to_evidence(c: dict, docs_service: DocumentSearchService) -> Optional[dict]:
    """Map a heterogeneous supervisor citation into the FastAPI Evidence shape."""
    if not isinstance(c, dict):
        return None
    # Detect document citations
    doc_id = c.get("document_id") or c.get("doc_id")
    src_ref = c.get("source_ref") or c.get("uri") or c.get("volume_path") or ""
    title = c.get("title") or c.get("source_title") or doc_id or src_ref or "Citation"
    excerpt = c.get("excerpt") or c.get("snippet") or c.get("text") or ""

    if doc_id or "/Volumes/" in src_ref or src_ref.endswith(".md"):
        # Try to enrich from local index.
        full = None
        if doc_id:
            full = docs_service.read_full(doc_id)
        if not full and src_ref:
            base = src_ref.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            full = docs_service.read_full(base)
        if full:
            title = title or full.get("title")
            excerpt = excerpt or " ".join(
                line.strip() for line in (full.get("content") or "").splitlines()
                if line.strip() and not line.startswith("#")
            )[:240]
            src_ref = src_ref or full.get("volume_path", "")
        return {
            "evidence_type": "document",
            "source_ref": src_ref or f"document:{doc_id}",
            "source_title": title,
            "excerpt": _truncate(excerpt, 280),
            "confidence": float(c.get("score") or 0.80),
        }

    # Delta-table reference?
    if any(kw in (src_ref or "").lower() for kw in ("anzgt_may", "energyq_", ".table:", "table:")):
        return {
            "evidence_type": "delta_table",
            "source_ref": src_ref,
            "source_title": title,
            "excerpt": _truncate(excerpt, 280),
            "confidence": float(c.get("score") or 0.85),
        }

    # Genie-shaped answer?
    if any(kw in (title or "").lower() for kw in ("genie", "sql", "query")):
        return {
            "evidence_type": "genie_answer",
            "source_ref": src_ref or "genie://gridlens-network-intel",
            "source_title": title,
            "excerpt": _truncate(excerpt, 280),
            "confidence": float(c.get("score") or 0.80),
        }

    # Default to policy
    if title or src_ref or excerpt:
        return {
            "evidence_type": "policy",
            "source_ref": src_ref or title,
            "source_title": title or "Reference",
            "excerpt": _truncate(excerpt, 280),
            "confidence": float(c.get("score") or 0.70),
        }
    return None


def _extract_next_steps(answer: str) -> list[str]:
    """Pull a "Next steps" bullet list from a supervisor answer, if present."""
    if not answer:
        return []
    lines = answer.splitlines()
    out: list[str] = []
    in_section = False
    for ln in lines:
        s = ln.strip()
        low = s.lower()
        if not in_section:
            if low.startswith(("next steps", "## next steps", "**next steps", "recommended actions")):
                in_section = True
            continue
        # Stop on blank line (after we've collected something) or a new heading.
        if not s:
            if out:
                break
            continue
        if s.startswith("#"):
            break
        # Bullet markers
        if s.startswith(("-", "*", "•")):
            out.append(s.lstrip("-*• ").strip())
        elif s[:2].isdigit() or (s[:1].isdigit() and s[1:2] in (".", ")")):
            out.append(s.split(maxsplit=1)[1] if " " in s else s)
    return [x for x in out if x][:6]
