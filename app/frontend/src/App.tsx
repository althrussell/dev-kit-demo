import { Routes, Route, Navigate } from 'react-router-dom';
import { AppShell } from './components/AppShell';
import { CommandMapPage } from './pages/CommandMap';
import { AssetDetailPage } from './pages/AssetDetail';
import { RegionalRiskPage } from './pages/RegionalRisk';
import { WorkPackagesPage } from './pages/WorkPackages';
import { AIInvestigationPage } from './pages/AIInvestigation';
import { GenieExplorerPage } from './pages/GenieExplorer';
import { ExecutiveBriefingPage } from './pages/ExecutiveBriefing';
import { AppStateProvider } from './lib/AppState';

export default function App() {
  return (
    <AppStateProvider>
      <AppShell>
        <Routes>
          <Route path="/" element={<Navigate to="/command-map" replace />} />
          <Route path="/command-map" element={<CommandMapPage />} />
          <Route path="/assets/:assetId" element={<AssetDetailPage />} />
          <Route path="/regional-risk" element={<RegionalRiskPage />} />
          <Route path="/work-packages" element={<WorkPackagesPage />} />
          <Route path="/work-packages/:workPackageId" element={<WorkPackagesPage />} />
          <Route path="/ai-investigation" element={<AIInvestigationPage />} />
          <Route path="/genie" element={<GenieExplorerPage />} />
          <Route path="/executive-briefing" element={<ExecutiveBriefingPage />} />
          <Route path="*" element={<Navigate to="/command-map" replace />} />
        </Routes>
      </AppShell>
    </AppStateProvider>
  );
}
