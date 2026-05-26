import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronDown, Eye, EyeOff, Layers, PencilLine, Share2, X } from "lucide-react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { API_BASE, apiActionHint, createJourneyShare, createManualJourneyZone, getBusLineDetails, getBusStopDetails, getJourneyTransportPoints, getJourneyZonesList, getPublicSafetyIncidentsForViewport, getSelectedTransportTrace, getTransportStopDetails, getZoneListings, updateJourney } from "../../api/client";
import { FeedbackFormButton } from "../../components/layout/FeedbackFormButton";
import { FavoritesPanel, WizardPanel } from "../../components/panels";
import { AuthAccessCard } from "../auth/AuthAccessCard";
import { getPoiCategoryMeta, getZonePoiSelectionKey, sortPoiPoints, ZonePoiPointLike, zoneNeedsPoiBackfill } from "../../domain/poi";
import { applyListingsPanelFilters, filterListingsByMapViewport, getListingDisplayPrice, getListingSelectionKey } from "../../lib/listingFormat";
import { getIncludedGreenVegetationLevels, useFavoritesStore, useJourneyStore, useUIStore, useZoneFavoritesStore } from "../../state";

const MAPTILER_KEY =
  import.meta.env.VITE_MAPTILER_API_KEY || (import.meta.env.MODE === "test" ? "test-maptiler-key" : "");

const mapTilerStyleUrl = (key: string) =>
  `https://api.maptiler.com/maps/bright-v2/style.json?key=${encodeURIComponent(key)}`;

const apiTileUrl = (path: string) => `${API_BASE}${path}`;

const BUS_LAYER_LIST = ["bus-line-layer", "bus-stop-layer", "bus-terminal-layer"] as const;
const TRANSPORT_CANDIDATES_SOURCE_ID = "transport-candidates-source-runtime";
const SELECTED_TRANSPORT_TRACE_SOURCE_ID = "selected-transport-trace-source-runtime";
const ZONES_SOURCE_ID = "journey-zones-source-runtime";
const DRAWN_ZONE_SOURCE_ID = "drawn-zone-source-runtime";
const ZONE_POIS_SOURCE_ID = "journey-zone-pois-source-runtime";
const SAVED_ZONES_SOURCE_ID = "saved-zones-source-runtime";
const SAVED_ZONE_POIS_SOURCE_ID = "saved-zone-pois-source-runtime";
const SAVED_ZONE_TRANSPORT_SOURCE_ID = "saved-zone-transport-source-runtime";
const SAVED_ZONE_LISTINGS_SOURCE_ID = "saved-zone-listings-source-runtime";
const SAVED_LISTINGS_SOURCE_ID = "saved-listings-source-runtime";
const LISTINGS_SOURCE_ID = "journey-listings-source-runtime";
const SAFETY_SOURCE_ID = "public-safety-source-runtime";
const PIN_INTERACTIVE_LAYER_LIST = ["transport-candidate-layer", "journey-listings-layer", "saved-listings-layer"] as const;
const TRANSPORT_CANDIDATE_PIN_ICON_ID = "transport-candidate-pin-icon";
const TRANSPORT_CANDIDATE_SELECTED_PIN_ICON_ID = "transport-candidate-pin-selected-icon";
const LISTING_PIN_ICON_ID = "listing-pin-icon";
const LISTING_SELECTED_PIN_ICON_ID = "listing-pin-selected-icon";
const SAVED_LISTING_PIN_ICON_ID = "saved-listing-pin-icon";
const SAVED_LISTING_SELECTED_PIN_ICON_ID = "saved-listing-pin-selected-icon";
const SAVED_ZONE_TRANSPORT_ICON_ID = "saved-zone-transport-diamond-icon";
const SELECTED_PIN_MARKER_STYLE_ID = "selected-map-pin-marker-styles";
const POPUP_PERSIST_LAYER_LIST = [...BUS_LAYER_LIST, "zone-pois-highlight-layer", "zone-pois-layer", "safety-incident-layer", "saved-zone-pois-layer", "saved-zone-transport-layer", "saved-zone-listings-layer", "saved-zones-fill-layer"] as const;
const SAVED_ZONE_POINT_LAYER_LIST = ["saved-zone-pois-layer", "saved-zone-transport-layer", "saved-zone-listings-layer", "saved-listings-layer"] as const;
const REFERENCE_POINT_BLOCKING_LAYER_LIST = [
  "bus-line-layer",
  "bus-stop-layer",
  "bus-terminal-layer",
  "transport-candidate-layer",
  "zones-runtime-fill-layer",
  "zone-pois-layer",
  "safety-incident-layer",
  "journey-listings-layer",
  "saved-zone-pois-layer",
  "saved-zone-transport-layer",
  "saved-zone-listings-layer",
  "saved-zones-fill-layer",
  "saved-listings-layer",
] as const;
const MAP_LAYER_STACK_ORDER = [
  "green-layer",
  "flood-layer",
  "safety-incident-heatmap-layer",
  "zones-runtime-fill-layer",
  "saved-zones-fill-layer",
  "drawn-zone-fill-layer",
  "zones-runtime-outline-layer",
  "saved-zones-outline-layer",
  "drawn-zone-outline-layer",
  "bus-line-layer",
  "bus-line-direction-layer",
  "metro-line-layer",
  "train-line-layer",
  "selected-bus-trace-casing-layer",
  "selected-bus-trace-layer",
  "selected-metro-trace-casing-layer",
  "selected-metro-trace-layer",
  "selected-train-trace-casing-layer",
  "selected-train-trace-layer",
  "zones-runtime-label-layer",
  "saved-zone-transport-label-layer",
  "zone-pois-highlight-layer",
  "safety-incident-layer",
  "metro-station-layer",
  "train-station-layer",
  "saved-zone-pois-layer",
  "saved-zone-transport-layer",
  "bus-stop-layer",
  "bus-terminal-layer",
  "transport-candidate-layer",
  "zone-pois-layer",
  "journey-listings-layer",
  "saved-zone-listings-layer",
  "saved-listings-layer",
] as const;
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

const SAFETY_GROUP_META = [
  { key: "theft", label: "Furto", color: "#eab308" },
  { key: "robbery", label: "Roubo", color: "#ef4444" },
  { key: "violence", label: "Violência", color: "#f97316" },
  { key: "sexual", label: "Violência sexual", color: "#db2777" },
  { key: "drugs", label: "Drogas", color: "#7c3aed" },
  { key: "other", label: "Outros", color: "#64748b" },
] as const;

type SafetyGroupKey = typeof SAFETY_GROUP_META[number]["key"];

const DEFAULT_SAFETY_GROUP_VISIBILITY = Object.fromEntries(
  SAFETY_GROUP_META.map((item) => [item.key, true])
) as Record<SafetyGroupKey, boolean>;

const SAFETY_GROUP_KEYS = SAFETY_GROUP_META.map((item) => item.key) as SafetyGroupKey[];

type MapOverlayLayerKey =
  | "routes"
  | "metro"
  | "train"
  | "busStops"
  | "transportCandidates"
  | "zones"
  | "pois"
  | "listings"
  | "safety"
  | "flood"
  | "green"
  | "savedZones"
  | "savedListings";

type LayerLegendMarkerKind = "line" | "dot" | "fill" | "pin" | "square" | "diamond";

type LayerLegendItem = {
  id: string;
  label: string;
  markerKind: LayerLegendMarkerKind;
  color: string;
  borderColor?: string;
  dashed?: boolean;
};

type SequentialLayerGroupKey = "transportPoints" | "transportLines" | "green" | "flood" | "safety";

type SequentialLayerSettings = {
  layerVisibility: Record<MapOverlayLayerKey, boolean>;
  greenEnabled: boolean;
  safetyEnabled: boolean;
};

type TransportCandidatePoint = {
  id: string;
  lon: number;
  lat: number;
  name?: string | null;
  route_count: number;
  source: string;
  external_id?: string | null;
  route_ids?: string[];
  modal_types?: string[];
};

const DEFAULT_LAYER_VISIBILITY: Record<MapOverlayLayerKey, boolean> = {
  routes: true,
  metro: true,
  train: true,
  busStops: true,
  transportCandidates: true,
  zones: true,
  pois: true,
  listings: false,
  safety: true,
  flood: true,
  green: true,
  savedZones: true,
  savedListings: true,
};

const MAP_LAYER_MENU_ITEMS: Array<{ key: MapOverlayLayerKey; label: string }> = [
  { key: "routes", label: "Rotas de ônibus" },
  { key: "metro", label: "Linhas de metrô" },
  { key: "train", label: "Linhas de trem" },
  { key: "busStops", label: "Paradas e terminais" },
  { key: "transportCandidates", label: "Pontos da etapa 2" },
  { key: "zones", label: "Zonas" },
  { key: "pois", label: "Pontos de interesse da zona" },
  { key: "listings", label: "Imóveis" },
  { key: "safety", label: "Segurança" },
  { key: "flood", label: "Alagamento" },
  { key: "green", label: "Áreas verdes" },
  { key: "savedZones", label: "Zonas salvas" },
  { key: "savedListings", label: "Imóveis salvos" },
];

const DEFAULT_LAYER_LEGEND_EXPANSION = Object.fromEntries(
  MAP_LAYER_MENU_ITEMS.map((item) => [item.key, false])
) as Record<MapOverlayLayerKey, boolean>;

const BASE_LAYER_LEGEND_ITEMS: Record<Exclude<MapOverlayLayerKey, "safety">, LayerLegendItem[]> = {
  routes: [
    { id: "routes-bus", label: "Traçado do ônibus", markerKind: "line", color: "#845ef7", dashed: true },
  ],
  metro: [
    { id: "metro-line", label: "Linha de metrô", markerKind: "line", color: "#e11d48" },
  ],
  train: [
    { id: "train-line", label: "Linha de trem", markerKind: "line", color: "#0f766e" },
  ],
  busStops: [
    { id: "bus-stop", label: "Ponto", markerKind: "dot", color: "#845ef7" },
    { id: "bus-terminal", label: "Terminal", markerKind: "dot", color: "#f97316" },
    { id: "metro-station", label: "Estação de metrô", markerKind: "diamond", color: "#e11d48" },
    { id: "train-station", label: "Estação de trem", markerKind: "diamond", color: "#0f766e" },
  ],
  transportCandidates: [
    { id: "transport-candidate", label: "Disponível", markerKind: "pin", color: "#64748b" },
    { id: "transport-candidate-selected", label: "Selecionado", markerKind: "pin", color: "#845ef7" },
  ],
  zones: [
    { id: "zone-default", label: "Zona", markerKind: "fill", color: "rgba(148,163,184,0.26)", borderColor: "#64748b" },
    { id: "zone-selected", label: "Selecionada", markerKind: "fill", color: "rgba(124,58,237,0.28)", borderColor: "#6d28d9" },
  ],
  pois: [
    { id: "poi-school", label: getPoiCategoryMeta("school").singularLabel, markerKind: "dot", color: getPoiCategoryMeta("school").color },
    { id: "poi-supermarket", label: getPoiCategoryMeta("supermarket").singularLabel, markerKind: "dot", color: getPoiCategoryMeta("supermarket").color },
    { id: "poi-pharmacy", label: getPoiCategoryMeta("pharmacy").singularLabel, markerKind: "dot", color: getPoiCategoryMeta("pharmacy").color },
    { id: "poi-park", label: getPoiCategoryMeta("park").singularLabel, markerKind: "dot", color: getPoiCategoryMeta("park").color },
    { id: "poi-restaurant", label: getPoiCategoryMeta("restaurant").singularLabel, markerKind: "dot", color: getPoiCategoryMeta("restaurant").color },
    { id: "poi-gym", label: getPoiCategoryMeta("gym").singularLabel, markerKind: "dot", color: getPoiCategoryMeta("gym").color },
  ],
  listings: [
    { id: "listing-default", label: "Imóvel", markerKind: "pin", color: "#845ef7" },
    { id: "listing-selected", label: "Selecionado", markerKind: "pin", color: "#5b21b6" },
  ],
  flood: [
    { id: "flood-fill", label: "Mancha de alagamento", markerKind: "fill", color: "rgba(55,138,221,0.24)", borderColor: "#378add" },
  ],
  green: [
    { id: "green-fill", label: "Cobertura vegetal", markerKind: "fill", color: "rgba(106,159,43,0.24)", borderColor: "#6a9f2b" },
  ],
  savedZones: [
    { id: "saved-zone-fill", label: "Zona salva", markerKind: "fill", color: "rgba(14,165,233,0.18)", borderColor: "#0369a1", dashed: true },
    { id: "saved-zone-transport", label: "Ponto seed", markerKind: "pin", color: "#1001b4" },
  ],
  savedListings: [
    { id: "saved-listing", label: "Imóvel salvo", markerKind: "pin", color: "#d33ff4" },
    { id: "saved-listing-selected", label: "Selecionado", markerKind: "pin", color: "#ea2afc" },
  ],
};

const SEQUENTIAL_LAYER_GROUPS: Array<{ key: SequentialLayerGroupKey; sourceId: string }> = [
  { key: "transportPoints", sourceId: "transport-stops-source" },
  { key: "transportLines", sourceId: "transport-lines-source" },
  { key: "green", sourceId: "green-areas-source" },
  { key: "flood", sourceId: "flood-areas-source" },
  { key: "safety", sourceId: SAFETY_SOURCE_ID },
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
    case "safety":
      return settings.layerVisibility.safety && settings.safetyEnabled;
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

function collectGeometryCoordinates(geom: GeoJSON.Geometry | null | undefined): [number, number][] {
  if (!geom) return [];
  const out: [number, number][] = [];
  const visit = (node: unknown): void => {
    if (!Array.isArray(node)) return;
    if (typeof node[0] === "number" && typeof node[1] === "number") {
      out.push([node[0] as number, node[1] as number]);
      return;
    }
    for (const item of node) visit(item);
  };
  if ("coordinates" in geom) {
    visit((geom as { coordinates: unknown }).coordinates);
  }
  return out;
}

const setGeoJsonSourceData = (map: maplibregl.Map, sourceId: string, data: GeoJSON.FeatureCollection<GeoJSON.Geometry>) => {
  const source = map.getSource(sourceId) as maplibregl.GeoJSONSource | undefined;
  if (source) {
    source.setData(data);
  }
};

const getMapViewportBounds = (map: maplibregl.Map) => {
  const bounds = map.getBounds();
  return {
    minLon: bounds.getWest(),
    minLat: bounds.getSouth(),
    maxLon: bounds.getEast(),
    maxLat: bounds.getNorth(),
  };
};

const getZonePalette = (index: number) => ZONE_COLOR_PALETTE[index % ZONE_COLOR_PALETTE.length];

const toTransportCandidatesFeatureCollection = (
  points: TransportCandidatePoint[],
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
  const width = 40;
  const height = 40;
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

const createEmptyStyleImage = (width: number, height: number) => ({
  width,
  height,
  data: new Uint8Array(width * height * 4),
});

const drawPinPath = (context: CanvasRenderingContext2D) => {
  context.beginPath();
  context.moveTo(18, 43);
  context.bezierCurveTo(17.2, 41.9, 6.2, 28.4, 6.2, 16.8);
  context.bezierCurveTo(6.2, 9.2, 11.4, 4.2, 18, 4.2);
  context.bezierCurveTo(24.6, 4.2, 29.8, 9.2, 29.8, 16.8);
  context.bezierCurveTo(29.8, 28.4, 18.8, 41.9, 18, 43);
  context.closePath();
};

const createPinIcon = (fillHex: string) => {
  const width = 36;
  const height = 48;

  if (typeof document === "undefined" || import.meta.env.MODE === "test") {
    return createEmptyStyleImage(width, height);
  }

  try {
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d");
    if (!context) {
      return createEmptyStyleImage(width, height);
    }

    context.clearRect(0, 0, width, height);
    context.fillStyle = fillHex;
    context.strokeStyle = "#ffffff";
    context.lineWidth = 2.4;
    context.lineJoin = "round";
    drawPinPath(context);
    context.fill();
    context.stroke();

    context.beginPath();
    context.arc(18, 16.4, 6.3, 0, Math.PI * 2);
    context.fillStyle = "rgba(255,255,255,0.98)";
    context.fill();

    const imageData = context.getImageData(0, 0, width, height);
    return {
      width,
      height,
      data: new Uint8Array(imageData.data),
    };
  } catch {
    return createEmptyStyleImage(width, height);
  }
};

const getPinSvgMarkup = (fillHex: string) => `
  <svg width="36" height="48" viewBox="0 0 36 48" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    <path d="M18 43C17.2 41.9 6.2 28.4 6.2 16.8C6.2 9.2 11.4 4.2 18 4.2C24.6 4.2 29.8 9.2 29.8 16.8C29.8 28.4 18.8 41.9 18 43Z" fill="${fillHex}" stroke="#ffffff" stroke-width="2.4" stroke-linejoin="round"/>
    <circle cx="18" cy="16.4" r="6.3" fill="rgba(255,255,255,0.98)"/>
  </svg>
`;

const ensureSelectedPinMarkerStyles = () => {
  if (typeof document === "undefined" || document.getElementById(SELECTED_PIN_MARKER_STYLE_ID)) {
    return;
  }

  const style = document.createElement("style");
  style.id = SELECTED_PIN_MARKER_STYLE_ID;
  style.textContent = `
    @keyframes selected-map-pin-bounce {
      0%, 100% { transform: translateY(0) scale(1.08); }
      32% { transform: translateY(-7px) scale(1.14); }
      68% { transform: translateY(-2px) scale(1.11); }
    }

    .selected-map-pin-root {
      pointer-events: none;
      transform: translateY(2px);
    }

    .selected-map-pin-bounce {
      animation: selected-map-pin-bounce 1.15s ease-in-out infinite;
      filter: drop-shadow(0 10px 14px rgba(15, 23, 42, 0.22));
      transform-origin: center bottom;
    }
  `;
  document.head.appendChild(style);
};

const createSelectedPinMarkerElement = (fillHex: string, kind: "listing" | "transport") => {
  ensureSelectedPinMarkerStyles();

  const root = document.createElement("div");
  root.className = "selected-map-pin-root";
  root.dataset.selectedPinKind = kind;

  const inner = document.createElement("div");
  inner.className = "selected-map-pin-bounce";
  inner.innerHTML = getPinSvgMarkup(fillHex);

  root.appendChild(inner);
  return root;
};

const removeMarker = (marker: maplibregl.Marker | null) => {
  marker?.remove();
  return null;
};

const buildSelectedPinMarker = (
  map: maplibregl.Map,
  coordinates: [number, number],
  fillHex: string,
  kind: "listing" | "transport"
) => {
  return new maplibregl.Marker({
    anchor: "bottom",
    element: createSelectedPinMarkerElement(fillHex, kind),
  })
    .setLngLat(coordinates)
    .addTo(map);
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

const createPolygonIcon = (fillHex: string, outerPoints: Array<[number, number]>, innerPoints: Array<[number, number]>) => {
  const width = 24;
  const height = 24;
  const data = new Uint8Array(width * height * 4);
  const [fr, fg, fb] = hexToRgb(fillHex);

  const pointInPolygon = (x: number, y: number, points: Array<[number, number]>) => {
    let inside = false;
    for (let i = 0, j = points.length - 1; i < points.length; j = i, i += 1) {
      const [xi, yi] = points[i];
      const [xj, yj] = points[j];
      const intersects = yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi;
      if (intersects) inside = !inside;
    }
    return inside;
  };

  const setPixel = (x: number, y: number, r: number, g: number, b: number, a: number) => {
    if (x < 0 || y < 0 || x >= width || y >= height) return;
    const idx = (y * width + x) * 4;
    data[idx] = r;
    data[idx + 1] = g;
    data[idx + 2] = b;
    data[idx + 3] = a;
  };

  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const px = x + 0.5;
      const py = y + 0.5;
      if (pointInPolygon(px, py, outerPoints)) {
        setPixel(x, y, 255, 255, 255, 255);
      }
      if (pointInPolygon(px, py, innerPoints)) {
        setPixel(x, y, fr, fg, fb, 255);
      }
    }
  }

  return { width, height, data };
};

const createDiamondIcon = (fillHex: string) =>
  createPolygonIcon(fillHex, [[12, 1], [23, 12], [12, 23], [1, 12]], [[12, 4], [20, 12], [12, 20], [4, 12]]);

const normalizeHexColor = (value: string | null | undefined, fallback = "#0ea5e9") =>
  typeof value === "string" && /^#[0-9a-fA-F]{6}$/.test(value.trim()) ? value.trim().toLowerCase() : fallback;

const getSavedZoneListingIconId = (color: string) => `saved-zone-listing-pin-${normalizeHexColor(color).slice(1)}`;

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
          name: point.name || "Ponto de interesse sem nome",
          address: point.address || "",
          category: point.category || "other"
        }
      };
    })
});

const toDrawnZoneFeatureCollection = (points: Array<[number, number]>): GeoJSON.FeatureCollection => {
  const features: GeoJSON.Feature[] = [];
  if (points.length >= 2) {
    features.push({
      type: "Feature",
      geometry: {
        type: "LineString",
        coordinates: points,
      },
      properties: { kind: "line" },
    });
  }
  if (points.length >= 3) {
    features.push({
      type: "Feature",
      geometry: {
        type: "Polygon",
        coordinates: [[...points, points[0]]],
      },
      properties: { kind: "polygon" },
    });
  }
  return { type: "FeatureCollection", features };
};

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
      : '<p style="margin:0; font-size:12px; color:#64748b;">Dados de linhas indisponíveis para este ponto.</p>';
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
    <p style="margin:0; font-size:12px; color:#64748b;">Carregando linhas encontradas...</p>
  </div>
`;

const poiPopupContent = (name: string, categoryLabel: string, address: string | null) => `
  <div style="font-family: system-ui, -apple-system, Segoe UI, sans-serif; min-width: 220px;">
    <p style="margin:0 0 4px; font-size:11px; letter-spacing:0.06em; text-transform:uppercase; color:#64748b;">${escapeHtml(categoryLabel)}</p>
    <p style="margin:0 0 8px; font-size:13px; font-weight:700; color:#0f172a;">${escapeHtml(name)}</p>
    ${address ? `<p style="margin:0; font-size:12px; color:#475569;">${escapeHtml(address)}</p>` : '<p style="margin:0; font-size:12px; color:#64748b;">Endereço indisponível.</p>'}
  </div>
`;

const formatSafetyOccurredAt = (occurredAt: string | null | undefined) => {
  if (!occurredAt) {
    return "Data indisponível";
  }
  const parsed = new Date(occurredAt);
  if (Number.isNaN(parsed.getTime())) {
    return "Data indisponível";
  }
  return parsed.toLocaleString("pt-BR");
};

const safetyPopupContent = (crimeType: string, crimeGroupLabel: string, occurredAt: string | null | undefined) => `
  <div style="font-family: system-ui, -apple-system, Segoe UI, sans-serif; min-width: 220px;">
    <p style="margin:0 0 4px; font-size:11px; letter-spacing:0.06em; text-transform:uppercase; color:#64748b;">${escapeHtml(crimeGroupLabel)}</p>
    <p style="margin:0 0 8px; font-size:13px; font-weight:700; color:#0f172a;">${escapeHtml(crimeType)}</p>
    <p style="margin:0; font-size:12px; color:#475569;">${escapeHtml(formatSafetyOccurredAt(occurredAt))}</p>
  </div>
`;

const savedSeedPopupContent = (name: string) => `
  <div style="font-family: system-ui, -apple-system, Segoe UI, sans-serif; min-width: 220px;">
    <p style="margin:0 0 4px; font-size:11px; letter-spacing:0.06em; text-transform:uppercase; color:#64748b;">Ponto seed salvo</p>
    <p style="margin:0; font-size:13px; font-weight:700; color:#0f172a;">${escapeHtml(name)}</p>
  </div>
`;

const savedZonePopupContent = (label: string) => `
  <div style="font-family: system-ui, -apple-system, Segoe UI, sans-serif; min-width: 220px;">
    <p style="margin:0 0 4px; font-size:11px; letter-spacing:0.06em; text-transform:uppercase; color:#64748b;">Zona salva</p>
    <p style="margin:0; font-size:13px; font-weight:700; color:#0f172a;">${escapeHtml(label)}</p>
  </div>
`;

function reorderMapLayers(map: maplibregl.Map) {
  for (const layerId of MAP_LAYER_STACK_ORDER) {
    map.moveLayer(layerId);
  }
}

function renderLegendMarker(item: LayerLegendItem) {
  if (item.markerKind === "line") {
    return (
      <span
        className={`block w-4 border-t-2 ${item.dashed ? "border-dashed" : ""}`}
        style={{ borderColor: item.color }}
        aria-hidden="true"
      />
    );
  }

  if (item.markerKind === "fill") {
    return (
      <span
        className="block h-2.5 w-2.5 rounded-[4px] border"
        style={{ backgroundColor: item.color, borderColor: item.borderColor || item.color }}
        aria-hidden="true"
      />
    );
  }

  if (item.markerKind === "pin") {
    return (
      <span className="relative block h-3.5 w-2.5" aria-hidden="true">
        <span
          className="absolute left-1/2 top-0 h-2.5 w-2.5 -translate-x-1/2 rounded-full border border-white/90 shadow-sm"
          style={{ backgroundColor: item.color }}
        />
        <span
          className="absolute left-1/2 top-[7px] h-1.5 w-1.5 -translate-x-1/2 rotate-45 border-b border-r border-white/90"
          style={{ backgroundColor: item.color }}
        />
      </span>
    );
  }

  return (
    <span
      className="block h-2.5 w-2.5 rounded-full border border-white/90 shadow-sm"
      style={{ backgroundColor: item.color }}
      aria-hidden="true"
    />
  );
}

export function FindIdealApp() {
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const queryClient = useQueryClient();
  const layerMenuRef = useRef<HTMLDivElement | null>(null);
  const layerMenuButtonRef = useRef<HTMLButtonElement | null>(null);
  const busPopupRef = useRef<maplibregl.Popup | null>(null);
  const pickedMarkerRef = useRef<maplibregl.Marker | null>(null);
  const selectedTransportMarkerRef = useRef<maplibregl.Marker | null>(null);
  const selectedListingMarkerRef = useRef<maplibregl.Marker | null>(null);
  const [isMapReady, setIsMapReady] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);
  const [isLayerMenuOpen, setIsLayerMenuOpen] = useState(false);
  const [layerVisibility, setLayerVisibility] = useState<Record<MapOverlayLayerKey, boolean>>(DEFAULT_LAYER_VISIBILITY);
  const [expandedLayerLegends, setExpandedLayerLegends] = useState<Record<MapOverlayLayerKey, boolean>>(DEFAULT_LAYER_LEGEND_EXPANSION);
  const [safetyGroupVisibility, setSafetyGroupVisibility] = useState<Record<SafetyGroupKey, boolean>>(DEFAULT_SAFETY_GROUP_VISIBILITY);
  const [isolatedSafetyGroup, setIsolatedSafetyGroup] = useState<SafetyGroupKey | null>(null);
  const [safetyGroupVisibilityBeforeIsolation, setSafetyGroupVisibilityBeforeIsolation] = useState<Record<SafetyGroupKey, boolean> | null>(null);
  const [visibleSequentialLayerGroupIndex, setVisibleSequentialLayerGroupIndex] = useState(-1);
  const [transportCandidatePoints, setTransportCandidatePoints] = useState<TransportCandidatePoint[]>([]);
  const [isDrawingZone, setIsDrawingZone] = useState(false);
  const [drawnZonePoints, setDrawnZonePoints] = useState<Array<[number, number]>>([]);
  const [manualZoneError, setManualZoneError] = useState<string | null>(null);
  const [isSavingManualZone, setIsSavingManualZone] = useState(false);
  const [selectedZonePoiState, setSelectedZonePoiState] = useState<{ zoneFingerprint: string | null; poiPoints: ZonePoiPointLike[] }>({
    zoneFingerprint: null,
    poiPoints: []
  });
  const step = useUIStore((state) => state.step);
  const goToStep = useUIStore((state) => state.goToStep);
  const setMaxStep = useUIStore((state) => state.setMaxStep);
  const pickedCoord = useJourneyStore((state) => state.pickedCoord);
  const referenceInputMode = useJourneyStore((state) => state.referenceInputMode);
  const pendingManualAreaDrawing = useJourneyStore((state) => state.pendingManualAreaDrawing);
  const isPickingReferencePoint = useJourneyStore((state) => state.isPickingReferencePoint);
  const setPickedCoord = useJourneyStore((state) => state.setPickedCoord);
  const setIsPickingReferencePoint = useJourneyStore((state) => state.setIsPickingReferencePoint);
  const journeyId = useJourneyStore((state) => state.journeyId);
  const selectedTransportId = useJourneyStore((state) => state.selectedTransportId);
  const selectedZoneFingerprint = useJourneyStore((state) => state.selectedZoneFingerprint);
  const selectedListingKey = useJourneyStore((state) => state.selectedListingKey);
  const selectedPoiKey = useJourneyStore((state) => state.selectedPoiKey);
  const activePoiCategory = useJourneyStore((state) => state.activePoiCategory);
  const listingsJobId = useJourneyStore((state) => state.listingsJobId);
  const listingsFilters = useJourneyStore((state) => state.listingsFilters);
  const listingsAddressScope = useJourneyStore((state) => state.listingsAddressScope);
  const mapViewportBounds = useJourneyStore((state) => state.mapViewportBounds);
  const config = useJourneyStore((state) => state.config);
  const isFavoritesPanelOpen = useFavoritesStore((state) => state.isPanelOpen);
  const favoriteListings = useFavoritesStore((state) => state.favorites);
  const selectedSavedListingKey = useFavoritesStore((state) => state.selectedSavedListingKey);
  const setSelectedSavedListingKey = useFavoritesStore((state) => state.setSelectedSavedListingKey);
  const savedZoneFavorites = useZoneFavoritesStore((state) => state.zoneFavorites);
  const hiddenSavedZoneKeys = useZoneFavoritesStore((state) => state.hiddenZoneKeys);
  const selectedSavedZoneKey = useZoneFavoritesStore((state) => state.selectedZoneKey);
  const setSelectedSavedZoneKey = useZoneFavoritesStore((state) => state.setSelectedZoneKey);
  const setSelectedTransportId = useJourneyStore((state) => state.setSelectedTransportId);
  const setSelectedListingKey = useJourneyStore((state) => state.setSelectedListingKey);
  const setSelectedPoiKey = useJourneyStore((state) => state.setSelectedPoiKey);
  const setSelectedZone = useJourneyStore((state) => state.setSelectedZone);
  const consumeManualAreaDrawingRequest = useJourneyStore((state) => state.consumeManualAreaDrawingRequest);
  const setMapViewportBounds = useJourneyStore((state) => state.setMapViewportBounds);
  const [copiedCoordsToast, setCopiedCoordsToast] = useState<string | null>(null);
  const [shareToast, setShareToast] = useState<{ title: string; detail?: string; tone: "success" | "error" } | null>(null);
  const [isSharingJourney, setIsSharingJourney] = useState(false);
  const copiedToastTimerRef = useRef<number | undefined>(undefined);
  const shareToastTimerRef = useRef<number | undefined>(undefined);
  const zonesDataRef = useRef<Array<{ fingerprint: string; isochrone_geom: unknown }>>([]);
  const stepRef = useRef(step);
  const isPickingReferencePointRef = useRef(isPickingReferencePoint);
  const isDrawingZoneRef = useRef(isDrawingZone);
  const drawnZonePointsRef = useRef(drawnZonePoints);
  const sequentialLayerSettingsRef = useRef<SequentialLayerSettings>({
    layerVisibility: DEFAULT_LAYER_VISIBILITY,
    greenEnabled: config.enrichments.green,
    safetyEnabled: config.enrichments.safety,
  });

  function toggleLayerVisibility(key: MapOverlayLayerKey) {
    setLayerVisibility((current) => ({
      ...current,
      [key]: !current[key]
    }));
  }

  function toggleLayerLegendExpansion(key: MapOverlayLayerKey) {
    setExpandedLayerLegends((current) => ({
      ...current,
      [key]: !current[key],
    }));
  }

  function toggleSafetyGroupVisibility(groupKey: SafetyGroupKey) {
    setSafetyGroupVisibility((current) => {
      const baseVisibility = safetyGroupVisibilityBeforeIsolation ?? current;
      const nextVisibility = !baseVisibility[groupKey];
      return {
        ...baseVisibility,
        [groupKey]: nextVisibility,
      };
    });
    setIsolatedSafetyGroup(null);
    setSafetyGroupVisibilityBeforeIsolation(null);
  }

  function toggleSafetyGroupIsolation(groupKey: SafetyGroupKey) {
    if (isolatedSafetyGroup === groupKey) {
      setSafetyGroupVisibility(safetyGroupVisibilityBeforeIsolation ?? DEFAULT_SAFETY_GROUP_VISIBILITY);
      setIsolatedSafetyGroup(null);
      setSafetyGroupVisibilityBeforeIsolation(null);
      return;
    }

    setSafetyGroupVisibilityBeforeIsolation(safetyGroupVisibility);
    setSafetyGroupVisibility(
      SAFETY_GROUP_KEYS.reduce<Record<SafetyGroupKey, boolean>>((accumulator, key) => {
        accumulator[key] = key === groupKey;
        return accumulator;
      }, { ...DEFAULT_SAFETY_GROUP_VISIBILITY })
    );
    setIsolatedSafetyGroup(groupKey);
  }

  function showShareToast(toast: { title: string; detail?: string; tone: "success" | "error" }) {
    setShareToast(toast);
    window.clearTimeout(shareToastTimerRef.current);
    shareToastTimerRef.current = window.setTimeout(() => setShareToast(null), toast.tone === "error" ? 5200 : 3200);
  }

  async function handleShareJourney() {
    if (!journeyId || isSharingJourney) {
      return;
    }
    setIsSharingJourney(true);
    try {
      const share = await createJourneyShare(journeyId);
      const url = new URL(window.location.href);
      url.hash = `#/jornada/compartilhada/${encodeURIComponent(share.token)}`;
      const shareUrl = url.toString();
      if (!navigator.clipboard?.writeText) {
        showShareToast({
          title: "Link criado",
          detail: shareUrl,
          tone: "success",
        });
        return;
      }
      await navigator.clipboard.writeText(shareUrl);
      showShareToast({
        title: "Link da jornada copiado",
        detail: shareUrl,
        tone: "success",
      });
    } catch (error) {
      showShareToast({
        title: "Não foi possível compartilhar",
        detail: apiActionHint(error),
        tone: "error",
      });
    } finally {
      setIsSharingJourney(false);
    }
  }

  function startDrawingZone() {
    if (!journeyId) {
      setManualZoneError("Crie a jornada antes de desenhar uma zona.");
      return;
    }
    setManualZoneError(null);
    setDrawnZonePoints([]);
    setIsPickingReferencePoint(false);
    setIsDrawingZone(true);
  }

  function cancelDrawingZone() {
    setIsDrawingZone(false);
    setDrawnZonePoints([]);
    setManualZoneError(null);
  }

  async function finishDrawingZone() {
    if (!journeyId || isSavingManualZone) {
      return;
    }
    const points = drawnZonePointsRef.current;
    if (points.length < 3) {
      setManualZoneError("Desenhe pelo menos 3 vértices para criar uma zona.");
      return;
    }
    setIsSavingManualZone(true);
    setManualZoneError(null);
    try {
      const geometry: GeoJSON.Polygon = {
        type: "Polygon",
        coordinates: [[...points, points[0]]],
      };
      const zone = await createManualJourneyZone(journeyId, geometry, `Zona desenhada ${points.length} pontos`);
      await queryClient.invalidateQueries({ queryKey: ["journey-zones", journeyId] });
      setSelectedZone(zone.id, zone.fingerprint);
      await updateJourney(journeyId, { selected_zone_id: zone.id, last_completed_step: 4 });
      setMaxStep(4);
      goToStep(4);
      setIsDrawingZone(false);
      setDrawnZonePoints([]);
    } catch (error) {
      setManualZoneError(apiActionHint(error));
    } finally {
      setIsSavingManualZone(false);
    }
  }

  useEffect(() => {
    if (!pendingManualAreaDrawing || !journeyId) {
      return;
    }
    consumeManualAreaDrawingRequest();
    startDrawingZone();
  }, [consumeManualAreaDrawingRequest, journeyId, pendingManualAreaDrawing]);

  useEffect(() => {
    stepRef.current = step;
  }, [step]);

  useEffect(() => {
    isPickingReferencePointRef.current = isPickingReferencePoint;
  }, [isPickingReferencePoint]);

  useEffect(() => {
    isDrawingZoneRef.current = isDrawingZone;
    const map = mapRef.current;
    if (map) {
      map.getCanvas().style.cursor = isDrawingZone ? "crosshair" : "";
    }
  }, [isDrawingZone]);

  useEffect(() => {
    drawnZonePointsRef.current = drawnZonePoints;
    const map = mapRef.current;
    if (map && isMapReady) {
      setGeoJsonSourceData(map, DRAWN_ZONE_SOURCE_ID, toDrawnZoneFeatureCollection(drawnZonePoints));
    }
  }, [drawnZonePoints, isMapReady]);

  useEffect(() => {
    if (step >= 6) {
      setLayerVisibility((current) => current.listings ? current : { ...current, listings: true });
    }
  }, [step]);

  useEffect(() => {
    sequentialLayerSettingsRef.current = {
      layerVisibility,
      greenEnabled: config.enrichments.green,
      safetyEnabled: config.enrichments.safety,
    };

    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }

    setVisibleSequentialLayerGroupIndex(resolveVisibleSequentialLayerGroupIndex(map, sequentialLayerSettingsRef.current));
  }, [config.enrichments.green, config.enrichments.safety, isMapReady, layerVisibility]);

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
    queryKey: ["zone-listings", journeyId, selectedZoneFingerprint, config.type, "all", listingsAddressScope],
    queryFn: async () => getZoneListings(journeyId as string, selectedZoneFingerprint as string, config.type, "all", "all", listingsAddressScope, 9999, 0),
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
    () => applyListingsPanelFilters(filterListingsByMapViewport(listingsQuery.data?.listings || [], mapViewportBounds), listingsFilters),
    [listingsFilters, listingsQuery.data?.listings, mapViewportBounds]
  );

  const activeSafetyGroups = useMemo(
    () => SAFETY_GROUP_KEYS.filter((groupKey) => safetyGroupVisibility[groupKey]),
    [safetyGroupVisibility]
  );

  const activeSafetyGroupsKey = activeSafetyGroups.join(",");

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
      const syncMapViewportBounds = () => {
        setMapViewportBounds(getMapViewportBounds(map));
      };

      const syncSequentialLayerLoadSequence = () => {
        setVisibleSequentialLayerGroupIndex(resolveVisibleSequentialLayerGroupIndex(map, sequentialLayerSettingsRef.current));
      };

      if (!map.hasImage("bus-stop-icon")) {
        map.addImage("bus-stop-icon", createBusIcon("#845ef7"));
      }
      if (!map.hasImage("bus-terminal-icon")) {
        map.addImage("bus-terminal-icon", createBusIcon("#f97316"));
      }
      if (!map.hasImage(TRANSPORT_CANDIDATE_PIN_ICON_ID)) {
        map.addImage(TRANSPORT_CANDIDATE_PIN_ICON_ID, createPinIcon("#64748b"));
      }
      if (!map.hasImage(TRANSPORT_CANDIDATE_SELECTED_PIN_ICON_ID)) {
        map.addImage(TRANSPORT_CANDIDATE_SELECTED_PIN_ICON_ID, createPinIcon("#845ef7"));
      }
      if (!map.hasImage(LISTING_PIN_ICON_ID)) {
        map.addImage(LISTING_PIN_ICON_ID, createPinIcon("#845ef7"));
      }
      if (!map.hasImage(LISTING_SELECTED_PIN_ICON_ID)) {
        map.addImage(LISTING_SELECTED_PIN_ICON_ID, createPinIcon("#5b21b6"));
      }
      if (!map.hasImage(SAVED_LISTING_PIN_ICON_ID)) {
        // Rosa dos botões "salvar/remover" (rose-500).
        map.addImage(SAVED_LISTING_PIN_ICON_ID, createPinIcon("#f43f5e"));
      }
      if (!map.hasImage(SAVED_LISTING_SELECTED_PIN_ICON_ID)) {
        map.addImage(SAVED_LISTING_SELECTED_PIN_ICON_ID, createPinIcon("#be123c"));
      }
      if (!map.hasImage(SAVED_ZONE_TRANSPORT_ICON_ID)) {
        map.addImage(SAVED_ZONE_TRANSPORT_ICON_ID, createDiamondIcon("#7c3aed"));
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

      map.addSource(SELECTED_TRANSPORT_TRACE_SOURCE_ID, {
        type: "geojson",
        data: EMPTY_FEATURE_COLLECTION,
      });

      map.addSource(ZONES_SOURCE_ID, {
        type: "geojson",
        data: EMPTY_FEATURE_COLLECTION,
      });

      map.addSource(DRAWN_ZONE_SOURCE_ID, {
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

      map.addSource(SAFETY_SOURCE_ID, {
        type: "geojson",
        data: EMPTY_FEATURE_COLLECTION,
      });

      map.addSource(SAVED_ZONES_SOURCE_ID, {
        type: "geojson",
        data: EMPTY_FEATURE_COLLECTION,
      });

      map.addSource(SAVED_ZONE_POIS_SOURCE_ID, {
        type: "geojson",
        data: EMPTY_FEATURE_COLLECTION,
      });

      map.addSource(SAVED_ZONE_TRANSPORT_SOURCE_ID, {
        type: "geojson",
        data: EMPTY_FEATURE_COLLECTION,
      });

      map.addSource(SAVED_ZONE_LISTINGS_SOURCE_ID, {
        type: "geojson",
        data: EMPTY_FEATURE_COLLECTION,
      });

      map.addSource(SAVED_LISTINGS_SOURCE_ID, {
        type: "geojson",
        data: EMPTY_FEATURE_COLLECTION,
      });

      map.addLayer({
        id: "bus-line-layer",
        type: "line",
        source: "transport-lines-source",
        "source-layer": "transport_lines",
        filter: ["==", ["get", "mode"], "bus"],
        layout: { visibility: "none" },
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
          visibility: "none",
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
        layout: { visibility: "none" },
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
        layout: { visibility: "none" },
        paint: {
          "line-color": "#0f766e",
          "line-width": ["interpolate", ["linear"], ["zoom"], 8, 1.5, 12, 2.8, 15, 4.2],
          "line-opacity": 0.88,
        },
      });

      map.addLayer({
        id: "selected-bus-trace-casing-layer",
        type: "line",
        source: SELECTED_TRANSPORT_TRACE_SOURCE_ID,
        filter: ["==", ["get", "mode"], "bus"],
        layout: { visibility: "none", "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": "#ffffff",
          "line-width": ["interpolate", ["linear"], ["zoom"], 8, 4.2, 12, 6.8, 15, 9.2],
          "line-opacity": 0.96,
        },
      });

      map.addLayer({
        id: "selected-bus-trace-layer",
        type: "line",
        source: SELECTED_TRANSPORT_TRACE_SOURCE_ID,
        filter: ["==", ["get", "mode"], "bus"],
        layout: { visibility: "none", "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": "#5b21b6",
          "line-width": ["interpolate", ["linear"], ["zoom"], 8, 2.4, 12, 4.4, 15, 6.4],
          "line-opacity": 0.98,
        },
      });

      map.addLayer({
        id: "selected-metro-trace-casing-layer",
        type: "line",
        source: SELECTED_TRANSPORT_TRACE_SOURCE_ID,
        filter: ["==", ["get", "mode"], "metro"],
        layout: { visibility: "none", "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": "#ffffff",
          "line-width": ["interpolate", ["linear"], ["zoom"], 8, 4.6, 12, 7.4, 15, 10],
          "line-opacity": 0.96,
        },
      });

      map.addLayer({
        id: "selected-metro-trace-layer",
        type: "line",
        source: SELECTED_TRANSPORT_TRACE_SOURCE_ID,
        filter: ["==", ["get", "mode"], "metro"],
        layout: { visibility: "none", "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": "#e11d48",
          "line-width": ["interpolate", ["linear"], ["zoom"], 8, 2.8, 12, 4.8, 15, 6.8],
          "line-opacity": 0.98,
        },
      });

      map.addLayer({
        id: "selected-train-trace-casing-layer",
        type: "line",
        source: SELECTED_TRANSPORT_TRACE_SOURCE_ID,
        filter: ["==", ["get", "mode"], "train"],
        layout: { visibility: "none", "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": "#ffffff",
          "line-width": ["interpolate", ["linear"], ["zoom"], 8, 4.4, 12, 7, 15, 9.6],
          "line-opacity": 0.96,
        },
      });

      map.addLayer({
        id: "selected-train-trace-layer",
        type: "line",
        source: SELECTED_TRANSPORT_TRACE_SOURCE_ID,
        filter: ["==", ["get", "mode"], "train"],
        layout: { visibility: "none", "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": "#0f766e",
          "line-width": ["interpolate", ["linear"], ["zoom"], 8, 2.6, 12, 4.6, 15, 6.6],
          "line-opacity": 0.98,
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
          visibility: "none",
          "icon-image": "bus-stop-icon",
          "icon-size": ["interpolate", ["linear"], ["zoom"], 9, 0.32, 12, 0.41, 15, 0.53],
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
          visibility: "none",
          "icon-image": "bus-terminal-icon",
          "icon-size": ["interpolate", ["linear"], ["zoom"], 9, 0.39, 12, 0.51, 15, 0.62],
          "icon-allow-overlap": true,
        },
      });

      map.addLayer({
        id: "metro-station-layer",
        type: "circle",
        source: "transport-stops-source",
        "source-layer": "transport_stops",
        filter: ["==", ["get", "kind"], "metro_station"],
        layout: { visibility: "none" },
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
        layout: { visibility: "none" },
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
        type: "symbol",
        source: TRANSPORT_CANDIDATES_SOURCE_ID,
        layout: {
          "icon-image": ["case", ["boolean", ["get", "selected"], false], TRANSPORT_CANDIDATE_SELECTED_PIN_ICON_ID, TRANSPORT_CANDIDATE_PIN_ICON_ID],
          "icon-size": ["interpolate", ["linear"], ["zoom"], 9, 0.48, 12, 0.58, 15, 0.7],
          "icon-anchor": "bottom",
          "icon-allow-overlap": true,
          "icon-ignore-placement": true,
        },
        paint: {
          "icon-opacity": ["case", ["boolean", ["get", "selected"], false], 0.001, 0.97],
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
        id: "drawn-zone-fill-layer",
        type: "fill",
        source: DRAWN_ZONE_SOURCE_ID,
        filter: ["==", ["geometry-type"], "Polygon"],
        paint: {
          "fill-color": "#7c3aed",
          "fill-opacity": 0.18,
        },
      });

      map.addLayer({
        id: "drawn-zone-outline-layer",
        type: "line",
        source: DRAWN_ZONE_SOURCE_ID,
        paint: {
          "line-color": "#6d28d9",
          "line-width": 2.4,
          "line-dasharray": [2, 1],
          "line-opacity": 0.95,
        },
      });

      map.addLayer({
        id: "saved-zones-fill-layer",
        type: "fill",
        source: SAVED_ZONES_SOURCE_ID,
        paint: {
          "fill-color": ["coalesce", ["get", "fill_color"], "#0ea5e9"],
          "fill-opacity": 0.12,
        },
      });

      map.addLayer({
        id: "saved-zones-outline-layer",
        type: "line",
        source: SAVED_ZONES_SOURCE_ID,
        paint: {
          "line-color": ["coalesce", ["get", "outline_color"], "#0369a1"],
          "line-width": 2.0,
          "line-dasharray": [2, 2],
          "line-opacity": 0.9,
        },
      });

      map.addLayer({
        id: "saved-zone-pois-layer",
        type: "symbol",
        source: SAVED_ZONE_POIS_SOURCE_ID,
        layout: {
          "icon-image": ["get", "icon_id"],
          "icon-size": ["interpolate", ["linear"], ["zoom"], 10, 0.28, 14, 0.48, 17, 0.64],
          "icon-allow-overlap": true,
          "icon-ignore-placement": true,
        },
        paint: {
          "icon-opacity": 0.92,
        },
      });

      map.addLayer({
        id: "saved-zone-listings-layer",
        type: "symbol",
        source: SAVED_ZONE_LISTINGS_SOURCE_ID,
        layout: {
          "icon-image": ["get", "icon_id"],
          "icon-size": ["interpolate", ["linear"], ["zoom"], 10, 0.45, 14, 0.58, 17, 0.72],
          "icon-anchor": "bottom",
          "icon-allow-overlap": true,
          "icon-ignore-placement": true,
        },
      });

      map.addLayer({
        id: "saved-zone-transport-layer",
        type: "symbol",
        source: SAVED_ZONE_TRANSPORT_SOURCE_ID,
        layout: {
          "icon-image": SAVED_ZONE_TRANSPORT_ICON_ID,
          "icon-size": ["interpolate", ["linear"], ["zoom"], 9, 0.36, 14, 0.6, 17, 0.84],
          "icon-allow-overlap": true,
          "icon-ignore-placement": true,
        },
        paint: {
          "icon-opacity": 0.96,
        },
      });

      map.addLayer({
        id: "saved-zone-transport-label-layer",
        type: "symbol",
        source: SAVED_ZONE_TRANSPORT_SOURCE_ID,
        layout: {
          "text-field": ["coalesce", ["get", "name"], "Ponto seed"],
          "text-size": 11,
          "text-font": ["Open Sans Bold", "Arial Unicode MS Bold"],
          "text-offset": [0, 1.6],
          "text-anchor": "top",
          "text-allow-overlap": true,
          "text-ignore-placement": true,
        },
        paint: {
          "text-color": "#6d28d9",
          "text-halo-color": "#ffffff",
          "text-halo-width": 1.6,
        },
      });

      map.addLayer({
        id: "saved-listings-layer",
        type: "symbol",
        source: SAVED_LISTINGS_SOURCE_ID,
        layout: {
          "icon-image": [
            "case",
            ["boolean", ["get", "selected"], false],
            SAVED_LISTING_SELECTED_PIN_ICON_ID,
            SAVED_LISTING_PIN_ICON_ID,
          ],
          "icon-size": ["interpolate", ["linear"], ["zoom"], 10, 0.45, 14, 0.58, 17, 0.72],
          "icon-anchor": "bottom",
          "icon-allow-overlap": true,
          "icon-ignore-placement": true,
        },
      });

      map.addLayer({
        id: "safety-incident-heatmap-layer",
        type: "heatmap",
        source: SAFETY_SOURCE_ID,
        layout: { visibility: "none" },
        paint: {
          "heatmap-weight": [
            "case",
            ["has", "point_count"],
            ["interpolate", ["linear"], ["get", "point_count"], 1, 0.2, 20, 0.55, 80, 1],
            0.12
          ],
          "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 10, 0.8, 12, 1.05, 14, 1.35],
          "heatmap-color": [
            "interpolate",
            ["linear"],
            ["heatmap-density"],
            0,
            "rgba(59,130,246,0)",
            0.2,
            "rgba(56,189,248,0.28)",
            0.45,
            "rgba(250,204,21,0.48)",
            0.7,
            "rgba(249,115,22,0.68)",
            1,
            "rgba(220,38,38,0.88)"
          ],
          "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 10, 18, 12, 26, 14, 36],
          "heatmap-opacity": ["interpolate", ["linear"], ["zoom"], 10, 0.6, 13, 0.78, 14, 0.48, 15, 0],
        },
      });

      map.addLayer({
        id: "safety-incident-layer",
        type: "circle",
        source: SAFETY_SOURCE_ID,
        filter: ["!", ["has", "point_count"]],
        layout: { visibility: "none" },
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 9, 3.6, 13, 5.2, 16, 6.4],
          "circle-color": [
            "match",
            ["get", "crime_group"],
            "theft",
            "#eab308",
            "robbery",
            "#ef4444",
            "violence",
            "#f97316",
            "sexual",
            "#db2777",
            "drugs",
            "#7c3aed",
            "#64748b"
          ],
          "circle-opacity": ["interpolate", ["linear"], ["zoom"], 10, 0, 15, 0, 16, 0.9],
          "circle-stroke-color": "#ffffff",
          "circle-stroke-opacity": ["interpolate", ["linear"], ["zoom"], 10, 0, 15, 0, 16, 0.92],
          "circle-stroke-width": ["interpolate", ["linear"], ["zoom"], 10, 0, 15, 0, 16, 1.5],
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
        type: "symbol",
        source: LISTINGS_SOURCE_ID,
        layout: {
          "icon-image": ["case", ["boolean", ["get", "selected"], false], LISTING_SELECTED_PIN_ICON_ID, LISTING_PIN_ICON_ID],
          "icon-size": ["interpolate", ["linear"], ["zoom"], 9, 0.46, 12, 0.56, 15, 0.68],
          "icon-anchor": "bottom",
          "icon-allow-overlap": true,
          "icon-ignore-placement": true,
        },
        paint: {
          "icon-opacity": ["case", ["boolean", ["get", "selected"], false], 0.001, 0.98],
        },
      });

      reorderMapLayers(map);

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
        const name = typeof properties.name === "string" && properties.name.trim() ? properties.name.trim() : "Ponto de interesse sem nome";
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

      map.on("click", "safety-incident-layer", (event) => {
        const feature = event.features?.[0];
        const properties = feature?.properties as Record<string, unknown> | undefined;
        if (!properties) {
          return;
        }

        const crimeType = typeof properties.crime_type === "string" && properties.crime_type.trim()
          ? properties.crime_type.trim()
          : "Ocorrência sem tipo";
        const crimeGroupLabel = typeof properties.crime_group_label === "string" && properties.crime_group_label.trim()
          ? properties.crime_group_label.trim()
          : "Segurança";
        const occurredAt = typeof properties.occurred_at === "string" ? properties.occurred_at : null;

        busPopupRef.current?.remove();
        const popup = new maplibregl.Popup({ closeButton: true, closeOnClick: false, maxWidth: "320px" })
          .setLngLat(event.lngLat)
          .setHTML(safetyPopupContent(crimeType, crimeGroupLabel, occurredAt))
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

      map.on("click", "saved-zone-pois-layer", (event) => {
        const feature = event.features?.[0];
        const properties = feature?.properties as Record<string, unknown> | undefined;
        if (!properties) {
          return;
        }

        const name = typeof properties.name === "string" && properties.name.trim() ? properties.name.trim() : "Ponto de interesse salvo";
        const address = typeof properties.address === "string" && properties.address.trim() ? properties.address.trim() : null;
        const categoryMeta = getPoiCategoryMeta(typeof properties.category === "string" ? properties.category : undefined);

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

      map.on("click", "saved-zone-transport-layer", (event) => {
        const feature = event.features?.[0];
        const properties = feature?.properties as Record<string, unknown> | undefined;
        const name = typeof properties?.name === "string" && properties.name.trim() ? properties.name.trim() : "Ponto seed";

        busPopupRef.current?.remove();
        const popup = new maplibregl.Popup({ closeButton: true, closeOnClick: false, maxWidth: "320px" })
          .setLngLat(event.lngLat)
          .setHTML(savedSeedPopupContent(name))
          .addTo(map);

        busPopupRef.current = popup;
        popup.on("close", () => {
          if (busPopupRef.current === popup) {
            busPopupRef.current = null;
          }
        });
      });

      map.on("click", "saved-zone-listings-layer", (event) => {
        const feature = event.features?.[0];
        const properties = feature?.properties as Record<string, unknown> | undefined;
        const zoneKey = typeof properties?.zone_key === "string" && properties.zone_key.trim() ? properties.zone_key.trim() : null;
        const address = typeof properties?.address === "string" && properties.address.trim() ? properties.address.trim() : "Imóvel salvo com a zona";
        if (zoneKey) {
          setSelectedSavedZoneKey(zoneKey);
        }

        busPopupRef.current?.remove();
        const popup = new maplibregl.Popup({ closeButton: true, closeOnClick: false, maxWidth: "320px" })
          .setLngLat(event.lngLat)
          .setHTML(`
            <div style="font-family: system-ui, -apple-system, Segoe UI, sans-serif; min-width: 220px;">
              <p style="margin:0 0 4px; font-size:11px; letter-spacing:0.06em; text-transform:uppercase; color:#64748b;">Imóvel salvo com a zona</p>
              <p style="margin:0; font-size:13px; font-weight:700; color:#0f172a;">${escapeHtml(address)}</p>
            </div>
          `)
          .addTo(map);

        busPopupRef.current = popup;
        popup.on("close", () => {
          if (busPopupRef.current === popup) {
            busPopupRef.current = null;
          }
        });
      });

      map.on("click", "saved-zones-fill-layer", (event) => {
        const clickedSavedPointFeatures = map.queryRenderedFeatures(event.point, {
          layers: [...SAVED_ZONE_POINT_LAYER_LIST],
        });
        if (clickedSavedPointFeatures.length > 0) {
          return;
        }

        const feature = event.features?.[0];
        const properties = feature?.properties as Record<string, unknown> | undefined;
        const zoneKey = typeof properties?.zone_key === "string" && properties.zone_key.trim() ? properties.zone_key.trim() : null;
        const label = typeof properties?.label === "string" && properties.label.trim() ? properties.label.trim() : zoneKey || "Zona salva";
        if (zoneKey) {
          setSelectedSavedZoneKey(zoneKey);
        }

        busPopupRef.current?.remove();
        const popup = new maplibregl.Popup({ closeButton: true, closeOnClick: false, maxWidth: "320px" })
          .setLngLat(event.lngLat)
          .setHTML(savedZonePopupContent(label))
          .addTo(map);

        busPopupRef.current = popup;
        popup.on("close", () => {
          if (busPopupRef.current === popup) {
            busPopupRef.current = null;
          }
        });
      });

      map.on("click", "saved-listings-layer", (event) => {
        const feature = event.features?.[0];
        const listingKey = feature?.properties?.listing_key;
        if (typeof listingKey === "string" && listingKey.trim()) {
          setSelectedSavedListingKey(listingKey);
        }
      });

      map.on("click", (event) => {
        if (isDrawingZoneRef.current) {
          setDrawnZonePoints((current) => [...current, [event.lngLat.lng, event.lngLat.lat]]);
          setManualZoneError(null);
          return;
        }

        if (stepRef.current === 1 && isPickingReferencePointRef.current) {
          const clickedInteractiveFeatures = map.queryRenderedFeatures(event.point, {
            layers: [...REFERENCE_POINT_BLOCKING_LAYER_LIST],
          });
          if (clickedInteractiveFeatures.length > 0) {
            return;
          }

          setPickedCoord({
            lat: event.lngLat.lat,
            lon: event.lngLat.lng,
            label: "Ponto principal"
          });
          setIsPickingReferencePoint(false);
        }

        const clickedPinFeatures = map.queryRenderedFeatures(event.point, {
          layers: [...PIN_INTERACTIVE_LAYER_LIST],
        });
        if (clickedPinFeatures.length === 0) {
          setSelectedTransportId(null);
          setSelectedListingKey(null);
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

      map.on("contextmenu", (event) => {
        const { lat, lng } = event.lngLat;
        const coordText = `${lat.toFixed(6)}, ${lng.toFixed(6)}`;
        navigator.clipboard.writeText(coordText).catch(() => {});
        setCopiedCoordsToast(coordText);
        window.clearTimeout(copiedToastTimerRef.current);
        copiedToastTimerRef.current = window.setTimeout(() => setCopiedCoordsToast(null), 2500);
        event.preventDefault();
      });

      for (const layerId of BUS_LAYER_LIST) {
        map.on("mouseenter", layerId, () => {
          map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseleave", layerId, () => {
          map.getCanvas().style.cursor = stepRef.current === 1 && isPickingReferencePointRef.current ? "crosshair" : "";
        });
      }

      for (const layerId of ["transport-candidate-layer", "zones-runtime-fill-layer", "zone-pois-highlight-layer", "zone-pois-layer", "journey-listings-layer", "safety-incident-layer", "saved-zone-pois-layer", "saved-zone-transport-layer", "saved-zone-listings-layer", "saved-zones-fill-layer", "saved-listings-layer"] as const) {
        map.on("mouseenter", layerId, () => {
          map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseleave", layerId, () => {
          map.getCanvas().style.cursor = stepRef.current === 1 && isPickingReferencePointRef.current ? "crosshair" : "";
        });
      }

      map.on("moveend", syncSequentialLayerLoadSequence);
      map.on("moveend", syncMapViewportBounds);
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
      syncMapViewportBounds();

      setIsMapReady(true);
    });

    return () => {
      busPopupRef.current?.remove();
      busPopupRef.current = null;
      pickedMarkerRef.current?.remove();
      pickedMarkerRef.current = null;
      selectedTransportMarkerRef.current?.remove();
      selectedTransportMarkerRef.current = null;
      selectedListingMarkerRef.current?.remove();
      selectedListingMarkerRef.current = null;
      setMapViewportBounds(null);
      map.remove();
    };
  }, [setIsPickingReferencePoint, setMapViewportBounds, setPickedCoord, setSelectedListingKey, setSelectedPoiKey, setSelectedSavedListingKey, setSelectedSavedZoneKey, setSelectedTransportId, setSelectedZone]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) return;

    map.getCanvas().style.cursor = step === 1 && isPickingReferencePoint ? "crosshair" : "";
  }, [isMapReady, isPickingReferencePoint, step]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }

    if (!pickedCoord || referenceInputMode === "area") {
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
  }, [isMapReady, pickedCoord, referenceInputMode]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady || step < 2 || !layerVisibility.transportCandidates || !selectedTransportId) {
      selectedTransportMarkerRef.current = removeMarker(selectedTransportMarkerRef.current);
      return;
    }

    const selectedPoint = transportCandidatePoints.find((point) => point.id === selectedTransportId);
    if (!selectedPoint) {
      selectedTransportMarkerRef.current = removeMarker(selectedTransportMarkerRef.current);
      return;
    }

    selectedTransportMarkerRef.current = removeMarker(selectedTransportMarkerRef.current);
    selectedTransportMarkerRef.current = buildSelectedPinMarker(
      map,
      [selectedPoint.lon, selectedPoint.lat],
      "#845ef7",
      "transport"
    );
  }, [isMapReady, layerVisibility.transportCandidates, selectedTransportId, step, transportCandidatePoints]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }

    let cancelled = false;
    let requestId = 0;

    const syncSafetyIncidents = async () => {
      const safetyVisible = isSequentialLayerGroupVisible("safety", visibleSequentialLayerGroupIndex, {
        layerVisibility,
        greenEnabled: config.enrichments.green,
        safetyEnabled: config.enrichments.safety,
      });

      if (!safetyVisible) {
        setGeoJsonSourceData(map, SAFETY_SOURCE_ID, EMPTY_FEATURE_COLLECTION);
        return;
      }

      if (activeSafetyGroups.length === 0) {
        setGeoJsonSourceData(map, SAFETY_SOURCE_ID, EMPTY_FEATURE_COLLECTION);
        return;
      }

      const zoom = Math.floor(map.getZoom());
      if (zoom < 10) {
        setGeoJsonSourceData(map, SAFETY_SOURCE_ID, EMPTY_FEATURE_COLLECTION);
        return;
      }

      requestId += 1;
      const currentRequestId = requestId;

      try {
        const viewport = getMapViewportBounds(map);
        const response = await getPublicSafetyIncidentsForViewport(viewport, zoom, activeSafetyGroups);
        if (cancelled || currentRequestId !== requestId) {
          return;
        }
        setGeoJsonSourceData(map, SAFETY_SOURCE_ID, response as GeoJSON.FeatureCollection<GeoJSON.Geometry>);
      } catch {
        if (cancelled || currentRequestId !== requestId) {
          return;
        }
        setGeoJsonSourceData(map, SAFETY_SOURCE_ID, EMPTY_FEATURE_COLLECTION);
      }
    };

    const handleMoveEnd = () => {
      void syncSafetyIncidents();
    };

    void syncSafetyIncidents();
    map.on("moveend", handleMoveEnd);

    return () => {
      cancelled = true;
      map.off("moveend", handleMoveEnd);
    };
  }, [
    activeSafetyGroups,
    activeSafetyGroupsKey,
    config.enrichments.green,
    config.enrichments.safety,
    isMapReady,
    layerVisibility,
    visibleSequentialLayerGroupIndex,
  ]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }
    const activeMap = map;

    let cancelled = false;

    async function syncTransportCandidates() {
      if (!journeyId || step < 2 || config.modal === "walk" || config.modal === "car") {
        setTransportCandidatePoints([]);
        setGeoJsonSourceData(activeMap, TRANSPORT_CANDIDATES_SOURCE_ID, EMPTY_FEATURE_COLLECTION);
        return;
      }

      const points = await getJourneyTransportPoints(journeyId);
      if (!cancelled) {
        setTransportCandidatePoints(points);
        setGeoJsonSourceData(
          activeMap,
          TRANSPORT_CANDIDATES_SOURCE_ID,
          toTransportCandidatesFeatureCollection(points, selectedTransportId)
        );
      }
    }

    void syncTransportCandidates().catch(() => {
      if (!cancelled) {
        setTransportCandidatePoints([]);
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
    let requestId = 0;

    async function syncSelectedTransportTrace() {
      if (!journeyId || step < 2 || !selectedTransportId) {
        setGeoJsonSourceData(activeMap, SELECTED_TRANSPORT_TRACE_SOURCE_ID, EMPTY_FEATURE_COLLECTION);
        return;
      }

      const selectedPoint = transportCandidatePoints.find((point) => point.id === selectedTransportId);
      if (!selectedPoint?.external_id) {
        setGeoJsonSourceData(activeMap, SELECTED_TRANSPORT_TRACE_SOURCE_ID, EMPTY_FEATURE_COLLECTION);
        return;
      }

      const currentRequestId = ++requestId;
      const routeIds = Array.isArray(selectedPoint.route_ids) ? selectedPoint.route_ids : [];
      const trace = await getSelectedTransportTrace(selectedPoint.source, selectedPoint.external_id, routeIds);
      if (!cancelled && currentRequestId === requestId) {
        setGeoJsonSourceData(activeMap, SELECTED_TRANSPORT_TRACE_SOURCE_ID, trace);
      }
    }

    void syncSelectedTransportTrace().catch(() => {
      if (!cancelled) {
        setGeoJsonSourceData(activeMap, SELECTED_TRANSPORT_TRACE_SOURCE_ID, EMPTY_FEATURE_COLLECTION);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [isMapReady, journeyId, selectedTransportId, step, transportCandidatePoints]);

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
        zonesDataRef.current = response.zones.map((z) => ({ fingerprint: z.fingerprint, isochrone_geom: z.isochrone_geom }));
        const selectedZone = response.zones.find((zone) => zone.fingerprint === selectedZoneFingerprint);
        const hasIncompleteZones = response.zones.some(
          (zone) => typeof zone.state === "string" && zone.state !== "complete" && zone.state !== "failed"
        );
        const hasLegacyPoiZones = response.zones.some((zone) => zoneNeedsPoiBackfill(zone));
        const selectedPoiPoints = ((selectedZone?.poi_points || []) as ZonePoiPointLike[]);
        setGeoJsonSourceData(
          activeMap,
          ZONES_SOURCE_ID,
          toZonesFeatureCollection(response.zones, selectedZoneFingerprint)
        );
        setSelectedZonePoiState({ zoneFingerprint: selectedZoneFingerprint || null, poiPoints: selectedPoiPoints });

        if (hasIncompleteZones || hasLegacyPoiZones) {
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
    if (!map || !isMapReady || step !== 4 || !selectedZoneFingerprint) return;
    const zone = zonesDataRef.current.find((z) => z.fingerprint === selectedZoneFingerprint);
    if (!zone?.isochrone_geom) return;
    try {
      const coords = collectGeometryCoordinates(zone.isochrone_geom as GeoJSON.Geometry);
      if (coords.length === 0) return;
      const bounds = coords.reduce(
        (box, c) => box.extend(c as [number, number]),
        new maplibregl.LngLatBounds(coords[0] as [number, number], coords[0] as [number, number]),
      );
      const currentZoom = map.getZoom();
      const padding = { top: 40, bottom: 40, left: 40, right: panelRightOffsetPx() + 40 };
      map.fitBounds(bounds, { padding, duration: 700, maxZoom: currentZoom });
    } catch {
      /* noop */
    }
  }, [isMapReady, selectedZoneFingerprint, step]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }

    if (!layerVisibility.listings || !selectedListingKey || step < 6) {
      selectedListingMarkerRef.current = removeMarker(selectedListingMarkerRef.current);
      return;
    }

    const selectedListing = filteredMapListings.find((listing) => {
      if (typeof listing.lat !== "number" || typeof listing.lon !== "number") {
        return false;
      }
      return getListingSelectionKey(listing) === selectedListingKey;
    });

    if (!selectedListing || typeof selectedListing.lat !== "number" || typeof selectedListing.lon !== "number") {
      selectedListingMarkerRef.current = removeMarker(selectedListingMarkerRef.current);
      return;
    }

    selectedListingMarkerRef.current = removeMarker(selectedListingMarkerRef.current);
    selectedListingMarkerRef.current = buildSelectedPinMarker(
      map,
      [selectedListing.lon, selectedListing.lat],
      "#5b21b6",
      "listing"
    );
  }, [filteredMapListings, isMapReady, layerVisibility.listings, selectedListingKey, step]);

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
    if (!map || !isMapReady) {
      return;
    }

    const hiddenZoneKeySet = new Set(hiddenSavedZoneKeys);
    const visibleSavedZoneFavorites = savedZoneFavorites.filter((entry) => !hiddenZoneKeySet.has(entry.zoneKey));
    for (const entry of visibleSavedZoneFavorites) {
      const color = normalizeHexColor(entry.color || entry.payload.color);
      const iconId = getSavedZoneListingIconId(color);
      if (!map.hasImage(iconId)) {
        map.addImage(iconId, createPinIcon(color));
      }
    }

    const zoneFeatures: GeoJSON.Feature<GeoJSON.Geometry>[] = visibleSavedZoneFavorites
      .filter((entry) => entry.payload.isochrone_geom)
      .map((entry) => {
        const color = normalizeHexColor(entry.color || entry.payload.color);
        return {
          type: "Feature" as const,
          geometry: entry.payload.isochrone_geom as GeoJSON.Geometry,
          properties: {
            zone_key: entry.zoneKey,
            label: `Zona ${entry.zoneFingerprint.slice(0, 8)}`,
            fill_color: color,
            outline_color: color,
          },
        };
      });

    const poiFeatures: GeoJSON.Feature<GeoJSON.Point>[] = visibleSavedZoneFavorites.flatMap((entry) =>
      (entry.payload.poi_points || []).map((poi, index) => {
        const meta = getPoiCategoryMeta(poi.category || null);
        return {
          type: "Feature" as const,
          geometry: { type: "Point" as const, coordinates: [poi.lon, poi.lat] },
          properties: {
            zone_key: entry.zoneKey,
            id: poi.id || `${entry.zoneKey}:${index}`,
            name: poi.name || "Ponto de interesse sem nome",
            category: poi.category || null,
            address: poi.address || null,
            color: meta.color,
            icon_id: meta.iconId,
          },
        };
      }),
    );

    const zoneListingFeatures: GeoJSON.Feature<GeoJSON.Point>[] = visibleSavedZoneFavorites.flatMap((entry) => {
      const color = normalizeHexColor(entry.color || entry.payload.color);
      const iconId = getSavedZoneListingIconId(color);
      return (entry.payload.listings || [])
        .filter((listing) => typeof listing.lat === "number" && typeof listing.lon === "number")
        .map((listing, index) => ({
          type: "Feature" as const,
          geometry: { type: "Point" as const, coordinates: [listing.lon as number, listing.lat as number] },
          properties: {
            zone_key: entry.zoneKey,
            listing_key: `${entry.zoneKey}:listing:${listing.property_id || listing.platform_listing_id || index}`,
            address: listing.address_normalized || "",
            icon_id: iconId,
          },
        }));
    });

    const transportFeatures: GeoJSON.Feature<GeoJSON.Point>[] = visibleSavedZoneFavorites
      .filter((entry) => entry.payload.transport_point?.lat != null && entry.payload.transport_point?.lon != null)
      .map((entry) => {
        const tp = entry.payload.transport_point!;
        return {
          type: "Feature" as const,
          geometry: { type: "Point" as const, coordinates: [tp.lon as number, tp.lat as number] },
          properties: {
            zone_key: entry.zoneKey,
            name: tp.name || `Seed ${entry.zoneFingerprint.slice(0, 6)}`,
          },
        };
      });

    setGeoJsonSourceData(map, SAVED_ZONES_SOURCE_ID, { type: "FeatureCollection", features: zoneFeatures });
    setGeoJsonSourceData(map, SAVED_ZONE_POIS_SOURCE_ID, { type: "FeatureCollection", features: poiFeatures });
    setGeoJsonSourceData(map, SAVED_ZONE_TRANSPORT_SOURCE_ID, { type: "FeatureCollection", features: transportFeatures });
    setGeoJsonSourceData(map, SAVED_ZONE_LISTINGS_SOURCE_ID, { type: "FeatureCollection", features: zoneListingFeatures });
  }, [hiddenSavedZoneKeys, isMapReady, savedZoneFavorites]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }
    const features: GeoJSON.Feature<GeoJSON.Point>[] = favoriteListings
      .filter((entry) => typeof entry.listing.lat === "number" && typeof entry.listing.lon === "number")
      .map((entry) => ({
        type: "Feature" as const,
        geometry: { type: "Point" as const, coordinates: [entry.listing.lon as number, entry.listing.lat as number] },
        properties: {
          listing_key: entry.listingKey,
          address: entry.listing.address_normalized || "",
          selected: entry.listingKey === selectedSavedListingKey,
        },
      }));
    setGeoJsonSourceData(map, SAVED_LISTINGS_SOURCE_ID, { type: "FeatureCollection", features });
  }, [favoriteListings, isMapReady, selectedSavedListingKey]);

  function panelRightOffsetPx(): number {
    if (typeof window === "undefined" || !isFavoritesPanelOpen) return 0;
    // Igual ao CSS .favorites-panel: width: min(50vw, 54rem)
    const vw = window.innerWidth;
    const maxPx = 54 * 16;
    return Math.min(vw * 0.5, maxPx);
  }

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady || !selectedSavedZoneKey) {
      return;
    }
    const entry = savedZoneFavorites.find((item) => item.zoneKey === selectedSavedZoneKey);
    if (!entry) {
      return;
    }
    const padding = { top: 40, bottom: 40, left: 40, right: panelRightOffsetPx() + 40 };
    const currentZoom = map.getZoom();
    const tp = entry.payload.transport_point;
    if (tp?.lat != null && tp?.lon != null) {
      // Zoom preservado — só recentra.
      map.easeTo({ center: [tp.lon, tp.lat], duration: 700, padding });
    } else if (entry.payload.isochrone_geom) {
      try {
        const coords = collectGeometryCoordinates(entry.payload.isochrone_geom as GeoJSON.Geometry);
        if (coords.length > 0) {
          const bounds = coords.reduce(
            (box, c) => box.extend(c as [number, number]),
            new maplibregl.LngLatBounds(coords[0] as [number, number], coords[0] as [number, number]),
          );
          map.fitBounds(bounds, { padding, duration: 700, maxZoom: currentZoom });
        }
      } catch {
        /* noop */
      }
    }
  }, [isMapReady, savedZoneFavorites, selectedSavedZoneKey, isFavoritesPanelOpen]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady || !selectedSavedListingKey) {
      return;
    }
    const entry = favoriteListings.find((item) => item.listingKey === selectedSavedListingKey);
    const lat = entry?.listing.lat;
    const lon = entry?.listing.lon;
    if (typeof lat !== "number" || typeof lon !== "number") return;
    map.easeTo({
      center: [lon, lat],
      duration: 700,
      padding: { top: 40, bottom: 40, left: 40, right: panelRightOffsetPx() + 40 },
    });
  }, [isMapReady, favoriteListings, selectedSavedListingKey, isFavoritesPanelOpen]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) return;

    const sequentialLayerSettings: SequentialLayerSettings = {
      layerVisibility,
      greenEnabled: config.enrichments.green,
      safetyEnabled: config.enrichments.safety,
    };
    const transportPointsVisible = isSequentialLayerGroupVisible("transportPoints", visibleSequentialLayerGroupIndex, sequentialLayerSettings);
    const transportLinesVisible = isSequentialLayerGroupVisible("transportLines", visibleSequentialLayerGroupIndex, sequentialLayerSettings);
    const greenVisible = isSequentialLayerGroupVisible("green", visibleSequentialLayerGroupIndex, sequentialLayerSettings);
    const floodVisible = isSequentialLayerGroupVisible("flood", visibleSequentialLayerGroupIndex, sequentialLayerSettings);
    const safetyVisible = isSequentialLayerGroupVisible("safety", visibleSequentialLayerGroupIndex, sequentialLayerSettings);
    const selectedTraceVisible = transportLinesVisible && Boolean(selectedTransportId);

    map.setLayoutProperty("bus-line-layer", "visibility", transportLinesVisible && layerVisibility.routes ? "visible" : "none");
    map.setLayoutProperty("bus-line-direction-layer", "visibility", transportLinesVisible && layerVisibility.routes ? "visible" : "none");
    map.setLayoutProperty("metro-line-layer", "visibility", transportLinesVisible && layerVisibility.metro ? "visible" : "none");
    map.setLayoutProperty("train-line-layer", "visibility", transportLinesVisible && layerVisibility.train ? "visible" : "none");
    map.setLayoutProperty("selected-bus-trace-casing-layer", "visibility", selectedTraceVisible && layerVisibility.routes ? "visible" : "none");
    map.setLayoutProperty("selected-bus-trace-layer", "visibility", selectedTraceVisible && layerVisibility.routes ? "visible" : "none");
    map.setLayoutProperty("selected-metro-trace-casing-layer", "visibility", selectedTraceVisible && layerVisibility.metro ? "visible" : "none");
    map.setLayoutProperty("selected-metro-trace-layer", "visibility", selectedTraceVisible && layerVisibility.metro ? "visible" : "none");
    map.setLayoutProperty("selected-train-trace-casing-layer", "visibility", selectedTraceVisible && layerVisibility.train ? "visible" : "none");
    map.setLayoutProperty("selected-train-trace-layer", "visibility", selectedTraceVisible && layerVisibility.train ? "visible" : "none");
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
    map.setLayoutProperty("safety-incident-heatmap-layer", "visibility", safetyVisible ? "visible" : "none");
    map.setLayoutProperty("safety-incident-layer", "visibility", safetyVisible ? "visible" : "none");
    const savedZonesVisible = layerVisibility.savedZones ? "visible" : "none";
    map.setLayoutProperty("saved-zones-fill-layer", "visibility", savedZonesVisible);
    map.setLayoutProperty("saved-zones-outline-layer", "visibility", savedZonesVisible);
    map.setLayoutProperty("saved-zone-pois-layer", "visibility", savedZonesVisible);
    map.setLayoutProperty("saved-zone-transport-layer", "visibility", savedZonesVisible);
    map.setLayoutProperty("saved-zone-transport-label-layer", "visibility", savedZonesVisible);
    map.setLayoutProperty("saved-zone-listings-layer", "visibility", savedZonesVisible);
    map.setLayoutProperty("saved-listings-layer", "visibility", layerVisibility.savedListings ? "visible" : "none");
    map.setLayoutProperty("flood-layer", "visibility", floodVisible ? "visible" : "none");
    map.setLayoutProperty("green-layer", "visibility", greenVisible ? "visible" : "none");
    map.setFilter("green-layer", ["in", "vegetation_level", ...getIncludedGreenVegetationLevels(config.greenVegetationLevel)] as never);
  }, [config, isMapReady, layerVisibility, selectedTransportId, visibleSequentialLayerGroupIndex]);

  if (mapError) {
    return (
      <main className="flex h-screen w-full items-center justify-center bg-slate-900 text-red-400">
        <p className="text-sm">{mapError}</p>
      </main>
    );
  }

  return (
    <main className={`find-ideal-app relative h-screen w-full overflow-hidden ${isFavoritesPanelOpen ? "find-ideal-app--favorites-open" : ""}`}>
      <div ref={mapContainerRef} className="h-full w-full" aria-label="Mapa principal" />
      {copiedCoordsToast ? (
        <div
          className="pointer-events-none absolute bottom-24 left-1/2 z-50 -translate-x-1/2 rounded-2xl border border-slate-200 bg-white/95 px-4 py-2.5 shadow-lg backdrop-blur-sm"
          aria-live="polite"
        >
          <p className="text-[11px] font-semibold text-slate-700">Coordenadas copiadas</p>
          <p className="mt-0.5 font-mono text-[11px] text-slate-500">{copiedCoordsToast}</p>
        </div>
      ) : null}
      {shareToast ? (
        <div
          className={`pointer-events-auto absolute bottom-24 left-1/2 z-50 w-[min(26rem,calc(100vw-2rem))] -translate-x-1/2 rounded-lg border bg-white/95 px-4 py-3 shadow-lg backdrop-blur-sm ${shareToast.tone === "error" ? "border-rose-200" : "border-slate-200"}`}
          aria-live="polite"
        >
          <p className={`text-[12px] font-bold ${shareToast.tone === "error" ? "text-rose-600" : "text-slate-800"}`}>{shareToast.title}</p>
          {shareToast.detail ? (
            <p className="mt-1 select-all break-all text-[11px] leading-snug text-slate-500">{shareToast.detail}</p>
          ) : null}
        </div>
      ) : null}
      <AuthAccessCard />
      <FavoritesPanel />
      <div className="map-side-controls pointer-events-none absolute bottom-14 right-4 z-40 flex flex-col items-end gap-2">
        {step >= 4 || journeyId ? (
          <div className="pointer-events-auto flex max-w-[min(22rem,calc(100vw-2rem))] flex-col items-end gap-2">
            {manualZoneError ? (
              <p className="rounded-lg border border-rose-200 bg-white/95 px-3 py-2 text-xs font-medium text-rose-700 shadow-md">{manualZoneError}</p>
            ) : null}
            {isDrawingZone ? (
              <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white/95 p-2 shadow-lg backdrop-blur-md">
                <span className="px-2 text-xs font-semibold text-slate-600">{drawnZonePoints.length} vértice{drawnZonePoints.length === 1 ? "" : "s"}</span>
                <button
                  type="button"
                  onClick={() => void finishDrawingZone()}
                  disabled={drawnZonePoints.length < 3 || isSavingManualZone}
                  className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-pastel-violet-500 px-3 text-xs font-semibold text-white transition hover:bg-pastel-violet-600 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500"
                >
                  <Check className="h-3.5 w-3.5" />
                  Salvar
                </button>
                <button
                  type="button"
                  onClick={cancelDrawingZone}
                  className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 transition hover:bg-slate-50"
                  aria-label="Cancelar desenho da zona"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={startDrawingZone}
                disabled={!journeyId}
                className="pointer-events-auto inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white/95 px-3 py-2 text-xs font-semibold text-slate-700 shadow-md backdrop-blur-md transition hover:bg-pastel-violet-50 hover:text-pastel-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <PencilLine className="h-4 w-4" />
                Desenhar zona
              </button>
            )}
          </div>
        ) : null}
        {isLayerMenuOpen ? (
          <div
            ref={layerMenuRef}
            className="map-layer-menu pointer-events-auto flex max-h-full w-[21rem] flex-col overflow-hidden rounded-[1.75rem] border border-slate-200 bg-white/95 shadow-xl backdrop-blur-md"
          >
            <p className="px-4 pb-2 pt-4 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">Camadas do mapa</p>
            <div className="panel-scroll min-h-0 overflow-y-auto pb-2">
              {MAP_LAYER_MENU_ITEMS.map((item) => (
                <div key={item.key} className="border-t border-slate-200/80 first:border-t-0">
                  <div className="flex items-center gap-2 px-4 py-2.5">
                    <label className="flex min-w-0 flex-1 cursor-pointer items-center gap-2.5 text-[13px] font-medium text-slate-700">
                      <input
                        type="checkbox"
                        checked={layerVisibility[item.key]}
                        onChange={() => toggleLayerVisibility(item.key)}
                        className="h-4 w-4 rounded accent-pastel-violet-500"
                      />
                      <span className={`min-w-0 break-words whitespace-normal leading-snug ${layerVisibility[item.key] ? "text-slate-700" : "text-slate-400"}`}>{item.label}</span>
                    </label>
                    <button
                      type="button"
                      aria-label={`${expandedLayerLegends[item.key] ? "Recolher" : "Expandir"} legenda de ${item.label}`}
                      aria-expanded={expandedLayerLegends[item.key]}
                      onClick={() => toggleLayerLegendExpansion(item.key)}
                      className="flex h-7 w-7 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-500 transition hover:border-slate-300 hover:text-slate-700"
                    >
                      <ChevronDown className={`h-3.5 w-3.5 transition-transform ${expandedLayerLegends[item.key] ? "rotate-180" : "rotate-0"}`} />
                    </button>
                  </div>
                  {expandedLayerLegends[item.key] ? (
                    <div className="border-t border-slate-200/80 bg-slate-50/70 px-4 py-2.5">
                      {item.key === "safety" ? (
                        <div>
                          <p className="mb-2 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">Tipos de ocorrência</p>
                          <div className={`grid gap-1.5 ${SAFETY_GROUP_META.length > 1 ? "grid-cols-2" : "grid-cols-1"}`}>
                            {SAFETY_GROUP_META.map((safetyItem) => {
                              const isSafetyItemVisible = safetyGroupVisibility[safetyItem.key];
                              return (
                                <div key={safetyItem.key} className="flex items-center justify-between gap-1.5 rounded-lg border border-slate-200/80 bg-white/85 px-2 py-1.5 text-[11px] text-slate-700 shadow-sm">
                                  <div className="flex min-w-0 items-center gap-1.5">
                                    <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: safetyItem.color }} />
                                    <span className={`min-w-0 break-words whitespace-normal leading-snug ${isSafetyItemVisible ? "text-slate-700" : "text-slate-400 line-through"}`}>{safetyItem.label}</span>
                                  </div>
                                  <div className="flex items-center justify-end gap-1">
                                    <button
                                      type="button"
                                      aria-label={`${safetyGroupVisibility[safetyItem.key] ? "Ocultar" : "Mostrar"} ${safetyItem.label}`}
                                      aria-pressed={!safetyGroupVisibility[safetyItem.key]}
                                      onClick={() => toggleSafetyGroupVisibility(safetyItem.key)}
                                      className={`flex h-5 w-5 items-center justify-center rounded-md border transition ${safetyGroupVisibility[safetyItem.key] ? "border-slate-200 bg-white text-slate-500 hover:border-slate-300 hover:text-slate-700" : "border-rose-200 bg-rose-50 text-rose-500 hover:border-rose-300 hover:text-rose-600"}`}
                                    >
                                      {safetyGroupVisibility[safetyItem.key] ? <Eye className="h-3 w-3" /> : <EyeOff className="h-3 w-3" />}
                                    </button>
                                    <button
                                      type="button"
                                      aria-label={`${isolatedSafetyGroup === safetyItem.key ? "Mostrar todas as categorias novamente" : `Mostrar apenas ${safetyItem.label}`}`}
                                      aria-pressed={isolatedSafetyGroup === safetyItem.key}
                                      onClick={() => toggleSafetyGroupIsolation(safetyItem.key)}
                                      className={`flex h-5 w-5 items-center justify-center rounded-md border transition ${isolatedSafetyGroup === safetyItem.key ? "border-pastel-violet-300 bg-pastel-violet-50 text-pastel-violet-700" : "border-slate-200 bg-white text-slate-500 hover:border-slate-300 hover:text-slate-700"}`}
                                    >
                                      <span className="relative block h-3 w-3 rounded-[0.3rem] border border-current">
                                        <span className="absolute left-1/2 top-1/2 h-1.5 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-current" />
                                      </span>
                                    </button>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      ) : (
                        <div className={`grid gap-1.5 ${BASE_LAYER_LEGEND_ITEMS[item.key].length > 2 ? "grid-cols-2" : "grid-cols-1"}`}>
                          {BASE_LAYER_LEGEND_ITEMS[item.key].map((legendItem) => (
                            <div key={legendItem.id} className="flex items-center gap-1.5 rounded-lg border border-slate-200/80 bg-white/85 px-2 py-1.5 text-[11px] text-slate-600 shadow-sm">
                              {renderLegendMarker(legendItem)}
                              <span className="min-w-0 break-words whitespace-normal leading-snug">{legendItem.label}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          </div>
        ) : null}
        <button
          type="button"
          aria-label={journeyId ? "Compartilhar jornada" : "Crie uma jornada para compartilhar"}
          title={journeyId ? "Compartilhar jornada" : "Crie uma jornada para compartilhar"}
          disabled={!journeyId || isSharingJourney}
          onClick={handleShareJourney}
          className={`${LAYER_TOGGLE_BUTTON_CLASS} ${!journeyId || isSharingJourney ? "cursor-not-allowed opacity-60" : ""}`}
        >
          <Share2 className="h-4 w-4" />
        </button>
        <button
          ref={layerMenuButtonRef}
          type="button"
          aria-label="Camadas"
          onClick={() => setIsLayerMenuOpen((current) => !current)}
          className={`${LAYER_TOGGLE_BUTTON_CLASS} ${isLayerMenuOpen ? "border-pastel-violet-300 text-pastel-violet-600" : ""}`}
        >
          <Layers className="h-4 w-4" />
        </button>
        <FeedbackFormButton />
      </div>
      <WizardPanel />
    </main>
  );
}
