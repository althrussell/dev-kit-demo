import { lazy, Suspense } from 'react';
import type { MapAsset, MapBundle } from '../types';
import { Loader2 } from 'lucide-react';

export interface MapViewProps {
  bundle: MapBundle | null;
  centerLat?: number | null;
  centerLon?: number | null;
  zoom?: number;
  onAssetClick?: (asset: MapAsset) => void;
}

const MAPBOX_TOKEN =
  (import.meta.env.VITE_MAPBOX_TOKEN as string | undefined)?.trim() ?? '';

const HAS_MAPBOX = MAPBOX_TOKEN.startsWith('pk.');

const MapboxLazy = lazy(async () => {
  const mod = await import('./MapboxMapView');
  return { default: (props: MapViewProps) => <mod.MapboxMapView {...props} token={MAPBOX_TOKEN} /> };
});

const MaplibreLazy = lazy(async () => {
  const mod = await import('./MaplibreMapView');
  return { default: mod.MaplibreMapView };
});

export function MapView(props: MapViewProps) {
  return (
    <Suspense fallback={<MapLoading />}>
      {HAS_MAPBOX ? <MapboxLazy {...props} /> : <MaplibreLazy {...props} />}
    </Suspense>
  );
}

function MapLoading() {
  return (
    <div className="absolute inset-0 grid-bg flex items-center justify-center">
      <div className="panel px-4 py-3 flex items-center gap-2 text-sm text-muted">
        <Loader2 className="w-4 h-4 animate-spin text-electric-cyan" />
        Loading map engine…
      </div>
    </div>
  );
}
