import './style.css';
import {
  Map as MaplibreMap,
  NavigationControl,
  AttributionControl,
  TerrainControl,
  Popup,
  setWorkerUrl,
  addProtocol,
  type LngLat,
  type MapLayerMouseEvent,
  type ErrorEvent
} from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
// v6 requires an explicit worker URL or map.on('load') never fires -- see docs-src/basemap.md.
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import { Protocol } from 'pmtiles';

setWorkerUrl(maplibreWorkerUrl);

const protocol = new Protocol();
addProtocol('pmtiles', protocol.tile);

const statusEl = document.getElementById('status') as HTMLParagraphElement;

// Real bbox of the 72-project coverage index (docs-src/discovery-report.md),
// not a guessed "looks about right" Hokkaido center.
const HOKKAIDO_COVERAGE_BOUNDS: [[number, number], [number, number]] = [
  [139.787722, 41.564459],
  [145.25183, 45.48685403853585]
];

interface TerrainSourceConfig {
  tiles_url: string;
  attribution: string;
  label: string;
}

interface CatalogSourceConfig {
  pmtiles_url: string;
  manifest_url: string;
}

// PMTiles features carry ONLY asset_id (startup spec, section on the catalog
// PMTiles). The actual object_url is never derivable from asset_id alone --
// it must be looked up in the published manifest. Guessing a path pattern
// like ".../latest.copc.laz" would also violate the "never a repeatedly
// overwritten latest object" rule, so there is deliberately no fallback path
// construction here: no manifest entry means no Eptium link, full stop.
interface ManifestEntry {
  asset_id: string;
  object_url: string;
}

async function loadJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`HTTP ${res.status} fetching ${url}`);
  }
  return res.json() as Promise<T>;
}

async function loadManifest(manifestUrl: string): Promise<Map<string, string>> {
  const map = new Map<string, string>();
  let res: Response;
  try {
    res = await fetch(manifestUrl);
  } catch {
    return map; // network failure -- treat as "not published yet", not a crash
  }
  if (!res.ok) {
    return map;
  }
  const text = await res.text();
  for (const line of text.split('\n')) {
    if (!line.trim()) continue;
    try {
      const entry = JSON.parse(line) as ManifestEntry;
      map.set(entry.asset_id, entry.object_url);
    } catch {
      console.warn('skipping malformed manifest line', line);
    }
  }
  return map;
}

async function main() {
  const base = import.meta.env.BASE_URL;
  const [terrainConfig, catalogConfig] = await Promise.all([
    loadJson<TerrainSourceConfig>(`${base}config/terrain-source.json`),
    loadJson<CatalogSourceConfig>(`${base}config/catalog-source.json`)
  ]);
  const manifest = await loadManifest(catalogConfig.manifest_url);

  const map = new MaplibreMap({
    container: 'map',
    style: 'https://stars.optgeo.org/style/bvmap-dark',
    bounds: HOKKAIDO_COVERAGE_BOUNDS,
    fitBoundsOptions: { padding: 24 },
    // Namespaced so the URL reads #map=z/lat/lng rather than a bare hash --
    // keeps the fragment identifiable if anything else ever shares the URL.
    // A URL that already carries #map=... on load wins over `bounds` above,
    // which is exactly what makes a shared/bookmarked view work.
    hash: 'map',
    // A style URL makes MapLibre add its own default attribution control;
    // disable it here so the explicit compact one below isn't duplicated.
    attributionControl: false
  });

  map.addControl(new NavigationControl(), 'top-right');
  map.addControl(new AttributionControl({ compact: true }), 'bottom-right');

  map.on('load', () => {
    map.addSource('terrain-dem', {
      type: 'raster-dem',
      tiles: [`${terrainConfig.tiles_url}/{z}/{x}/{y}`],
      tileSize: 512,
      attribution: terrainConfig.attribution
    });
    // No vertical exaggeration, as a matter of policy -- this is survey/
    // provenance-oriented tooling, not a scenic viewer, and an exaggerated
    // terrain would misrepresent the data.
    map.setTerrain({ source: 'terrain-dem', exaggeration: 1.0 });
    map.addControl(new TerrainControl({ source: 'terrain-dem', exaggeration: 1.0 }), 'top-right');

    addCatalogLayer(map, catalogConfig, manifest, statusEl);
  });

  map.on('error', (e: ErrorEvent) => {
    console.error('map error', e.error);
  });
}

function addCatalogLayer(
  map: MaplibreMap,
  catalogConfig: CatalogSourceConfig,
  manifest: Map<string, string>,
  statusEl: HTMLParagraphElement
) {
  map.addSource('copc-footprints', {
    type: 'vector',
    url: `pmtiles://${catalogConfig.pmtiles_url}`
  });

  map.addLayer({
    id: 'copc-footprints-fill',
    type: 'fill',
    source: 'copc-footprints',
    'source-layer': 'footprints',
    paint: {
      'fill-color': '#4fd1c5',
      'fill-opacity': 0.35
    }
  });

  map.addLayer({
    id: 'copc-footprints-line',
    type: 'line',
    source: 'copc-footprints',
    'source-layer': 'footprints',
    paint: {
      'line-color': '#4fd1c5',
      'line-width': 1.5
    }
  });

  map.on('click', 'copc-footprints-fill', (e: MapLayerMouseEvent) => {
    const feature = e.features?.[0];
    const assetId = feature?.properties?.asset_id;
    if (!assetId || !e.lngLat) return;
    showAssetPopup(map, e.lngLat, String(assetId), manifest.get(String(assetId)));
  });

  map.on('mouseenter', 'copc-footprints-fill', () => {
    map.getCanvas().style.cursor = 'pointer';
  });
  map.on('mouseleave', 'copc-footprints-fill', () => {
    map.getCanvas().style.cursor = '';
  });

  // pmtiles.js reports a load failure as a source/tile error event rather
  // than a rejected promise -- catch it here so "not published yet" reads
  // as an honest empty state instead of a silently broken layer.
  let sawError = false;
  map.on('error', (e: ErrorEvent & { sourceId?: string }) => {
    if (e.sourceId === 'copc-footprints' && !sawError) {
      sawError = true;
      statusEl.textContent =
        '公開済みのCOPCカタログはまだありません(パイプライン未実行)。地図基盤・地形のみ表示しています。';
    }
  });
  // Give the source a moment to either load or fail before declaring success,
  // since there's no direct "this vector source loaded with N features" event.
  setTimeout(() => {
    if (!sawError) {
      statusEl.textContent = 'カタログを読み込みました。フットプリントをクリックすると詳細が表示されます。';
    }
  }, 3000);
}

function eptiumUrl(copcUrl: string): string {
  return `https://eptium.com/?copc=${encodeURIComponent(copcUrl)}`;
}

function showAssetPopup(map: MaplibreMap, lngLat: LngLat, assetId: string, objectUrl: string | undefined) {
  const container = document.createElement('div');
  container.className = 'popup-content';

  const idEl = document.createElement('p');
  idEl.className = 'popup-asset-id';
  idEl.textContent = assetId;
  container.appendChild(idEl);

  if (objectUrl) {
    const note = document.createElement('p');
    note.className = 'popup-note';
    note.textContent = 'Eptiumは本プロジェクトと無関係の第三者ビューアです。開くと外部サイトに移動します。';
    container.appendChild(note);

    const button = document.createElement('a');
    button.href = eptiumUrl(objectUrl);
    button.target = '_blank';
    button.rel = 'noopener noreferrer';
    button.className = 'popup-eptium-button';
    button.textContent = 'Eptiumで開く';
    container.appendChild(button);
  } else {
    const note = document.createElement('p');
    note.className = 'popup-note';
    note.textContent = '公開先URLがカタログに見つかりませんでした。';
    container.appendChild(note);
  }

  new Popup({ closeButton: true }).setLngLat(lngLat).setDOMContent(container).addTo(map);
}

main().catch((err) => {
  console.error(err);
  statusEl.textContent = `初期化に失敗しました: ${err instanceof Error ? err.message : String(err)}`;
});
