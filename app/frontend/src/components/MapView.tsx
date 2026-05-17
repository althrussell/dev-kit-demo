import type { MapAsset, MapBundle } from '../types';
import { AlertTriangle } from 'lucide-react';
import { MapboxMapView, type MapStyleId } from './MapboxMapView';

export interface MapViewProps {
  bundle: MapBundle | null;
  centerLat?: number | null;
  centerLon?: number | null;
  zoom?: number;
  onAssetClick?: (asset: MapAsset) => void;
  mapStyle?: MapStyleId;
}

const MAPBOX_TOKEN =
  (import.meta.env.VITE_MAPBOX_TOKEN as string | undefined)?.trim() ?? '';

export function MapView(props: MapViewProps) {
  if (!MAPBOX_TOKEN) {
    return (
      <div className="absolute inset-0 grid-bg flex items-center justify-center p-6">
        <div className="panel max-w-md px-5 py-4 text-sm text-muted flex gap-3">
          <AlertTriangle className="w-5 h-5 shrink-0 text-electric-cyan" />
          <div>
            <div className="text-text-primary font-medium mb-1">
              Mapbox token missing
            </div>
            Set <code className="font-mono text-text-primary">VITE_MAPBOX_TOKEN</code>{' '}
            in <code className="font-mono text-text-primary">app/frontend/.env.local</code>{' '}
            and rebuild the frontend.
          </div>
        </div>
      </div>
    );
  }

  return <MapboxMapView {...props} token={MAPBOX_TOKEN} />;
}
