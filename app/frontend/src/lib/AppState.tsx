import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { api } from './api';
import type { Region, ScenarioId } from '../types';

type LayerId =
  | 'assets'
  | 'feeders'
  | 'substations'
  | 'outages'
  | 'vegetation'
  | 'hazards'
  | 'critical_customers'
  | 'depots'
  | 'mobile_gen'
  | 'planned_works';

interface AppStateValue {
  regions: Region[];
  selectedRegion: string | null;
  setSelectedRegion: (id: string | null) => void;
  scenario: ScenarioId;
  setScenario: (s: ScenarioId) => void;
  layers: Record<LayerId, boolean>;
  toggleLayer: (id: LayerId) => void;
  selectedAssetId: string | null;
  setSelectedAssetId: (id: string | null) => void;
  lastAgentRecommendationId: string | null;
  setLastAgentRecommendationId: (id: string | null) => void;
}

const Ctx = createContext<AppStateValue | null>(null);

const DEFAULT_LAYERS: Record<LayerId, boolean> = {
  assets: true,
  feeders: false,
  substations: true,
  outages: false,
  vegetation: false,
  hazards: true,
  critical_customers: true,
  depots: true,
  mobile_gen: false,
  planned_works: false,
};

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [regions, setRegions] = useState<Region[]>([]);
  const [selectedRegion, setSelectedRegion] = useState<string | null>(null);
  const [scenario, setScenario] = useState<ScenarioId>('storm_readiness');
  const [layers, setLayers] = useState<Record<LayerId, boolean>>(DEFAULT_LAYERS);
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null);
  const [lastAgentRecommendationId, setLastAgentRecommendationId] = useState<string | null>(null);

  useEffect(() => {
    api.regions().then(setRegions).catch(() => setRegions([]));
  }, []);

  const value = useMemo<AppStateValue>(
    () => ({
      regions,
      selectedRegion,
      setSelectedRegion,
      scenario,
      setScenario,
      layers,
      toggleLayer: (id) => setLayers((prev) => ({ ...prev, [id]: !prev[id] })),
      selectedAssetId,
      setSelectedAssetId,
      lastAgentRecommendationId,
      setLastAgentRecommendationId,
    }),
    [regions, selectedRegion, scenario, layers, selectedAssetId, lastAgentRecommendationId],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAppState() {
  const v = useContext(Ctx);
  if (!v) throw new Error('useAppState used outside provider');
  return v;
}

export type { LayerId };
