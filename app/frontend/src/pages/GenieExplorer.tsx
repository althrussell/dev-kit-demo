import { useEffect, useState } from 'react';
import { MessageSquare, SendHorizonal, Loader2, Database } from 'lucide-react';
import { api } from '../lib/api';
import type { GenieAnswer } from '../types';
import { MarkdownBody } from '../components/MarkdownBody';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

export function GenieExplorerPage() {
  const [suggested, setSuggested] = useState<string[]>([]);
  const [prompt, setPrompt] = useState('');
  const [answer, setAnswer] = useState<GenieAnswer | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.genieSuggested().then(setSuggested).catch(() => setSuggested([]));
  }, []);

  const ask = async (q: string) => {
    setPrompt(q);
    setLoading(true);
    setError(null);
    try {
      const r = await api.genieAsk(q);
      setAnswer(r);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="h-full grid grid-cols-[24rem_minmax(0,1fr)]">
      <div className="border-r border-border/40 overflow-y-auto px-5 py-5 space-y-3 min-w-0">
        <div className="flex items-center gap-2">
          <MessageSquare className="w-4 h-4 text-electric-cyan" />
          <h2 className="text-sm font-semibold tracking-tight">Suggested questions</h2>
        </div>
        <p className="text-xs text-muted leading-relaxed">
          Genie Space:{' '}
          <span className="text-text-primary">Energy Queensland Network Intelligence</span>.
          Backed by curated <span className="font-mono text-text-primary">energyq_gold</span>{' '}
          tables.
        </p>
        <div className="space-y-1.5 pt-2">
          {suggested.map((q) => (
            <button
              key={q}
              onClick={() => ask(q)}
              className={`block w-full text-left text-xs px-3 py-2 rounded-md transition-colors border ${
                prompt === q
                  ? 'bg-electric-cyan/10 border-electric-cyan/60 text-text-primary'
                  : 'border-border/40 text-text-secondary hover:text-text-primary hover:border-electric-cyan/40'
              }`}
            >
              {q}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-col h-full min-w-0">
        <div className="flex-1 overflow-y-auto px-8 py-6 min-w-0">
          {!answer && !loading && !error && (
            <div className="panel p-10 text-center max-w-xl mx-auto">
              <Database className="w-8 h-8 mx-auto text-electric-cyan" />
              <h3 className="text-lg font-semibold mt-4">Ask a business question</h3>
              <p className="text-sm text-muted mt-2 leading-relaxed">
                Every answer shows the generated SQL, the rows, the visualisation, and the
                business definitions used.
              </p>
            </div>
          )}
          {loading && (
            <div className="panel p-6 max-w-3xl mx-auto flex items-center gap-3 text-muted">
              <Loader2 className="w-4 h-4 animate-spin text-electric-cyan" />
              Querying gold tables…
            </div>
          )}
          {error && (
            <div className="panel p-6 max-w-3xl mx-auto text-sm text-critical-red">{error}</div>
          )}
          {answer && !loading && <AnswerView answer={answer} />}
        </div>
        <div className="border-t border-border/40 px-8 py-4">
          <div className="panel-soft flex items-center gap-2 px-3 py-2.5">
            <MessageSquare className="w-4 h-4 text-electric-cyan" />
            <input
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && prompt.trim()) ask(prompt.trim());
              }}
              placeholder="Ask Genie…"
              className="flex-1 bg-transparent outline-none text-sm placeholder:text-muted"
            />
            <button
              className="btn-primary text-xs"
              onClick={() => prompt.trim() && ask(prompt.trim())}
              disabled={loading}
            >
              <SendHorizonal className="w-3.5 h-3.5" />
              Ask
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function AnswerView({ answer }: { answer: GenieAnswer }) {
  const objectRows = (answer.rows ?? []).map((row) => {
    const obj: Record<string, string | number> = {};
    answer.columns.forEach((col, idx) => {
      obj[col] = row[idx] ?? '';
    });
    return obj;
  });

  return (
    <div className="space-y-4 max-w-4xl min-w-0">
      <div className="panel p-5 space-y-3 min-w-0">
        <MarkdownBody
          source={answer.summary}
          size="base"
          className="text-text-primary [&_p]:my-0 [&_p]:text-text-primary [&_p]:font-medium [&_p]:text-lg [&_p]:leading-snug"
        />
        {answer.cards && answer.cards.length > 0 && (
          <div className="grid grid-cols-3 gap-2">
            {answer.cards.map((card, i) => (
              <div key={i} className="panel-soft p-3">
                <div className="kpi-label">{card.label}</div>
                <div className="text-lg font-semibold mt-1">{card.value}</div>
                {card.sub_label && (
                  <div className="text-[11px] text-muted mt-0.5">{card.sub_label}</div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {objectRows.length > 0 && (
        <div className="panel p-5 space-y-3 min-w-0">
          <h4 className="text-[11px] uppercase tracking-wider text-muted">Result</h4>
          {answer.chart_type === 'bar' && answer.columns.length >= 2 && (
            <div className="h-64">
              <ResponsiveContainer>
                <BarChart data={objectRows}>
                  <CartesianGrid stroke="#254963" strokeDasharray="3 3" vertical={false} />
                  <XAxis
                    dataKey={answer.columns[0]}
                    stroke="#A9BED1"
                    fontSize={11}
                    tickLine={false}
                    axisLine={{ stroke: '#254963' }}
                  />
                  <YAxis
                    stroke="#A9BED1"
                    fontSize={11}
                    tickLine={false}
                    axisLine={{ stroke: '#254963' }}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#0E263A',
                      border: '1px solid #254963',
                      borderRadius: 8,
                    }}
                  />
                  {answer.columns.slice(1).map((c, idx) => (
                    <Bar
                      key={c}
                      dataKey={c}
                      fill={idx === 0 ? '#18D4FF' : idx === 1 ? '#FFB020' : '#E5484D'}
                    />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-[10px] uppercase tracking-wider text-muted border-b border-border/40">
                  {answer.columns.map((c) => (
                    <th key={c} className="text-left py-2 pr-3 font-medium">
                      {c.replace(/_/g, ' ')}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {objectRows.map((row, i) => (
                  <tr key={i} className="border-b border-border/20 row-hover">
                    {answer.columns.map((c) => (
                      <td key={c} className="py-1.5 pr-3 text-text-secondary font-mono">
                        {formatValue(row[c])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 gap-4 min-w-0">
        <div className="panel p-5 space-y-2 min-w-0">
          <h4 className="text-[11px] uppercase tracking-wider text-muted">Generated SQL</h4>
          <pre className="text-[11px] font-mono leading-relaxed text-text-secondary whitespace-pre-wrap break-words bg-deep-navy/60 rounded-md p-3 border border-border/40 overflow-x-auto">
{answer.sql || '-- not available'}
          </pre>
        </div>
        <div className="panel p-5 space-y-2 min-w-0">
          <h4 className="text-[11px] uppercase tracking-wider text-muted">Business definitions</h4>
          {(answer.business_definitions ?? []).length === 0 ? (
            <p className="text-sm text-muted">No business definitions attached.</p>
          ) : (
            <ul className="space-y-2 text-sm text-text-secondary leading-relaxed">
              {answer.business_definitions.map((d, i) => (
                <li key={i} className="flex gap-2">
                  <span className="text-electric-cyan">•</span>
                  <span>{d}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

function formatValue(v: unknown): string {
  if (v === null || v === undefined || v === '') return '—';
  if (typeof v === 'number') return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return String(v);
}
