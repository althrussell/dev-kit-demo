import { useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  Sparkles,
  SendHorizonal,
  Database,
  FileText,
  Map,
  ShieldCheck,
  ChevronRight,
  Loader2,
  Wrench,
  Bot,
} from 'lucide-react';
import { api } from '../lib/api';
import type { AgentResponse, AgentEvidence } from '../types';
import { useAppState } from '../lib/AppState';

const SUGGESTIONS = [
  'Show me the top 20 assets that should be remediated before storm season.',
  'Which feeders have the highest combination of vegetation exposure and outage history?',
  'Create a work package for the Mackay high-risk cluster and avoid duplicate planned works.',
  'Explain why this selected asset is high risk using inspection documents.',
  'What is the customer impact if we defer this work by six months?',
  'Prepare a regional manager briefing for the selected risk zone.',
];

const EVIDENCE_ICON: Record<AgentEvidence['evidence_type'], React.ReactNode> = {
  delta_table: <Database className="w-3.5 h-3.5 text-electric-cyan" />,
  document: <FileText className="w-3.5 h-3.5 text-sandstone" />,
  genie_answer: <Sparkles className="w-3.5 h-3.5 text-substation-violet" />,
  map_selection: <Map className="w-3.5 h-3.5 text-vegetation-green" />,
  policy: <ShieldCheck className="w-3.5 h-3.5 text-risk-amber" />,
};

interface Conversation {
  prompt: string;
  response?: AgentResponse;
  pending?: boolean;
  error?: string;
}

export function AIInvestigationPage() {
  const { selectedRegion, scenario, setLastAgentRecommendationId } = useAppState();
  const loc = useLocation();
  const nav = useNavigate();
  const seed = (loc.state ?? {}) as { asset_id?: string; region_id?: string; feeder_id?: string };
  const [prompt, setPrompt] = useState('');
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [creatingPackage, setCreatingPackage] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (seed?.asset_id) {
      const initial = `Why is asset ${seed.asset_id} high risk? What should we do before storm season?`;
      submit(initial);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [conversations]);

  const submit = async (text: string) => {
    setConversations((c) => [...c, { prompt: text, pending: true }]);
    setPrompt('');
    try {
      const r = await api.agentInvestigate({
        prompt: text,
        asset_id: seed?.asset_id,
        feeder_id: seed?.feeder_id,
        region_id: seed?.region_id ?? selectedRegion ?? undefined,
        scenario_type: scenario,
      });
      setLastAgentRecommendationId(r.recommendation_id);
      setConversations((c) =>
        c.map((x, i) => (i === c.length - 1 ? { prompt: x.prompt, response: r } : x)),
      );
    } catch (err) {
      setConversations((c) =>
        c.map((x, i) =>
          i === c.length - 1 ? { prompt: x.prompt, error: String(err) } : x,
        ),
      );
    }
  };

  const last = conversations[conversations.length - 1]?.response;

  const handleCreateWorkPackage = async () => {
    if (!last) return;
    setCreatingPackage(true);
    const wpAssetIds = collectAssetEvidence(last.evidence).slice(0, 8);
    if (!wpAssetIds.length && seed?.asset_id) wpAssetIds.push(seed.asset_id);
    try {
      const wp = await api.agentCreateWorkPackage({
        recommendation_id: last.recommendation_id,
        title: last.headline.slice(0, 120),
        priority: 'high',
        region_id: seed?.region_id ?? selectedRegion ?? 'REG-MKY',
        feeder_id: seed?.feeder_id,
        asset_ids: wpAssetIds,
      });
      nav(`/work-packages/${wp.work_package_id}`);
    } finally {
      setCreatingPackage(false);
    }
  };

  return (
    <div className="h-full grid grid-cols-[1fr_22rem]">
      <div className="flex flex-col h-full">
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-8 py-6 space-y-5">
          {conversations.length === 0 && (
            <Welcome onSuggestion={submit} />
          )}
          {conversations.map((c, i) => (
            <ConversationCard
              key={i}
              c={c}
              onCreate={handleCreateWorkPackage}
              creatingPackage={creatingPackage}
            />
          ))}
        </div>
        <div className="border-t border-border/40 px-8 py-4">
          <div className="panel-soft flex items-center gap-2 px-3 py-2.5">
            <Bot className="w-4 h-4 text-electric-cyan" />
            <input
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && prompt.trim()) submit(prompt.trim());
              }}
              placeholder="Ask the Grid Operations Advisor…"
              className="flex-1 bg-transparent outline-none text-sm placeholder:text-muted"
            />
            <button className="btn-primary text-xs" onClick={() => prompt.trim() && submit(prompt.trim())}>
              <SendHorizonal className="w-3.5 h-3.5" />
              Send
            </button>
          </div>
          <div className="flex flex-wrap gap-2 mt-3">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => submit(s)}
                className="text-[11px] text-muted hover:text-text-primary border border-border/40 hover:border-electric-cyan/60 px-2 py-1 rounded-md transition-colors"
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      </div>

      <SidePanel last={last} />
    </div>
  );
}

function Welcome({ onSuggestion }: { onSuggestion: (s: string) => void }) {
  return (
    <div className="panel p-8 max-w-3xl mx-auto text-center">
      <div className="w-12 h-12 rounded-xl mx-auto bg-electric-cyan/10 ring-1 ring-electric-cyan/40 flex items-center justify-center">
        <Sparkles className="w-6 h-6 text-electric-cyan" />
      </div>
      <h2 className="mt-4 text-2xl font-semibold tracking-tight">Grid Operations Advisor</h2>
      <p className="text-sm text-text-secondary mt-2 max-w-xl mx-auto leading-relaxed">
        Multi-agent system grounded in Delta tables, Unity Catalog volume documents, Genie analytics, and policy
        references. Every answer includes evidence citations and a draft work plan you can convert into a Lakebase-backed
        work package.
      </p>
      <div className="grid grid-cols-2 gap-2 mt-6 text-left">
        {SUGGESTIONS.slice(0, 4).map((s) => (
          <button
            key={s}
            onClick={() => onSuggestion(s)}
            className="panel-soft p-3 text-sm text-text-secondary hover:text-text-primary hover:border-electric-cyan/40 transition-colors text-left"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

function ConversationCard({
  c,
  onCreate,
  creatingPackage,
}: {
  c: Conversation;
  onCreate: () => void;
  creatingPackage: boolean;
}) {
  return (
    <div className="space-y-3">
      <div className="ml-auto max-w-xl panel-soft px-4 py-2.5 rounded-2xl rounded-tr-sm text-sm w-fit">
        <span className="text-text-primary">{c.prompt}</span>
      </div>
      {c.pending && (
        <div className="panel p-4 max-w-3xl flex items-center gap-3 text-sm text-muted">
          <Loader2 className="w-4 h-4 animate-spin text-electric-cyan" />
          Grid Operations Advisor coordinating specialists…
        </div>
      )}
      {c.error && (
        <div className="panel p-4 text-sm text-critical-red max-w-3xl">{c.error}</div>
      )}
      {c.response && (
        <div className="panel p-5 max-w-3xl space-y-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h3 className="text-lg font-semibold tracking-tight leading-snug">
                {c.response.headline}
              </h3>
              <div className="text-[11px] text-muted mt-1 font-mono">{c.response.recommendation_id}</div>
            </div>
            <span className="pill pill-medium">
              <Sparkles className="w-3 h-3" />
              confidence {Math.round(c.response.confidence * 100)}%
            </span>
          </div>

          <pre className="text-[13px] leading-relaxed text-text-secondary whitespace-pre-wrap font-sans">
            {c.response.body}
          </pre>

          <div>
            <h4 className="text-[11px] uppercase tracking-wider text-muted mb-2">Next steps</h4>
            <ul className="space-y-1 text-sm">
              {c.response.next_steps.map((s, i) => (
                <li key={i} className="flex gap-2">
                  <span className="text-electric-cyan">→</span>
                  <span>{s}</span>
                </li>
              ))}
            </ul>
          </div>

          <div>
            <h4 className="text-[11px] uppercase tracking-wider text-muted mb-2">Evidence ({c.response.evidence.length})</h4>
            <div className="grid grid-cols-2 gap-2">
              {c.response.evidence.map((e, i) => (
                <div key={i} className="panel-soft p-3 text-xs space-y-1">
                  <div className="flex items-center gap-2 text-text-primary">
                    {EVIDENCE_ICON[e.evidence_type]}
                    <span className="font-medium">{e.source_title}</span>
                    <span className="ml-auto text-[10px] text-muted font-mono">
                      {Math.round(e.confidence * 100)}%
                    </span>
                  </div>
                  <div className="text-text-secondary leading-snug">{e.excerpt}</div>
                  <div className="text-[10px] text-muted font-mono truncate">{e.source_ref}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="flex gap-2 pt-2 border-t border-border/30">
            <button
              className="btn-primary text-xs"
              onClick={onCreate}
              disabled={creatingPackage}
            >
              {creatingPackage ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Wrench className="w-3.5 h-3.5" />}
              Convert to work package
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function SidePanel({ last }: { last?: AgentResponse }) {
  return (
    <div className="border-l border-border/40 overflow-y-auto px-5 py-5 space-y-4">
      <div>
        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted">Specialist agent trace</h3>
        <p className="text-xs text-muted mt-1">
          Supervisor: <span className="text-text-primary">Grid Operations Advisor</span>
        </p>
      </div>
      {!last && (
        <div className="text-sm text-muted">Run an investigation to see the agent trace.</div>
      )}
      {last?.trace.map((step, i) => (
        <div key={i} className="panel-soft p-3 text-xs space-y-1">
          <div className="flex items-center justify-between text-text-primary text-[12px]">
            <span className="font-medium">{step.agent}</span>
            <span className="font-mono text-muted">
              {Math.round(step.confidence * 100)}%
            </span>
          </div>
          <div className="text-muted">
            <span className="font-mono">{step.action}</span>
          </div>
          <div className="text-text-secondary leading-snug">{step.output_summary}</div>
        </div>
      ))}
      {last && (
        <div className="text-[11px] text-muted leading-relaxed pt-3 border-t border-border/30">
          Trace shape mirrors a real Agent Bricks MAS response. Replace with{' '}
          <span className="font-mono text-text-primary">AGENTBRICKS_SUPERVISOR_ENDPOINT</span>{' '}
          to call the real supervisor.
        </div>
      )}
    </div>
  );
}

function collectAssetEvidence(evidence: AgentEvidence[]): string[] {
  const ids = new Set<string>();
  const re = /AST-[A-Z]+-[A-Z]+-\d+/g;
  for (const e of evidence) {
    const m = `${e.source_title} ${e.excerpt} ${e.source_ref}`.match(re);
    if (m) m.forEach((x) => ids.add(x));
  }
  return Array.from(ids);
}
