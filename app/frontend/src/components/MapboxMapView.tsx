import { useEffect, useRef, useState } from 'react';
import mapboxgl from 'mapbox-gl';
import 'mapbox-gl/dist/mapbox-gl.css';
import type {
  MapBundle,
  MapAsset,
  HazardZone,
  CriticalCustomer,
  Depot,
  MobileGenSite,
} from '../types';
import { useAppState } from '../lib/AppState';
import { useNavigate } from 'react-router-dom';

const RISK_COLORS: Record<string, string> = {
  low: '#2FB344',
  medium: '#18D4FF',
  high: '#FFB020',
  critical: '#E5484D',
};

const RISK_RADIUS: Record<string, number> = {
  low: 3,
  medium: 4,
  high: 5,
  critical: 6,
};

const MAPBOX_STYLE = 'mapbox://styles/mapbox/dark-v11';

export interface MapboxMapViewProps {
  bundle: MapBundle | null;
  centerLat?: number | null;
  centerLon?: number | null;
  zoom?: number;
  onAssetClick?: (asset: MapAsset) => void;
  token: string;
}

export function MapboxMapView({
  bundle,
  centerLat,
  centerLon,
  zoom,
  onAssetClick,
  token,
}: MapboxMapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const pulseAnimRef = useRef<number | null>(null);
  const cycloneAnimRef = useRef<number | null>(null);
  const resizeObserverRef = useRef<ResizeObserver | null>(null);
  // Flips true once `map.on('load')` fires — i.e. all sources + layers exist.
  // The bundle / selected-asset effects gate on this so they don't try to call
  // `getSource('assets')` before the source is added.
  const [sourcesReady, setSourcesReady] = useState(false);
  const { layers, selectedAssetId } = useAppState();
  const nav = useNavigate();

  // Keep callbacks in a ref so the init useEffect (which constructs the
  // expensive mapboxgl.Map instance and wires every event listener) does not
  // re-run on every parent render. Without this, a new `onAssetClick` arrow
  // function on each CommandMap render would tear down the map mid-init,
  // producing "Cannot read properties of undefined (reading 'send')" from
  // pending workers and a permanently blank canvas.
  const onAssetClickRef = useRef(onAssetClick);
  useEffect(() => {
    onAssetClickRef.current = onAssetClick;
  }, [onAssetClick]);

  const navRef = useRef(nav);
  useEffect(() => {
    navRef.current = nav;
  }, [nav]);

  // ---------------- init ----------------
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    mapboxgl.accessToken = token;

    const map = new mapboxgl.Map({
      container: containerRef.current,
      style: MAPBOX_STYLE,
      // Centre Queensland directly. No cinematic globe → flyTo dance —
      // it was the source of "Map cannot fit within canvas" and worker
      // teardown errors when the React tree re-rendered mid-animation.
      center: [146.0, -22.5],
      zoom: 4.8,
      pitch: 0,
      bearing: 0,
      attributionControl: false,
      antialias: true,
      hash: false,
    });
    map.addControl(
      new mapboxgl.AttributionControl({ compact: true }),
      'bottom-right',
    );
    // No NavigationControl — it collides with the React Refresh button at
    // top-right. Mouse-wheel and pinch already cover zoom + rotate.
    mapRef.current = map;

    // Mapbox does not observe container size changes — only window resize.
    // In a CSS grid/flex layout the container can grow after first paint,
    // leaving the canvas stuck at its initial (small) size. Re-fit on every
    // container resize so the map always fills the available space.
    if (typeof ResizeObserver !== 'undefined' && containerRef.current) {
      const ro = new ResizeObserver(() => {
        if (mapRef.current) mapRef.current.resize();
      });
      ro.observe(containerRef.current);
      resizeObserverRef.current = ro;
    }

    map.on('load', () => {
      // Animated cyclone storm fan-out — built from hazards by hazard_type=cyclone.
      map.addSource('hazards', { type: 'geojson', data: emptyFC() });
      map.addSource('hazards-cyclone', { type: 'geojson', data: emptyFC() });
      map.addSource('critical-customers', { type: 'geojson', data: emptyFC() });
      map.addSource('depots', { type: 'geojson', data: emptyFC() });
      map.addSource('mobile-gen', { type: 'geojson', data: emptyFC() });
      map.addSource('assets', { type: 'geojson', data: emptyFC() });
      map.addSource('selected-asset', { type: 'geojson', data: emptyFC() });
      map.addSource('asset-heat', { type: 'geojson', data: emptyFC() });

      const beforeId = firstSymbolLayer(map);

      map.addLayer(
        {
          id: 'hazards-fill',
          type: 'circle',
          source: 'hazards',
          paint: {
            'circle-radius': [
              'interpolate', ['linear'], ['zoom'],
              3, ['*', ['get', 'radius_km'], 0.5],
              6, ['*', ['get', 'radius_km'], 1.4],
              10, ['*', ['get', 'radius_km'], 5],
            ],
            'circle-color': [
              'match', ['get', 'hazard_type'],
              'cyclone', '#7C3AED',
              'flood', '#1E88E5',
              'bushfire', '#E5484D',
              'heat', '#FFB020',
              'storm', '#18D4FF',
              'coastal_corrosion', '#D8B06A',
              '#7C3AED',
            ],
            'circle-opacity': 0.1,
            'circle-stroke-color': '#A9BED1',
            'circle-stroke-width': 0.4,
            'circle-stroke-opacity': 0.35,
          },
        },
        beforeId,
      );

      // Animated cyclone storm rings (pulse).
      map.addLayer(
        {
          id: 'hazards-cyclone-pulse',
          type: 'circle',
          source: 'hazards-cyclone',
          paint: {
            'circle-radius': [
              'interpolate', ['linear'], ['zoom'],
              3, ['*', ['get', 'radius_km'], 0.4],
              8, ['*', ['get', 'radius_km'], 2.4],
              11, ['*', ['get', 'radius_km'], 6],
            ],
            'circle-color': 'transparent',
            'circle-stroke-color': '#7C3AED',
            'circle-stroke-width': 1.4,
            'circle-stroke-opacity': 0.7,
          },
        },
        beforeId,
      );
      map.addLayer(
        {
          id: 'hazards-cyclone-core',
          type: 'circle',
          source: 'hazards-cyclone',
          paint: {
            'circle-radius': 3,
            'circle-color': '#A26FF7',
            'circle-opacity': 0.9,
            'circle-stroke-color': '#F5FAFF',
            'circle-stroke-width': 0.6,
          },
        },
        beforeId,
      );

      // High-risk asset heatmap — visible at low zoom, fades out as circles emerge.
      map.addLayer(
        {
          id: 'asset-heat',
          type: 'heatmap',
          source: 'asset-heat',
          maxzoom: 12,
          paint: {
            'heatmap-weight': [
              'interpolate', ['linear'], ['get', 'weight'],
              0, 0,
              1, 1,
            ],
            'heatmap-intensity': [
              'interpolate', ['linear'], ['zoom'],
              4, 0.9,
              9, 2.4,
              12, 3.2,
            ],
            'heatmap-color': [
              'interpolate', ['linear'], ['heatmap-density'],
              0, 'rgba(7, 24, 39, 0)',
              0.15, 'rgba(24, 212, 255, 0.25)',
              0.4, 'rgba(255, 176, 32, 0.55)',
              0.7, 'rgba(229, 72, 77, 0.7)',
              1, 'rgba(255, 235, 235, 0.85)',
            ],
            'heatmap-radius': [
              'interpolate', ['linear'], ['zoom'],
              4, 8,
              7, 18,
              10, 28,
              12, 40,
            ],
            'heatmap-opacity': [
              'interpolate', ['linear'], ['zoom'],
              4, 0.85,
              9, 0.7,
              11, 0.35,
              12, 0,
            ],
          },
        },
        beforeId,
      );

      // Depots
      map.addLayer(
        {
          id: 'depots-layer',
          type: 'circle',
          source: 'depots',
          paint: {
            'circle-radius': 5,
            'circle-color': '#D8B06A',
            'circle-stroke-color': '#071827',
            'circle-stroke-width': 1.4,
          },
        },
        beforeId,
      );

      // Mobile gen
      map.addLayer(
        {
          id: 'mobile-gen-layer',
          type: 'circle',
          source: 'mobile-gen',
          paint: {
            'circle-radius': 4.5,
            'circle-color': '#18D4FF',
            'circle-opacity': 0.85,
            'circle-stroke-color': '#0E263A',
            'circle-stroke-width': 1.2,
          },
        },
        beforeId,
      );

      // Critical customers
      map.addLayer(
        {
          id: 'critical-customers-layer',
          type: 'circle',
          source: 'critical-customers',
          paint: {
            'circle-radius': [
              'interpolate', ['linear'], ['zoom'],
              5, 3,
              10, 5,
              14, 8,
            ],
            'circle-color': '#FFB020',
            'circle-stroke-color': '#071827',
            'circle-stroke-width': 1.4,
            'circle-opacity': 0.95,
          },
        },
        beforeId,
      );

      // Assets (heavy)
      map.addLayer(
        {
          id: 'assets-layer',
          type: 'circle',
          source: 'assets',
          paint: {
            'circle-radius': [
              'interpolate', ['linear'], ['zoom'],
              4, ['*', ['coalesce', ['get', 'r_size'], 3], 0.7],
              8, ['get', 'r_size'],
              12, ['*', ['coalesce', ['get', 'r_size'], 3], 1.6],
              15, ['*', ['coalesce', ['get', 'r_size'], 3], 2.6],
            ],
            'circle-color': ['coalesce', ['get', 'r_color'], '#18D4FF'],
            'circle-opacity': [
              'interpolate', ['linear'], ['zoom'],
              4, 0.7,
              9, 0.92,
            ],
            'circle-stroke-color': '#071827',
            'circle-stroke-width': 0.6,
            'circle-blur': [
              'interpolate', ['linear'], ['zoom'],
              4, 0.4,
              10, 0.05,
            ],
          },
        },
        beforeId,
      );

      // 3D buildings — only at high zoom, gives the SEQ metro view real
      // depth when inspecting critical customers.
      if (!map.getLayer('buildings-3d')) {
        map.addLayer(
          {
            id: 'buildings-3d',
            source: 'composite',
            'source-layer': 'building',
            filter: ['==', 'extrude', 'true'],
            type: 'fill-extrusion',
            minzoom: 13,
            paint: {
              'fill-extrusion-color': '#14324A',
              'fill-extrusion-height': [
                'interpolate', ['linear'], ['zoom'],
                13, 0,
                14, ['get', 'height'],
              ],
              'fill-extrusion-base': [
                'interpolate', ['linear'], ['zoom'],
                13, 0,
                14, ['get', 'min_height'],
              ],
              'fill-extrusion-opacity': 0.7,
            },
          },
          beforeId,
        );
      }

      // Selected asset emphasis ring + outer pulse
      map.addLayer({
        id: 'selected-asset-outer',
        type: 'circle',
        source: 'selected-asset',
        paint: {
          'circle-radius': 28,
          'circle-color': '#18D4FF',
          'circle-opacity': 0.18,
        },
      });
      map.addLayer({
        id: 'selected-asset-ring',
        type: 'circle',
        source: 'selected-asset',
        paint: {
          'circle-radius': 14,
          'circle-color': 'transparent',
          'circle-stroke-color': '#F5FAFF',
          'circle-stroke-width': 2,
          'circle-stroke-opacity': 0.95,
        },
      });

      // ---- popups & interactions
      const popup = new mapboxgl.Popup({
        closeButton: false,
        closeOnClick: false,
        offset: 12,
        className: 'gridlens-popup',
      });
      map.on('mouseenter', 'assets-layer', (e) => {
        const f = e.features?.[0];
        if (!f) return;
        map.getCanvas().style.cursor = 'pointer';
        const props = f.properties as MapAsset & { r_color: string; r_size: number };
        popup
          .setLngLat((f.geometry as GeoJSON.Point).coordinates as [number, number])
          .setHTML(assetPopupHtml(props))
          .addTo(map);
      });
      map.on('mouseleave', 'assets-layer', () => {
        map.getCanvas().style.cursor = '';
        popup.remove();
      });
      map.on('click', 'assets-layer', (e) => {
        const f = e.features?.[0];
        if (!f) return;
        const props = f.properties as MapAsset;
        onAssetClickRef.current?.(props);
        navRef.current(`/assets/${props.asset_id}`);
      });

      map.on('mouseenter', 'critical-customers-layer', () => {
        map.getCanvas().style.cursor = 'pointer';
      });
      map.on('mouseleave', 'critical-customers-layer', () => {
        map.getCanvas().style.cursor = '';
      });
      map.on('click', 'critical-customers-layer', (e) => {
        const f = e.features?.[0];
        if (!f) return;
        const p = f.properties as CriticalCustomer;
        new mapboxgl.Popup({ offset: 12, className: 'gridlens-popup' })
          .setLngLat((f.geometry as GeoJSON.Point).coordinates as [number, number])
          .setHTML(
            `<div><div style="font-weight:600;">${p.site_name}</div><div style="margin-top:2px;color:#A9BED1;font-size:11px;">${String(p.site_type).replace(/_/g, ' ')} · ${p.feeder_id}</div></div>`,
          )
          .addTo(map);
      });

      map.on('mouseenter', 'depots-layer', () => {
        map.getCanvas().style.cursor = 'pointer';
      });
      map.on('mouseleave', 'depots-layer', () => {
        map.getCanvas().style.cursor = '';
      });
      map.on('click', 'depots-layer', (e) => {
        const f = e.features?.[0];
        if (!f) return;
        const p = f.properties as Depot;
        new mapboxgl.Popup({ offset: 12, className: 'gridlens-popup' })
          .setLngLat((f.geometry as GeoJSON.Point).coordinates as [number, number])
          .setHTML(
            `<div><div style="font-weight:600;">${p.depot_name}</div><div style="margin-top:2px;color:#A9BED1;font-size:11px;">Crew ${p.crew_count} · Mobile gen ${p.mobile_generation_units}</div></div>`,
          )
          .addTo(map);
      });

      // Animation: selected-asset outer pulse
      const startPulse = () => {
        const start = performance.now();
        const tick = () => {
          const t = (performance.now() - start) / 1500;
          const phase = (Math.sin(t * Math.PI * 2) + 1) / 2; // 0..1
          if (map.getLayer('selected-asset-outer')) {
            map.setPaintProperty(
              'selected-asset-outer',
              'circle-radius',
              22 + phase * 12,
            );
            map.setPaintProperty(
              'selected-asset-outer',
              'circle-opacity',
              0.05 + (1 - phase) * 0.22,
            );
          }
          pulseAnimRef.current = requestAnimationFrame(tick);
        };
        pulseAnimRef.current = requestAnimationFrame(tick);
      };
      startPulse();

      // Animation: cyclone storm rings rotate
      const startCyclone = () => {
        const start = performance.now();
        const tick = () => {
          const t = (performance.now() - start) / 2400;
          const phase = (Math.sin(t * Math.PI * 2) + 1) / 2;
          if (map.getLayer('hazards-cyclone-pulse')) {
            map.setPaintProperty(
              'hazards-cyclone-pulse',
              'circle-stroke-opacity',
              0.25 + phase * 0.6,
            );
            map.setPaintProperty(
              'hazards-cyclone-pulse',
              'circle-stroke-width',
              0.8 + phase * 1.8,
            );
          }
          cycloneAnimRef.current = requestAnimationFrame(tick);
        };
        cycloneAnimRef.current = requestAnimationFrame(tick);
      };
      startCyclone();

      // Signal to the bundle / selected-asset effects that every source +
      // layer is now present, so it's safe to call `getSource('assets')`,
      // `setData(...)`, `setLayoutProperty(...)`, etc.
      setSourcesReady(true);
    });

    return () => {
      if (pulseAnimRef.current) cancelAnimationFrame(pulseAnimRef.current);
      if (cycloneAnimRef.current) cancelAnimationFrame(cycloneAnimRef.current);
      if (resizeObserverRef.current) {
        resizeObserverRef.current.disconnect();
        resizeObserverRef.current = null;
      }
      map.remove();
      mapRef.current = null;
    };
    // token is a build-time constant; nav and onAssetClick are accessed via
    // refs above so this effect intentionally constructs the map exactly once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  // ---------------- bundle ----------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !bundle || !sourcesReady) return;
    (map.getSource('assets') as mapboxgl.GeoJSONSource | undefined)?.setData(
      assetsToFC(bundle.assets),
    );
    (map.getSource('asset-heat') as mapboxgl.GeoJSONSource | undefined)?.setData(
      assetsToHeatFC(bundle.assets),
    );
    const allHazards = bundle.hazards ?? [];
    const cyclones = allHazards.filter((h) => h.hazard_type === 'cyclone');
    const others = allHazards.filter((h) => h.hazard_type !== 'cyclone');
    (map.getSource('hazards') as mapboxgl.GeoJSONSource | undefined)?.setData(
      hazardsToFC(others),
    );
    (map.getSource('hazards-cyclone') as mapboxgl.GeoJSONSource | undefined)?.setData(
      hazardsToFC(cyclones),
    );
    (map.getSource('critical-customers') as mapboxgl.GeoJSONSource | undefined)?.setData(
      criticalCustomersToFC(bundle.critical_customers),
    );
    (map.getSource('depots') as mapboxgl.GeoJSONSource | undefined)?.setData(
      depotsToFC(bundle.depots),
    );
    (map.getSource('mobile-gen') as mapboxgl.GeoJSONSource | undefined)?.setData(
      mobileGenToFC(bundle.mobile_gen_sites),
    );
  }, [bundle, sourcesReady]);

  // ---------------- layer toggles ----------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !sourcesReady) return;
    const set = (id: string, visible: boolean) => {
      if (!map.getLayer(id)) return;
      map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none');
    };
    set('assets-layer', layers.assets);
    set('asset-heat', layers.assets);
    set('hazards-fill', layers.hazards);
    set('hazards-cyclone-pulse', layers.hazards);
    set('hazards-cyclone-core', layers.hazards);
    set('critical-customers-layer', layers.critical_customers);
    set('depots-layer', layers.depots);
    set('mobile-gen-layer', layers.mobile_gen);
  }, [layers, sourcesReady]);

  // ---------------- center / zoom ----------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (centerLat != null && centerLon != null) {
      map.flyTo({
        center: [centerLon, centerLat],
        zoom: zoom ?? 8,
        speed: 0.9,
        curve: 1.4,
        pitch: 42,
        bearing: -8,
        essential: true,
      });
    }
  }, [centerLat, centerLon, zoom]);

  // ---------------- selected asset ring ----------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !bundle || !sourcesReady) return;
    const found = bundle.assets.find((a) => a.asset_id === selectedAssetId);
    const src = map.getSource('selected-asset') as mapboxgl.GeoJSONSource | undefined;
    if (!src) return;
    if (found) {
      src.setData({
        type: 'FeatureCollection',
        features: [
          {
            type: 'Feature',
            geometry: { type: 'Point', coordinates: [found.lon, found.lat] },
            properties: { asset_id: found.asset_id },
          },
        ],
      });
    } else {
      src.setData(emptyFC());
    }
  }, [selectedAssetId, bundle, sourcesReady]);

  return <div ref={containerRef} className="absolute inset-0 grid-bg" />;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function firstSymbolLayer(map: mapboxgl.Map): string | undefined {
  const layers = map.getStyle().layers ?? [];
  return layers.find((l) => l.type === 'symbol')?.id;
}

function assetPopupHtml(props: MapAsset & { r_color: string; r_size: number }): string {
  return `<div style="min-width:208px">
    <div style="font-weight:600;letter-spacing:-0.01em;">${props.asset_id}</div>
    <div style="margin-top:2px;color:#A9BED1;font-size:11px;">${String(props.asset_type).toUpperCase()} on ${props.feeder_id}</div>
    <div style="margin-top:8px;display:flex;gap:6px;align-items:center;">
      <span style="display:inline-block;padding:2px 8px;border-radius:999px;font-size:10px;text-transform:uppercase;letter-spacing:0.06em;background:${RISK_COLORS[props.risk_band]}22;color:${RISK_COLORS[props.risk_band]};border:1px solid ${RISK_COLORS[props.risk_band]}66;">${props.risk_band}</span>
      <span style="font-size:11px;color:#F5FAFF;">risk ${Number(props.risk_score).toFixed(1)}</span>
    </div>
    <div style="margin-top:6px;font-size:11px;color:#A9BED1;">Click to open Asset 360</div>
  </div>`;
}

function emptyFC(): GeoJSON.FeatureCollection {
  return { type: 'FeatureCollection', features: [] };
}

function assetsToFC(assets: MapAsset[]): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: assets.map((a) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [a.lon, a.lat] },
      properties: {
        ...a,
        r_color: RISK_COLORS[a.risk_band] ?? '#18D4FF',
        r_size: RISK_RADIUS[a.risk_band] ?? 4,
      },
    })),
  };
}

function assetsToHeatFC(assets: MapAsset[]): GeoJSON.FeatureCollection {
  // Only high + critical contribute to the heat surface.
  const weighted = assets.filter((a) => a.risk_band === 'high' || a.risk_band === 'critical');
  return {
    type: 'FeatureCollection',
    features: weighted.map((a) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [a.lon, a.lat] },
      properties: {
        weight: a.risk_band === 'critical' ? 1.0 : 0.55,
      },
    })),
  };
}

function hazardsToFC(hazards: HazardZone[]): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: hazards.map((h) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [h.lon, h.lat] },
      properties: { ...h },
    })),
  };
}

function criticalCustomersToFC(cc: CriticalCustomer[]): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: cc.map((c) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [c.lon, c.lat] },
      properties: { ...c },
    })),
  };
}

function depotsToFC(d: Depot[]): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: d.map((x) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [x.lon, x.lat] },
      properties: { ...x },
    })),
  };
}

function mobileGenToFC(m: MobileGenSite[]): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: m.map((x) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [x.lon, x.lat] },
      properties: { ...x },
    })),
  };
}
