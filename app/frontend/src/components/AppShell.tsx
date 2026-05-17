import { NavLink, useLocation } from 'react-router-dom';
import {
  Activity,
  Map,
  LineChart,
  Wrench,
  Sparkles,
  Database,
  FileText,
  Compass,
  RadioTower,
  PanelLeftClose,
  PanelLeftOpen,
} from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';

const NAV = [
  { to: '/command-map', label: 'Command Map', icon: Map },
  { to: '/regional-risk', label: 'Regional Risk', icon: LineChart },
  { to: '/work-packages', label: 'Work Packages', icon: Wrench },
  { to: '/ai-investigation', label: 'AI Investigation', icon: Sparkles },
  { to: '/genie', label: 'Genie Explorer', icon: Database },
  { to: '/executive-briefing', label: 'Executive Briefing', icon: FileText },
];

const COLLAPSED_KEY = 'gridlens.sidebar.collapsed';

export function AppShell({ children }: { children: ReactNode }) {
  const loc = useLocation();
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    return window.localStorage.getItem(COLLAPSED_KEY) === '1';
  });

  useEffect(() => {
    window.localStorage.setItem(COLLAPSED_KEY, collapsed ? '1' : '0');
  }, [collapsed]);

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Side rail */}
      <aside
        className={`${
          collapsed ? 'w-16' : 'w-60'
        } shrink-0 bg-panel/90 backdrop-blur border-r border-border/60 flex flex-col transition-[width] duration-200 ease-out`}
      >
        <div
          className={`${
            collapsed ? 'px-2 justify-center' : 'px-5 justify-start'
          } py-5 border-b border-border/40 flex items-center gap-3`}
        >
          <div className="relative w-9 h-9 shrink-0 rounded-lg bg-deep-navy ring-1 ring-electric-cyan/40 flex items-center justify-center shadow-glow">
            <Compass className="w-5 h-5 text-electric-cyan" />
          </div>
          {!collapsed && (
            <div className="min-w-0">
              <div className="text-sm font-semibold tracking-tight">GridLens</div>
              <div className="text-[11px] text-muted tracking-wider uppercase">Queensland</div>
            </div>
          )}
        </div>

        <nav className={`flex-1 ${collapsed ? 'px-2' : 'px-3'} py-4 space-y-1`}>
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              title={collapsed ? label : undefined}
              className={({ isActive }) =>
                `nav-link ${collapsed ? 'justify-center px-2' : ''} ${
                  isActive || loc.pathname.startsWith(to) ? 'active' : ''
                }`
              }
            >
              <Icon className="w-4 h-4 shrink-0" />
              {!collapsed && <span className="truncate">{label}</span>}
            </NavLink>
          ))}
        </nav>

        <div
          className={`${
            collapsed ? 'px-2' : 'px-3'
          } py-3 border-t border-border/40 text-[11px] text-muted space-y-2`}
        >
          <button
            type="button"
            onClick={() => setCollapsed((c) => !c)}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            className={`w-full flex items-center ${
              collapsed ? 'justify-center' : 'justify-between'
            } gap-2 px-2 py-1.5 rounded-md text-text-secondary hover:text-text-primary hover:bg-panel-soft transition-colors`}
          >
            {!collapsed && <span>Collapse</span>}
            {collapsed ? (
              <PanelLeftOpen className="w-4 h-4" />
            ) : (
              <PanelLeftClose className="w-4 h-4" />
            )}
          </button>

          {!collapsed && (
            <>
              <div className="flex items-center gap-2">
                <span className="pulse-dot" />
                <span>Live demo backend connected</span>
              </div>
              <div className="px-1 leading-relaxed">
                UC: <span className="text-text-primary font-mono">anzgt_may</span>
                <br />
                Lakebase: <span className="text-text-primary font-mono">gridlens.*</span>
              </div>
            </>
          )}
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-hidden flex flex-col">
        <TopBar />
        <div className="flex-1 overflow-hidden">{children}</div>
      </main>
    </div>
  );
}

function TopBar() {
  const loc = useLocation();
  const page =
    NAV.find((n) => loc.pathname.startsWith(n.to))?.label ?? 'GridLens Queensland';
  return (
    <header className="h-14 shrink-0 border-b border-border/50 bg-deep-navy/60 backdrop-blur flex items-center justify-between px-6">
      <div className="flex items-center gap-3">
        <RadioTower className="w-4 h-4 text-electric-cyan" />
        <div className="text-sm font-medium">{page}</div>
        <div className="text-[11px] text-muted">
          / AI-powered geospatial asset intelligence for Queensland's electricity network
        </div>
      </div>
      <div className="flex items-center gap-2 text-[12px] text-muted">
        <Activity className="w-3.5 h-3.5 text-vegetation-green" />
        <span>Synthetic demo data — Energy Queensland</span>
      </div>
    </header>
  );
}
