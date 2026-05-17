import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import type { RegionalSummary } from '../types';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Tooltip,
  XAxis,
  YAxis,
  ResponsiveContainer,
} from 'recharts';
import { ShieldAlert, TreePine, Truck, Users } from 'lucide-react';

const COLOURS: Record<string, string> = {
  'SEQ Metro Storm Belt': '#1E88E5',
  'Mackay / Whitsunday Corridor': '#FFB020',
  'Townsville / Cairns Coastal Corridor': '#E5484D',
  'Central Queensland Industrial Belt': '#7C3AED',
  'Remote Western Queensland': '#D8B06A',
};

export function RegionalRiskPage() {
  const [data, setData] = useState<RegionalSummary[] | null>(null);

  useEffect(() => {
    api.regionalRisk().then(setData).catch(() => setData(null));
  }, []);

  if (!data) return <div className="h-full flex items-center justify-center text-muted">Loading…</div>;
  const sorted = [...data].sort((a, b) => b.high_risk_assets + b.critical_risk_assets - (a.high_risk_assets + a.critical_risk_assets));
  const totalCritical = sorted.reduce((acc, r) => acc + r.critical_risk_assets, 0);
  const totalHigh = sorted.reduce((acc, r) => acc + r.high_risk_assets, 0);
  const totalBacklog = sorted.reduce((acc, r) => acc + r.vegetation_backlog, 0);
  const totalCrit = sorted.reduce((acc, r) => acc + r.critical_customer_count_exposed, 0);

  return (
    <div className="h-full overflow-y-auto px-8 py-6 space-y-6">
      <div className="grid grid-cols-4 gap-4">
        <Kpi label="Critical-risk assets" value={totalCritical} icon={<ShieldAlert className="w-4 h-4 text-critical-red" />} />
        <Kpi label="High-risk assets" value={totalHigh} icon={<ShieldAlert className="w-4 h-4 text-risk-amber" />} />
        <Kpi label="Vegetation backlog" value={totalBacklog} icon={<TreePine className="w-4 h-4 text-vegetation-green" />} />
        <Kpi label="Critical customers exposed" value={totalCrit} icon={<Users className="w-4 h-4 text-electric-cyan" />} />
      </div>

      <div className="panel p-6">
        <h3 className="text-sm font-semibold mb-4">High / critical asset count by region</h3>
        <div className="h-72">
          <ResponsiveContainer>
            <BarChart data={sorted}>
              <CartesianGrid stroke="#254963" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="region_name" stroke="#A9BED1" fontSize={11} tickLine={false} axisLine={{ stroke: '#254963' }} />
              <YAxis stroke="#A9BED1" fontSize={11} tickLine={false} axisLine={{ stroke: '#254963' }} />
              <Tooltip contentStyle={{ backgroundColor: '#0E263A', border: '1px solid #254963', borderRadius: 8 }} />
              <Legend wrapperStyle={{ fontSize: 11, color: '#A9BED1' }} />
              <Bar dataKey="high_risk_assets" name="High" stackId="risk" fill="#FFB020">
                {sorted.map((r) => (
                  <Cell key={r.region_id} fill="#FFB020" />
                ))}
              </Bar>
              <Bar dataKey="critical_risk_assets" name="Critical" stackId="risk" fill="#E5484D" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="panel p-6 overflow-x-auto">
        <h3 className="text-sm font-semibold mb-3">Regional leaderboard</h3>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[11px] uppercase tracking-wider text-muted border-b border-border/40">
              <th className="text-left py-2">Region</th>
              <th className="text-right">Assets</th>
              <th className="text-right">High</th>
              <th className="text-right">Critical</th>
              <th className="text-right">Veg backlog</th>
              <th className="text-right">Mobile gen ready</th>
              <th className="text-right">Critical customers</th>
              <th className="text-right">Avg risk</th>
              <th className="text-right">Customers at risk</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr key={r.region_id} className="border-b border-border/20 row-hover">
                <td className="py-2.5 flex items-center gap-2">
                  <span className="inline-block w-2 h-2 rounded-full" style={{ backgroundColor: COLOURS[r.region_name] ?? '#18D4FF' }} />
                  {r.region_name}
                </td>
                <td className="text-right font-mono">{r.total_assets.toLocaleString()}</td>
                <td className="text-right font-mono text-risk-amber">{r.high_risk_assets.toLocaleString()}</td>
                <td className="text-right font-mono text-critical-red">{r.critical_risk_assets.toLocaleString()}</td>
                <td className="text-right font-mono">{r.vegetation_backlog.toLocaleString()}</td>
                <td className="text-right font-mono text-vegetation-green">{r.mobile_gen_ready_sites.toLocaleString()}</td>
                <td className="text-right font-mono">{r.critical_customer_count_exposed.toLocaleString()}</td>
                <td className="text-right font-mono">{r.avg_risk_score.toFixed(1)}</td>
                <td className="text-right font-mono">{r.customers_at_risk.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Kpi({ label, value, icon }: { label: string; value: number; icon: React.ReactNode }) {
  return (
    <div className="kpi">
      <div className="flex items-center justify-between">
        <div className="kpi-label">{label}</div>
        {icon}
      </div>
      <div className="kpi-value">{value.toLocaleString()}</div>
    </div>
  );
}
