import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Layers,
  CloudLightning,
  Wrench,
  Trees,
  ShieldAlert,
  Building2,
  Truck,
  Activity,
  ChevronRight,
  ChevronUp,
  Search,
  Loader2,
  Sparkles,
  PanelRightClose,
  PanelRightOpen,
  Info,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { MapView } from '../components/MapView';
import type { MapStyleId } from '../components/MapboxMapView';
import { useAppState, type LayerId } from '../lib/AppState';
import { api } from '../lib/api';
import type { MapBundle, ScenarioId } from '../types';

const MAP_STYLE_OPTIONS: { id: MapStyleId; label: string }[] = [
  { id: 'satellite_streets', label: 'Satellite + roads' },
  { id: 'satellite', label: 'Satellite' },
  { id: 'streets', label: 'Streets' },
  { id: 'outdoors', label: 'Outdoors' },
  { id: 'light', label: 'Light' },
  { id: 'dark', label: 'Dark' },
];

const SCENARIOS: { id: ScenarioId; label: string; description: string }[] = [
  { id: 'normal', label: 'Normal operations', description: 'Baseline assets, hazards, depots.' },
  { id: 'storm_readiness', label: 'Storm readiness', description: 'Pre-storm-season high-risk clusters.' },
  { id: 'vegetation_program', label: 'Vegetation program', description: 'Treatment backlog and risky spans.' },
  { id: 'reliability_improvement', label: 'Reliability improvement', description: 'Repeated outage feeders.' },
  { id: 'capex_prioritisation', label: 'Capex prioritisation', description: 'Replacement candidates.' },
  { id: 'field_inspection_review', label: 'Field inspection review', description: 'Stale inspections, access risk.' },
];

const LAYER_DEFS: { id: LayerId; label: string; Icon: typeof Layers }[] = [
  { id: 'assets', label: 'Assets', Icon: Activity },
  { id: 'hazards', label: 'Hazard zones', Icon: CloudLightning },
  { id: 'critical_customers', label: 'Critical customers', Icon: ShieldAlert },
  { id: 'depots', label: 'Depots', Icon: Building2 },
  { id: 'mobile_gen', label: 'Mobile generation', Icon: Truck },
  { id: 'planned_works', label: 'Planned works', Icon: Wrench },
  { id: 'vegetation', label: 'Vegetation risk', Icon: Trees },
];

const RISK_COLOURS: Record<string, string> = {
  low: '#2FB344',
  medium: '#18D4FF',
  high: '#FFB020',
  critical: '#E5484D',
};

export function CommandMapPage() {
  const nav = useNavigate();
  const { regions, selectedRegion, setSelectedRegion, scenario, setScenario, layers, toggleLayer, setSelectedAssetId, selectedAssetId } =
    useAppState();

  const [bundle, setBundle] = useState<MapBundle | null>(null);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [rightCollapsed, setRightCollapsed] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    return window.localStorage.getItem('gridlens.rightCollapsed') === '1';
  });
  const [mapStyleId, setMapStyleId] = useState<MapStyleId>(() => {
    if (typeof window === 'undefined') return 'satellite_streets';
    const saved = window.localStorage.getItem('gridlens.mapStyle');
    const valid = MAP_STYLE_OPTIONS.some((o) => o.id === saved);
    return valid ? (saved as MapStyleId) : 'satellite_streets';
  });

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem('gridlens.rightCollapsed', rightCollapsed ? '1' : '0');
  }, [rightCollapsed]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem('gridlens.mapStyle', mapStyleId);
  }, [mapStyleId]);

  const centerLat = useMemo(() => regions.find((r) => r.region_id === selectedRegion)?.centre_lat ?? null, [regions, selectedRegion]);
  const centerLon = useMemo(() => regions.find((r) => r.region_id === selectedRegion)?.centre_lon ?? null, [regions, selectedRegion]);

  const load = useCallback(() => {
    setLoading(true);
    api
      .mapBundle({ region: selectedRegion, scenario, asset_limit: 5000 })
      .then((b) => setBundle(b))
      .catch(() => setBundle(null))
      .finally(() => setLoading(false));
  }, [selectedRegion, scenario]);

  useEffect(() => {
    load();
  }, [load]);

  const topRecommendation = useMemo(() => {
    if (!bundle) return null;
    const critical = bundle.assets.find((a) => a.risk_band === 'critical');
    const high = bundle.assets.find((a) => a.risk_band === 'high');
    const focus = critical ?? high;
    if (!focus) return null;
    return {
      asset_id: focus.asset_id,
      feeder_id: focus.feeder_id,
      reason:
        focus.risk_band === 'critical'
          ? 'Top critical asset on a risky feeder — bundle for pre-storm remediation.'
          : 'Top high-risk asset — review with AI investigation.',
    };
  }, [bundle]);

  return (
    <div
      className="h-full grid transition-[grid-template-columns] duration-300 ease-out"
      style={{
        gridTemplateColumns: rightCollapsed
          ? '18rem minmax(0,1fr) 2.5rem'
          : '18rem minmax(0,1fr) 22rem',
      }}
    >
      {/* Left rail: layers + scenarios + search */}
      <div className="border-r border-border/40 overflow-y-auto px-4 py-4 space-y-5">
        <div>
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-[11px] font-semibold tracking-wider uppercase text-muted">Region</h3>
            {selectedRegion && (
              <button onClick={() => setSelectedRegion(null)} className="text-[11px] text-electric-cyan hover:underline">
                Clear
              </button>
            )}
          </div>
          <select
            className="w-full bg-panel-soft border border-border/50 rounded-md text-sm px-3 py-2 outline-none focus:border-electric-cyan/60"
            value={selectedRegion ?? ''}
            onChange={(e) => setSelectedRegion(e.target.value || null)}
          >
            <option value="">All Queensland regions</option>
            {regions.map((r) => (
              <option key={r.region_id} value={r.region_id}>
                {r.region_name}
              </option>
            ))}
          </select>
        </div>

        <div>
          <h3 className="text-[11px] font-semibold tracking-wider uppercase text-muted mb-2">Scenario</h3>
          <div className="space-y-1.5">
            {SCENARIOS.map((s) => (
              <button
                key={s.id}
                onClick={() => setScenario(s.id)}
                className={`w-full text-left rounded-md border px-3 py-2 transition-colors ${
                  scenario === s.id
                    ? 'border-electric-cyan/70 bg-electric-cyan/10 text-text-primary'
                    : 'border-border/40 bg-panel-soft/60 text-text-secondary hover:border-electric-cyan/30 hover:text-text-primary'
                }`}
              >
                <div className="text-sm font-medium">{s.label}</div>
                <div className="text-[11px] mt-0.5 text-muted leading-relaxed">{s.description}</div>
              </button>
            ))}
          </div>
        </div>

        <div>
          <h3 className="text-[11px] font-semibold tracking-wider uppercase text-muted mb-2">Layers</h3>
          <div className="space-y-1">
            {LAYER_DEFS.map(({ id, label, Icon }) => (
              <label
                key={id}
                className="flex items-center justify-between gap-2 px-2 py-1.5 rounded-md row-hover cursor-pointer"
              >
                <span className="flex items-center gap-2 text-sm">
                  <Icon className="w-3.5 h-3.5 text-muted" />
                  {label}
                </span>
                <input
                  type="checkbox"
                  checked={layers[id]}
                  onChange={() => toggleLayer(id)}
                  className="accent-electric-cyan"
                />
              </label>
            ))}
          </div>
        </div>

        <div>
          <h3 className="text-[11px] font-semibold tracking-wider uppercase text-muted mb-2">Risk legend</h3>
          <div className="space-y-1 px-1">
            {(['critical', 'high', 'medium', 'low'] as const).map((b) => (
              <div key={b} className="flex items-center gap-2 text-xs text-text-secondary">
                <span className="inline-block w-2.5 h-2.5 rounded-full" style={{ backgroundColor: RISK_COLOURS[b] }} />
                <span className="uppercase tracking-wider text-[11px]">{b}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Center: map */}
      <div className="relative">
        <MapView
          bundle={bundle}
          centerLat={centerLat}
          centerLon={centerLon}
          zoom={selectedRegion ? 7.5 : undefined}
          onAssetClick={(a) => setSelectedAssetId(a.asset_id)}
          mapStyle={mapStyleId}
        />

        {/* Map search overlay */}
        <div className="absolute top-4 left-4 right-4 flex items-center gap-2 pointer-events-none">
          <div className="panel px-3 py-2 flex items-center gap-2 pointer-events-auto w-80">
            <Search className="w-4 h-4 text-muted" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && search.startsWith('AST-')) {
                  nav(`/assets/${search.trim()}`);
                }
              }}
              placeholder="Search asset id (e.g. AST-MKY-POL-000482)"
              className="flex-1 bg-transparent outline-none text-sm text-text-primary placeholder:text-muted"
            />
          </div>
          <div className="ml-auto flex items-center gap-2 pointer-events-auto">
            {loading && (
              <div className="panel px-3 py-2 text-xs text-muted flex items-center gap-2">
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                Loading map bundle…
              </div>
            )}
            <div className="panel px-2.5 py-1.5 flex items-center gap-1.5 text-xs text-muted">
              <Layers className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Style</span>
              <select
                aria-label="Map style"
                value={mapStyleId}
                onChange={(e) => setMapStyleId(e.target.value as MapStyleId)}
                className="bg-transparent text-text-primary text-xs outline-none cursor-pointer pr-1"
              >
                {MAP_STYLE_OPTIONS.map((o) => (
                  <option key={o.id} value={o.id} className="bg-panel text-text-primary">
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
            <button
              className="btn-secondary"
              onClick={load}
              disabled={loading}
            >
              <Layers className="w-3.5 h-3.5" />
              Refresh
            </button>
          </div>
        </div>

        <ScenarioPill bundle={bundle} scenario={scenario} loading={loading} />
      </div>

      {/* Right: stats + recommendation (collapsible) */}
      {rightCollapsed ? (
        <button
          onClick={() => setRightCollapsed(false)}
          className="border-l border-border/40 bg-panel/60 hover:bg-panel transition-colors flex flex-col items-center justify-start py-3 text-muted hover:text-text-primary group"
          title="Expand right panel"
          aria-label="Expand right panel"
        >
          <PanelRightOpen className="w-4 h-4" />
          <div className="mt-3 text-[10px] tracking-[0.18em] uppercase [writing-mode:vertical-rl] rotate-180">
            Insights
          </div>
          {bundle && (bundle.critical_asset_count > 0 || bundle.high_risk_asset_count > 0) && (
            <div className="mt-3 flex flex-col items-center gap-1.5">
              {bundle.critical_asset_count > 0 && (
                <span
                  className="text-[10px] font-semibold rounded-md px-1.5 py-0.5"
                  style={{ color: '#E5484D', backgroundColor: 'rgba(229,72,77,0.10)' }}
                  title={`${bundle.critical_asset_count} critical assets`}
                >
                  {bundle.critical_asset_count}
                </span>
              )}
              {bundle.high_risk_asset_count > 0 && (
                <span
                  className="text-[10px] font-semibold rounded-md px-1.5 py-0.5"
                  style={{ color: '#FFB020', backgroundColor: 'rgba(255,176,32,0.10)' }}
                  title={`${bundle.high_risk_asset_count} high-risk assets`}
                >
                  {bundle.high_risk_asset_count}
                </span>
              )}
            </div>
          )}
        </button>
      ) : (
        <div className="border-l border-border/40 overflow-y-auto px-4 py-4 space-y-4 relative">
          <button
            onClick={() => setRightCollapsed(true)}
            className="absolute top-3 right-3 p-1 rounded-md text-muted hover:text-text-primary hover:bg-panel-soft/80 transition-colors"
            title="Collapse right panel"
            aria-label="Collapse right panel"
          >
            <PanelRightClose className="w-4 h-4" />
          </button>

          <div className="grid grid-cols-2 gap-3 pr-7">
            <Kpi label="Assets visible" value={bundle?.assets.length ?? 0} />
            <Kpi label="Feeders" value={bundle?.feeders_count ?? 0} />
            <Kpi
              label="High risk"
              value={bundle?.high_risk_asset_count ?? 0}
              accent="#FFB020"
            />
            <Kpi
              label="Critical"
              value={bundle?.critical_asset_count ?? 0}
              accent="#E5484D"
            />
            <Kpi
              label="Critical customers"
              value={bundle?.critical_customers.length ?? 0}
              accent="#FFB020"
            />
            <Kpi
              label="Customers exposed"
              value={bundle?.customers_exposed ?? 0}
            />
          </div>

          <div className="panel p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-[11px] font-semibold tracking-wider uppercase text-muted">Top recommendation</h3>
              <Sparkles className="w-3.5 h-3.5 text-electric-cyan" />
            </div>
            {topRecommendation ? (
              <div className="space-y-3">
                <div className="text-sm leading-relaxed">{topRecommendation.reason}</div>
                <div className="text-xs text-muted">
                  Focus asset:{' '}
                  <span className="font-mono text-text-primary">{topRecommendation.asset_id}</span>
                </div>
                <div className="flex gap-2 pt-1">
                  <button
                    className="btn-secondary text-xs"
                    onClick={() => nav(`/assets/${topRecommendation.asset_id}`)}
                  >
                    Open Asset 360 <ChevronRight className="w-3 h-3" />
                  </button>
                  <button
                    className="btn-primary text-xs"
                    onClick={() => nav('/ai-investigation')}
                  >
                    Ask AI <Sparkles className="w-3 h-3" />
                  </button>
                </div>
              </div>
            ) : (
              <div className="text-sm text-muted">No high-risk assets in current view.</div>
            )}
          </div>

          {selectedAssetId && (
            <div className="panel p-4">
              <h3 className="text-[11px] font-semibold tracking-wider uppercase text-muted mb-2">Selected asset</h3>
              <div className="font-mono text-sm">{selectedAssetId}</div>
              <button
                className="btn-secondary text-xs mt-3"
                onClick={() => nav(`/assets/${selectedAssetId}`)}
              >
                Open Asset 360 <ChevronRight className="w-3 h-3" />
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Kpi({ label, value, accent }: { label: string; value: number | string; accent?: string }) {
  return (
    <div className="kpi">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value" style={accent ? { color: accent } : undefined}>
        {typeof value === 'number' ? value.toLocaleString() : value}
      </div>
    </div>
  );
}

/**
 * Compact scenario status pill. Sits in the bottom-left corner above the
 * Mapbox logo. Defaults to a one-line chip showing scenario name + the most
 * relevant counts; clicking expands a popover with the full narrative and
 * every count chip (incl. PostGIS-derived ones).
 */
function ScenarioPill({
  bundle,
  scenario,
  loading,
}: {
  bundle: MapBundle | null;
  scenario: ScenarioId;
  loading: boolean;
}) {
  const [open, setOpen] = useState(false);
  const summary = bundle?.scenario_summary;
  const fallback = SCENARIOS.find((s) => s.id === scenario);
  const headline = summary?.headline ?? fallback?.label ?? 'Scenario';
  const accent = summary?.accent_color ?? '#18D4FF';
  const counts = summary?.counts;

  // Pick the 2 most representative count chips per scenario so the pill stays
  // one line. The full set is in the expanded popover.
  const primaryChips: { label: string; value: number; color?: string }[] = [];
  if (counts) {
    primaryChips.push({ label: 'assets', value: counts.assets_shown });
    if (counts.hazards_shown > 0) {
      primaryChips.push({ label: 'hazards', value: counts.hazards_shown, color: '#7C3AED' });
    }
    if (counts.vegetation_lines > 0) {
      primaryChips.push({ label: 'veg spans', value: counts.vegetation_lines, color: '#2FB344' });
    }
    if (counts.outage_lines > 0) {
      primaryChips.push({ label: 'outage feeders', value: counts.outage_lines, color: '#E5484D' });
    }
    if (counts.risk_extrusions > 0) {
      primaryChips.push({ label: 'risk bars', value: counts.risk_extrusions, color: '#FFB020' });
    }
    if ((counts.inspection_stale ?? 0) > 0) {
      primaryChips.push({
        label: 'stale inspections',
        value: counts.inspection_stale!,
        color: '#FFB020',
      });
    }
  }

  return (
    <div className="absolute bottom-3 left-28 pointer-events-none z-10">
      <div className="pointer-events-auto relative">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="panel pl-2.5 pr-2 py-1.5 flex items-center gap-2 text-xs hover:bg-panel-soft/70 transition-colors"
          aria-expanded={open}
          aria-label="Scenario details"
        >
          <span
            className="inline-block w-1.5 h-1.5 rounded-full animate-pulse"
            style={{ backgroundColor: accent }}
          />
          <span className="font-medium text-text-primary whitespace-nowrap">{headline}</span>
          {loading && (
            <Loader2 className="w-3 h-3 animate-spin text-muted" />
          )}
          {!loading && primaryChips.slice(0, 4).map((c, i) => (
            <span key={i} className="text-muted whitespace-nowrap">
              <span className="opacity-50 mx-1">·</span>
              <span style={c.color ? { color: c.color } : undefined}>
                {c.value.toLocaleString()}
              </span>{' '}
              {c.label}
            </span>
          ))}
          <ChevronUp
            className={`w-3 h-3 text-muted transition-transform ${open ? '' : 'rotate-180'}`}
          />
        </button>
        {open && summary && (
          <div className="panel absolute bottom-full mb-2 left-0 w-80 p-3 shadow-xl shadow-black/40">
            <div className="flex items-start gap-2 mb-2">
              <Info className="w-3.5 h-3.5 mt-0.5 shrink-0" style={{ color: accent }} />
              <div>
                <div className="text-sm font-medium text-text-primary">{headline}</div>
                <div className="text-[11px] text-muted leading-snug mt-0.5">
                  {summary.narrative}
                </div>
              </div>
            </div>
            <div className="flex flex-wrap gap-1.5 mt-2">
              <Chip label="assets" value={summary.counts.assets_shown} />
              {summary.counts.hazards_shown > 0 && (
                <Chip label="hazards" value={summary.counts.hazards_shown} color="#7C3AED" />
              )}
              {(summary.counts.critical_customers ?? 0) > 0 && (
                <Chip
                  label="critical customers"
                  value={summary.counts.critical_customers!}
                  color="#FFB020"
                />
              )}
              {summary.counts.vegetation_lines > 0 && (
                <Chip
                  label="veg spans"
                  value={summary.counts.vegetation_lines}
                  color="#2FB344"
                />
              )}
              {summary.counts.outage_lines > 0 && (
                <Chip
                  label="outage feeders"
                  value={summary.counts.outage_lines}
                  color="#E5484D"
                />
              )}
              {summary.counts.risk_extrusions > 0 && (
                <Chip
                  label="3D risk bars"
                  value={summary.counts.risk_extrusions}
                  color="#FFB020"
                />
              )}
              {(summary.counts.inspection_stale ?? 0) > 0 && (
                <Chip
                  label="stale inspections"
                  value={summary.counts.inspection_stale!}
                  color="#FFB020"
                  title="Assets with last inspection >24 months and elevated access difficulty"
                />
              )}
              {(summary.counts.postgis_impact_assets ?? 0) > 0 && (
                <Chip
                  label="PostGIS impact"
                  value={summary.counts.postgis_impact_assets!}
                  color="#E5478A"
                  title="Assets within 20km of severe hazards (PostGIS ST_DWithin on Lakebase)"
                />
              )}
              {(summary.counts.postgis_hazard_polygons ?? 0) > 0 && (
                <Chip
                  label="PostGIS polygons"
                  value={summary.counts.postgis_hazard_polygons!}
                  color="#A26FF7"
                  title="Buffered hazard geographies served by Lakebase PostGIS"
                />
              )}
            </div>
            {summary.primary_layers.length > 0 && (
              <div className="text-[10px] text-muted/80 mt-2 leading-snug">
                Primary layers: {summary.primary_layers.join(' · ').replace(/_/g, ' ')}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function Chip({
  label,
  value,
  color,
  title,
}: {
  label: string;
  value: number;
  color?: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      className="inline-flex items-center gap-1 text-[10px] rounded-full px-2 py-0.5 border border-border/40 bg-panel-soft/40"
      style={color ? { color, borderColor: `${color}33` } : undefined}
    >
      <span className="font-medium">{value.toLocaleString()}</span>
      <span className="opacity-70">{label}</span>
    </span>
  );
}
