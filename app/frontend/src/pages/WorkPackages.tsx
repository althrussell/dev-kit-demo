import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Wrench, Plus, CheckCircle2, Clock, AlertTriangle, Sparkles } from 'lucide-react';
import { api } from '../lib/api';
import type { WorkPackage } from '../types';

const STATUS_ICON: Record<string, React.ReactNode> = {
  draft: <Clock className="w-3.5 h-3.5" />,
  pending_approval: <AlertTriangle className="w-3.5 h-3.5" />,
  approved: <CheckCircle2 className="w-3.5 h-3.5" />,
  scheduled: <CheckCircle2 className="w-3.5 h-3.5" />,
  completed: <CheckCircle2 className="w-3.5 h-3.5" />,
};

const STATUS_COLOUR: Record<string, string> = {
  draft: 'pill pill-neutral',
  pending_approval: 'pill pill-high',
  approved: 'pill pill-low',
  scheduled: 'pill pill-medium',
  completed: 'pill pill-low',
};

const PRIORITY_COLOUR: Record<string, string> = {
  low: 'pill pill-low',
  medium: 'pill pill-medium',
  high: 'pill pill-high',
  urgent: 'pill pill-critical',
};

export function WorkPackagesPage() {
  const { workPackageId } = useParams<{ workPackageId?: string }>();
  const nav = useNavigate();
  const [list, setList] = useState<WorkPackage[]>([]);
  const [detail, setDetail] = useState<WorkPackage | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = () => {
    setLoading(true);
    api.workPackages().then(setList).finally(() => setLoading(false));
  };

  useEffect(refresh, []);

  useEffect(() => {
    if (workPackageId) {
      api.workPackage(workPackageId).then(setDetail).catch(() => setDetail(null));
    } else {
      setDetail(null);
    }
  }, [workPackageId]);

  return (
    <div className="h-full grid grid-cols-[1fr_22rem]">
      <div className="overflow-y-auto px-8 py-6 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Work packages</h1>
            <p className="text-sm text-muted">Lakebase-backed transactional state. {list.length} packages.</p>
          </div>
          <button
            className="btn-secondary text-sm"
            onClick={refresh}
            disabled={loading}
          >
            Refresh
          </button>
        </div>

        {list.length === 0 && (
          <div className="panel p-8 text-center text-muted text-sm">
            No work packages yet. Create one from Asset 360 or the AI Investigation console.
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          {list.map((wp) => (
            <button
              key={wp.work_package_id}
              onClick={() => nav(`/work-packages/${wp.work_package_id}`)}
              className={`text-left panel p-4 hover:border-electric-cyan/60 transition-colors ${
                detail?.work_package_id === wp.work_package_id ? 'border-electric-cyan/60' : ''
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold">{wp.title}</div>
                  <div className="text-[11px] text-muted mt-1 font-mono">{wp.work_package_id}</div>
                </div>
                <div className="flex flex-col gap-1 items-end">
                  <span className={STATUS_COLOUR[wp.status] ?? 'pill pill-neutral'}>
                    {STATUS_ICON[wp.status]}
                    {wp.status.replace(/_/g, ' ')}
                  </span>
                  <span className={PRIORITY_COLOUR[wp.priority] ?? 'pill pill-neutral'}>{wp.priority}</span>
                </div>
              </div>
              <div className="mt-3 text-xs text-muted grid grid-cols-3 gap-2">
                <div>
                  <div className="kpi-label">Region</div>
                  <div className="text-text-primary text-[12px]">{wp.region_id}</div>
                </div>
                <div>
                  <div className="kpi-label">Hours</div>
                  <div className="text-text-primary text-[12px]">{wp.estimated_hours ?? '-'}</div>
                </div>
                <div>
                  <div className="kpi-label">Cost (AUD)</div>
                  <div className="text-text-primary text-[12px]">
                    {wp.estimated_cost_aud ? `$${Math.round(wp.estimated_cost_aud).toLocaleString()}` : '-'}
                  </div>
                </div>
              </div>
              {wp.recommended_by_agent && (
                <div className="mt-3 inline-flex items-center gap-1.5 text-[11px] text-electric-cyan">
                  <Sparkles className="w-3 h-3" />
                  Recommended by Grid Operations Advisor
                </div>
              )}
            </button>
          ))}
        </div>
      </div>

      <div className="border-l border-border/40 overflow-y-auto px-5 py-5">
        {!detail && (
          <div className="text-sm text-muted text-center mt-12">Select a work package to view detail.</div>
        )}
        {detail && (
          <div className="space-y-4">
            <div>
              <h2 className="text-lg font-semibold leading-tight">{detail.title}</h2>
              <div className="text-[11px] text-muted mt-1 font-mono">{detail.work_package_id}</div>
            </div>
            <div className="flex flex-wrap gap-2">
              <span className={STATUS_COLOUR[detail.status] ?? 'pill pill-neutral'}>{detail.status.replace(/_/g, ' ')}</span>
              <span className={PRIORITY_COLOUR[detail.priority] ?? 'pill pill-neutral'}>{detail.priority}</span>
              {detail.recommended_by_agent && (
                <span className="pill pill-medium">
                  <Sparkles className="w-3 h-3" />
                  agent-recommended
                </span>
              )}
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Metric label="Region" value={detail.region_id} />
              <Metric label="Feeder" value={detail.feeder_id ?? '-'} />
              <Metric label="Hours" value={(detail.estimated_hours ?? 0).toString()} />
              <Metric label="Cost (AUD)" value={`$${Math.round(detail.estimated_cost_aud ?? 0).toLocaleString()}`} />
              <Metric
                label="Customer impact reduction"
                value={(detail.estimated_customer_impact_reduction ?? 0).toLocaleString()}
              />
              <Metric label="Suggested depot" value={detail.suggested_depot_id ?? '-'} />
            </div>
            {detail.evidence_summary && (
              <div className="panel-soft p-3 text-sm text-text-secondary leading-relaxed">
                {detail.evidence_summary}
              </div>
            )}
            <div>
              <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted mb-2">Bundled assets</h3>
              <div className="space-y-1">
                {(detail.assets ?? []).map((a) => (
                  <div
                    key={a.asset_id}
                    className="flex justify-between text-xs text-text-secondary py-1.5 px-2 rounded-md row-hover"
                  >
                    <span className="font-mono">{a.asset_id}</span>
                    <span>{a.role}</span>
                  </div>
                ))}
                {(detail.assets ?? []).length === 0 && (
                  <div className="text-xs text-muted">No bundled assets recorded.</div>
                )}
              </div>
            </div>

            <ApprovalActions
              detail={detail}
              onUpdate={(wp) => {
                setDetail(wp);
                refresh();
              }}
            />
          </div>
        )}
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="kpi-label">{label}</div>
      <div className="text-sm font-mono mt-0.5">{value}</div>
    </div>
  );
}

function ApprovalActions({
  detail,
  onUpdate,
}: {
  detail: WorkPackage;
  onUpdate: (wp: WorkPackage) => void;
}) {
  const status = detail.status;
  const NEXT: Partial<Record<typeof status, [string, string][]>> = {
    draft: [
      ['Submit for approval', 'pending_approval'],
    ],
    pending_approval: [
      ['Approve', 'approved'],
      ['Send back to draft', 'draft'],
    ],
    approved: [
      ['Schedule', 'scheduled'],
    ],
    scheduled: [
      ['Mark complete', 'completed'],
    ],
    completed: [],
  };
  const actions = NEXT[status] ?? [];
  if (actions.length === 0) {
    return <div className="text-xs text-muted">No further actions for this status.</div>;
  }
  return (
    <div className="flex flex-wrap gap-2 pt-2 border-t border-border/30">
      {actions.map(([label, target]) => (
        <button
          key={target}
          className="btn-secondary text-xs"
          onClick={async () => {
            const wp = await api.patchWorkPackage(detail.work_package_id, { status: target });
            onUpdate(wp);
          }}
        >
          <Wrench className="w-3.5 h-3.5" />
          {label}
        </button>
      ))}
    </div>
  );
}
