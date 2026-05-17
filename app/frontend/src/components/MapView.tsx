import { useEffect, useRef } from 'react';
import maplibregl, { type Map, type GeoJSONSource } from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import type { MapBundle, MapAsset, HazardZone, CriticalCustomer, Depot, MobileGenSite } from '../types';
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

const DARK_STYLE = {
  version: 8 as const,
  sources: {
    'carto-dark': {
      type: 'raster' as const,
      tiles: [
        'https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
        'https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
        'https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
        'https://d.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
      ],
      tileSize: 256,
      attribution:
        '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
      maxzoom: 19,
    },
  },
  layers: [
    {
      id: 'carto-dark',
      type: 'raster' as const,
      source: 'carto-dark',
    },
  ],
};

export interface MapViewProps {
  bundle: MapBundle | null;
  centerLat?: number | null;
  centerLon?: number | null;
  zoom?: number;
  onAssetClick?: (asset: MapAsset) => void;
}

export function MapView({ bundle, centerLat, centerLon, zoom, onAssetClick }: MapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<Map | null>(null);
  const initialFitRef = useRef(false);
  const { layers, selectedAssetId } = useAppState();
  const nav = useNavigate();

  // Init.
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: DARK_STYLE,
      center: [145.0, -22.5],
      zoom: 4.6,
      attributionControl: { compact: true },
      pitch: 18,
      bearing: 0,
      hash: false,
    });
    map.addControl(
      new maplibregl.NavigationControl({ visualizePitch: true, showCompass: true }),
      'top-right',
    );
    mapRef.current = map;

    map.on('load', () => {
      // Sources.
      map.addSource('assets', { type: 'geojson', data: emptyFC() });
      map.addSource('hazards', { type: 'geojson', data: emptyFC() });
      map.addSource('critical-customers', { type: 'geojson', data: emptyFC() });
      map.addSource('depots', { type: 'geojson', data: emptyFC() });
      map.addSource('mobile-gen', { type: 'geojson', data: emptyFC() });
      map.addSource('selected-asset', { type: 'geojson', data: emptyFC() });

      // Layers — hazards beneath everything, asset circles on top.
      map.addLayer({
        id: 'hazards-fill',
        type: 'circle',
        source: 'hazards',
        paint: {
          'circle-radius': [
            'interpolate',
            ['linear'],
            ['zoom'],
            4, ['*', ['get', 'radius_km'], 0.6],
            10, ['*', ['get', 'radius_km'], 4],
          ],
          'circle-color': [
            'match',
            ['get', 'hazard_type'],
            'cyclone', '#7C3AED',
            'flood', '#1E88E5',
            'bushfire', '#E5484D',
            'heat', '#FFB020',
            'storm', '#18D4FF',
            'coastal_corrosion', '#D8B06A',
            '#7C3AED',
          ],
          'circle-opacity': 0.10,
          'circle-stroke-color': '#A9BED1',
          'circle-stroke-width': 0.4,
          'circle-stroke-opacity': 0.35,
        },
      });

      // Depots
      map.addLayer({
        id: 'depots-layer',
        type: 'circle',
        source: 'depots',
        paint: {
          'circle-radius': 5,
          'circle-color': '#D8B06A',
          'circle-stroke-color': '#071827',
          'circle-stroke-width': 1.4,
        },
      });

      // Mobile gen
      map.addLayer({
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
      });

      // Critical customers
      map.addLayer({
        id: 'critical-customers-layer',
        type: 'circle',
        source: 'critical-customers',
        paint: {
          'circle-radius': 4,
          'circle-color': '#FFB020',
          'circle-stroke-color': '#071827',
          'circle-stroke-width': 1.4,
        },
      });

      // Assets (heavy layer)
      map.addLayer({
        id: 'assets-layer',
        type: 'circle',
        source: 'assets',
        paint: {
          'circle-radius': [
            'interpolate',
            ['linear'],
            ['zoom'],
            4, ['*', ['coalesce', ['get', 'r_size'], 3], 0.7],
            8, ['get', 'r_size'],
            12, ['*', ['coalesce', ['get', 'r_size'], 3], 1.4],
          ],
          'circle-color': ['coalesce', ['get', 'r_color'], '#18D4FF'],
          'circle-opacity': 0.85,
          'circle-stroke-color': '#071827',
          'circle-stroke-width': 0.6,
        },
      });

      // Selected asset emphasis ring
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
      map.addLayer({
        id: 'selected-asset-pulse',
        type: 'circle',
        source: 'selected-asset',
        paint: {
          'circle-radius': 22,
          'circle-color': '#18D4FF',
          'circle-opacity': 0.10,
        },
      });

      // Interactions: hover popup
      const popup = new maplibregl.Popup({
        closeButton: false,
        closeOnClick: false,
        offset: 12,
      });
      map.on('mouseenter', 'assets-layer', (e) => {
        if (!e.features?.[0]) return;
        map.getCanvas().style.cursor = 'pointer';
        const f = e.features[0];
        const props = f.properties as MapAsset & { r_color: string; r_size: number };
        popup
          .setLngLat((f.geometry as GeoJSON.Point).coordinates as [number, number])
          .setHTML(
            `<div style="min-width:200px">
              <div style="font-weight:600;letter-spacing:-0.01em;">${props.asset_id}</div>
              <div style="margin-top:2px;color:#A9BED1;font-size:11px;">${props.asset_type.toUpperCase()} on ${props.feeder_id}</div>
              <div style="margin-top:8px;display:flex;gap:6px;align-items:center;">
                <span style="display:inline-block;padding:2px 8px;border-radius:999px;font-size:10px;text-transform:uppercase;letter-spacing:0.06em;background:${RISK_COLORS[props.risk_band]}22;color:${RISK_COLORS[props.risk_band]};border:1px solid ${RISK_COLORS[props.risk_band]}66;">${props.risk_band}</span>
                <span style="font-size:11px;color:#F5FAFF;">risk ${Number(props.risk_score).toFixed(1)}</span>
              </div>
              <div style="margin-top:6px;font-size:11px;color:#A9BED1;">Click to open Asset 360</div>
            </div>`,
          )
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
        onAssetClick?.(props);
        nav(`/assets/${props.asset_id}`);
      });

      map.on('mouseenter', 'critical-customers-layer', () => (map.getCanvas().style.cursor = 'pointer'));
      map.on('mouseleave', 'critical-customers-layer', () => (map.getCanvas().style.cursor = ''));
      map.on('click', 'critical-customers-layer', (e) => {
        const f = e.features?.[0];
        if (!f) return;
        const p = f.properties as CriticalCustomer;
        new maplibregl.Popup({ offset: 12 })
          .setLngLat((f.geometry as GeoJSON.Point).coordinates as [number, number])
          .setHTML(
            `<div><div style="font-weight:600;">${p.site_name}</div><div style="margin-top:2px;color:#A9BED1;font-size:11px;">${p.site_type.replace(/_/g, ' ')} · ${p.feeder_id}</div></div>`,
          )
          .addTo(map);
      });

      map.on('mouseenter', 'depots-layer', () => (map.getCanvas().style.cursor = 'pointer'));
      map.on('mouseleave', 'depots-layer', () => (map.getCanvas().style.cursor = ''));
      map.on('click', 'depots-layer', (e) => {
        const f = e.features?.[0];
        if (!f) return;
        const p = f.properties as Depot;
        new maplibregl.Popup({ offset: 12 })
          .setLngLat((f.geometry as GeoJSON.Point).coordinates as [number, number])
          .setHTML(
            `<div><div style="font-weight:600;">${p.depot_name}</div><div style="margin-top:2px;color:#A9BED1;font-size:11px;">Crew ${p.crew_count} · Mobile gen ${p.mobile_generation_units}</div></div>`,
          )
          .addTo(map);
      });
    });
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [nav, onAssetClick]);

  // Update bundle.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !bundle) return;
    const ensure = (fn: () => void) => {
      if (!map.isStyleLoaded()) {
        map.once('load', fn);
      } else {
        fn();
      }
    };
    ensure(() => {
      const assetsSrc = map.getSource('assets') as GeoJSONSource | undefined;
      if (assetsSrc) assetsSrc.setData(assetsToFC(bundle.assets));
      const hazardsSrc = map.getSource('hazards') as GeoJSONSource | undefined;
      if (hazardsSrc) hazardsSrc.setData(hazardsToFC(bundle.hazards));
      const ccSrc = map.getSource('critical-customers') as GeoJSONSource | undefined;
      if (ccSrc) ccSrc.setData(criticalCustomersToFC(bundle.critical_customers));
      const depotsSrc = map.getSource('depots') as GeoJSONSource | undefined;
      if (depotsSrc) depotsSrc.setData(depotsToFC(bundle.depots));
      const mgSrc = map.getSource('mobile-gen') as GeoJSONSource | undefined;
      if (mgSrc) mgSrc.setData(mobileGenToFC(bundle.mobile_gen_sites));
    });
  }, [bundle]);

  // Update visibility per layer toggles.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const set = (id: string, visible: boolean) => {
      if (!map.getLayer(id)) return;
      map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none');
    };
    set('assets-layer', layers.assets);
    set('hazards-fill', layers.hazards);
    set('critical-customers-layer', layers.critical_customers);
    set('depots-layer', layers.depots);
    set('mobile-gen-layer', layers.mobile_gen);
  }, [layers]);

  // Center / zoom updates.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (centerLat != null && centerLon != null) {
      map.flyTo({ center: [centerLon, centerLat], zoom: zoom ?? 8, speed: 0.9, curve: 1.4 });
    }
  }, [centerLat, centerLon, zoom]);

  // After first asset bundle, fit to data bounds.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !bundle || initialFitRef.current) return;
    if (bundle.assets.length < 5) return;
    const lats = bundle.assets.map((a) => a.lat);
    const lons = bundle.assets.map((a) => a.lon);
    const south = Math.min(...lats);
    const north = Math.max(...lats);
    const west = Math.min(...lons);
    const east = Math.max(...lons);
    map.fitBounds(
      [
        [west, south],
        [east, north],
      ],
      { padding: 60, duration: 1200, maxZoom: 9 },
    );
    initialFitRef.current = true;
  }, [bundle]);

  // Selected asset ring.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !bundle) return;
    const found = bundle.assets.find((a) => a.asset_id === selectedAssetId);
    const src = map.getSource('selected-asset') as GeoJSONSource | undefined;
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
  }, [selectedAssetId, bundle]);

  return <div ref={containerRef} className="absolute inset-0 grid-bg" />;
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
