/* eslint-disable @typescript-eslint/no-explicit-any */
import type {
  Region,
  MapBundle,
  AssetDetail,
  AssetDocument,
  RegionalSummary,
  WorkPackage,
  AgentResponse,
  GenieAnswer,
  ExecutiveBriefing,
  ScenarioId,
} from '../types';

const BASE = '/api';

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'content-type': 'application/json' },
    ...init,
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // ignore
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export const api = {
  regions: () => http<Region[]>('/regions'),
  scenarios: () => http<{ built_in: any[]; saved: any[] }>('/scenarios'),
  mapBundle: (params: {
    region?: string | null;
    scenario?: ScenarioId | null;
    risk_band?: string | null;
    asset_type?: string | null;
    asset_limit?: number;
  }) => {
    const q = new URLSearchParams();
    if (params.region) q.set('region', params.region);
    if (params.scenario) q.set('scenario', params.scenario);
    if (params.risk_band) q.set('risk_band', params.risk_band);
    if (params.asset_type) q.set('asset_type', params.asset_type);
    if (params.asset_limit) q.set('asset_limit', String(params.asset_limit));
    return http<MapBundle>(`/map/bundle?${q.toString()}`);
  },
  asset: (assetId: string) => http<AssetDetail>(`/assets/${encodeURIComponent(assetId)}`),
  assetInspections: (assetId: string) =>
    http<any[]>(`/assets/${encodeURIComponent(assetId)}/inspections`),
  assetDefects: (assetId: string) =>
    http<any[]>(`/assets/${encodeURIComponent(assetId)}/defects`),
  assetOutages: (assetId: string) =>
    http<any[]>(`/assets/${encodeURIComponent(assetId)}/outages`),
  assetWorkOrders: (assetId: string) =>
    http<any[]>(`/assets/${encodeURIComponent(assetId)}/work-orders`),
  assetDocuments: (assetId: string) =>
    http<AssetDocument[]>(`/assets/${encodeURIComponent(assetId)}/documents`),
  regionalRisk: () => http<RegionalSummary[]>('/regional-risk'),
  workPackages: () => http<WorkPackage[]>('/work-packages'),
  workPackage: (id: string) => http<WorkPackage>(`/work-packages/${encodeURIComponent(id)}`),
  createWorkPackage: (body: any) =>
    http<WorkPackage>('/work-packages', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  patchWorkPackage: (id: string, body: any) =>
    http<WorkPackage>(`/work-packages/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  agentInvestigate: (body: {
    prompt: string;
    asset_id?: string;
    feeder_id?: string;
    region_id?: string;
    scenario_type?: string;
    selected_asset_ids?: string[];
  }) =>
    http<AgentResponse>('/agent/investigate', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  agentCreateWorkPackage: (body: {
    recommendation_id: string;
    title?: string;
    priority: string;
    region_id: string;
    feeder_id?: string;
    asset_ids: string[];
  }) =>
    http<WorkPackage>('/agent/create-work-package', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  genieAsk: (question: string) =>
    http<GenieAnswer>('/genie/ask', {
      method: 'POST',
      body: JSON.stringify({ question }),
    }),
  genieSuggested: () => http<string[]>('/genie/suggested-questions'),
  executiveBriefing: (region?: string | null) => {
    const q = region ? `?region=${encodeURIComponent(region)}` : '';
    return http<ExecutiveBriefing>(`/executive-briefing${q}`);
  },
};
