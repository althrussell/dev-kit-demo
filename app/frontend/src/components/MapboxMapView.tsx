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
  VegetationLine,
  OutageLine,
  RiskExtrusion,
  InspectionStaleAsset,
  HazardImpactAsset,
  HazardPolygon,
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

export const MAPBOX_STYLES = {
  satellite_streets: 'mapbox://styles/mapbox/satellite-streets-v12',
  satellite: 'mapbox://styles/mapbox/satellite-v9',
  streets: 'mapbox://styles/mapbox/streets-v12',
  outdoors: 'mapbox://styles/mapbox/outdoors-v12',
  light: 'mapbox://styles/mapbox/light-v11',
  dark: 'mapbox://styles/mapbox/dark-v11',
} as const;
export type MapStyleId = keyof typeof MAPBOX_STYLES;
export const DEFAULT_MAP_STYLE: MapStyleId = 'satellite_streets';

export interface MapboxMapViewProps {
  bundle: MapBundle | null;
  centerLat?: number | null;
  centerLon?: number | null;
  zoom?: number;
  onAssetClick?: (asset: MapAsset) => void;
  token: string;
  mapStyle?: MapStyleId;
}

export function MapboxMapView({
  bundle,
  centerLat,
  centerLon,
  zoom,
  onAssetClick,
  token,
  mapStyle = DEFAULT_MAP_STYLE,
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
      style: MAPBOX_STYLES[mapStyle],
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

    // Sources + layers must be (re-)added every time a style finishes loading,
    // because `map.setStyle(...)` wipes them.  Interactions/animations stay
    // bound to the map itself, so they survive style swaps and are wired
    // separately in `installInteractions` below.
    const installSourcesAndLayers = () => {
      setSourcesReady(false);
      // Animated cyclone storm fan-out — built from hazards by hazard_type=cyclone.
      map.addSource('hazards', { type: 'geojson', data: emptyFC() });
      map.addSource('hazards-cyclone', { type: 'geojson', data: emptyFC() });
      map.addSource('critical-customers', { type: 'geojson', data: emptyFC() });
      map.addSource('depots', { type: 'geojson', data: emptyFC() });
      map.addSource('mobile-gen', { type: 'geojson', data: emptyFC() });
      map.addSource('assets', { type: 'geojson', data: emptyFC() });
      map.addSource('selected-asset', { type: 'geojson', data: emptyFC() });
      map.addSource('asset-heat', { type: 'geojson', data: emptyFC() });
      map.addSource('vegetation-lines', { type: 'geojson', data: emptyFC() });
      map.addSource('outage-lines', { type: 'geojson', data: emptyFC() });
      map.addSource('risk-extrusions', { type: 'geojson', data: emptyFC() });
      map.addSource('hazard-polygons', { type: 'geojson', data: emptyFC() });
      map.addSource('hazard-impact-assets', { type: 'geojson', data: emptyFC() });
      map.addSource('inspection-stale', { type: 'geojson', data: emptyFC() });

      const beforeId = firstSymbolLayer(map);

      // Real PostGIS-buffered hazard polygons (geography Polygon) painted
      // underneath the circle approximations. Drops gracefully to empty
      // when Lakebase isn't reachable.
      map.addLayer(
        {
          id: 'hazard-polygons-fill',
          type: 'fill',
          source: 'hazard-polygons',
          paint: {
            'fill-color': [
              'match', ['get', 'hazard_type'],
              'cyclone', '#7C3AED',
              'flood', '#1E88E5',
              'bushfire', '#E5484D',
              'heat', '#FFB020',
              'storm', '#18D4FF',
              'coastal_corrosion', '#D8B06A',
              '#7C3AED',
            ],
            'fill-opacity': [
              'interpolate', ['linear'], ['get', 'severity_score'],
              30, 0.05,
              70, 0.18,
              99, 0.28,
            ],
          },
        },
        beforeId,
      );
      map.addLayer(
        {
          id: 'hazard-polygons-outline',
          type: 'line',
          source: 'hazard-polygons',
          layout: { 'line-join': 'round' },
          paint: {
            'line-color': [
              'match', ['get', 'hazard_type'],
              'cyclone', '#A26FF7',
              'flood', '#5BA3F0',
              'bushfire', '#FF6B6F',
              'heat', '#FFD27A',
              'storm', '#74E8FF',
              'coastal_corrosion', '#E8C68B',
              '#A26FF7',
            ],
            'line-width': 0.6,
            'line-opacity': 0.45,
          },
        },
        beforeId,
      );

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

      // Outage feeder lines — substation → asset centroid, width by outage count.
      map.addLayer(
        {
          id: 'outage-lines-glow',
          type: 'line',
          source: 'outage-lines',
          layout: { 'line-cap': 'round', 'line-join': 'round' },
          paint: {
            'line-color': '#E5484D',
            'line-blur': 4,
            'line-opacity': 0.35,
            'line-width': [
              'interpolate', ['linear'], ['get', 'outage_count'],
              0, 1,
              20, 8,
              80, 18,
            ],
          },
        },
        beforeId,
      );
      map.addLayer(
        {
          id: 'outage-lines-layer',
          type: 'line',
          source: 'outage-lines',
          layout: { 'line-cap': 'round', 'line-join': 'round' },
          paint: {
            'line-color': [
              'interpolate', ['linear'], ['get', 'outage_count'],
              0, '#FFB020',
              30, '#E5484D',
              80, '#FFE7E7',
            ],
            'line-width': [
              'interpolate', ['linear'], ['get', 'outage_count'],
              0, 0.6,
              20, 2.2,
              80, 5,
            ],
            'line-opacity': 0.95,
          },
        },
        beforeId,
      );

      // Vegetation backlog spans rendered as gradient lines (green→amber→red).
      map.addLayer(
        {
          id: 'vegetation-lines-layer',
          type: 'line',
          source: 'vegetation-lines',
          layout: { 'line-cap': 'round', 'line-join': 'round' },
          paint: {
            'line-color': [
              'interpolate', ['linear'], ['get', 'risk_score'],
              0, '#2FB344',
              40, '#18D4FF',
              70, '#FFB020',
              90, '#E5484D',
            ],
            'line-width': [
              'interpolate', ['linear'], ['zoom'],
              5, 1.2,
              9, 2.4,
              12, 4,
            ],
            'line-opacity': [
              'interpolate', ['linear'], ['zoom'],
              4, 0.55,
              9, 0.9,
            ],
          },
        },
        beforeId,
      );

      // PostGIS impact-asset halo — assets within ST_DWithin range of a severe
      // hazard, returned by Lakebase. Glowing magenta ring underlay so the
      // user can see exactly *which* assets are in the impact corridor.
      map.addLayer(
        {
          id: 'hazard-impact-halo',
          type: 'circle',
          source: 'hazard-impact-assets',
          paint: {
            'circle-radius': [
              'interpolate', ['linear'], ['zoom'],
              4, 4,
              8, 10,
              12, 18,
            ],
            'circle-color': '#E5478A',
            'circle-opacity': 0.18,
            'circle-stroke-color': '#FF9CC8',
            'circle-stroke-width': 0.6,
            'circle-stroke-opacity': 0.55,
            'circle-blur': 0.5,
          },
        },
        beforeId,
      );

      // Stale-inspection halos — only painted for the field_inspection_review
      // scenario. Amber translucent ring whose radius and opacity scale with
      // how overdue + how hard-to-access the asset is, so the worst stale
      // inspections "ring loud" on the map.
      map.addLayer(
        {
          id: 'inspection-stale-halo',
          type: 'circle',
          source: 'inspection-stale',
          paint: {
            'circle-radius': [
              'interpolate', ['linear'], ['zoom'],
              4, [
                'interpolate', ['linear'], ['get', 'overdue_days'],
                0, 4,
                365, 8,
                1500, 14,
                3000, 18,
              ],
              10, [
                'interpolate', ['linear'], ['get', 'overdue_days'],
                0, 8,
                365, 16,
                1500, 26,
                3000, 36,
              ],
            ],
            'circle-color': [
              'interpolate', ['linear'], ['get', 'overdue_days'],
              0, '#D8B06A',
              365, '#FFB020',
              1500, '#FF8B3D',
              3000, '#E5484D',
            ],
            'circle-opacity': [
              'interpolate', ['linear'], ['get', 'access_difficulty_score'],
              0, 0.12,
              50, 0.22,
              90, 0.36,
            ],
            'circle-stroke-color': '#FFE3A8',
            'circle-stroke-width': 0.8,
            'circle-stroke-opacity': 0.6,
            'circle-blur': 0.3,
          },
        },
        beforeId,
      );

      // 3D risk extrusions — top-N assets shown as illuminated bars.
      // minzoom 5 (was 6) so they appear at the default Queensland view.
      map.addLayer(
        {
          id: 'risk-extrusions-layer',
          type: 'fill-extrusion',
          source: 'risk-extrusions',
          minzoom: 5,
          paint: {
            'fill-extrusion-color': [
              'match', ['get', 'risk_band'],
              'critical', '#E5484D',
              'high', '#FFB020',
              'medium', '#18D4FF',
              '#7C3AED',
            ],
            'fill-extrusion-height': ['get', 'height_m'],
            'fill-extrusion-base': 0,
            'fill-extrusion-opacity': 0.78,
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
      // depth when inspecting critical customers. Only the Mapbox vector
      // styles ship the `composite` source with a `building` source-layer;
      // pure satellite styles do not, so we skip it there.
      const compositeSource = map.getSource('composite') as
        | (mapboxgl.AnySourceImpl & { vectorLayerIds?: string[] })
        | undefined;
      const hasBuildings = !!compositeSource?.vectorLayerIds?.includes('building');
      if (hasBuildings && !map.getLayer('buildings-3d')) {
        try {
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
        } catch (e) {
          // Style doesn't expose buildings — ignore silently.
          console.warn('buildings-3d skipped:', e);
        }
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

      // Signal to the bundle / selected-asset effects that every source +
      // layer is now present, so it's safe to call `getSource('assets')`,
      // `setData(...)`, `setLayoutProperty(...)`, etc.  This fires both on
      // initial load AND after every `setStyle(...)` so the data is re-pushed.
      setSourcesReady(true);
    };

    // Interactions and animation loops are bound once and persist across
    // style swaps. Popups, mouse handlers, and rAF tickers attach to the map
    // instance itself, not to specific style layers, so they survive
    // `setStyle()` cleanly.
    const installInteractions = () => {
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
    };

    // `style.load` fires on the initial style download AND after every
    // `setStyle()`. We re-add sources + layers there so a style swap can
    // never leave the map blank.  `load` only fires once on the very first
    // style load — perfect for one-shot interaction wiring.
    map.on('style.load', installSourcesAndLayers);
    map.once('load', installInteractions);

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
    // `mapStyle` is intentionally not a dependency — style changes are handled
    // by the dedicated effect below using `map.setStyle()`, which preserves
    // the map instance, camera, and bound interactions.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  // ---------------- style switch ----------------
  // Swap basemap on demand. `setStyle` wipes all custom sources/layers, but
  // `installSourcesAndLayers` is bound to `style.load`, so they're added back
  // automatically. We flip `sourcesReady` false here so the bundle effect
  // won't try to call `setData` on a source that no longer exists during the
  // brief swap window.
  const currentStyleRef = useRef<MapStyleId>(mapStyle);
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (currentStyleRef.current === mapStyle) return;
    currentStyleRef.current = mapStyle;
    setSourcesReady(false);
    map.setStyle(MAPBOX_STYLES[mapStyle]);
  }, [mapStyle]);

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
    (map.getSource('vegetation-lines') as mapboxgl.GeoJSONSource | undefined)?.setData(
      vegetationLinesToFC(bundle.vegetation_lines ?? []),
    );
    (map.getSource('outage-lines') as mapboxgl.GeoJSONSource | undefined)?.setData(
      outageLinesToFC(bundle.outage_lines ?? []),
    );
    (map.getSource('risk-extrusions') as mapboxgl.GeoJSONSource | undefined)?.setData(
      riskExtrusionsToFC(bundle.risk_extrusions ?? []),
    );
    (map.getSource('hazard-polygons') as mapboxgl.GeoJSONSource | undefined)?.setData(
      hazardPolygonsToFC(bundle.hazard_polygons ?? []),
    );
    (map.getSource('hazard-impact-assets') as mapboxgl.GeoJSONSource | undefined)?.setData(
      hazardImpactToFC(bundle.hazard_impact_assets ?? []),
    );
    (map.getSource('inspection-stale') as mapboxgl.GeoJSONSource | undefined)?.setData(
      inspectionStaleToFC(bundle.inspection_stale_assets ?? []),
    );
  }, [bundle, sourcesReady]);

  // ---------------- layer toggles ----------------
  // The user's sidebar toggles + the scenario_summary.primary_layers preset
  // combine: a layer is visible iff the user enabled it AND the scenario
  // primary layer set lists it (or the layer is not scenario-gated).
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !sourcesReady) return;
    const primary = bundle?.scenario_summary?.primary_layers ?? [];
    const inScenario = (name: string) => primary.length === 0 || primary.includes(name);

    const set = (id: string, visible: boolean) => {
      if (!map.getLayer(id)) return;
      map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none');
    };

    set('assets-layer', layers.assets && inScenario('assets'));
    set('asset-heat', layers.assets && inScenario('assets'));
    set('hazards-fill', layers.hazards && inScenario('hazards'));
    set('hazards-cyclone-pulse', layers.hazards && inScenario('hazards'));
    set('hazards-cyclone-core', layers.hazards && inScenario('hazards'));
    set('hazard-polygons-fill', layers.hazards && inScenario('hazards'));
    set('hazard-polygons-outline', layers.hazards && inScenario('hazards'));
    set('critical-customers-layer', layers.critical_customers && inScenario('critical_customers'));
    set('depots-layer', layers.depots && inScenario('depots'));
    set('mobile-gen-layer', layers.mobile_gen && inScenario('mobile_gen'));
    // Scenario-only layers: visible only when in the scenario's primary set.
    // They have no sidebar toggle — the scenario itself controls them.
    set('vegetation-lines-layer', inScenario('vegetation_lines'));
    set('outage-lines-layer', inScenario('outage_lines'));
    set('outage-lines-glow', inScenario('outage_lines'));
    set('risk-extrusions-layer', inScenario('risk_extrusions'));
    set('inspection-stale-halo', inScenario('inspection_stale'));
    // PostGIS impact-asset halo is visible whenever the scenario uses hazards
    // (storm/normal/vegetation). It piggybacks on the hazards layer toggle so
    // turning hazards off also hides the impact ring.
    set('hazard-impact-halo', layers.hazards && inScenario('hazards'));

    // When the scenario's headline visualisation is a non-asset layer
    // (vegetation lines, outage glow lines, 3D extrusions, or stale halos),
    // dim the dense asset dot cloud so the headline layer dominates the eye.
    // We do this with `circle-opacity` rather than hiding assets entirely so
    // users can still see context.
    if (map.getLayer('assets-layer')) {
      const dimming = bundle?.scenario_summary?.scenario_id;
      const isLineDominant =
        dimming === 'vegetation_program' ||
        dimming === 'reliability_improvement' ||
        dimming === 'field_inspection_review';
      const isExtrusionDominant = dimming === 'capex_prioritisation';
      let opacityExpr: mapboxgl.ExpressionSpecification | number;
      if (isLineDominant) {
        opacityExpr = [
          'interpolate', ['linear'], ['zoom'],
          4, 0.35,
          9, 0.55,
        ];
      } else if (isExtrusionDominant) {
        opacityExpr = [
          'interpolate', ['linear'], ['zoom'],
          4, 0.55,
          9, 0.75,
        ];
      } else {
        opacityExpr = [
          'interpolate', ['linear'], ['zoom'],
          4, 0.7,
          9, 0.92,
        ];
      }
      map.setPaintProperty('assets-layer', 'circle-opacity', opacityExpr);
    }
  }, [layers, sourcesReady, bundle]);

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

function vegetationLinesToFC(lines: VegetationLine[]): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: lines.map((v) => ({
      type: 'Feature',
      geometry: {
        type: 'LineString',
        coordinates: [
          [v.from_lon, v.from_lat],
          [v.to_lon, v.to_lat],
        ],
      },
      properties: {
        vegetation_span_id: v.vegetation_span_id,
        risk_score: v.risk_score,
        overdue_days: v.overdue_days,
        treatment_priority: v.treatment_priority ?? '',
        feeder_id: v.feeder_id,
      },
    })),
  };
}

function outageLinesToFC(lines: OutageLine[]): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: lines.map((o) => ({
      type: 'Feature',
      geometry: {
        type: 'LineString',
        coordinates: [
          [o.from_lon, o.from_lat],
          [o.to_lon, o.to_lat],
        ],
      },
      properties: {
        feeder_id: o.feeder_id,
        feeder_name: o.feeder_name,
        outage_count: o.outage_count,
        saidi_minutes: o.saidi_minutes,
        customers_interrupted: o.customers_interrupted,
      },
    })),
  };
}

function hazardPolygonsToFC(polys: HazardPolygon[]): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: polys
      .filter((p) => p.polygon != null)
      .map((p) => ({
        type: 'Feature',
        geometry: p.polygon as GeoJSON.Polygon,
        properties: {
          hazard_zone_id: p.hazard_zone_id,
          hazard_type: p.hazard_type,
          zone_name: p.zone_name,
          severity_score: p.severity_score,
          radius_km: p.radius_km,
          seasonal_window: p.seasonal_window,
        },
      })),
  };
}

function hazardImpactToFC(items: HazardImpactAsset[]): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: items.map((a) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [a.lon, a.lat] },
      properties: {
        asset_id: a.asset_id,
        feeder_id: a.feeder_id,
        risk_band: a.risk_band,
        risk_score: a.risk_score,
        distance_m: a.distance_m,
        hazard_severity: a.hazard_severity,
      },
    })),
  };
}

function inspectionStaleToFC(items: InspectionStaleAsset[]): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: items.map((a) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [a.lon, a.lat] },
      properties: {
        asset_id: a.asset_id,
        feeder_id: a.feeder_id,
        risk_band: a.risk_band,
        overdue_days: a.overdue_days,
        access_difficulty_score: a.access_difficulty_score,
      },
    })),
  };
}

// Build a tiny rectangle around (lat, lon) so the fill-extrusion has a footprint.
// We size it ~80m at the equator (≈ 0.00072° lat / 0.00081° lon at QLD latitudes).
function riskExtrusionsToFC(items: RiskExtrusion[]): GeoJSON.FeatureCollection {
  const halfLat = 0.0008;
  const halfLon = 0.0009;
  return {
    type: 'FeatureCollection',
    features: items.map((r) => {
      const ring: GeoJSON.Position[] = [
        [r.lon - halfLon, r.lat - halfLat],
        [r.lon + halfLon, r.lat - halfLat],
        [r.lon + halfLon, r.lat + halfLat],
        [r.lon - halfLon, r.lat + halfLat],
        [r.lon - halfLon, r.lat - halfLat],
      ];
      return {
        type: 'Feature',
        geometry: { type: 'Polygon', coordinates: [ring] },
        properties: {
          asset_id: r.asset_id,
          risk_band: r.risk_band,
          risk_score: r.risk_score,
          height_m: r.height_m,
        },
      };
    }),
  };
}
