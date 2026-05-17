import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  AlertTriangle,
  FileText,
  Wrench,
  CloudLightning,
  Trees,
  ShieldAlert,
  Sparkles,
  ChevronRight,
} from 'lucide-react';
import { api } from '../lib/api';
import type { AssetDetail, AssetDocument } from '../types';
import { RiskPill } from '../components/RiskPill';
import { useAppState } from '../lib/AppState';

export function AssetDetailPage() {
  const { assetId = '' } = useParams<{ assetId: string }>();
  const nav = useNavigate();
  const { setSelectedAssetId } = useAppState();
  const [asset, setAsset] = useState<AssetDetail | null>(null);
  const [docs, setDocs] = useState<AssetDocument[]>([]);
  const [defects, setDefects] = useState<any[]>([]);
  const [inspections, setInspections] = useState<any[]>([]);
  const [outages, setOutages] = useState<any[]>([]);
  const [workOrders, setWorkOrders] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!assetId) return;
    setSelectedAssetId(assetId);
    setLoading(true);
    setError(null);
    Promise.all([
      api.asset(assetId),
      api.assetDocuments(assetId),
      api.assetDefects(assetId),
      api.assetInspections(assetId),
      api.assetOutages(assetId),
      api.assetWorkOrders(assetId),
    ])
      .then(([a, d, df, ins, out, wo]) => {
        setAsset(a);
        setDocs(d);
        setDefects(df);
        setInspections(ins);
        setOutages(out);
        setWorkOrders(wo);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [assetId, setSelectedAssetId]);

  if (loading) return <Loading />;
  if (error || !asset) return <ErrorState message={error ?? 'Asset not found'} />;

  return (
    <div className="h-full overflow-y-auto px-8 py-6 space-y-6">
      <div className="flex items-center gap-3 text-sm text-muted">
        <button onClick={() => nav('/command-map')} className="btn-ghost text-xs">
          <ArrowLeft className="w-3.5 h-3.5" />
          Back to map
        </button>
        <span>/</span>
        <span>{asset.region_name}</span>
        <span>/</span>
        <span>{asset.feeder_name}</span>
        <span>/</span>
        <span className="text-text-primary">{asset.asset_id}</span>
      </div>

      <div className="grid grid-cols-12 gap-6">
        <div className="col-span-8 space-y-6">
          {/* Header */}
          <div className="panel p-6">
            <div className="flex items-start justify-between gap-6">
              <div>
                <div className="flex items-center gap-3 mb-1">
                  <h1 className="text-2xl font-semibold tracking-tight">{asset.asset_name}</h1>
                  <RiskPill band={asset.risk_band} />
                </div>
                <div className="text-sm text-muted">
                  {asset.asset_type.toUpperCase()} · {asset.voltage_kv} kV · installed {asset.install_year} ·{' '}
                  {asset.manufacturer} · {asset.material}
                </div>
                <div className="text-xs text-muted mt-3">
                  Feeder <span className="text-text-primary font-mono">{asset.feeder_id}</span> · Substation{' '}
                  <span className="text-text-primary">{asset.substation_name}</span>
                </div>
              </div>
              <div className="flex gap-2">
                <button className="btn-secondary text-xs" onClick={() => nav('/ai-investigation', { state: { asset_id: asset.asset_id, region_id: asset.region_id, feeder_id: asset.feeder_id } })}>
                  <Sparkles className="w-3.5 h-3.5" />
                  Ask AI about this asset
                </button>
                <button
                  className="btn-primary text-xs"
                  onClick={async () => {
                    const wp = await api.createWorkPackage({
                      title: `Asset 360 — ${asset.asset_id}`,
                      region_id: asset.region_id,
                      feeder_id: asset.feeder_id,
                      scenario_type: 'storm_readiness',
                      priority: asset.risk_band === 'critical' ? 'urgent' : 'high',
                      status: 'draft',
                      asset_ids: [asset.asset_id],
                      evidence_summary: `Asset 360 manual creation — risk ${asset.risk_score}/100`,
                      estimated_hours: 8,
                      estimated_cost_aud: 4200,
                      estimated_customer_impact_reduction: Math.round(asset.customer_count * 0.2),
                    });
                    nav(`/work-packages/${wp.work_package_id}`);
                  }}
                >
                  <Wrench className="w-3.5 h-3.5" />
                  Create work package
                </button>
              </div>
            </div>

            <div className="mt-5 grid grid-cols-4 gap-4">
              <Metric label="Risk score" value={asset.risk_score.toFixed(1)} suffix="/100" accent="#FFB020" />
              <Metric label="Condition" value={asset.condition_score.toFixed(1)} suffix={`/100 · ${asset.health_band}`} />
              <Metric label="Failure prob. 12m" value={(asset.failure_probability_12m * 100).toFixed(1)} suffix="%" />
              <Metric label="Failure prob. 36m" value={(asset.failure_probability_36m * 100).toFixed(1)} suffix="%" />
            </div>
          </div>

          {/* Risk drivers */}
          <div className="panel p-6 space-y-3">
            <h3 className="text-sm font-semibold tracking-tight">Top risk drivers</h3>
            <div className="flex flex-wrap gap-2">
              {asset.risk_drivers.length ? (
                asset.risk_drivers.map((d) => (
                  <span key={d} className="pill pill-high">
                    {d.replace(/_/g, ' ')}
                  </span>
                ))
              ) : (
                <span className="text-muted text-sm">None identified.</span>
              )}
            </div>
            <div className="grid grid-cols-3 gap-3 pt-2">
              <ScoreBar label="Criticality" value={asset.criticality_score} />
              <ScoreBar label="Coastal corrosion" value={asset.coastal_corrosion_score} />
              <ScoreBar label="Access difficulty" value={asset.access_difficulty_score} />
              <ScoreBar label="Cyclone exposure" value={asset.cyclone_exposure_score} />
              <ScoreBar label="Flood exposure" value={asset.flood_exposure_score} />
              <ScoreBar label="Bushfire exposure" value={asset.bushfire_exposure_score} />
            </div>
            <div className="divider pt-3" />
            <div className="text-sm">
              <span className="text-muted">Recommended action:</span>{' '}
              <span className="text-text-primary">{asset.recommended_action}</span>
            </div>
          </div>

          {/* History */}
          <div className="grid grid-cols-2 gap-4">
            <HistoryCard title="Inspections" Icon={ShieldAlert} rows={inspections.slice(0, 5).map((i) => ({
              left: i.inspection_date,
              middle: i.inspection_type,
              right: `${i.defect_count} defects`,
            }))} empty="No inspections recorded." />
            <HistoryCard title="Defects" Icon={AlertTriangle} rows={defects.slice(0, 5).map((d) => ({
              left: d.detected_date,
              middle: d.defect_type.replace(/_/g, ' '),
              right: `${d.severity} · ${d.status}`,
            }))} empty="No defects recorded." />
            <HistoryCard title="Outages on this asset" Icon={CloudLightning} rows={outages.slice(0, 5).map((o) => ({
              left: o.outage_start?.slice(0, 10),
              middle: o.cause_category,
              right: `${o.duration_minutes} min · ${o.customers_interrupted} cust.`,
            }))} empty="No outages directly linked." />
            <HistoryCard title="Work orders" Icon={Wrench} rows={workOrders.slice(0, 5).map((w) => ({
              left: w.created_date,
              middle: w.work_type.replace(/_/g, ' '),
              right: `${w.priority} · ${w.status}`,
            }))} empty="No work orders." />
          </div>
        </div>

        <div className="col-span-4 space-y-4">
          {/* Vegetation proximity */}
          <div className="panel p-5">
            <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
              <Trees className="w-4 h-4 text-vegetation-green" />
              Vegetation proximity
            </h3>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <div className="kpi-label">Min clearance</div>
                <div className="text-xl font-semibold">{asset.vegetation_min_clearance_m.toFixed(2)} m</div>
              </div>
              <div>
                <div className="kpi-label">Max risk score</div>
                <div className="text-xl font-semibold">{asset.vegetation_risk_score_max.toFixed(0)}</div>
              </div>
            </div>
          </div>

          {/* Documents */}
          <div className="panel p-5 space-y-3">
            <h3 className="text-sm font-semibold flex items-center gap-2">
              <FileText className="w-4 h-4 text-electric-cyan" />
              Related documents
            </h3>
            {docs.length === 0 && <div className="text-sm text-muted">No documents linked.</div>}
            {docs.map((d) => (
              <div key={d.document_id} className="text-sm panel-soft p-3 space-y-1">
                <div className="flex items-center justify-between gap-3">
                  <div className="font-medium leading-snug">{d.document_title}</div>
                  <span className="pill pill-neutral">{d.document_type.replace(/_/g, ' ')}</span>
                </div>
                <div className="text-[11px] text-muted truncate font-mono">{d.volume_path}</div>
                {d.excerpt && <div className="text-xs text-text-secondary leading-relaxed">{d.excerpt}</div>}
              </div>
            ))}
          </div>

          {/* Customer impact summary */}
          <div className="panel p-5 space-y-3">
            <h3 className="text-sm font-semibold flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 text-risk-amber" />
              Customer impact
            </h3>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <Metric label="Outages 12m" value={asset.outage_count_12m.toString()} />
              <Metric label="Outages 36m" value={asset.outage_count_36m.toString()} />
              <Metric label="Customers impacted" value={asset.customers_impact_total.toLocaleString()} />
              <Metric label="Critical on feeder" value={asset.critical_customer_count.toString()} />
            </div>
          </div>

          <button
            className="btn-secondary w-full justify-between"
            onClick={() => nav('/work-packages')}
          >
            Open Work Packages
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}

function Metric({ label, value, suffix, accent }: { label: string; value: string; suffix?: string; accent?: string }) {
  return (
    <div>
      <div className="kpi-label">{label}</div>
      <div className="text-xl font-semibold" style={accent ? { color: accent } : undefined}>
        {value}
        {suffix && <span className="text-sm font-medium text-muted ml-1">{suffix}</span>}
      </div>
    </div>
  );
}

function ScoreBar({ label, value }: { label: string; value: number }) {
  const colour = value > 75 ? '#E5484D' : value > 55 ? '#FFB020' : value > 30 ? '#18D4FF' : '#2FB344';
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-[11px] text-muted">
        <span>{label}</span>
        <span className="font-mono text-text-primary">{value.toFixed(0)}</span>
      </div>
      <div className="h-1.5 rounded-full bg-panel-soft overflow-hidden">
        <div className="h-full" style={{ width: `${Math.min(100, value)}%`, backgroundColor: colour }} />
      </div>
    </div>
  );
}

function HistoryCard({
  title,
  Icon,
  rows,
  empty,
}: {
  title: string;
  Icon: typeof Wrench;
  rows: { left: string; middle: string; right: string }[];
  empty: string;
}) {
  return (
    <div className="panel p-5">
      <h3 className="text-sm font-semibold flex items-center gap-2 mb-3">
        <Icon className="w-4 h-4 text-muted" />
        {title}
      </h3>
      {rows.length === 0 ? (
        <div className="text-sm text-muted">{empty}</div>
      ) : (
        <div className="space-y-1.5">
          {rows.map((r, i) => (
            <div key={i} className="flex items-center justify-between text-xs text-text-secondary py-1 row-hover px-2 rounded-md">
              <span className="font-mono text-text-primary/90">{r.left}</span>
              <span>{r.middle}</span>
              <span className="text-right text-muted">{r.right}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Loading() {
  return (
    <div className="h-full flex items-center justify-center text-muted">
      <span className="animate-pulse">Loading asset…</span>
    </div>
  );
}

function ErrorState({ message }: { message: string }) {
  return (
    <div className="h-full flex items-center justify-center">
      <div className="panel p-6 text-center">
        <AlertTriangle className="w-6 h-6 text-critical-red mx-auto mb-2" />
        <div className="text-sm text-text-primary">{message}</div>
      </div>
    </div>
  );
}
