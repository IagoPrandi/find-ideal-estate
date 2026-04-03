import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Layers } from "lucide-react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { API_BASE, getBusLineDetails, getBusStopDetails, getJourneyTransportPoints, getJourneyZonesList, getTransportStopDetails, getZoneListings } from "../../api/client";
import { WizardPanel } from "../../components/panels";
import { getPoiCategoryMeta, getZonePoiSelectionKey, sortPoiPoints, ZonePoiPointLike, zoneNeedsPoiBackfill } from "../../domain/poi";
import { applyListingsPanelFilters, getListingDisplayPrice, getListingSelectionKey } from "../../lib/listingFormat";
import { getIncludedGreenVegetationLevels, useJourneyStore, useUIStore } from "../../state";

const MAPTILER_KEY =
  import.meta.env.VITE_MAPTILER_API_KEY || (import.meta.env.MODE === "test" ? "test-maptiler-key" : "");

const mapTilerStyleUrl = (key: string) =>
  `https://api.maptiler.com/maps/bright-v2/style.json?key=${encodeURIComponent(key)}`;

const apiTileUrl = (path: string) => `${API_BASE}${path}`;

const BUS_LAYER_LIST = ["bus-line-layer", "bus-stop-layer", "bus-terminal-layer"] as const;
const TRANSPORT_CANDIDATES_SOURCE_ID = "transport-candidates-source-runtime";
const ZONES_SOURCE_ID = "journey-zones-source-runtime";
const ZONE_POIS_SOURCE_ID = "journey-zone-pois-source-runtime";
const LISTINGS_SOURCE_ID = "journey-listings-source-runtime";
const POPUP_PERSIST_LAYER_LIST = [...BUS_LAYER_LIST, "zone-pois-highlight-layer", "zone-pois-layer"] as const;
const LAYER_TOGGLE_BUTTON_CLASS = "pointer-events-auto flex h-8 w-8 items-center justify-center rounded-lg border border-slate-100 bg-white/95 text-slate-500 shadow-md backdrop-blur-md transition-colors hover:bg-pastel-violet-50 hover:text-pastel-violet-600";

const ZONE_COLOR_PALETTE = [
  { fill: "#bfdbfe", outline: "#2563eb", label: "#1d4ed8" },
  { fill: "#bbf7d0", outline: "#16a34a", label: "#15803d" },
  { fill: "#fde68a", outline: "#ca8a04", label: "#a16207" },
  { fill: "#fecdd3", outline: "#db2777", label: "#be185d" },
  { fill: "#ddd6fe", outline: "#7c3aed", label: "#6d28d9" },
  { fill: "#fed7aa", outline: "#ea580c", label: "#c2410c" },
  { fill: "#bae6fd", outline: "#0284c7", label: "#0369a1" },
  { fill: "#e9d5ff", outline: "#9333ea", label: "#7e22ce" },
] as const;

type MapOverlayLayerKey =
  | "routes"
  | "metro"
  | "train"
  | "busStops"
  | "transportCandidates"
  | "zones"
  | "pois"
  | "listings"
  | "flood"
  | "green";

type SequentialLayerGroupKey = "transportPoints" | "transportLines" | "green" | "flood";

type SequentialLayerSettings = {
  layerVisibility: Record<MapOverlayLayerKey, boolean>;
  greenEnabled: boolean;
};

const DEFAULT_LAYER_VISIBILITY: Record<MapOverlayLayerKey, boolean> = {
  routes: true,
  metro: true,
  train: true,
  busStops: true,
  transportCandidates: true,
  zones: true,
  pois: true,
  listings: true,
  flood: true,
  green: true,
};

const MAP_LAYER_MENU_ITEMS: Array<{ key: MapOverlayLayerKey; label: string }> = [
  { key: "routes", label: "Rotas de ônibus" },
  { key: "metro", label: "Linhas de metrô" },
  { key: "train", label: "Linhas de trem" },
  { key: "busStops", label: "Paradas e terminais" },
  { key: "transportCandidates", label: "Pontos etapa 2" },
  { key: "zones", label: "Zonas" },
  { key: "pois", label: "POIs da zona" },
  { key: "listings", label: "Imóveis" },
  { key: "flood", label: "Alagamento" },
  { key: "green", label: "Área verde" },
];

const SEQUENTIAL_LAYER_GROUPS: Array<{ key: SequentialLayerGroupKey; sourceId: string }> = [
  { key: "transportPoints", sourceId: "transport-stops-source" },
  { key: "transportLines", sourceId: "transport-lines-source" },
  { key: "green", sourceId: "green-areas-source" },
  { key: "flood", sourceId: "flood-areas-source" },
];

const getSequentialLayerGroupEnabled = (groupKey: SequentialLayerGroupKey, settings: SequentialLayerSettings) => {
  switch (groupKey) {
    case "transportPoints":
      return settings.layerVisibility.busStops || settings.layerVisibility.metro || settings.layerVisibility.train;
    case "transportLines":
      return settings.layerVisibility.routes || settings.layerVisibility.metro || settings.layerVisibility.train;
    case "green":
      return settings.layerVisibility.green && settings.greenEnabled;
    case "flood":
      return settings.layerVisibility.flood;
  }
};

const getFirstEnabledSequentialLayerGroupIndex = (settings: SequentialLayerSettings) => {
  return SEQUENTIAL_LAYER_GROUPS.findIndex((group) => getSequentialLayerGroupEnabled(group.key, settings));
};

const getNextEnabledSequentialLayerGroupIndex = (settings: SequentialLayerSettings, startIndex: number) => {
  for (let index = startIndex; index < SEQUENTIAL_LAYER_GROUPS.length; index += 1) {
    if (getSequentialLayerGroupEnabled(SEQUENTIAL_LAYER_GROUPS[index].key, settings)) {
      return index;
    }
  }
  return -1;
};

const resolveVisibleSequentialLayerGroupIndex = (map: maplibregl.Map, settings: SequentialLayerSettings) => {
  let currentIndex = getFirstEnabledSequentialLayerGroupIndex(settings);
  if (currentIndex === -1) {
    return -1;
  }

  while (currentIndex !== -1) {
    const currentGroup = SEQUENTIAL_LAYER_GROUPS[currentIndex];
    if (!map.isSourceLoaded(currentGroup.sourceId)) {
      return currentIndex;
    }

    const nextIndex = getNextEnabledSequentialLayerGroupIndex(settings, currentIndex + 1);
    if (nextIndex === -1) {
      return currentIndex;
    }
    currentIndex = nextIndex;
  }

  return -1;
};

const isSequentialLayerGroupVisible = (groupKey: SequentialLayerGroupKey, visibleGroupIndex: number, settings: SequentialLayerSettings) => {
  const groupIndex = SEQUENTIAL_LAYER_GROUPS.findIndex((group) => group.key === groupKey);
  if (groupIndex === -1) {
    return false;
  }
  return getSequentialLayerGroupEnabled(groupKey, settings) && visibleGroupIndex >= groupIndex;
};

const EMPTY_FEATURE_COLLECTION: GeoJSON.FeatureCollection<GeoJSON.Geometry> = {
  type: "FeatureCollection",
  features: []
};

const setGeoJsonSourceData = (map: maplibregl.Map, sourceId: string, data: GeoJSON.FeatureCollection<GeoJSON.Geometry>) => {
  const source = map.getSource(sourceId) as maplibregl.GeoJSONSource | undefined;
  if (source) {
    source.setData(data);
  }
};

const getZonePalette = (index: number) => ZONE_COLOR_PALETTE[index % ZONE_COLOR_PALETTE.length];

const toTransportCandidatesFeatureCollection = (
  points: Array<{ id: string; lon: number; lat: number; name?: string | null; route_count: number; source: string; external_id?: string | null }>,
  selectedTransportId: string | null
): GeoJSON.FeatureCollection => ({
  type: "FeatureCollection",
  features: points.map((point) => ({
    type: "Feature",
    geometry: {
      type: "Point",
      coordinates: [point.lon, point.lat]
    },
    properties: {
      id: point.id,
      name: point.name || "Ponto de transporte",
      route_count: point.route_count,
      source: point.source,
      external_id: point.external_id || "",
      selected: point.id === selectedTransportId
    }
  }))
});

const toZonesFeatureCollection = (
  zones: Array<{ id: string; fingerprint: string; travel_time_minutes?: number | null; isochrone_geom?: unknown }>,
  selectedZoneFingerprint: string | null
): GeoJSON.FeatureCollection => ({
  type: "FeatureCollection",
  features: zones
    .filter((zone) => Boolean(zone.isochrone_geom && typeof zone.isochrone_geom === "object"))
    .map((zone, index) => {
      const palette = getZonePalette(index);
      const isSelected = zone.fingerprint === selectedZoneFingerprint;
      return {
        type: "Feature",
        geometry: zone.isochrone_geom as GeoJSON.Geometry,
        properties: {
          id: zone.id,
          fingerprint: zone.fingerprint,
          label: zone.travel_time_minutes ? `${index + 1} · ${zone.travel_time_minutes}m` : String(index + 1),
          selected: isSelected,
          sequence: index + 1,
          fill_color: palette.fill,
          outline_color: palette.outline,
          label_color: palette.label,
        }
      };
    })
});

const toListingsFeatureCollection = (
  listings: Array<Record<string, unknown>>,
  selectedListingKey: string | null
): GeoJSON.FeatureCollection => ({
  type: "FeatureCollection",
  features: listings
    .filter((listing) => typeof listing.lon === "number" && typeof listing.lat === "number")
    .map((listing) => {
      const listingKey = getListingSelectionKey(listing as never);
      return {
        type: "Feature",
        geometry: {
          type: "Point",
          coordinates: [listing.lon as number, listing.lat as number]
        },
        properties: {
          listing_key: listingKey,
          platform: String(listing.platform || "Plataforma"),
          price: getListingDisplayPrice(listing as never) || 0,
          selected: listingKey !== "" && listingKey === selectedListingKey
        }
      };
    })
});

const hexToRgb = (hex: string): [number, number, number] => {
  const normalized = hex.replace("#", "");
  const pair = normalized.length === 3 ? normalized.split("").map((c) => `${c}${c}`) : [normalized.slice(0, 2), normalized.slice(2, 4), normalized.slice(4, 6)];
  return [parseInt(pair[0], 16), parseInt(pair[1], 16), parseInt(pair[2], 16)];
};

const createBusIcon = (fillHex: string) => {
  const width = 30;
  const height = 30;
  const data = new Uint8Array(width * height * 4);
  const [fr, fg, fb] = hexToRgb(fillHex);

  const setPixel = (x: number, y: number, r: number, g: number, b: number, a: number) => {
    if (x < 0 || y < 0 || x >= width || y >= height) return;
    const idx = (y * width + x) * 4;
    data[idx] = r;
    data[idx + 1] = g;
    data[idx + 2] = b;
    data[idx + 3] = a;
  };

  const fillRect = (x0: number, y0: number, w: number, h: number, r: number, g: number, b: number, a: number) => {
    for (let y = y0; y < y0 + h; y += 1) {
      for (let x = x0; x < x0 + w; x += 1) {
        setPixel(x, y, r, g, b, a);
      }
    }
  };

  const fillCircle = (cx: number, cy: number, radius: number, r: number, g: number, b: number, a: number) => {
    const rr = radius * radius;
    for (let y = cy - radius; y <= cy + radius; y += 1) {
      for (let x = cx - radius; x <= cx + radius; x += 1) {
        const dx = x - cx;
        const dy = y - cy;
        if (dx * dx + dy * dy <= rr) {
          setPixel(x, y, r, g, b, a);
        }
      }
    }
  };

  fillRect(4, 6, 20, 14, fr, fg, fb, 255);
  fillRect(7, 9, 14, 5, 255, 255, 255, 230);
  fillRect(6, 18, 16, 2, 255, 255, 255, 224);
  fillCircle(9, 22, 2, fr, fg, fb, 255);
  fillCircle(19, 22, 2, fr, fg, fb, 255);

  return { width, height, data };
};

const createPoiIcon = (fillHex: string, category: string) => {
  const width = 24;
  const height = 24;
  const data = new Uint8Array(width * height * 4);
  const [fr, fg, fb] = hexToRgb(fillHex);

  const setPixel = (x: number, y: number, r: number, g: number, b: number, a: number) => {
    if (x < 0 || y < 0 || x >= width || y >= height) return;
    const idx = (y * width + x) * 4;
    data[idx] = r;
    data[idx + 1] = g;
    data[idx + 2] = b;
    data[idx + 3] = a;
  };

  const fillRect = (x0: number, y0: number, w: number, h: number, r: number, g: number, b: number, a: number) => {
    for (let y = y0; y < y0 + h; y += 1) {
      for (let x = x0; x < x0 + w; x += 1) {
        setPixel(x, y, r, g, b, a);
      }
    }
  };

  const fillCircle = (cx: number, cy: number, radius: number, r: number, g: number, b: number, a: number) => {
    const rr = radius * radius;
    for (let y = cy - radius; y <= cy + radius; y += 1) {
      for (let x = cx - radius; x <= cx + radius; x += 1) {
        const dx = x - cx;
        const dy = y - cy;
        if (dx * dx + dy * dy <= rr) {
          setPixel(x, y, r, g, b, a);
        }
      }
    }
  };

  fillCircle(13, 13, 11, fr, fg, fb, 255);

  switch (category) {
    case "school":
      fillRect(8, 9, 10, 7, 255, 255, 255, 240);
      fillRect(10, 7, 6, 2, 255, 255, 255, 240);
      fillRect(9, 16, 2, 3, 255, 255, 255, 240);
      fillRect(15, 16, 2, 3, 255, 255, 255, 240);
      break;
    case "supermarket":
      fillRect(8, 9, 9, 4, 255, 255, 255, 240);
      fillRect(9, 13, 7, 2, 255, 255, 255, 240);
      fillRect(7, 8, 2, 4, 255, 255, 255, 240);
      fillCircle(10, 18, 1, 255, 255, 255, 240);
      fillCircle(15, 18, 1, 255, 255, 255, 240);
      break;
    case "pharmacy":
      fillRect(11, 7, 4, 12, 255, 255, 255, 240);
      fillRect(7, 11, 12, 4, 255, 255, 255, 240);
      break;
    case "park":
      fillCircle(10, 11, 3, 255, 255, 255, 240);
      fillCircle(16, 11, 3, 255, 255, 255, 240);
      fillCircle(13, 8, 4, 255, 255, 255, 240);
      fillRect(12, 13, 2, 5, 255, 255, 255, 240);
      break;
    case "restaurant":
      fillCircle(10, 10, 2, 255, 255, 255, 240);
      fillRect(9, 12, 2, 6, 255, 255, 255, 240);
      fillRect(14, 8, 2, 10, 255, 255, 255, 240);
      fillRect(13, 8, 4, 2, 255, 255, 255, 240);
      break;
    case "gym":
      fillRect(8, 11, 3, 4, 255, 255, 255, 240);
      fillRect(15, 11, 3, 4, 255, 255, 255, 240);
      fillRect(11, 12, 4, 2, 255, 255, 255, 240);
      fillRect(7, 10, 1, 6, 255, 255, 255, 240);
      fillRect(18, 10, 1, 6, 255, 255, 255, 240);
      break;
    default:
      fillCircle(13, 13, 5, 255, 255, 255, 240);
      break;
  }

  return { width, height, data };
};

const toZonePoisFeatureCollection = (
  poiPoints: ZonePoiPointLike[],
  zoneFingerprint: string | null,
  activePoiCategory: string,
  selectedPoiKey: string | null
): GeoJSON.FeatureCollection => ({
  type: "FeatureCollection",
  features: sortPoiPoints(poiPoints)
    .filter((point) => activePoiCategory === "all" || point.category === activePoiCategory)
    .map((point, index) => {
      const selectionKey = getZonePoiSelectionKey(point, zoneFingerprint, index);
      return {
        type: "Feature",
        geometry: {
          type: "Point",
          coordinates: [point.lon, point.lat]
        },
        properties: {
          id: point.id || selectionKey,
          selection_key: selectionKey,
          selected: selectionKey === selectedPoiKey,
          zone_fingerprint: zoneFingerprint || "",
          name: point.name || "POI sem nome",
          address: point.address || "",
          category: point.category || "other"
        }
      };
    })
});

const escapeHtml = (value: string) =>
  value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");

const parseBusList = (rawValue: unknown) => {
  if (typeof rawValue !== "string" || !rawValue.trim()) {
    return [];
  }
  const items = rawValue
    .split("||")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
  return items;
};

const hasInlineBusDetails = (properties: Record<string, unknown> | undefined) => {
  if (!properties) {
    return false;
  }
  const buses = parseBusList(properties.bus_list);
  if (buses.length > 0) {
    return true;
  }
  const reportedCount = Number(properties.bus_count);
  return Number.isFinite(reportedCount) && reportedCount > 0;
};

const popupContent = (title: string, name: string, busCountLabel: string, buses: string[]) => {
  const listItems = buses.map((bus) => `<li style="margin-bottom:4px;">${escapeHtml(bus)}</li>`).join("");
  const listSection =
    buses.length > 0
      ? `<ul style="margin:0; padding-left:16px; max-height:140px; overflow:auto; font-size:12px; color:#334155;">${listItems}</ul>`
      : '<p style="margin:0; font-size:12px; color:#64748b;">Dados de linhas indisponíveis para esta feição.</p>';
  return `
    <div style="font-family: system-ui, -apple-system, Segoe UI, sans-serif; min-width: 220px;">
      <p style="margin:0 0 4px; font-size:11px; letter-spacing:0.06em; text-transform:uppercase; color:#64748b;">${escapeHtml(title)}</p>
      <p style="margin:0 0 10px; font-size:13px; font-weight:700; color:#0f172a;">${escapeHtml(name)}</p>
      <p style="margin:0 0 8px; font-size:12px; color:#0f172a;">
        Ônibus identificados: <strong>${busCountLabel}</strong>
      </p>
      ${listSection}
    </div>
  `;
};

const popupLoadingContent = (title: string, name: string) => `
  <div style="font-family: system-ui, -apple-system, Segoe UI, sans-serif; min-width: 220px;">
    <p style="margin:0 0 4px; font-size:11px; letter-spacing:0.06em; text-transform:uppercase; color:#64748b;">${escapeHtml(title)}</p>
    <p style="margin:0 0 10px; font-size:13px; font-weight:700; color:#0f172a;">${escapeHtml(name)}</p>
    <p style="margin:0; font-size:12px; color:#64748b;">Carregando linhas identificadas...</p>
  </div>
`;

const poiPopupContent = (name: string, categoryLabel: string, address: string | null) => `
  <div style="font-family: system-ui, -apple-system, Segoe UI, sans-serif; min-width: 220px;">
    <p style="margin:0 0 4px; font-size:11px; letter-spacing:0.06em; text-transform:uppercase; color:#64748b;">${escapeHtml(categoryLabel)}</p>
    <p style="margin:0 0 8px; font-size:13px; font-weight:700; color:#0f172a;">${escapeHtml(name)}</p>
    ${address ? `<p style="margin:0; font-size:12px; color:#475569;">${escapeHtml(address)}</p>` : '<p style="margin:0; font-size:12px; color:#64748b;">Endereco indisponivel.</p>'}
  </div>
`;

export function FindIdealApp() {
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const layerMenuRef = useRef<HTMLDivElement | null>(null);
  const layerMenuButtonRef = useRef<HTMLButtonElement | null>(null);
  const busPopupRef = useRef<maplibregl.Popup | null>(null);
  const pickedMarkerRef = useRef<maplibregl.Marker | null>(null);
  const [isMapReady, setIsMapReady] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);
  const [isLayerMenuOpen, setIsLayerMenuOpen] = useState(false);
  const [layerVisibility, setLayerVisibility] = useState<Record<MapOverlayLayerKey, boolean>>(DEFAULT_LAYER_VISIBILITY);
  const [visibleSequentialLayerGroupIndex, setVisibleSequentialLayerGroupIndex] = useState(-1);
  const [selectedZonePoiState, setSelectedZonePoiState] = useState<{ zoneFingerprint: string | null; poiPoints: ZonePoiPointLike[] }>({
    zoneFingerprint: null,
    poiPoints: []
  });
  const step = useUIStore((state) => state.step);
  const pickedCoord = useJourneyStore((state) => state.pickedCoord);
  const setPickedCoord = useJourneyStore((state) => state.setPickedCoord);
  const journeyId = useJourneyStore((state) => state.journeyId);
  const selectedTransportId = useJourneyStore((state) => state.selectedTransportId);
  const selectedZoneFingerprint = useJourneyStore((state) => state.selectedZoneFingerprint);
  const selectedListingKey = useJourneyStore((state) => state.selectedListingKey);
  const selectedPoiKey = useJourneyStore((state) => state.selectedPoiKey);
  const activePoiCategory = useJourneyStore((state) => state.activePoiCategory);
  const listingsJobId = useJourneyStore((state) => state.listingsJobId);
  const listingsFilters = useJourneyStore((state) => state.listingsFilters);
  const config = useJourneyStore((state) => state.config);
  const setSelectedTransportId = useJourneyStore((state) => state.setSelectedTransportId);
  const setSelectedListingKey = useJourneyStore((state) => state.setSelectedListingKey);
  const setSelectedPoiKey = useJourneyStore((state) => state.setSelectedPoiKey);
  const setSelectedZone = useJourneyStore((state) => state.setSelectedZone);
  const stepRef = useRef(step);
  const sequentialLayerSettingsRef = useRef<SequentialLayerSettings>({
    layerVisibility: DEFAULT_LAYER_VISIBILITY,
    greenEnabled: config.enrichments.green,
  });

  function toggleLayerVisibility(key: MapOverlayLayerKey) {
    setLayerVisibility((current) => ({
      ...current,
      [key]: !current[key]
    }));
  }

  useEffect(() => {
    stepRef.current = step;
  }, [step]);

  useEffect(() => {
    sequentialLayerSettingsRef.current = {
      layerVisibility,
      greenEnabled: config.enrichments.green,
    };

    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }

    setVisibleSequentialLayerGroupIndex(resolveVisibleSequentialLayerGroupIndex(map, sequentialLayerSettingsRef.current));
  }, [config.enrichments.green, isMapReady, layerVisibility]);

  useEffect(() => {
    if (!isLayerMenuOpen) {
      return;
    }

    function handlePointerDown(event: MouseEvent) {
      const target = event.target as Node | null;
      if (!target) {
        setIsLayerMenuOpen(false);
        return;
      }
      if (layerMenuRef.current?.contains(target) || layerMenuButtonRef.current?.contains(target)) {
        return;
      }
      setIsLayerMenuOpen(false);
    }

    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsLayerMenuOpen(false);
      }
    }

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [isLayerMenuOpen]);

  const listingsQuery = useQuery({
    queryKey: ["zone-listings", journeyId, selectedZoneFingerprint, config.type, "all"],
    queryFn: async () => getZoneListings(journeyId as string, selectedZoneFingerprint as string, config.type, "all", "all"),
    enabled: Boolean(journeyId && selectedZoneFingerprint && step >= 6),
    refetchInterval: (query) => {
      if (step < 6) {
        return false;
      }
      const data = query.state.data;
      if (!data) {
        return 5000;
      }
      const emptyResults = (data.total_count || 0) === 0;
      return data.source === "none" || data.freshness_status === "no_cache" || emptyResults || Boolean(listingsJobId) ? 5000 : false;
    }
  });

  const filteredMapListings = useMemo(
    () => applyListingsPanelFilters(listingsQuery.data?.listings || [], listingsFilters),
    [listingsFilters, listingsQuery.data?.listings]
  );

  useEffect(() => {
    if (!mapContainerRef.current) return;

    if (!MAPTILER_KEY) {
      setMapError("Defina VITE_MAPTILER_API_KEY no .env do frontend para renderizar o mapa.");
      return;
    }

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: mapTilerStyleUrl(MAPTILER_KEY),
      center: [-46.633308, -23.55052],
      zoom: 10.7,
      pitchWithRotate: false,
      dragRotate: false,
    });

    mapRef.current = map;

    map.on("load", () => {
      const syncSequentialLayerLoadSequence = () => {
        setVisibleSequentialLayerGroupIndex(resolveVisibleSequentialLayerGroupIndex(map, sequentialLayerSettingsRef.current));
      };

      if (!map.hasImage("bus-stop-icon")) {
        map.addImage("bus-stop-icon", createBusIcon("#845ef7"));
      }
      if (!map.hasImage("bus-terminal-icon")) {
        map.addImage("bus-terminal-icon", createBusIcon("#f97316"));
      }
      for (const category of ["school", "supermarket", "pharmacy", "park", "restaurant", "gym", "default"] as const) {
        const meta = getPoiCategoryMeta(category === "default" ? undefined : category);
        if (!map.hasImage(meta.iconId)) {
          map.addImage(meta.iconId, createPoiIcon(meta.color, category));
        }
      }

      map.addSource("transport-lines-source", {
        type: "vector",
        tiles: [apiTileUrl("/transport/tiles/lines/{z}/{x}/{y}.pbf")],
        minzoom: 8,
        maxzoom: 16,
        attribution: "Dados GTFS + GeoSampa",
      });

      map.addSource("transport-stops-source", {
        type: "vector",
        tiles: [apiTileUrl("/transport/tiles/stops/{z}/{x}/{y}.pbf")],
        minzoom: 9,
        maxzoom: 17,
        attribution: "Dados GTFS + GeoSampa",
      });

      map.addSource("green-areas-source", {
        type: "vector",
        tiles: [apiTileUrl("/transport/tiles/environment/green/{z}/{x}/{y}.pbf")],
        minzoom: 9,
        maxzoom: 17,
        attribution: "GeoSampa",
      });

      map.addSource("flood-areas-source", {
        type: "vector",
        tiles: [apiTileUrl("/transport/tiles/environment/flood/{z}/{x}/{y}.pbf")],
        minzoom: 9,
        maxzoom: 17,
        attribution: "GeoSampa",
      });

      map.addSource(TRANSPORT_CANDIDATES_SOURCE_ID, {
        type: "geojson",
        data: EMPTY_FEATURE_COLLECTION,
      });

      map.addSource(ZONES_SOURCE_ID, {
        type: "geojson",
        data: EMPTY_FEATURE_COLLECTION,
      });

      map.addSource(ZONE_POIS_SOURCE_ID, {
        type: "geojson",
        data: EMPTY_FEATURE_COLLECTION,
      });

      map.addSource(LISTINGS_SOURCE_ID, {
        type: "geojson",
        data: EMPTY_FEATURE_COLLECTION,
      });

      map.addLayer({
        id: "bus-line-layer",
        type: "line",
        source: "transport-lines-source",
        "source-layer": "transport_lines",
        filter: ["==", ["get", "mode"], "bus"],
        paint: {
          "line-color": "#845ef7",
          "line-width": ["interpolate", ["linear"], ["zoom"], 8, 1.2, 12, 2.2, 15, 3.5],
          "line-opacity": 0.72,
          "line-dasharray": [1.4, 1.1],
        },
      });

      map.addLayer({
        id: "bus-line-direction-layer",
        type: "symbol",
        source: "transport-lines-source",
        "source-layer": "transport_lines",
        filter: ["==", ["get", "mode"], "bus"],
        layout: {
          "symbol-placement": "line",
          "symbol-spacing": 170,
          "text-field": "▶",
          "text-size": 11,
          "text-keep-upright": false,
          "text-allow-overlap": true,
        },
        paint: {
          "text-color": "#5b3fd6",
          "text-opacity": 0.76,
        },
      });

      map.addLayer({
        id: "metro-line-layer",
        type: "line",
        source: "transport-lines-source",
        "source-layer": "transport_lines",
        filter: ["==", ["get", "mode"], "metro"],
        paint: {
          "line-color": "#e11d48",
          "line-width": ["interpolate", ["linear"], ["zoom"], 8, 1.8, 12, 3.2, 15, 4.8],
          "line-opacity": 0.9,
        },
      });

      map.addLayer({
        id: "train-line-layer",
        type: "line",
        source: "transport-lines-source",
        "source-layer": "transport_lines",
        filter: ["==", ["get", "mode"], "train"],
        paint: {
          "line-color": "#0f766e",
          "line-width": ["interpolate", ["linear"], ["zoom"], 8, 1.5, 12, 2.8, 15, 4.2],
          "line-opacity": 0.88,
        },
      });

      map.addLayer({
        id: "flood-layer",
        type: "fill",
        source: "flood-areas-source",
        "source-layer": "flood_areas",
        layout: { visibility: "none" },
        paint: {
          "fill-color": "#378add",
          "fill-opacity": ["interpolate", ["linear"], ["zoom"], 9, 0.12, 13, 0.2, 16, 0.3],
        },
      });

      map.addLayer({
        id: "green-layer",
        type: "fill",
        source: "green-areas-source",
        "source-layer": "green_areas",
        layout: { visibility: "none" },
        paint: {
          "fill-color": "#6a9f2b",
          "fill-opacity": ["interpolate", ["linear"], ["zoom"], 9, 0.1, 13, 0.18, 16, 0.28],
        },
      });

      map.addLayer({
        id: "bus-stop-layer",
        type: "symbol",
        source: "transport-stops-source",
        "source-layer": "transport_stops",
        filter: ["==", ["get", "kind"], "bus_stop"],
        layout: {
          "icon-image": "bus-stop-icon",
          "icon-size": ["interpolate", ["linear"], ["zoom"], 9, 0.28, 12, 0.36, 15, 0.46],
          "icon-allow-overlap": true,
        },
      });

      map.addLayer({
        id: "bus-terminal-layer",
        type: "symbol",
        source: "transport-stops-source",
        "source-layer": "transport_stops",
        filter: ["==", ["get", "kind"], "bus_terminal"],
        layout: {
          "icon-image": "bus-terminal-icon",
          "icon-size": ["interpolate", ["linear"], ["zoom"], 9, 0.34, 12, 0.44, 15, 0.54],
          "icon-allow-overlap": true,
        },
      });

      map.addLayer({
        id: "metro-station-layer",
        type: "circle",
        source: "transport-stops-source",
        "source-layer": "transport_stops",
        filter: ["==", ["get", "kind"], "metro_station"],
        paint: {
          "circle-radius": 5.4,
          "circle-color": "#e11d48",
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 1.6,
          "circle-opacity": 0.96,
        },
      });

      map.addLayer({
        id: "train-station-layer",
        type: "circle",
        source: "transport-stops-source",
        "source-layer": "transport_stops",
        filter: ["==", ["get", "kind"], "train_station"],
        paint: {
          "circle-radius": 5.6,
          "circle-color": "#0f766e",
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 1.6,
          "circle-opacity": 0.97,
        },
      });

      map.addLayer({
        id: "transport-candidate-layer",
        type: "circle",
        source: TRANSPORT_CANDIDATES_SOURCE_ID,
        paint: {
          "circle-radius": ["case", ["boolean", ["get", "selected"], false], 8, 5],
          "circle-color": ["case", ["boolean", ["get", "selected"], false], "#845ef7", "#64748b"],
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 2,
          "circle-opacity": 0.92,
        },
      });

      map.addLayer({
        id: "zones-runtime-fill-layer",
        type: "fill",
        source: ZONES_SOURCE_ID,
        paint: {
          "fill-color": ["case", ["boolean", ["get", "selected"], false], "#7c3aed", ["coalesce", ["get", "fill_color"], "#94a3b8"]],
          "fill-opacity": ["case", ["boolean", ["get", "selected"], false], 0.3, 0.18],
        },
      });

      map.addLayer({
        id: "zones-runtime-outline-layer",
        type: "line",
        source: ZONES_SOURCE_ID,
        paint: {
          "line-color": ["case", ["boolean", ["get", "selected"], false], "#6d28d9", ["coalesce", ["get", "outline_color"], "#94a3b8"]],
          "line-width": ["case", ["boolean", ["get", "selected"], false], 2.8, 1.8],
          "line-opacity": 0.9,
        },
      });

      map.addLayer({
        id: "zones-runtime-label-layer",
        type: "symbol",
        source: ZONES_SOURCE_ID,
        layout: {
          "text-field": ["get", "label"],
          "text-size": 12,
          "text-font": ["Open Sans Bold", "Arial Unicode MS Bold"],
          "text-allow-overlap": true,
          "text-ignore-placement": true,
        },
        paint: {
          "text-color": ["case", ["boolean", ["get", "selected"], false], "#581c87", ["coalesce", ["get", "label_color"], "#0f172a"]],
          "text-halo-color": "#ffffff",
          "text-halo-width": 1.2,
        },
      });

      map.addLayer({
        id: "zone-pois-highlight-layer",
        type: "circle",
        source: ZONE_POIS_SOURCE_ID,
        filter: ["==", ["coalesce", ["get", "selected"], false], true],
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 9, 9.35, 12, 11.9, 15, 13.6],
          "circle-color": "#ffffff",
          "circle-opacity": 0.5,
          "circle-stroke-color": "#5b21b6",
          "circle-stroke-width": 1.5
        }
      });

      map.addLayer({
        id: "zone-pois-layer",
        type: "symbol",
        source: ZONE_POIS_SOURCE_ID,
        layout: {
          "icon-image": [
            "match",
            ["get", "category"],
            "school",
            getPoiCategoryMeta("school").iconId,
            "supermarket",
            getPoiCategoryMeta("supermarket").iconId,
            "pharmacy",
            getPoiCategoryMeta("pharmacy").iconId,
            "park",
            getPoiCategoryMeta("park").iconId,
            "restaurant",
            getPoiCategoryMeta("restaurant").iconId,
            "gym",
            getPoiCategoryMeta("gym").iconId,
            getPoiCategoryMeta(undefined).iconId
          ],
          "icon-size": ["interpolate", ["linear"], ["zoom"], 9, 0.62, 12, 0.76, 15, 0.9],
          "icon-allow-overlap": true
        }
      });

      map.addLayer({
        id: "journey-listings-layer",
        type: "circle",
        source: LISTINGS_SOURCE_ID,
        paint: {
          "circle-radius": ["case", ["boolean", ["get", "selected"], false], 8, 5],
          "circle-color": ["case", ["boolean", ["get", "selected"], false], "#5b21b6", "#845ef7"],
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": ["case", ["boolean", ["get", "selected"], false], 2.2, 1.5],
          "circle-opacity": 0.94,
        },
      });

      const openBusPopup = async (
        title: string,
        event: maplibregl.MapLayerMouseEvent,
        fallbackName: string,
        options?: {
          fallbackCount?: number;
          detailLoader?: () => Promise<{ count: number; buses: string[] }>;
        }
      ) => {
        const feature = event.features?.[0];
        if (!feature?.properties) return;
        const props = feature.properties as Record<string, unknown>;
        const featureName = typeof props.name === "string" && props.name.trim() ? props.name.trim() : fallbackName;
        let buses = parseBusList(props.bus_list);
        const reportedCount = Number(props.bus_count);
        let busCount = Number.isFinite(reportedCount) && reportedCount > 0 ? reportedCount : buses.length;
        if (typeof options?.fallbackCount === "number" && options.fallbackCount > 0) {
          busCount = Math.max(busCount, options.fallbackCount);
        }

        busPopupRef.current?.remove();

        const popup = new maplibregl.Popup({ closeButton: true, closeOnClick: false, maxWidth: "340px" })
          .setLngLat(event.lngLat)
          .setHTML(options?.detailLoader ? popupLoadingContent(title, featureName) : popupContent(title, featureName, busCount > 0 ? String(busCount) : "n/d", buses))
          .addTo(map);

        busPopupRef.current = popup;
        popup.on("close", () => {
          if (busPopupRef.current === popup) {
            busPopupRef.current = null;
          }
        });

        if (!options?.detailLoader) {
          return;
        }

        try {
          const details = await options.detailLoader();
          buses = details.buses;
          if (details.count > 0) {
            busCount = details.count;
          } else if (buses.length > 0) {
            busCount = buses.length;
          }
        } catch {
          // Keep the tile fallback when details are unavailable.
        }

        if (busPopupRef.current !== popup) {
          return;
        }

        popup.setHTML(popupContent(title, featureName, busCount > 0 ? String(busCount) : "n/d", buses));
      };

      map.on("click", "bus-line-layer", (event) => {
        const properties = event.features?.[0]?.properties as Record<string, unknown> | undefined;
        const lineId = properties?.id;
        const sourceKind = properties?.source_kind;
        void openBusPopup("Linha de ônibus", event, "Linha de ônibus", {
          detailLoader:
            !hasInlineBusDetails(properties) &&
            typeof sourceKind === "string" &&
            sourceKind === "gtfs_shape" &&
            typeof lineId === "string" &&
            lineId.trim()
              ? () => getBusLineDetails(lineId)
              : undefined
        });
      });

      map.on("click", "bus-stop-layer", (event) => {
        const properties = event.features?.[0]?.properties as Record<string, unknown> | undefined;
        const stopId = properties?.id;
        const sourceKind = properties?.source_kind;
        void openBusPopup("Ponto de ônibus", event, "Ponto de ônibus", {
          detailLoader:
            !hasInlineBusDetails(properties) &&
            typeof sourceKind === "string" &&
            typeof stopId === "string" &&
            stopId.trim()
              ? () => getTransportStopDetails(stopId, sourceKind)
              : undefined
        });
      });

      map.on("click", "bus-terminal-layer", (event) => {
        const properties = event.features?.[0]?.properties as Record<string, unknown> | undefined;
        const stopId = properties?.id;
        const sourceKind = properties?.source_kind;
        void openBusPopup("Terminal de ônibus", event, "Terminal de ônibus", {
          detailLoader:
            !hasInlineBusDetails(properties) &&
            typeof sourceKind === "string" &&
            typeof stopId === "string" &&
            stopId.trim()
              ? () => getTransportStopDetails(stopId, sourceKind)
              : undefined
        });
      });

      map.on("click", "transport-candidate-layer", (event) => {
        const feature = event.features?.[0];
        const transportId = feature?.properties?.id;
        if (typeof transportId === "string") {
          setSelectedTransportId(transportId);
        }

        const props = feature?.properties as Record<string, unknown> | undefined;
        const externalId = props?.external_id;
        const source = props?.source;
        const routeCount = Number(props?.route_count);
        if (typeof source === "string" && source === "gtfs_stop" && typeof externalId === "string" && externalId.trim()) {
          void openBusPopup("Ponto de ônibus", event, "Ponto de ônibus", {
            fallbackCount: Number.isFinite(routeCount) ? routeCount : undefined,
            detailLoader: () => getBusStopDetails(externalId)
          });
        }
      });

      map.on("click", "zones-runtime-fill-layer", (event) => {
        const feature = event.features?.[0];
        const zoneId = feature?.properties?.id;
        const fingerprint = feature?.properties?.fingerprint;
        if (typeof zoneId === "string" && typeof fingerprint === "string") {
          setSelectedZone(zoneId, fingerprint);
        }
      });

      map.on("click", "zone-pois-layer", (event) => {
        const feature = event.features?.[0];
        const properties = feature?.properties as Record<string, unknown> | undefined;
        if (!properties) {
          return;
        }
        const selectionKey = typeof properties.selection_key === "string" && properties.selection_key.trim() ? properties.selection_key.trim() : null;
        const name = typeof properties.name === "string" && properties.name.trim() ? properties.name.trim() : "POI sem nome";
        const address = typeof properties.address === "string" && properties.address.trim() ? properties.address.trim() : null;
        const categoryMeta = getPoiCategoryMeta(typeof properties.category === "string" ? properties.category : undefined);
        if (selectionKey) {
          setSelectedPoiKey(selectionKey);
        }

        busPopupRef.current?.remove();
        const popup = new maplibregl.Popup({ closeButton: true, closeOnClick: false, maxWidth: "320px" })
          .setLngLat(event.lngLat)
          .setHTML(poiPopupContent(name, categoryMeta.singularLabel, address))
          .addTo(map);

        busPopupRef.current = popup;
        popup.on("close", () => {
          if (busPopupRef.current === popup) {
            busPopupRef.current = null;
          }
        });
      });

      map.on("click", "journey-listings-layer", (event) => {
        const feature = event.features?.[0];
        const listingKey = feature?.properties?.listing_key;
        if (typeof listingKey === "string" && listingKey.trim()) {
          setSelectedListingKey(listingKey);
        }
      });

      map.on("click", (event) => {
        if (stepRef.current === 1) {
          setPickedCoord({
            lat: event.lngLat.lat,
            lon: event.lngLat.lng,
            label: "Ponto principal"
          });
        }

        const activePopup = busPopupRef.current;
        if (!activePopup) return;

        const clickedBusFeatures = map.queryRenderedFeatures(event.point, {
          layers: [...POPUP_PERSIST_LAYER_LIST],
        });
        if (clickedBusFeatures.length > 0) return;

        const popupElement = activePopup.getElement();
        const targetNode = (event.originalEvent?.target as Node | null) ?? null;
        if (targetNode && popupElement.contains(targetNode)) return;

        activePopup.remove();
        busPopupRef.current = null;
      });

      for (const layerId of BUS_LAYER_LIST) {
        map.on("mouseenter", layerId, () => {
          map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseleave", layerId, () => {
          map.getCanvas().style.cursor = "";
        });
      }

      for (const layerId of ["transport-candidate-layer", "zones-runtime-fill-layer", "zone-pois-highlight-layer", "zone-pois-layer", "journey-listings-layer"] as const) {
        map.on("mouseenter", layerId, () => {
          map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseleave", layerId, () => {
          map.getCanvas().style.cursor = stepRef.current === 1 ? "crosshair" : "";
        });
      }

      map.on("moveend", syncSequentialLayerLoadSequence);
      map.on("sourcedata", (event) => {
        if (event.dataType !== "source" || typeof event.sourceId !== "string") {
          return;
        }

        const isSequentialSource = SEQUENTIAL_LAYER_GROUPS.some((group) => group.sourceId === event.sourceId);
        if (!isSequentialSource || !map.isSourceLoaded(event.sourceId)) {
          return;
        }

        syncSequentialLayerLoadSequence();
      });

      syncSequentialLayerLoadSequence();

      setIsMapReady(true);
    });

    return () => {
      busPopupRef.current?.remove();
      busPopupRef.current = null;
      map.remove();
    };
  }, [setPickedCoord, setSelectedListingKey, setSelectedPoiKey, setSelectedTransportId, setSelectedZone]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) return;

    map.getCanvas().style.cursor = step === 1 ? "crosshair" : "";
  }, [isMapReady, step]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }

    if (!pickedCoord) {
      pickedMarkerRef.current?.remove();
      pickedMarkerRef.current = null;
      return;
    }

    if (!pickedMarkerRef.current) {
      const markerElement = document.createElement("div");
      markerElement.className = "flex h-6 w-6 items-center justify-center rounded-full border-2 border-white bg-[#845ef7] shadow-lg";
      markerElement.innerHTML = '<span style="display:block;width:8px;height:8px;border-radius:9999px;background:#ffffff"></span>';
      pickedMarkerRef.current = new maplibregl.Marker({ element: markerElement, anchor: "center" })
        .setLngLat([pickedCoord.lon, pickedCoord.lat])
        .addTo(map);
    } else {
      pickedMarkerRef.current.setLngLat([pickedCoord.lon, pickedCoord.lat]);
    }

    map.easeTo({ center: [pickedCoord.lon, pickedCoord.lat], duration: 600, zoom: Math.max(map.getZoom(), 13) });
  }, [isMapReady, pickedCoord]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }
    const activeMap = map;

    let cancelled = false;

    async function syncTransportCandidates() {
      if (!journeyId || step < 2 || config.modal === "walk" || config.modal === "car") {
        setGeoJsonSourceData(activeMap, TRANSPORT_CANDIDATES_SOURCE_ID, EMPTY_FEATURE_COLLECTION);
        return;
      }

      const points = await getJourneyTransportPoints(journeyId);
      if (!cancelled) {
        setGeoJsonSourceData(
          activeMap,
          TRANSPORT_CANDIDATES_SOURCE_ID,
          toTransportCandidatesFeatureCollection(points, selectedTransportId)
        );
      }
    }

    void syncTransportCandidates().catch(() => {
      if (!cancelled) {
        setGeoJsonSourceData(activeMap, TRANSPORT_CANDIDATES_SOURCE_ID, EMPTY_FEATURE_COLLECTION);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [config.modal, isMapReady, journeyId, selectedTransportId, step]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }
    const activeMap = map;

    let cancelled = false;
    let pollTimeout: number | undefined;

    async function syncZones() {
      if (!journeyId || step < 3) {
        setGeoJsonSourceData(activeMap, ZONES_SOURCE_ID, EMPTY_FEATURE_COLLECTION);
        setGeoJsonSourceData(activeMap, ZONE_POIS_SOURCE_ID, EMPTY_FEATURE_COLLECTION);
        setSelectedZonePoiState({ zoneFingerprint: null, poiPoints: [] });
        return;
      }

      const response = await getJourneyZonesList(journeyId);
      if (!cancelled) {
        const selectedZone = response.zones.find((zone) => zone.fingerprint === selectedZoneFingerprint);
        const hasLegacyPoiZones = response.zones.some((zone) => zoneNeedsPoiBackfill(zone));
        const selectedPoiPoints = ((selectedZone?.poi_points || []) as ZonePoiPointLike[]);
        setGeoJsonSourceData(
          activeMap,
          ZONES_SOURCE_ID,
          toZonesFeatureCollection(response.zones, selectedZoneFingerprint)
        );
        setSelectedZonePoiState({ zoneFingerprint: selectedZoneFingerprint || null, poiPoints: selectedPoiPoints });

        if (hasLegacyPoiZones) {
          pollTimeout = window.setTimeout(() => {
            void syncZones().catch(() => {
              if (!cancelled) {
                setGeoJsonSourceData(activeMap, ZONES_SOURCE_ID, EMPTY_FEATURE_COLLECTION);
                setGeoJsonSourceData(activeMap, ZONE_POIS_SOURCE_ID, EMPTY_FEATURE_COLLECTION);
                setSelectedZonePoiState({ zoneFingerprint: null, poiPoints: [] });
              }
            });
          }, 3000);
        }
      }
    }

    void syncZones().catch(() => {
      if (!cancelled) {
        setGeoJsonSourceData(activeMap, ZONES_SOURCE_ID, EMPTY_FEATURE_COLLECTION);
        setGeoJsonSourceData(activeMap, ZONE_POIS_SOURCE_ID, EMPTY_FEATURE_COLLECTION);
        setSelectedZonePoiState({ zoneFingerprint: null, poiPoints: [] });
      }
    });

    return () => {
      cancelled = true;
      if (pollTimeout) {
        window.clearTimeout(pollTimeout);
      }
    };
  }, [isMapReady, journeyId, selectedZoneFingerprint, step]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }

    const poiData = selectedZonePoiState.zoneFingerprint && step >= 4
      ? toZonePoisFeatureCollection(selectedZonePoiState.poiPoints, selectedZonePoiState.zoneFingerprint, activePoiCategory, selectedPoiKey)
      : EMPTY_FEATURE_COLLECTION;
    setGeoJsonSourceData(map, ZONE_POIS_SOURCE_ID, poiData);

    if (!selectedPoiKey) {
      return;
    }

    const selectedPoint = sortPoiPoints(selectedZonePoiState.poiPoints).find(
      (point, index) => getZonePoiSelectionKey(point, selectedZonePoiState.zoneFingerprint, index) === selectedPoiKey
    );
    if (!selectedPoint) {
      return;
    }

    if (activePoiCategory !== "all" && selectedPoint.category !== activePoiCategory) {
      return;
    }

    map.easeTo({ center: [selectedPoint.lon, selectedPoint.lat], duration: 600, zoom: Math.max(map.getZoom(), 15) });
  }, [activePoiCategory, isMapReady, selectedPoiKey, selectedZonePoiState, step]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }

    if (!selectedListingKey || step < 6) {
      return;
    }

    const selectedListing = (listingsQuery.data?.listings || []).find((listing) => {
      if (typeof listing.lat !== "number" || typeof listing.lon !== "number") {
        return false;
      }
      return getListingSelectionKey(listing) === selectedListingKey;
    });

    if (!selectedListing || typeof selectedListing.lat !== "number" || typeof selectedListing.lon !== "number") {
      return;
    }

    map.easeTo({ center: [selectedListing.lon, selectedListing.lat], duration: 600, zoom: Math.max(map.getZoom(), 14) });
  }, [isMapReady, listingsQuery.data?.listings, selectedListingKey, step]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }

    if (!journeyId || !selectedZoneFingerprint || step < 6 || listingsQuery.error) {
      setGeoJsonSourceData(map, LISTINGS_SOURCE_ID, EMPTY_FEATURE_COLLECTION);
      return;
    }

    setGeoJsonSourceData(
      map,
      LISTINGS_SOURCE_ID,
      toListingsFeatureCollection(filteredMapListings as Array<Record<string, unknown>>, selectedListingKey)
    );
  }, [filteredMapListings, isMapReady, journeyId, listingsQuery.error, selectedListingKey, selectedZoneFingerprint, step]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) return;

    const sequentialLayerSettings: SequentialLayerSettings = {
      layerVisibility,
      greenEnabled: config.enrichments.green,
    };
    const transportPointsVisible = isSequentialLayerGroupVisible("transportPoints", visibleSequentialLayerGroupIndex, sequentialLayerSettings);
    const transportLinesVisible = isSequentialLayerGroupVisible("transportLines", visibleSequentialLayerGroupIndex, sequentialLayerSettings);
    const greenVisible = isSequentialLayerGroupVisible("green", visibleSequentialLayerGroupIndex, sequentialLayerSettings);
    const floodVisible = isSequentialLayerGroupVisible("flood", visibleSequentialLayerGroupIndex, sequentialLayerSettings);

    map.setLayoutProperty("bus-line-layer", "visibility", transportLinesVisible && layerVisibility.routes ? "visible" : "none");
    map.setLayoutProperty("bus-line-direction-layer", "visibility", transportLinesVisible && layerVisibility.routes ? "visible" : "none");
    map.setLayoutProperty("metro-line-layer", "visibility", transportLinesVisible && layerVisibility.metro ? "visible" : "none");
    map.setLayoutProperty("train-line-layer", "visibility", transportLinesVisible && layerVisibility.train ? "visible" : "none");
    map.setLayoutProperty("bus-stop-layer", "visibility", transportPointsVisible && layerVisibility.busStops ? "visible" : "none");
    map.setLayoutProperty("bus-terminal-layer", "visibility", transportPointsVisible && layerVisibility.busStops ? "visible" : "none");
    map.setLayoutProperty("metro-station-layer", "visibility", transportPointsVisible && layerVisibility.metro ? "visible" : "none");
    map.setLayoutProperty("train-station-layer", "visibility", transportPointsVisible && layerVisibility.train ? "visible" : "none");
    map.setLayoutProperty("transport-candidate-layer", "visibility", layerVisibility.transportCandidates ? "visible" : "none");
    map.setLayoutProperty("zones-runtime-fill-layer", "visibility", layerVisibility.zones ? "visible" : "none");
    map.setLayoutProperty("zones-runtime-outline-layer", "visibility", layerVisibility.zones ? "visible" : "none");
    map.setLayoutProperty("zones-runtime-label-layer", "visibility", layerVisibility.zones ? "visible" : "none");
    map.setLayoutProperty("zone-pois-highlight-layer", "visibility", layerVisibility.pois ? "visible" : "none");
    map.setLayoutProperty("zone-pois-layer", "visibility", layerVisibility.pois ? "visible" : "none");
    map.setLayoutProperty("journey-listings-layer", "visibility", layerVisibility.listings ? "visible" : "none");
    map.setLayoutProperty("flood-layer", "visibility", floodVisible ? "visible" : "none");
    map.setLayoutProperty("green-layer", "visibility", greenVisible ? "visible" : "none");
    map.setFilter("green-layer", ["in", "vegetation_level", ...getIncludedGreenVegetationLevels(config.greenVegetationLevel)] as never);
  }, [config, isMapReady, layerVisibility, visibleSequentialLayerGroupIndex]);

  if (mapError) {
    return (
      <main className="flex h-screen w-full items-center justify-center bg-slate-900 text-red-400">
        <p className="text-sm">{mapError}</p>
      </main>
    );
  }

  return (
    <main className="relative h-screen w-full overflow-hidden">
      <div ref={mapContainerRef} className="h-full w-full" aria-label="Mapa principal" />
      <div className="pointer-events-none absolute bottom-14 right-4 z-40 flex flex-col items-end gap-2">
        {isLayerMenuOpen ? (
          <div
            ref={layerMenuRef}
            className="pointer-events-auto w-56 rounded-xl border border-slate-200 bg-white/95 p-3 shadow-lg backdrop-blur-md"
          >
            <p className="mb-3 text-[11px] font-bold uppercase tracking-[0.14em] text-slate-500">Camadas do mapa</p>
            <div className="space-y-2">
              {MAP_LAYER_MENU_ITEMS.map((item) => (
                <label key={item.key} className="flex cursor-pointer items-center gap-2.5 text-sm text-slate-700">
                  <input
                    type="checkbox"
                    checked={layerVisibility[item.key]}
                    onChange={() => toggleLayerVisibility(item.key)}
                    className="h-4 w-4 rounded accent-pastel-violet-500"
                  />
                  <span>{item.label}</span>
                </label>
              ))}
            </div>
          </div>
        ) : null}
        <button
          ref={layerMenuButtonRef}
          type="button"
          aria-label="Camadas"
          onClick={() => setIsLayerMenuOpen((current) => !current)}
          className={`${LAYER_TOGGLE_BUTTON_CLASS} ${isLayerMenuOpen ? "border-pastel-violet-300 text-pastel-violet-600" : ""}`}
        >
          <Layers className="h-4 w-4" />
        </button>
      </div>
      <WizardPanel />
    </main>
  );
}
