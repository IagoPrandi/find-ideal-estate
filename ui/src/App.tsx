import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  Search,
  MapPin,
  Layers,
  Loader2,
  HelpCircle,
  Minus,
  Plus,
  ChevronLeft,
  ChevronsLeft,
  ChevronsRight,
  X
} from "lucide-react";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import {
  API_BASE,
  apiActionHint,
  createRun,
  finalizeRun,
  getFinalListings,
  getFinalListingsJson,
  getRunStatus,
  getTransportLayers,
  getTransportStops,
  getZoneDetail,
  getZoneStreets,
  getZones,
  scrapeZoneListings,
  selectZones
} from "./api/client";
import type {
  ListingsCollection,
  RunCreateResponse,
  RunStatusResponse,
  ZoneDetailResponse,
  ZonesCollection
} from "./api/schemas";

type LayerKey = "routes" | "train" | "busStops" | "zones" | "flood" | "green" | "pois";
type InteractionMode = "primary" | "interest";
type PropertyMode = "rent" | "buy";
type ExecutionStageKey = "zones" | "selectZone" | "detailZone" | "zoneListings" | "finalize";

type ReferencePoint = {
  name: string;
  lat: number;
  lon: number;
};

type InterestPoint = {
  id: string;
  label: string;
  category: string;
  lat: number;
  lon: number;
};

type ZoneFeature = ZonesCollection["features"][number];
type ListingFeature = ListingsCollection["features"][number];
type TransportAnchorPoint = {
  id: string;
  name: string;
  kind: string;
  lon: number;
  lat: number;
  zoneUid?: string;
};

type ListingSortMode = "price-asc" | "price-desc" | "size-desc" | "size-asc";

const MAPBOX_TOKEN =
  import.meta.env.VITE_MAPBOX_ACCESS_TOKEN || (import.meta.env.MODE === "test" ? "test-token" : "");

const STEPS = [
  { id: 1, title: "Referência", desc: "Defina o ponto principal" },
  { id: 2, title: "Zonas", desc: "Selecione e detalhe a zona" },
  { id: 3, title: "Imóveis", desc: "Busque e revise resultados" }
] as const;

const LAYER_INFO: Record<LayerKey, { label: string; color: string }> = {
  routes: { label: "Rotas de ônibus", color: "#2563eb" },
  train: { label: "Metrô/Trem", color: "#0f766e" },
  busStops: { label: "Paradas (ônibus/estações)", color: "#f97316" },
  zones: { label: "Zonas candidatas", color: "#2563eb" },
  flood: { label: "Alagamento", color: "#7c3aed" },
  green: { label: "Área verde", color: "#16a34a" },
  pois: { label: "POIs", color: "#d97706" }
};

const INTEREST_CATEGORIES = [
  "Parque",
  "Academia",
  "Mercado",
  "Restaurante",
  "Farmácia",
  "Pin livre"
];

const EXECUTION_STAGE_META: Record<ExecutionStageKey, { label: string; expectedSec: number }> = {
  zones: { label: "Gerar zonas", expectedSec: 180 },
  selectZone: { label: "Selecionar zona", expectedSec: 8 },
  detailZone: { label: "Detalhar zona", expectedSec: 60 },
  zoneListings: { label: "Buscar imóveis", expectedSec: 180 },
  finalize: { label: "Finalizar", expectedSec: 90 }
};

const EXECUTION_STAGE_ORDER: ExecutionStageKey[] = [
  "zones",
  "selectZone",
  "detailZone",
  "zoneListings",
  "finalize"
];

const ZONE_RADIUS_MIN_M = 300;
const ZONE_RADIUS_MAX_M = 2500;
const ZONE_RADIUS_STEP_M = 50;

const clampZoneRadius = (value: number) =>
  Math.max(ZONE_RADIUS_MIN_M, Math.min(ZONE_RADIUS_MAX_M, Math.round(value)));

const buildCircleCoordinates = (centerLon: number, centerLat: number, radiusM: number) => {
  const earthRadiusM = 6371008.8;
  const latRad = (centerLat * Math.PI) / 180;
  const dLat = (radiusM / earthRadiusM) * (180 / Math.PI);
  const dLon = dLat / Math.max(Math.cos(latRad), 0.000001);

  const ring: [number, number][] = [];
  const steps = 48;
  for (let i = 0; i <= steps; i += 1) {
    const angle = (2 * Math.PI * i) / steps;
    ring.push([centerLon + dLon * Math.cos(angle), centerLat + dLat * Math.sin(angle)]);
  }
  return [ring];
};

const haversineMeters = (lat1: number, lon1: number, lat2: number, lon2: number) => {
  const radius = 6371000;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return radius * c;
};

const createInitialExecutionStages = () =>
  EXECUTION_STAGE_ORDER.reduce(
    (acc, key) => {
      acc[key] = {
        status: "idle" as "idle" | "running" | "done" | "error",
        elapsedSec: 0,
        etaSec: EXECUTION_STAGE_META[key].expectedSec,
        durationSec: null as number | null
      };
      return acc;
    },
    {} as Record<
      ExecutionStageKey,
      {
        status: "idle" | "running" | "done" | "error";
        elapsedSec: number;
        etaSec: number;
        durationSec: number | null;
      }
    >
  );

export default function App() {
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const primaryMarkerRef = useRef<mapboxgl.Marker | null>(null);
  const interestMarkerRefs = useRef<Map<string, mapboxgl.Marker>>(new Map());
  const interactionModeRef = useRef<InteractionMode>("primary");
  const interestLabelRef = useRef("");
  const interestCategoryRef = useRef(INTEREST_CATEGORIES[0]);
  const runIdRef = useRef("");

  const [searchValue, setSearchValue] = useState("");
  const [isPanelMinimized, setIsPanelMinimized] = useState(false);
  const [isLayerMenuOpen, setIsLayerMenuOpen] = useState(false);
  const [isHelpOpen, setIsHelpOpen] = useState(false);
  const [isMapReady, setIsMapReady] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);
  const [isOptionalInterestsExpanded, setIsOptionalInterestsExpanded] = useState(false);
  const [viewport, setViewport] = useState({ lat: -23.55052, lon: -46.633308, zoom: 10.7 });
  const [layerVisibility, setLayerVisibility] = useState<Record<LayerKey, boolean>>({
    routes: true,
    train: true,
    busStops: true,
    zones: true,
    flood: false,
    green: false,
    pois: false
  });

  const [activeStep, setActiveStep] = useState<1 | 2 | 3>(1);
  const [interactionMode, setInteractionMode] = useState<InteractionMode>("primary");
  const [propertyMode, setPropertyMode] = useState<PropertyMode>("rent");
  const [primaryPoint, setPrimaryPoint] = useState<ReferencePoint | null>(null);
  const [interestLabel, setInterestLabel] = useState("");
  const [interestCategory, setInterestCategory] = useState(INTEREST_CATEGORIES[0]);
  const [interests, setInterests] = useState<InterestPoint[]>([]);

  const [runId, setRunId] = useState("");
  const [runStatus, setRunStatus] = useState<RunStatusResponse["status"] | null>(null);
  const [statusMessage, setStatusMessage] = useState("Defina o ponto principal no mapa para continuar.");
  const [isCreatingRun, setIsCreatingRun] = useState(false);
  const [isPolling, setIsPolling] = useState(false);
  const [zonesState, setZonesState] = useState<
    "idle" | "loading" | "ready" | "empty" | "error-recoverable" | "error-fatal"
  >("idle");
  const [zonesStateMessage, setZonesStateMessage] = useState("Aguardando criação da run.");
  const [zonesCollection, setZonesCollection] = useState<ZoneFeature[]>([]);
  const [selectedZoneUid, setSelectedZoneUid] = useState("");
  const [zoneSelectionMessage, setZoneSelectionMessage] = useState("Selecione uma zona consolidada.");
  const [zoneDetailData, setZoneDetailData] = useState<ZoneDetailResponse | null>(null);
  const [zoneListingMessage, setZoneListingMessage] = useState("Aguardando seleção e detalhamento da zona.");
  const [streetFilterMode, setStreetFilterMode] = useState<"all" | "specific">("all");
  const [selectedStreet, setSelectedStreet] = useState("");
  const [zoneRadiusM, setZoneRadiusM] = useState(900);
  const [zoneStreets, setZoneStreets] = useState<string[]>([]);
  const [stopsLoading, setStopsLoading] = useState(false);
  const [loadingText, setLoadingText] = useState("");
  const [originalSeedPoint, setOriginalSeedPoint] = useState<TransportAnchorPoint | null>(null);
  const [zoneSeedPoints, setZoneSeedPoints] = useState<TransportAnchorPoint[]>([]);
  const [zoneDownstreamPoints, setZoneDownstreamPoints] = useState<TransportAnchorPoint[]>([]);
  const [finalListings, setFinalListings] = useState<ListingFeature[]>([]);
  const [listingsWithoutCoords, setListingsWithoutCoords] = useState<Array<Record<string, unknown>>>([]);
  const [focusedListingKey, setFocusedListingKey] = useState<string>("");
  const [selectedListingKeys, setSelectedListingKeys] = useState<string[]>([]);
  const [listingSortMode, setListingSortMode] = useState<ListingSortMode>("price-asc");
  const [poiCountRadiusM, setPoiCountRadiusM] = useState(800);
  const [finalizeMessage, setFinalizeMessage] = useState("Finalize o run para carregar os imóveis.");
  const [isSelectingZone, setIsSelectingZone] = useState(false);
  const [isDetailingZone, setIsDetailingZone] = useState(false);
  const [isListingZone, setIsListingZone] = useState(false);
  const [executionProgress, setExecutionProgress] = useState<{
    active: boolean;
    label: string;
    percent: number;
    etaSec: number;
    elapsedSec: number;
  }>({
    active: false,
    label: "Aguardando execução.",
    percent: 0,
    etaSec: 0,
    elapsedSec: 0
  });
  const [, setExecutionStages] = useState(createInitialExecutionStages);
  const [activeExecutionStage, setActiveExecutionStage] = useState<ExecutionStageKey | null>(null);
  const [, setExecutionHistory] = useState<Array<{ label: string; durationSec: number }>>([]);

  const initialViewport = useRef(viewport);
  const progressTimerRef = useRef<number | null>(null);
  const stopsDebounceRef = useRef<number | null>(null);
  const progressStartRef = useRef<number>(0);
  const progressExpectedRef = useRef<number>(0);

  const hasRouteData = Boolean(runId && zonesCollection.length > 0);

  const isLoading =
    isCreatingRun ||
    isPolling ||
    isSelectingZone ||
    isDetailingZone ||
    isListingZone;

  useEffect(() => {
    interactionModeRef.current = interactionMode;
  }, [interactionMode]);

  useEffect(() => {
    interestLabelRef.current = interestLabel;
  }, [interestLabel]);

  useEffect(() => {
    interestCategoryRef.current = interestCategory;
  }, [interestCategory]);

  useEffect(() => {
    runIdRef.current = runId;
  }, [runId]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }

    const immediate = window.setTimeout(() => map.resize(), 40);
    const postTransition = window.setTimeout(() => map.resize(), 360);

    return () => {
      window.clearTimeout(immediate);
      window.clearTimeout(postTransition);
    };
  }, [isMapReady, isPanelMinimized]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }
    const onResize = () => map.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
    };
  }, [isMapReady]);

  useEffect(() => {
    if (!isHelpOpen) {
      return;
    }

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsHelpOpen(false);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [isHelpOpen]);

  useEffect(() => {
    if (!mapContainerRef.current) {
      return;
    }

    if (!MAPBOX_TOKEN) {
      setMapError("Defina VITE_MAPBOX_ACCESS_TOKEN no .env do frontend para renderizar o mapa.");
      setZonesState("error-fatal");
      setZonesStateMessage("Configuração obrigatória ausente: VITE_MAPBOX_ACCESS_TOKEN.");
      return;
    }

    mapboxgl.accessToken = MAPBOX_TOKEN;
    const interestMarkers = interestMarkerRefs.current;
    const map = new mapboxgl.Map({
      container: mapContainerRef.current,
      style: "mapbox://styles/mapbox/light-v11",
      center: [initialViewport.current.lon, initialViewport.current.lat],
      zoom: initialViewport.current.zoom,
      pitchWithRotate: false,
      dragRotate: false
    });

    mapRef.current = map;

    map.on("load", () => {
      map.addSource("transport-demo", {
        type: "geojson",
        data: {
          type: "FeatureCollection",
          features: []
        }
      });

      map.addSource("env-demo", {
        type: "geojson",
        data: {
          type: "FeatureCollection",
          features: [
            {
              type: "Feature",
              geometry: {
                type: "Polygon",
                coordinates: [
                  [
                    [-46.67, -23.57],
                    [-46.64, -23.57],
                    [-46.64, -23.54],
                    [-46.67, -23.54],
                    [-46.67, -23.57]
                  ]
                ]
              },
              properties: { kind: "flood" }
            },
            {
              type: "Feature",
              geometry: {
                type: "Polygon",
                coordinates: [
                  [
                    [-46.62, -23.55],
                    [-46.59, -23.55],
                    [-46.59, -23.52],
                    [-46.62, -23.52],
                    [-46.62, -23.55]
                  ]
                ]
              },
              properties: { kind: "green" }
            }
          ]
        }
      });

      map.addSource("poi-zone-source", {
        type: "geojson",
        data: {
          type: "FeatureCollection",
          features: []
        }
      });

      map.addSource("bus-stop-demo", {
        type: "geojson",
        data: {
          type: "FeatureCollection",
          features: []
        }
      });

      map.addSource("zones-source", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] }
      });
      map.addSource("zone-centroid-source", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] }
      });
      map.addSource("reference-transport-source", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] }
      });
      map.addSource("downstream-transport-source", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] }
      });
      map.addSource("original-seed-source", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] }
      });
      map.addSource("zones-seed-source", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] }
      });
      map.addSource("zones-downstream-source", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] }
      });
      map.addSource("listings-source", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] }
      });

      map.addLayer({
        id: "bus-layer",
        type: "line",
        source: "transport-demo",
        filter: ["==", ["get", "mode"], "bus"],
        paint: { "line-color": "#2563eb", "line-width": 4, "line-dasharray": [1.5, 1.5] }
      });
      map.addLayer({
        id: "train-layer",
        type: "line",
        source: "transport-demo",
        filter: ["==", ["get", "mode"], "train"],
        paint: { "line-color": "#0f766e", "line-width": 4 }
      });
      map.addLayer({
        id: "flood-layer",
        type: "fill",
        source: "env-demo",
        filter: ["==", ["get", "kind"], "flood"],
        paint: { "fill-color": "#7c3aed", "fill-opacity": 0.28 }
      });
      map.addLayer({
        id: "green-layer",
        type: "fill",
        source: "env-demo",
        filter: ["==", ["get", "kind"], "green"],
        paint: { "fill-color": "#16a34a", "fill-opacity": 0.28 }
      });
      map.addLayer({
        id: "poi-layer",
        type: "circle",
        source: "poi-zone-source",
        paint: {
          "circle-radius": 7,
          "circle-color": "#d97706",
          "circle-stroke-color": "#fff",
          "circle-stroke-width": 2
        }
      });
      map.addLayer({
        id: "bus-stop-layer",
        type: "circle",
        source: "bus-stop-demo",
        paint: {
          "circle-radius": ["match", ["get", "kind"], "station", 5.5, 4.5],
          "circle-color": ["match", ["get", "kind"], "station", "#0f766e", "#2563eb"],
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 1.5,
          "circle-opacity": 0.95
        }
      });
      map.addLayer({
        id: "zone-centroid-layer",
        type: "circle",
        source: "zone-centroid-source",
        paint: {
          "circle-radius": 5,
          "circle-color": "#1d4ed8",
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 2
        }
      });
      map.addLayer({
        id: "reference-transport-layer",
        type: "circle",
        source: "reference-transport-source",
        paint: {
          "circle-radius": 9,
          "circle-color": "#dc2626",
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 2
        }
      });
      map.addLayer({
        id: "downstream-transport-layer",
        type: "circle",
        source: "downstream-transport-source",
        paint: {
          "circle-radius": 7,
          "circle-color": "#7c3aed",
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 2
        }
      });
      map.addLayer({
        id: "original-seed-layer",
        type: "circle",
        source: "original-seed-source",
        paint: {
          "circle-radius": 10,
          "circle-color": "#b91c1c",
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 2
        }
      });
      map.addLayer({
        id: "zones-seed-layer",
        type: "circle",
        source: "zones-seed-source",
        paint: {
          "circle-radius": 7,
          "circle-color": "#ea580c",
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 2
        }
      });
      map.addLayer({
        id: "zones-downstream-layer",
        type: "circle",
        source: "zones-downstream-source",
        paint: {
          "circle-radius": 6,
          "circle-color": "#7c3aed",
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 2
        }
      });
      map.addLayer({
        id: "listings-layer",
        type: "circle",
        source: "listings-source",
        paint: {
          "circle-radius": 5,
          "circle-color": "#16a34a",
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 2,
          "circle-opacity": 0.95
        }
      });

      map.on("click", "listings-layer", (event) => {
        const feature = event.features?.[0] as mapboxgl.MapboxGeoJSONFeature | undefined;
        if (!feature || feature.geometry.type !== "Point") {
          return;
        }
        const coordinates = feature.geometry.coordinates as [number, number];
        const props = feature.properties || {};
        const price = String(props.priceLabel || "Preço não informado");
        const address = String(props.address || "Endereço não informado");
        const listingKey = String(props.listing_key || "");
        if (listingKey) {
          setFocusedListingKey(listingKey);
        }
        new mapboxgl.Popup({ offset: 12 })
          .setLngLat(coordinates)
          .setHTML(`<strong>${price}</strong><br/>${address}`)
          .addTo(map);
      });
      map.on("mouseenter", "listings-layer", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "listings-layer", () => {
        map.getCanvas().style.cursor = "";
      });

      map.on("click", "poi-layer", (event) => {
        const feature = event.features?.[0] as mapboxgl.MapboxGeoJSONFeature | undefined;
        if (!feature || feature.geometry.type !== "Point") {
          return;
        }
        const coordinates = feature.geometry.coordinates as [number, number];
        const props = feature.properties || {};
        const name = String(props.name || "POI");
        const category = String(props.category || "outros");
        const address = String(props.address || "");
        const description = address ? `${category}<br/>${address}` : category;
        new mapboxgl.Popup({ offset: 10 })
          .setLngLat(coordinates)
          .setHTML(`<strong>${name}</strong><br/>${description}`)
          .addTo(map);
      });
      map.on("mouseenter", "poi-layer", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "poi-layer", () => {
        map.getCanvas().style.cursor = "";
      });

      map.addLayer({
        id: "zones-fill-layer",
        type: "fill",
        source: "zones-source",
        paint: {
          "fill-color": "#2563eb",
          "fill-opacity": 0.2,
          "fill-outline-color": "#2563eb"
        }
      });
      map.addLayer({
        id: "zones-outline-layer",
        type: "line",
        source: "zones-source",
        paint: {
          "line-color": "#2563eb",
          "line-width": 2
        }
      });

      map.moveLayer("poi-layer");
      map.moveLayer("original-seed-layer");
      map.moveLayer("zones-seed-layer");
      map.moveLayer("zones-downstream-layer");

      map.on("mouseenter", "zones-fill-layer", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "zones-fill-layer", () => {
        map.getCanvas().style.cursor = "";
      });

      map.on("moveend", () => {
        const center = map.getCenter();
        setViewport({ lat: center.lat, lon: center.lng, zoom: map.getZoom() });
      });

      map.on("click", (event) => {
        const features = map.queryRenderedFeatures(event.point, {
          layers: ["zones-fill-layer"]
        });
        if (features.length > 0) {
          const uid = features[0].properties?.zone_uid as string | undefined;
          const currentRunId = runIdRef.current;
          if (uid && currentRunId) {
            setSelectedZoneUid(uid);
            setZoneSelectionMessage(`Zona ${uid} selecionada no mapa. Carregando detalhes...`);
            setActiveStep(3);
            void (async () => {
              setIsSelectingZone(true);
              setIsDetailingZone(true);
              try {
                await selectZones(currentRunId, [uid]);
                const detail = await getZoneDetail(currentRunId, uid);
                setZoneDetailData(detail);
                setLayerVisibility((current) => ({ ...current, pois: true, busStops: true }));
                setZoneListingMessage("Detalhamento concluído. Escolha como buscar imóveis.");
                setStatusMessage(`Detalhamento finalizado para ${uid}.`);
              } catch (error) {
                const hint = apiActionHint(error);
                setZoneSelectionMessage(hint);
                setZoneListingMessage(hint);
                setStatusMessage(hint);
              } finally {
                setIsSelectingZone(false);
                setIsDetailingZone(false);
              }
            })();
            return;
          }
          if (uid) {
            setSelectedZoneUid(uid);
            setZoneSelectionMessage(`Zona ${uid} selecionada no mapa.`);
            setActiveStep(2);
            return;
          }
        }

        const lat = Number(event.lngLat.lat.toFixed(6));
        const lon = Number(event.lngLat.lng.toFixed(6));

        if (interactionModeRef.current === "primary") {
          setPrimaryPoint({ name: "Ponto principal", lat, lon });
          setRunId("");
          setRunStatus(null);
          setActiveStep(1);
          setStatusMessage("Ponto principal definido. Gere zonas candidatas.");
          return;
        }

        const id = `${Date.now()}_${Math.random().toString(16).slice(2, 8)}`;
        const nextLabel = interestLabelRef.current.trim() || interestCategoryRef.current;
        setInterests((current) => [
          ...current,
          {
            id,
            label: nextLabel,
            category: interestCategoryRef.current,
            lat,
            lon
          }
        ]);
        setStatusMessage(`Interesse '${nextLabel}' adicionado.`);
      });

      setIsMapReady(true);
    });

    map.on("error", () => {
      setMapError("Falha ao carregar mapa. Verifique token, rede e estilo configurado.");
    });

    return () => {
      primaryMarkerRef.current?.remove();
      interestMarkers.forEach((marker) => marker.remove());
      interestMarkers.clear();
      map.remove();
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }

    const visibility = (value: boolean) => (value ? "visible" : "none");
    map.setLayoutProperty("bus-layer", "visibility", visibility(layerVisibility.routes && hasRouteData));
    map.setLayoutProperty("train-layer", "visibility", visibility(layerVisibility.train && hasRouteData));
    map.setLayoutProperty("bus-stop-layer", "visibility", visibility(layerVisibility.busStops));
    map.setLayoutProperty("original-seed-layer", "visibility", visibility(layerVisibility.busStops && Boolean(originalSeedPoint)));
    map.setLayoutProperty("zones-seed-layer", "visibility", visibility(layerVisibility.busStops && zoneSeedPoints.length > 0));
    map.setLayoutProperty(
      "zones-downstream-layer",
      "visibility",
      visibility(layerVisibility.busStops && zoneDownstreamPoints.length > 0)
    );
    map.setLayoutProperty(
      "reference-transport-layer",
      "visibility",
      visibility(layerVisibility.busStops && Boolean(zoneDetailData?.seed_transport_point || zoneDetailData?.reference_transport_point))
    );
    map.setLayoutProperty(
      "downstream-transport-layer",
      "visibility",
      visibility(layerVisibility.busStops && Boolean(zoneDetailData?.downstream_transport_point))
    );
    if (map.getLayer("zones-fill-layer")) {
      map.setLayoutProperty(
        "zones-fill-layer",
        "visibility",
        visibility(layerVisibility.zones && zonesCollection.length > 0)
      );
    }
    if (map.getLayer("zones-outline-layer")) {
      map.setLayoutProperty(
        "zones-outline-layer",
        "visibility",
        visibility(layerVisibility.zones && zonesCollection.length > 0)
      );
    }
    map.setLayoutProperty("flood-layer", "visibility", visibility(layerVisibility.flood));
    map.setLayoutProperty("green-layer", "visibility", visibility(layerVisibility.green));
    map.setLayoutProperty("poi-layer", "visibility", visibility(layerVisibility.pois));
  }, [
    hasRouteData,
    isMapReady,
    layerVisibility,
    originalSeedPoint,
    zoneDetailData,
    zoneDownstreamPoints.length,
    zoneSeedPoints.length,
    zonesCollection.length
  ]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }
    const source = map.getSource("original-seed-source") as mapboxgl.GeoJSONSource | undefined;
    if (!source || !originalSeedPoint) {
      source?.setData({ type: "FeatureCollection", features: [] });
      return;
    }
    source.setData({
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          geometry: { type: "Point", coordinates: [originalSeedPoint.lon, originalSeedPoint.lat] },
          properties: {
            kind: originalSeedPoint.kind,
            id: originalSeedPoint.id,
            name: originalSeedPoint.name
          }
        }
      ]
    });
  }, [isMapReady, originalSeedPoint]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }
    const seedSource = map.getSource("zones-seed-source") as mapboxgl.GeoJSONSource | undefined;
    const downstreamSource = map.getSource("zones-downstream-source") as mapboxgl.GeoJSONSource | undefined;
    if (!seedSource || !downstreamSource) {
      return;
    }

    seedSource.setData({
      type: "FeatureCollection",
      features: zoneSeedPoints.map((point) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [point.lon, point.lat] },
        properties: {
          kind: point.kind,
          id: point.id,
          name: point.name,
          zone_uid: point.zoneUid || ""
        }
      }))
    });

    downstreamSource.setData({
      type: "FeatureCollection",
      features: zoneDownstreamPoints.map((point) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [point.lon, point.lat] },
        properties: {
          kind: point.kind,
          id: point.id,
          name: point.name,
          zone_uid: point.zoneUid || ""
        }
      }))
    });
  }, [isMapReady, zoneDownstreamPoints, zoneSeedPoints]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }

    const busStopSource = map.getSource("bus-stop-demo") as mapboxgl.GeoJSONSource | undefined;
    if (!busStopSource) {
      return;
    }

    if (selectedZoneUid && zoneDetailData) {
      const features = (zoneDetailData.transport_points || [])
        .filter((point) => Number.isFinite(point.lon) && Number.isFinite(point.lat))
        .map((point) => ({
          type: "Feature" as const,
          geometry: {
            type: "Point" as const,
            coordinates: [point.lon, point.lat] as [number, number]
          },
          properties: {
            kind: point.kind,
            id: point.id || "",
            name: point.name || ""
          }
        }));
      busStopSource.setData({ type: "FeatureCollection", features: features as unknown as any[] });
      setStopsLoading(false);
      return;
    }

    let cancelled = false;

    const loadStops = () => {
      const bounds = map.getBounds();
      if (!bounds) {
        return;
      }
      const bbox = {
        minLon: bounds.getWest(),
        minLat: bounds.getSouth(),
        maxLon: bounds.getEast(),
        maxLat: bounds.getNorth()
      };

      setStopsLoading(true);
      getTransportStops(0, 0, 2500, bbox)
        .then((stops) => {
          if (!cancelled) {
            busStopSource.setData(stops);
          }
        })
        .catch(() => {
          if (!cancelled) {
            busStopSource.setData({ type: "FeatureCollection", features: [] });
          }
        })
        .finally(() => {
          if (!cancelled) {
            setStopsLoading(false);
          }
        });
    };

    if (stopsDebounceRef.current) {
      window.clearTimeout(stopsDebounceRef.current);
    }
    stopsDebounceRef.current = window.setTimeout(loadStops, 350);

    return () => {
      cancelled = true;
      if (stopsDebounceRef.current) {
        window.clearTimeout(stopsDebounceRef.current);
        stopsDebounceRef.current = null;
      }
    };
  }, [isMapReady, selectedZoneUid, zoneDetailData, viewport.lat, viewport.lon, viewport.zoom]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }

    const zonesSource = map.getSource("zones-source") as mapboxgl.GeoJSONSource | undefined;
    if (!zonesSource) {
      return;
    }

    if (zonesCollection.length === 0) {
      zonesSource.setData({ type: "FeatureCollection", features: [] });
      return;
    }

    const circleFeatures = zonesCollection
      .map((feature) => {
        const props = feature.properties || {};
        const lon = Number(props.centroid_lon);
        const lat = Number(props.centroid_lat);
        const zoneRadius = clampZoneRadius(
          Number(
            props.analysis_radius_m ??
            props.zone_radius_m ??
            props.radius_m ??
            props.buffer_m ??
            zoneRadiusM
          )
        );
        if (!Number.isFinite(lon) || !Number.isFinite(lat)) {
          return null;
        }
        return {
          type: "Feature" as const,
          geometry: {
            type: "Polygon" as const,
            coordinates: buildCircleCoordinates(lon, lat, zoneRadius)
          },
          properties: {
            ...props,
            zone_uid: String(props.zone_uid || ""),
            analysis_radius_m: zoneRadius
          }
        };
      })
      .filter(Boolean);

    zonesSource.setData({
      type: "FeatureCollection",
      features: circleFeatures as unknown as any[]
    });

    const centroidSource = map.getSource("zone-centroid-source") as mapboxgl.GeoJSONSource | undefined;
    if (centroidSource) {
      const centroidFeatures = zonesCollection
        .map((feature) => {
          const props = feature.properties || {};
          const lon = Number(props.centroid_lon);
          const lat = Number(props.centroid_lat);
          if (!Number.isFinite(lon) || !Number.isFinite(lat)) {
            return null;
          }
          return {
            type: "Feature" as const,
            geometry: { type: "Point" as const, coordinates: [lon, lat] as [number, number] },
            properties: {
              zone_uid: String(props.zone_uid || "")
            }
          };
        })
        .filter(Boolean);
      centroidSource.setData({ type: "FeatureCollection", features: centroidFeatures as unknown as any[] });
    }
  }, [isMapReady, zoneRadiusM, zonesCollection]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady || !map.getLayer("zones-fill-layer")) {
      return;
    }

    if (selectedZoneUid) {
      map.setPaintProperty("zones-fill-layer", "fill-opacity", [
        "case",
        ["==", ["get", "zone_uid"], selectedZoneUid],
        0.35,
        0.12
      ]);
      map.setPaintProperty("zones-outline-layer", "line-width", [
        "case",
        ["==", ["get", "zone_uid"], selectedZoneUid],
        3,
        2
      ]);
      if (map.getLayer("zone-centroid-layer")) {
        map.setPaintProperty("zone-centroid-layer", "circle-radius", [
          "case",
          ["==", ["get", "zone_uid"], selectedZoneUid],
          7,
          5
        ]);
      }
    } else {
      map.setPaintProperty("zones-fill-layer", "fill-opacity", 0.2);
      map.setPaintProperty("zones-outline-layer", "line-width", 2);
      if (map.getLayer("zone-centroid-layer")) {
        map.setPaintProperty("zone-centroid-layer", "circle-radius", 5);
      }
    }
  }, [isMapReady, selectedZoneUid]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }
    const source = map.getSource("poi-zone-source") as mapboxgl.GeoJSONSource | undefined;
    if (!source) {
      return;
    }
    if (!zoneDetailData) {
      source.setData({ type: "FeatureCollection", features: [] });
      return;
    }

    const poiFeatures = (zoneDetailData.poi_points || [])
      .filter((point) => Number.isFinite(point.lon) && Number.isFinite(point.lat))
      .map((point) => ({
        type: "Feature" as const,
        geometry: {
          type: "Point" as const,
          coordinates: [point.lon, point.lat] as [number, number]
        },
        properties: {
          kind: "poi",
          id: point.id || "",
          name: point.name || "POI",
          category: point.category || "outros"
        }
      }));

    source.setData({ type: "FeatureCollection", features: poiFeatures as unknown as any[] });
  }, [isMapReady, zoneDetailData]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }
    const seedSource = map.getSource("reference-transport-source") as mapboxgl.GeoJSONSource | undefined;
    const downstreamSource = map.getSource("downstream-transport-source") as mapboxgl.GeoJSONSource | undefined;
    if (!seedSource || !downstreamSource) {
      return;
    }

    const seedPoint = zoneDetailData?.seed_transport_point || zoneDetailData?.reference_transport_point;
    if (!seedPoint || typeof seedPoint.lon !== "number" || typeof seedPoint.lat !== "number") {
      seedSource.setData({ type: "FeatureCollection", features: [] });
    } else {
      seedSource.setData({
        type: "FeatureCollection",
        features: [
          {
            type: "Feature",
            geometry: {
              type: "Point",
              coordinates: [seedPoint.lon, seedPoint.lat]
            },
            properties: {
              kind: seedPoint.kind || "transport",
              name: seedPoint.name || "Parada seed"
            }
          }
        ]
      });
    }

    const downstreamPoint = zoneDetailData?.downstream_transport_point;
    if (!downstreamPoint || typeof downstreamPoint.lon !== "number" || typeof downstreamPoint.lat !== "number") {
      downstreamSource.setData({ type: "FeatureCollection", features: [] });
    } else {
      downstreamSource.setData({
        type: "FeatureCollection",
        features: [
          {
            type: "Feature",
            geometry: {
              type: "Point",
              coordinates: [downstreamPoint.lon, downstreamPoint.lat]
            },
            properties: {
              kind: downstreamPoint.kind || "transport",
              name: downstreamPoint.name || "Parada downstream"
            }
          }
        ]
      });
    }
  }, [isMapReady, zoneDetailData]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }
    const source = map.getSource("listings-source") as mapboxgl.GeoJSONSource | undefined;
    if (!source) {
      return;
    }
    const features = finalListings
      .map((feature, index) => {
        if (feature.geometry.type !== "Point") {
          return null;
        }
        const listingKey = `${index}_${feature.geometry.coordinates.join("_")}`;
        const info = resolveListingText(feature);
        return {
          type: "Feature" as const,
          geometry: feature.geometry,
          properties: {
            listing_key: listingKey,
            priceLabel: info.priceLabel,
            address: info.address
          }
        };
      })
      .filter(Boolean);
    source.setData({ type: "FeatureCollection", features: features as unknown as any[] });

    if (map.getLayer("listings-layer")) {
      map.setPaintProperty("listings-layer", "circle-radius", [
        "case",
        ["==", ["get", "listing_key"], focusedListingKey],
        7,
        5
      ]);
    }
  }, [finalListings, focusedListingKey, isMapReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }

    primaryMarkerRef.current?.remove();
    if (!primaryPoint) {
      return;
    }

    primaryMarkerRef.current = new mapboxgl.Marker({ color: "#2563eb" })
      .setLngLat([primaryPoint.lon, primaryPoint.lat])
      .setPopup(
        new mapboxgl.Popup({ offset: 12 }).setHTML(
          `<strong>Ponto principal</strong><br/>${primaryPoint.lat.toFixed(5)}, ${primaryPoint.lon.toFixed(5)}`
        )
      )
      .addTo(map);
  }, [isMapReady, primaryPoint]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }

    const markerMap = interestMarkerRefs.current;
    const currentIds = new Set(interests.map((interest) => interest.id));

    markerMap.forEach((marker, id) => {
      if (!currentIds.has(id)) {
        marker.remove();
        markerMap.delete(id);
      }
    });

    interests.forEach((interest) => {
      if (markerMap.has(interest.id)) {
        return;
      }

      const markerElement = document.createElement("button");
      markerElement.type = "button";
      markerElement.className = "h-3.5 w-3.5 rounded-full border-2 border-white bg-[#d97706] shadow";
      markerElement.title = `${interest.label} (${interest.category})`;

      const marker = new mapboxgl.Marker({ element: markerElement })
        .setLngLat([interest.lon, interest.lat])
        .setPopup(
          new mapboxgl.Popup({ offset: 10 }).setHTML(
            `<strong>${interest.label}</strong><br/>${interest.category}<br/>${interest.lat.toFixed(5)}, ${interest.lon.toFixed(5)}`
          )
        )
        .addTo(map);
      markerMap.set(interest.id, marker);
    });
  }, [interests, isMapReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }

    const routeSource = map.getSource("transport-demo") as mapboxgl.GeoJSONSource | undefined;
    if (!routeSource) {
      return;
    }

    if (!runId || zonesCollection.length === 0) {
      routeSource.setData({
        type: "FeatureCollection",
        features: []
      });
      return;
    }

    let cancelled = false;

    const loadRealTransportLayers = async () => {
      try {
        const layers = await getTransportLayers(runId);
        if (cancelled) {
          return;
        }
        routeSource.setData(layers.routes);
      } catch (error) {
        if (cancelled) {
          return;
        }
        routeSource.setData({
          type: "FeatureCollection",
          features: []
        });
        setZoneSelectionMessage(`Camadas de transporte indisponíveis agora. ${apiActionHint(error)}`);
      }
    };

    void loadRealTransportLayers();

    return () => {
      cancelled = true;
    };
  }, [isMapReady, runId, zonesCollection.length]);

  useEffect(() => {
    if (!runId || zonesCollection.length === 0) {
      setOriginalSeedPoint(null);
      setZoneSeedPoints([]);
      setZoneDownstreamPoints([]);
      return;
    }

    let cancelled = false;

    const parsePointFeature = (feature: any): TransportAnchorPoint | null => {
      if (!feature || feature.geometry?.type !== "Point") {
        return null;
      }
      const coordinates = feature.geometry.coordinates;
      if (!Array.isArray(coordinates) || coordinates.length < 2) {
        return null;
      }
      const lon = Number(coordinates[0]);
      const lat = Number(coordinates[1]);
      if (!Number.isFinite(lon) || !Number.isFinite(lat)) {
        return null;
      }
      const props = feature.properties || {};
      const id = String(props.id || "").trim();
      const name = String(props.name || "").trim();
      const kind = String(props.kind || "transport").trim() || "transport";
      return { id, name, kind, lon, lat };
    };

    const loadRunAnchors = async () => {
      const zoneRefs = zonesCollection
        .map((zone) => {
          const props = zone.properties || {};
          const trace = (props.trace as Record<string, unknown> | undefined) || {};
          const seedId = String(trace.seed_bus_stop_id || "").trim();
          const downstreamId = String(trace.downstream_stop_id || "").trim();
          return {
            zoneUid: String(props.zone_uid || ""),
            seedId,
            downstreamId,
            downstreamName: String(trace.stop_name || "").trim()
          };
        })
        .filter((entry) => entry.zoneUid && (entry.seedId || entry.downstreamId));

      const centroids = zonesCollection
        .map((zone) => {
          const props = zone.properties || {};
          const lon = Number(props.centroid_lon);
          const lat = Number(props.centroid_lat);
          if (!Number.isFinite(lon) || !Number.isFinite(lat)) {
            return null;
          }
          return { lon, lat };
        })
        .filter(Boolean) as Array<{ lon: number; lat: number }>;

      const seedPoints: TransportAnchorPoint[] = [];
      const downstreamPoints: TransportAnchorPoint[] = [];

      if (centroids.length > 0) {
        const minLon = Math.min(...centroids.map((item) => item.lon));
        const minLat = Math.min(...centroids.map((item) => item.lat));
        const maxLon = Math.max(...centroids.map((item) => item.lon));
        const maxLat = Math.max(...centroids.map((item) => item.lat));
        const padding = 0.04;
        const stops = await getTransportStops(0, 0, 2500, {
          minLon: minLon - padding,
          minLat: minLat - padding,
          maxLon: maxLon + padding,
          maxLat: maxLat + padding
        });

        const points = (stops.features || [])
          .map((feature) => parsePointFeature(feature))
          .filter(Boolean) as TransportAnchorPoint[];
        const byId = new Map<string, TransportAnchorPoint>();
        points.forEach((point) => {
          if (point.id) {
            byId.set(point.id, point);
          }
        });

        zoneRefs.forEach((entry) => {
          if (entry.seedId) {
            const point = byId.get(entry.seedId);
            if (point) {
              seedPoints.push({ ...point, zoneUid: entry.zoneUid });
            }
          }
          if (entry.downstreamId) {
            const point = byId.get(entry.downstreamId);
            if (point) {
              downstreamPoints.push({
                ...point,
                zoneUid: entry.zoneUid,
                name: point.name || entry.downstreamName || point.name
              });
            }
          }
        });
      }

      let originalSeed: TransportAnchorPoint | null = null;
      if (primaryPoint) {
        const nearestStops = await getTransportStops(primaryPoint.lon, primaryPoint.lat, 1200);
        const nearestCandidates = (nearestStops.features || [])
          .map((feature) => parsePointFeature(feature))
          .filter(Boolean) as TransportAnchorPoint[];
        originalSeed = nearestCandidates
          .map((point) => ({
            point,
            distance: haversineMeters(primaryPoint.lat, primaryPoint.lon, point.lat, point.lon)
          }))
          .sort((a, b) => a.distance - b.distance)[0]?.point || null;
      }

      if (!cancelled) {
        setOriginalSeedPoint(originalSeed);
        setZoneSeedPoints(seedPoints);
        setZoneDownstreamPoints(downstreamPoints);
      }
    };

    void loadRunAnchors().catch(() => {
      if (!cancelled) {
        setOriginalSeedPoint(null);
        setZoneSeedPoints([]);
        setZoneDownstreamPoints([]);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [primaryPoint, runId, zonesCollection]);

  useEffect(() => {
    if (!runId || !isPolling) {
      return;
    }

    let cancelled = false;
    let timeoutId: number | undefined;
    let attempt = 0;

    const loadZonesContract = async () => {
      setZonesState("loading");
      setZonesStateMessage("Validando payload de zonas (contrato Zod)...");
      try {
        const zones = await getZones(runId);
        if ((zones.features || []).length === 0) {
          setZonesCollection([]);
          setSelectedZoneUid("");
          setZonesState("empty");
          setZonesStateMessage("Nenhuma zona consolidada retornada. Revise os dados de referência.");
          setZoneSelectionMessage("Nenhuma zona disponível para seleção.");
        } else {
          setZonesCollection(zones.features);
          setSelectedZoneUid(zones.features[0]?.properties.zone_uid || "");
          setZonesState("ready");
          setZonesStateMessage(`Payload válido: ${zones.features.length} zonas consolidadas.`);
          setZoneSelectionMessage("Selecione 1 zona e prossiga para detalhamento/listings.");
          setZoneDetailData(null);
          setZoneListingMessage("Aguardando detalhamento da zona selecionada.");
          setFinalListings([]);
          setListingsWithoutCoords([]);
          setFinalizeMessage("Finalize o run para carregar os imóveis.");
        }
      } catch (error) {
        const hint = apiActionHint(error);
        const recoverable = hint.includes("Tente novamente") || hint.includes("run_id existe");
        setZonesState(recoverable ? "error-recoverable" : "error-fatal");
        setZonesStateMessage(hint);
        setZonesCollection([]);
        setSelectedZoneUid("");
        setZoneSelectionMessage(hint);
      }
    };

    const poll = async () => {
      if (cancelled) {
        return;
      }

      try {
        const data = await getRunStatus(runId);
        setRunStatus(data.status);
        setStatusMessage(`Run ${runId}: ${data.status.stage} (${data.status.state})`);

        if (data.status.state === "success") {
          setIsPolling(false);
          setActiveStep(2);
          setStatusMessage("Zonas candidatas prontas. Avance para o passo 2.");
          setExecutionProgress((current) => ({
            ...current,
            active: true,
            label: "Zonas candidatas prontas.",
            percent: 100,
            etaSec: 0
          }));
          window.setTimeout(() => stopExecutionProgress("Zonas candidatas prontas."), 900);
          await loadZonesContract();
          return;
        }

        if (data.status.state === "failed") {
          setIsPolling(false);
          setActiveStep(1);
          setZonesState("error-recoverable");
          setZonesStateMessage("Run falhou antes de gerar zonas. Ajuste ponto/parâmetros e tente novamente.");
          setStatusMessage("Run falhou. Ajuste o ponto principal e tente novamente.");
          stopExecutionProgress("Execução interrompida com erro.", "error");
          return;
        }

        const base = Math.min(10000, 1400 * 2 ** attempt);
        const jitter = Math.floor(Math.random() * 300);
        timeoutId = window.setTimeout(poll, base + jitter);
        attempt += 1;
      } catch (error) {
        const hint = apiActionHint(error);
        setStatusMessage(hint);
        setZonesState("error-recoverable");
        setZonesStateMessage(hint);

        const retryDelay = Math.min(10000, 1800 * 2 ** attempt);
        timeoutId = window.setTimeout(poll, retryDelay);
        attempt += 1;
      }
    };

    void poll();

    return () => {
      cancelled = true;
      if (timeoutId) {
        window.clearTimeout(timeoutId);
      }
    };
  }, [isPolling, runId]);

  const activeLegendItems = useMemo(
    () =>
      (Object.keys(layerVisibility) as LayerKey[])
        .filter((key) => {
          if ((key === "routes" || key === "train") && !hasRouteData) {
            return false;
          }
          if (key === "zones" && zonesCollection.length === 0) {
            return false;
          }
          return layerVisibility[key];
        })
        .map((key) => ({ key, ...LAYER_INFO[key] })),
    [hasRouteData, layerVisibility, zonesCollection.length]
  );

  const mapBusyMessage = useMemo(() => {
    if (isCreatingRun) {
      return "Criando run e iniciando pipeline de zonas...";
    }
    if (isPolling) {
      return runStatus ? `Processando etapa: ${runStatus.stage}` : "Processando zonas candidatas...";
    }
    return "";
  }, [isCreatingRun, isPolling, runStatus]);

  const stopExecutionProgress = (finalLabel?: string, outcome: "done" | "error" = "done") => {
    if (progressTimerRef.current) {
      window.clearInterval(progressTimerRef.current);
      progressTimerRef.current = null;
    }
    const elapsedSec = Math.max(0, Math.floor((Date.now() - progressStartRef.current) / 1000));
    const stageKey = activeExecutionStage;
    if (stageKey) {
      setExecutionStages((current) => ({
        ...current,
        [stageKey]: {
          ...current[stageKey],
          status: outcome === "error" ? "error" : "done",
          elapsedSec,
          etaSec: 0,
          durationSec: elapsedSec
        }
      }));
      setActiveExecutionStage(null);
    }
    if (progressStartRef.current > 0 && finalLabel) {
      setExecutionHistory((current) => [{ label: finalLabel, durationSec: elapsedSec }, ...current].slice(0, 5));
    }
    setExecutionProgress((current) => ({
      active: false,
      label: finalLabel || current.label,
      percent: current.percent,
      etaSec: 0,
      elapsedSec
    }));
  };

  const startExecutionProgress = (stage: ExecutionStageKey, label: string, expectedSec: number) => {
    if (progressTimerRef.current) {
      window.clearInterval(progressTimerRef.current);
    }

    progressStartRef.current = Date.now();
    progressExpectedRef.current = expectedSec;
    setActiveExecutionStage(stage);
    setExecutionStages((current) => ({
      ...current,
      [stage]: {
        ...current[stage],
        status: "running",
        elapsedSec: 0,
        etaSec: expectedSec,
        durationSec: null
      }
    }));
    setExecutionProgress({
      active: true,
      label,
      percent: 1,
      etaSec: expectedSec,
      elapsedSec: 0
    });

    progressTimerRef.current = window.setInterval(() => {
      const elapsedSec = Math.floor((Date.now() - progressStartRef.current) / 1000);
      const expected = Math.max(1, progressExpectedRef.current);
      const ratio = Math.min(0.95, elapsedSec / expected);
      const activeStage = stage;
      setExecutionProgress((current) => ({
        ...current,
        active: true,
        percent: Math.max(current.percent, Math.floor(ratio * 100)),
        etaSec: Math.max(0, expected - elapsedSec),
        elapsedSec
      }));
      setExecutionStages((current) => ({
        ...current,
        [activeStage]: {
          ...current[activeStage],
          status: "running",
          elapsedSec,
          etaSec: Math.max(0, expected - elapsedSec)
        }
      }));
    }, 1000);
  };

  const resetExecutionTracking = () => {
    if (progressTimerRef.current) {
      window.clearInterval(progressTimerRef.current);
      progressTimerRef.current = null;
    }
    setExecutionStages(createInitialExecutionStages());
    setActiveExecutionStage(null);
    setExecutionHistory([]);
    setExecutionProgress({
      active: false,
      label: "Aguardando execução.",
      percent: 0,
      etaSec: 0,
      elapsedSec: 0
    });
    progressStartRef.current = 0;
    progressExpectedRef.current = 0;
  };

  useEffect(() => {
    return () => {
      if (progressTimerRef.current) {
        window.clearInterval(progressTimerRef.current);
      }
    };
  }, []);

  const handleSearch = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const map = mapRef.current;
    if (!map || !searchValue.trim() || !MAPBOX_TOKEN) {
      return;
    }

    try {
      const encodedQuery = encodeURIComponent(searchValue.trim());
      const url = `https://api.mapbox.com/geocoding/v5/mapbox.places/${encodedQuery}.json?access_token=${MAPBOX_TOKEN}&limit=1&language=pt`;
      const response = await fetch(url);
      const data = (await response.json()) as {
        features?: Array<{ center?: [number, number] }>;
      };
      const center = data.features?.[0]?.center;
      if (!center) {
        setStatusMessage("Nenhum resultado encontrado para esta busca. Tente outro endereço/bairro.");
        return;
      }

      map.flyTo({ center, zoom: 13, duration: 900 });
    } catch {
      setStatusMessage("Falha na busca. Verifique internet/token Mapbox e tente novamente.");
    }
  };

  const handleCreateRun = async () => {
    if (!primaryPoint || isCreatingRun || isPolling) {
      return;
    }

    resetExecutionTracking();
    startExecutionProgress("zones", "Gerando zonas candidatas...", 180);
    setIsCreatingRun(true);
    setLoadingText("Analisando rotas de transporte e gerando zonas isócronas...");
    setStatusMessage("Criando run...");
    setZonesState("idle");
    setZonesStateMessage("Aguardando processamento das zonas.");

    try {
      const data: RunCreateResponse = await createRun({
        reference_points: [
          {
            name: primaryPoint.name,
            lat: primaryPoint.lat,
            lon: primaryPoint.lon
          }
        ],
        params: {
          cache_dir: "data_cache",
          zone_dedupe_m: 50,
          zone_radius_m: zoneRadiusM,
          max_streets_per_zone: 3,
          listing_max_pages: 2,
          listing_mode: propertyMode
        }
      });
      setRunId(data.run_id);
      setRunStatus(data.status);
      setIsPolling(true);
      setStatusMessage(`Run criada: ${data.run_id}. Aguardando zonas...`);
      setZonesState("loading");
      setZonesStateMessage("Pipeline iniciado. Aguardando status da run...");
      setZonesCollection([]);
      setSelectedZoneUid("");
      setZoneSelectionMessage("Aguardando zonas consolidadas.");
      setZoneDetailData(null);
      setZoneListingMessage("Aguardando seleção e detalhamento da zona.");
      setFinalListings([]);
      setListingsWithoutCoords([]);
      setFinalizeMessage("Finalize o run para carregar os imóveis.");
    } catch (error) {
      const message = apiActionHint(error);
      setStatusMessage(message);
      setIsPolling(false);
      setZonesState("error-recoverable");
      setZonesStateMessage(message);
      stopExecutionProgress("Falha ao criar run.", "error");
    } finally {
      setIsCreatingRun(false);
    }
  };

  const removePrimaryPoint = () => {
    setPrimaryPoint(null);
    setRunId("");
    setRunStatus(null);
    setIsPolling(false);
    setZonesState("idle");
    setZonesStateMessage("Aguardando criação da run.");
    setZonesCollection([]);
    setSelectedZoneUid("");
    setZoneSelectionMessage("Selecione uma zona consolidada.");
    setZoneDetailData(null);
    setZoneListingMessage("Aguardando seleção e detalhamento da zona.");
    setFinalListings([]);
    setListingsWithoutCoords([]);
    setFinalizeMessage("Finalize o run para carregar os imóveis.");
    resetExecutionTracking();
    setActiveStep(1);
    setStatusMessage("Ponto principal removido.");
  };

  const resetFromStep = (step: 2 | 3) => {
    if (step <= 2) {
      setSelectedZoneUid("");
      setZoneSelectionMessage("Selecione uma zona consolidada.");
    }
    if (step <= 3) {
      setZoneDetailData(null);
      setZoneStreets([]);
      setSelectedStreet("");
      setZoneListingMessage("Aguardando seleção e detalhamento da zona.");
    }
    if (step <= 3) {
      setFinalListings([]);
      setListingsWithoutCoords([]);
      setFocusedListingKey("");
      setFinalizeMessage("Finalize o run para carregar os imóveis.");
    }
  };

  const handleSelectZone = async () => {
    if (!runId || !selectedZoneUid || isSelectingZone) {
      return;
    }

    let succeeded = false;
    startExecutionProgress("selectZone", "Selecionando zona...", 8);
    setIsSelectingZone(true);
    setZoneSelectionMessage("Persistindo zona selecionada...");
    try {
      const result = await selectZones(runId, [selectedZoneUid]);
      setZoneSelectionMessage(result.message);
      setActiveStep(3);
      setStatusMessage(`Zona ${selectedZoneUid} selecionada.`);
      succeeded = true;
    } catch (error) {
      const hint = apiActionHint(error);
      setZoneSelectionMessage(hint);
      setStatusMessage(hint);
      stopExecutionProgress("Falha ao selecionar zona.", "error");
    } finally {
      setIsSelectingZone(false);
      if (succeeded) {
        setExecutionProgress((current) => ({ ...current, percent: 100, etaSec: 0, label: "Zona selecionada." }));
        window.setTimeout(() => stopExecutionProgress("Zona selecionada."), 700);
      }
    }
  };

  useEffect(() => {
    if (!runId || !selectedZoneUid || !zoneDetailData) {
      setZoneStreets([]);
      return;
    }

    let cancelled = false;
    getZoneStreets(runId, selectedZoneUid)
      .then((data) => {
        if (!cancelled) {
          setZoneStreets(data.streets || []);
          if (data.streets?.length && !selectedStreet) {
            setSelectedStreet(data.streets[0]);
          }
        }
      })
      .catch(() => {
        if (!cancelled) {
          setZoneStreets([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [runId, selectedZoneUid, zoneDetailData]);

  const handleDetailZone = async () => {
    if (!runId || !selectedZoneUid || isDetailingZone) {
      return;
    }

    let succeeded = false;
    startExecutionProgress("detailZone", "Detalhando zona...", 60);
    setIsDetailingZone(true);
    setLoadingText("Cruzando bases geográficas, recolhendo ruas e efetuando scraping dos imóveis...");
    setZoneListingMessage("Executando detalhamento da zona...");
    try {
      const detail = await getZoneDetail(runId, selectedZoneUid);
      setZoneDetailData(detail);
      setLayerVisibility((current) => ({ ...current, pois: true, busStops: true }));
      setZoneListingMessage("Detalhamento concluído. Escolha como buscar imóveis.");
      setStatusMessage(`Detalhamento finalizado para ${selectedZoneUid}.`);
      setActiveStep(3);
      succeeded = true;
    } catch (error) {
      const hint = apiActionHint(error);
      setZoneListingMessage(hint);
      setStatusMessage(hint);
      stopExecutionProgress("Falha no detalhamento da zona.", "error");
    } finally {
      setIsDetailingZone(false);
      if (succeeded) {
        setExecutionProgress((current) => ({
          ...current,
          percent: 100,
          etaSec: 0,
          label: "Detalhamento concluído."
        }));
        window.setTimeout(() => stopExecutionProgress("Detalhamento concluído."), 700);
      }
    }
  };

  const handleZoneListings = async () => {
    if (!runId || !selectedZoneUid || !zoneDetailData || isListingZone) {
      return;
    }

    const streetFilter = streetFilterMode === "specific" && selectedStreet ? selectedStreet : undefined;

    let succeeded = false;
    startExecutionProgress("zoneListings", "Coletando imóveis por rua...", 180);
    setIsListingZone(true);
    setLoadingText("Buscando imóveis nas plataformas...");
    setZoneListingMessage(
      streetFilter ? `Buscando imóveis na rua ${streetFilter}...` : "Buscando imóveis em todas as ruas da zona..."
    );
    try {
      const result = await scrapeZoneListings(runId, selectedZoneUid, streetFilter);
      setZoneListingMessage(
        `Coleta concluída: ${result.listings_count} lote(s) processados. Consolidando resultado...`
      );
      setLoadingText("Consolidando resultado final...");
      await finalizeRun(runId);
      const [finalGeo, finalJson] = await Promise.all([getFinalListings(runId), getFinalListingsJson(runId)]);
      setFinalListings(finalGeo.features || []);
      const withoutCoords = (finalJson || []).filter((item) => {
        const lat = Number(item.lat ?? item.latitude);
        const lon = Number(item.lon ?? item.longitude);
        return !Number.isFinite(lat) || !Number.isFinite(lon);
      });
      setListingsWithoutCoords(withoutCoords);
      setFinalizeMessage(
        `Resultado final pronto: ${finalGeo.features.length} no mapa e ${withoutCoords.length} sem localização no mapa.`
      );
      setStatusMessage("Busca e consolidação concluídas. Cards e exports disponíveis no painel.");
      setActiveStep(3);
      succeeded = true;
    } catch (error) {
      const hint = apiActionHint(error);
      setZoneListingMessage(hint);
      setFinalizeMessage(hint);
      setStatusMessage(hint);
      stopExecutionProgress("Falha na coleta de imóveis.", "error");
    } finally {
      setIsListingZone(false);
      if (succeeded) {
        setExecutionProgress((current) => ({
          ...current,
          percent: 100,
          etaSec: 0,
          label: "Coleta de imóveis concluída."
        }));
        window.setTimeout(() => stopExecutionProgress("Coleta de imóveis concluída."), 700);
      }
    }
  };

  const removeInterest = (id: string) => {
    setInterests((current) => current.filter((item) => item.id !== id));
  };

  const navigateToStep = (targetStep: 1 | 2 | 3) => {
    if (targetStep === 1 && activeStep > 1) {
      removePrimaryPoint();
      return;
    }

    if (targetStep < activeStep) {
      if (targetStep === 2) {
        resetFromStep(3);
      }
      setActiveStep(targetStep);
      return;
    }

    const canAdvanceTo2 = Boolean(runId && zonesCollection.length > 0);
    const canAdvanceTo3 = Boolean(selectedZoneUid);

    if (targetStep === 2 && canAdvanceTo2) {
      setActiveStep(2);
    } else if (targetStep === 3 && canAdvanceTo3) {
      setActiveStep(3);
    } else if (targetStep <= activeStep) {
      setActiveStep(targetStep);
    }
  };

  const toggleLayer = (key: LayerKey) => {
    setLayerVisibility((current) => ({ ...current, [key]: !current[key] }));
  };

  const zoomIn = () => mapRef.current?.zoomIn({ duration: 180 });
  const zoomOut = () => mapRef.current?.zoomOut({ duration: 180 });
  const rightUiOffsetClass = isPanelMinimized ? "right-6" : "right-[422px]";

  const formatCurrencyBr = (value: unknown): string => {
    if (typeof value !== "number" || Number.isNaN(value)) {
      return "Preço não informado";
    }
    return new Intl.NumberFormat("pt-BR", {
      style: "currency",
      currency: "BRL",
      maximumFractionDigits: 0
    }).format(value);
  };

  const parseFiniteNumber = (value: unknown): number | null => {
    if (typeof value === "number") {
      return Number.isFinite(value) ? value : null;
    }
    if (typeof value === "string") {
      const sanitized = value.replace(/\./g, "").replace(",", ".").trim();
      const parsed = Number(sanitized);
      return Number.isFinite(parsed) ? parsed : null;
    }
    return null;
  };

  const normalizeCategory = (value: string) =>
    value
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .trim()
      .toLowerCase();

  const formatMeters = (value: number | null) => {
    if (value === null || !Number.isFinite(value)) {
      return "n/d";
    }
    if (value >= 1000) {
      return `${(value / 1000).toFixed(1)} km`;
    }
    return `${Math.round(value)} m`;
  };

  const getListingKey = (feature: ListingFeature, index: number) => `${index}_${feature.geometry.coordinates.join("_")}`;

  const getListingAnalytics = (feature: ListingFeature, index: number) => {
    const props = feature.properties || {};
    const priceValue =
      parseFiniteNumber(props.price) ??
      parseFiniteNumber(props.rent_price) ??
      parseFiniteNumber(props.sale_price) ??
      parseFiniteNumber(props.total_price);
    const sizeM2 =
      parseFiniteNumber(props.area_m2) ??
      parseFiniteNumber(props.area) ??
      parseFiniteNumber(props.area_total_m2) ??
      parseFiniteNumber(props.private_area) ??
      parseFiniteNumber(props.usable_area);
    const bedrooms =
      parseFiniteNumber(props.bedrooms) ??
      parseFiniteNumber(props.beds) ??
      parseFiniteNumber(props.quartos);
    const distanceTransportM =
      parseFiniteNumber(props.distance_transport_m) ??
      parseFiniteNumber(props.dist_transport_m) ??
      parseFiniteNumber(props.distance_to_transport_m);
    const platform =
      String(props.source || props.platform || props.site || "")
        .trim()
        .toUpperCase() || "PLATAFORMA N/D";
    const listingKey = getListingKey(feature, index);

    let poiCountWithinRadius = 0;
    const nearestPoiByCategory: Array<{ category: string; distanceM: number | null }> = [];

    if (feature.geometry.type === "Point") {
      const [lon, lat] = feature.geometry.coordinates;
      const categoriesPriority =
        interests.length > 0
          ? Array.from(new Set(interests.map((item) => item.category))).filter(Boolean)
          : Object.entries(zoneDetailData?.poi_count_by_category || {})
              .sort((a, b) => b[1] - a[1])
              .map(([category]) => category)
              .slice(0, 3);

      const nearestByNormalized = new Map<string, { category: string; distanceM: number | null }>();
      categoriesPriority.forEach((category) => {
        nearestByNormalized.set(normalizeCategory(category), { category, distanceM: null });
      });

      for (const poi of zoneDetailData?.poi_points || []) {
        if (!Number.isFinite(poi.lon) || !Number.isFinite(poi.lat)) {
          continue;
        }
        const distanceM = haversineMeters(lat, lon, poi.lat, poi.lon);
        if (distanceM <= poiCountRadiusM) {
          poiCountWithinRadius += 1;
        }
        const poiCategory = String(poi.category || "outros");
        const normalized = normalizeCategory(poiCategory);
        const current = nearestByNormalized.get(normalized);
        if (!current) {
          continue;
        }
        if (current.distanceM === null || distanceM < current.distanceM) {
          current.distanceM = distanceM;
          current.category = poiCategory;
        }
      }

      nearestPoiByCategory.push(...nearestByNormalized.values());
    }

    return {
      listingKey,
      priceValue,
      sizeM2,
      bedrooms,
      distanceTransportM,
      platform,
      poiCountWithinRadius,
      nearestPoiByCategory
    };
  };

  const resolveListingText = (feature: ListingFeature) => {
    const props = feature.properties || {};
    const price =
      (props.price as number | undefined) ||
      (props.rent_price as number | undefined) ||
      (props.sale_price as number | undefined) ||
      (props.total_price as number | undefined);
    const address =
      (props.address as string | undefined) ||
      (props.street as string | undefined) ||
      (props.title as string | undefined) ||
      "Endereço não informado";
    const url =
      (props.url as string | undefined) ||
      (props.listing_url as string | undefined) ||
      (props.link as string | undefined) ||
      "";
    return {
      priceLabel: formatCurrencyBr(price),
      address,
      url
    };
  };

  const sortedListings = useMemo(() => {
    const decorated = finalListings.map((feature, index) => ({
      feature,
      index,
      info: resolveListingText(feature),
      analytics: getListingAnalytics(feature, index)
    }));

    const withFallback = (value: number | null, fallback: number) => (value === null ? fallback : value);
    decorated.sort((a, b) => {
      if (listingSortMode === "price-asc") {
        return withFallback(a.analytics.priceValue, Number.POSITIVE_INFINITY) - withFallback(b.analytics.priceValue, Number.POSITIVE_INFINITY);
      }
      if (listingSortMode === "price-desc") {
        return withFallback(b.analytics.priceValue, Number.NEGATIVE_INFINITY) - withFallback(a.analytics.priceValue, Number.NEGATIVE_INFINITY);
      }
      if (listingSortMode === "size-asc") {
        return withFallback(a.analytics.sizeM2, Number.POSITIVE_INFINITY) - withFallback(b.analytics.sizeM2, Number.POSITIVE_INFINITY);
      }
      return withFallback(b.analytics.sizeM2, Number.NEGATIVE_INFINITY) - withFallback(a.analytics.sizeM2, Number.NEGATIVE_INFINITY);
    });
    return decorated;
  }, [finalListings, interests, listingSortMode, poiCountRadiusM, zoneDetailData?.poi_count_by_category, zoneDetailData?.poi_points]);

  const selectedListingsForComparison = useMemo(
    () => sortedListings.filter((item) => selectedListingKeys.includes(item.analytics.listingKey)),
    [selectedListingKeys, sortedListings]
  );

  const comparisonExtremes = useMemo(() => {
    const numeric = {
      price: selectedListingsForComparison
        .map((item) => item.analytics.priceValue)
        .filter((value): value is number => value !== null),
      size: selectedListingsForComparison
        .map((item) => item.analytics.sizeM2)
        .filter((value): value is number => value !== null),
      transport: selectedListingsForComparison
        .map((item) => item.analytics.distanceTransportM)
        .filter((value): value is number => value !== null),
      poiCount: selectedListingsForComparison
        .map((item) => item.analytics.poiCountWithinRadius)
        .filter((value): value is number => Number.isFinite(value))
    };

    const resolveMinMax = (values: number[]) => {
      if (values.length === 0) {
        return { min: null as number | null, max: null as number | null };
      }
      return {
        min: Math.min(...values),
        max: Math.max(...values)
      };
    };

    return {
      price: resolveMinMax(numeric.price),
      size: resolveMinMax(numeric.size),
      transport: resolveMinMax(numeric.transport),
      poiCount: resolveMinMax(numeric.poiCount)
    };
  }, [selectedListingsForComparison]);

  const getComparisonCellClass = (
    value: number | null,
    min: number | null,
    max: number | null,
    strategy: "lower-better" | "higher-better"
  ) => {
    if (value === null || min === null || max === null) {
      return "text-text";
    }
    const isClose = (a: number, b: number) => Math.abs(a - b) < 0.0001;
    const isBest = strategy === "lower-better" ? isClose(value, min) : isClose(value, max);
    const isWorst = strategy === "lower-better" ? isClose(value, max) : isClose(value, min);
    if (isBest && isWorst) {
      return "font-semibold text-text";
    }
    if (isBest) {
      return "font-semibold text-success";
    }
    if (isWorst) {
      return "font-semibold text-danger";
    }
    return "text-text";
  };

  const resolveRawListingText = (item: Record<string, unknown>) => {
    const price = item.price || item.rent_price || item.sale_price || item.total_price;
    const address =
      (item.address as string | undefined) ||
      (item.street as string | undefined) ||
      (item.title as string | undefined) ||
      "Endereço não informado";
    const url =
      (item.url as string | undefined) ||
      (item.listing_url as string | undefined) ||
      (item.link as string | undefined) ||
      "";
    return {
      priceLabel: formatCurrencyBr(price),
      address,
      url
    };
  };

  const focusListingOnMap = (feature: ListingFeature, index: number) => {
    if (feature.geometry.type !== "Point") {
      return;
    }
    const [lon, lat] = feature.geometry.coordinates;
    const listingKey = getListingKey(feature, index);
    setFocusedListingKey(listingKey);
    const info = resolveListingText(feature);
    mapRef.current?.flyTo({ center: [lon, lat], zoom: 14.8, duration: 700 });
    if (mapRef.current) {
      new mapboxgl.Popup({ offset: 12 })
        .setLngLat([lon, lat])
        .setHTML(`<strong>${info.priceLabel}</strong><br/>${info.address}`)
        .addTo(mapRef.current);
    }
  };

  const handleListingCardClick = (feature: ListingFeature, index: number) => {
    const listingKey = getListingKey(feature, index);
    focusListingOnMap(feature, index);
    setSelectedListingKeys((current) => {
      if (current.includes(listingKey)) {
        const next = current.filter((item) => item !== listingKey);
        if (focusedListingKey === listingKey) {
          setFocusedListingKey("");
        }
        return next;
      }
      return [...current, listingKey];
    });
  };

  return (
    <main className="flex h-screen w-full overflow-hidden bg-[#F0EDE5] font-sans text-slate-800 select-none">
      <div className="relative flex h-full w-full overflow-hidden max-lg:flex-col">
        <section className="relative h-full min-w-0 flex-1 overflow-hidden bg-[#E5E3DF] transition-all duration-300 max-lg:h-[55vh] max-lg:flex-none">
          <div ref={mapContainerRef} className="h-full w-full" aria-label="Mapa principal" />

          <div className="pointer-events-none absolute inset-0">
            {/* Barra de Pesquisa - estilo esboço */}
            <div className="pointer-events-auto absolute left-6 top-6 z-40 w-80">
              <form onSubmit={handleSearch} className="bg-white/95 backdrop-blur-md rounded-lg shadow-md flex items-center px-4 py-3 border border-slate-200">
                <Search className="text-slate-400 w-5 h-5 mr-3 shrink-0" />
                <input
                  id="map-search"
                  value={searchValue}
                  onChange={(e) => setSearchValue(e.target.value)}
                  placeholder="Endereço ou bairro..."
                  className="bg-transparent border-none outline-none w-full text-slate-700 placeholder-slate-400 text-sm font-medium"
                />
                <button type="submit" className="text-[#2563EB] text-sm font-bold ml-2">
                  Buscar
                </button>
              </form>
            </div>

            {/* Modo de interação */}
            <div className="pointer-events-auto absolute left-6 top-20 z-40 flex gap-2">
              <button
                type="button"
                onClick={() => setInteractionMode("primary")}
                className={`rounded-lg px-2.5 py-1.5 text-xs font-semibold transition ${
                  interactionMode === "primary" ? "bg-[#2563EB] text-white" : "bg-white/95 text-slate-500 border border-slate-200"
                }`}
              >
                Definir principal
              </button>
              <button
                type="button"
                onClick={() => setInteractionMode("interest")}
                className={`rounded-lg px-2.5 py-1.5 text-xs font-semibold transition ${
                  interactionMode === "interest" ? "bg-[#2563EB] text-white" : "bg-white/95 text-slate-500 border border-slate-200"
                }`}
              >
                Adicionar interesse
              </button>
            </div>

            <div className={`pointer-events-auto absolute top-6 z-40 flex flex-col items-end gap-2 ${rightUiOffsetClass}`}>
              <button
                type="button"
                onClick={() => setIsLayerMenuOpen((o) => !o)}
                className={`bg-white/95 backdrop-blur-md px-4 py-2.5 rounded-lg shadow-md border text-slate-700 font-bold flex items-center gap-2 transition-all pointer-events-auto ${
                  isLayerMenuOpen ? "border-[#2563EB] text-[#2563EB]" : "border-slate-200"
                }`}
              >
                <Layers className="w-5 h-5" /> Camadas
              </button>
              {isLayerMenuOpen ? (
                <div className="absolute top-full mt-2 right-0 bg-white/95 backdrop-blur-md p-4 rounded-xl shadow-xl border border-slate-200 w-48 pointer-events-auto">
                  <div className="text-xs font-bold text-slate-800 mb-3 uppercase flex justify-between items-center">
                    Camadas Visíveis
                    <button onClick={() => setIsLayerMenuOpen(false)} className="text-slate-400 hover:text-slate-700">
                      <X size={16} />
                    </button>
                  </div>
                  {(Object.keys(LAYER_INFO) as LayerKey[]).map((key) => (
                    <label key={key} className="flex items-center gap-2.5 mb-3 cursor-pointer group">
                      <input
                        type="checkbox"
                        checked={layerVisibility[key]}
                        onChange={() => toggleLayer(key)}
                        className="w-4 h-4 rounded text-[#2563EB]"
                      />
                      <span className={`text-sm font-medium ${(key === "routes" || key === "train") && !hasRouteData ? "text-slate-400" : "text-slate-700"}`}>
                        {LAYER_INFO[key].label}
                      </span>
                    </label>
                  ))}
                </div>
              ) : null}
            </div>

            {/* Zoom e Ajuda - canto inferior direito */}
            <div className={`pointer-events-auto absolute bottom-6 z-40 flex flex-col gap-2 ${rightUiOffsetClass}`}>
              <div className="bg-white/95 backdrop-blur-md rounded-lg shadow-lg border border-slate-200 flex flex-col overflow-hidden">
                <button onClick={zoomIn} className="p-2 text-slate-600 hover:text-[#2563EB] hover:bg-slate-50 border-b border-slate-100 transition-colors" title="Aumentar zoom">
                  <Plus size={20} />
                </button>
                <button onClick={zoomOut} className="p-2 text-slate-600 hover:text-[#2563EB] hover:bg-slate-50 transition-colors" title="Diminuir zoom">
                  <Minus size={20} />
                </button>
              </div>
              <button
                onClick={() => setIsHelpOpen(true)}
                className="bg-white/95 backdrop-blur-md rounded-lg shadow-lg border border-slate-200 p-2 text-slate-600 hover:text-[#2563EB] hover:bg-slate-50 transition-colors"
                title="Ajuda"
              >
                <HelpCircle size={20} />
              </button>
            </div>

            {/* Legenda - estilo esboço */}
            <div className="pointer-events-auto absolute bottom-6 left-6 z-40 flex flex-col gap-3">
              {(layerVisibility.flood || layerVisibility.green || (layerVisibility.routes && hasRouteData) || activeLegendItems.length > 0) && (
                <div className="bg-white/95 backdrop-blur-md p-4 rounded-xl shadow-lg border border-slate-200 text-xs text-slate-600 font-medium flex flex-col gap-2.5 min-w-[160px]">
                  <span className="text-[10px] uppercase font-bold text-slate-400 mb-0.5 tracking-wider">Legenda</span>
                  {stopsLoading && layerVisibility.busStops ? (
                    <p className="text-slate-500">Carregando paradas...</p>
                  ) : null}
                  {layerVisibility.flood && <div className="flex items-center gap-2"><div className="w-3.5 h-3.5 rounded bg-purple-600/50 border border-purple-700/30" /> Risco de Cheia</div>}
                  {layerVisibility.green && <div className="flex items-center gap-2"><div className="w-3.5 h-3.5 rounded bg-green-500/50 border border-green-600/30" /> Área Verde</div>}
                  {layerVisibility.routes && hasRouteData && (
                    <>
                      <div className="flex items-center gap-2"><div className="w-4 border-b-2 border-red-500" /> Metrô/Trem</div>
                      <div className="flex items-center gap-2"><div className="w-4 border-b-2 border-dashed border-orange-500" /> Ônibus</div>
                    </>
                  )}
                  {layerVisibility.busStops && <div className="flex items-center gap-2"><div className="w-3.5 h-3.5 rounded-full bg-blue-600 border border-white" /> Paradas/estações</div>}
                  {layerVisibility.busStops && originalSeedPoint ? (
                    <div className="flex items-center gap-2"><div className="w-3.5 h-3.5 rounded-full bg-red-700 border border-white" /> Seed original</div>
                  ) : null}
                  {layerVisibility.busStops && zoneSeedPoints.length > 0 ? (
                    <div className="flex items-center gap-2"><div className="w-3.5 h-3.5 rounded-full bg-orange-600 border border-white" /> Seeds das zonas</div>
                  ) : null}
                  {layerVisibility.busStops && zoneDownstreamPoints.length > 0 ? (
                    <div className="flex items-center gap-2"><div className="w-3.5 h-3.5 rounded-full bg-violet-600 border border-white" /> Downstream das zonas</div>
                  ) : null}
                  {layerVisibility.busStops && zoneDetailData?.seed_transport_point ? (
                    <div className="flex items-center gap-2"><div className="w-3.5 h-3.5 rounded-full bg-red-600 border border-white" /> Seed (ponto principal)</div>
                  ) : null}
                  {layerVisibility.busStops && zoneDetailData?.downstream_transport_point ? (
                    <div className="flex items-center gap-2"><div className="w-3.5 h-3.5 rounded-full bg-violet-600 border border-white" /> Downstream da zona</div>
                  ) : null}
                  {layerVisibility.zones && zonesCollection.length > 0 && <div className="flex items-center gap-2"><div className="w-3.5 h-3.5 rounded bg-blue-500/30 border border-blue-600/50" /> Zonas</div>}
                </div>
              )}
            </div>

            {/* Loading Overlay - estilo esboço/Gemini */}
            {(isLoading || mapBusyMessage) && (
              <div className="absolute inset-0 bg-white/40 backdrop-blur-[3px] z-50 flex flex-col items-center justify-center pointer-events-none">
                <div className="bg-white/95 px-8 py-6 rounded-2xl shadow-2xl flex flex-col items-center border border-slate-200 text-center max-w-sm pointer-events-auto">
                  <Loader2 className="w-10 h-10 text-[#2563EB] animate-spin mb-4" />
                  <h3 className="font-bold text-slate-800 text-lg mb-2">Processando...</h3>
                  <p className="text-sm text-slate-500 font-medium leading-relaxed">
                    {loadingText || mapBusyMessage || "Aguarde..."}
                  </p>
                </div>
              </div>
            )}

            {mapError ? (
              <div className="pointer-events-none absolute inset-0 z-30 grid place-items-center bg-slate-950/35 p-6">
                <div className="pointer-events-auto max-w-md rounded-panel border border-danger/30 bg-panel p-4 text-sm text-danger shadow-panel">
                  {mapError}
                </div>
              </div>
            ) : null}
          </div>
        </section>

        <aside
          className={`bg-white h-full shadow-2xl z-40 flex flex-col border-l border-slate-200 shrink-0 relative overflow-visible transition-[width] duration-300 ${isPanelMinimized ? "w-0 border-l-0" : "w-[400px]"} max-lg:fixed max-lg:bottom-0 max-lg:left-0 max-lg:right-0 max-lg:z-30 max-lg:w-full max-lg:border-l-0 max-lg:border-t max-lg:h-[48vh]`}
          aria-label="Painel lateral"
        >
          <button
            type="button"
            onClick={() => setIsPanelMinimized((current) => !current)}
            className="absolute -left-5 top-6 z-50 bg-white/95 backdrop-blur-md p-2.5 rounded-full shadow-xl border border-slate-200 text-[#2563EB] hover:bg-slate-50 transition-all flex items-center justify-center"
            title={isPanelMinimized ? "Expandir painel" : "Minimizar painel"}
          >
            {isPanelMinimized ? <ChevronsLeft size={20} /> : <ChevronsRight size={20} />}
          </button>

          <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between gap-2 bg-slate-50">
            <button
              type="button"
              onClick={() => navigateToStep(Math.max(1, activeStep - 1) as 1 | 2 | 3)}
              disabled={activeStep === 1}
              className="text-[#2563EB] text-xs font-bold flex items-center hover:underline disabled:opacity-50"
            >
              <ChevronLeft className="w-4 h-4 mr-1" /> Voltar
            </button>
            <div className="flex items-center gap-1">
              {STEPS.map((step) => (
                <button
                  key={step.id}
                  type="button"
                  onClick={() => navigateToStep(step.id as 1 | 2 | 3)}
                  className={`h-2.5 w-2.5 rounded-full ${activeStep >= step.id ? "bg-[#2563EB]" : "bg-slate-300"}`}
                  title={`${step.title}`}
                />
              ))}
            </div>
            <span className="text-slate-500 text-xs font-semibold">{STEPS[activeStep - 1].title}</span>
          </div>

          {!isPanelMinimized ? (
            <div className="panel-scroll flex-1 overflow-y-auto px-5 pb-6 pt-12">
              {/* ETAPA 1 */}
              <div className={activeStep === 1 ? "block" : "hidden"}>
              <h2 className="text-xl font-bold text-slate-800 mb-6">Ponto de Referência</h2>
              <section className="rounded-xl border border-slate-200 p-4 text-sm">
                <h3 className="font-semibold text-slate-700 mb-3 flex items-center gap-2">
                  <MapPin className="w-4 h-4 text-[#2563EB]" /> Ponto Principal
                </h3>
                {primaryPoint ? (
                  <div className="mt-2 space-y-2">
                    <p>
                      <strong>{primaryPoint.name}</strong>
                    </p>
                    <p className="text-muted">
                      {primaryPoint.lat.toFixed(6)}, {primaryPoint.lon.toFixed(6)}
                    </p>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => setInteractionMode("primary")}
                        className="rounded-lg border border-border px-3 py-1.5 text-xs font-semibold"
                      >
                        Alterar no mapa
                      </button>
                      <button
                        type="button"
                        onClick={removePrimaryPoint}
                        className="rounded-lg border border-danger/40 px-3 py-1.5 text-xs font-semibold text-danger"
                      >
                        Remover
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="mt-2 space-y-2">
                    <p className="text-muted">Clique no mapa em “Definir principal”.</p>
                    <button
                      type="button"
                      onClick={() => {
                        setPrimaryPoint({
                          name: "Ponto principal",
                          lat: Number(viewport.lat.toFixed(6)),
                          lon: Number(viewport.lon.toFixed(6))
                        });
                        setStatusMessage("Ponto principal definido pelo centro atual do mapa.");
                      }}
                      className="rounded-lg border border-border px-3 py-1.5 text-xs font-semibold"
                    >
                      Usar centro atual
                    </button>
                  </div>
                )}
              </section>

              <section className="mt-4 rounded-panel border border-border p-4 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <h2 className="font-semibold">2) Interesses (opcional)</h2>
                  <button
                    type="button"
                    onClick={() => setIsOptionalInterestsExpanded((current) => !current)}
                    className="rounded-lg border border-border px-2 py-1 text-xs font-semibold"
                  >
                    {isOptionalInterestsExpanded ? "Minimizar" : "Adicionar interesse"}
                  </button>
                </div>
                {isOptionalInterestsExpanded ? (
                <div className="mt-2 space-y-2">
                  <label className="block">
                    <span className="mb-1 block text-xs text-muted">Categoria</span>
                    <select
                      value={interestCategory}
                      onChange={(event) => setInterestCategory(event.target.value)}
                      className="w-full rounded-lg border border-border px-2 py-2 text-sm"
                    >
                      {INTEREST_CATEGORIES.map((category) => (
                        <option key={category} value={category}>
                          {category}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="block">
                    <span className="mb-1 block text-xs text-muted">Rótulo (opcional)</span>
                    <input
                      value={interestLabel}
                      onChange={(event) => setInterestLabel(event.target.value)}
                      placeholder="Ex.: Academia XYZ"
                      className="w-full rounded-lg border border-border px-2 py-2 text-sm"
                    />
                  </label>
                  <button
                    type="button"
                    onClick={() => setInteractionMode("interest")}
                    className="rounded-lg border border-border px-3 py-1.5 text-xs font-semibold"
                  >
                    Selecionar no mapa
                  </button>
                  <p className="text-xs text-muted">Mude para “Adicionar interesse” e clique no mapa.</p>
                </div>
                ) : (
                  <p className="mt-2 text-xs text-muted">Minimizado. Clique em “Adicionar interesse” para abrir.</p>
                )}

                {interests.length > 0 ? (
                  <ul className="mt-3 space-y-2">
                    {interests.map((interest) => (
                      <li
                        key={interest.id}
                        className="rounded-lg border border-border px-2 py-2 text-xs text-muted"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <div>
                            <p className="font-semibold text-text">{interest.label}</p>
                            <p>
                              {interest.category} · {interest.lat.toFixed(5)}, {interest.lon.toFixed(5)}
                            </p>
                          </div>
                          <button
                            type="button"
                            onClick={() => removeInterest(interest.id)}
                            className="rounded border border-danger/40 px-2 py-1 font-semibold text-danger"
                          >
                            Remover
                          </button>
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </section>

              <section className="mt-4 rounded-panel border border-border p-4 text-sm">
                <h2 className="font-semibold">3) Tipo de busca</h2>
                <div className="mt-2 inline-flex rounded-lg border border-border p-1">
                  <button
                    type="button"
                    onClick={() => setPropertyMode("rent")}
                    className={`rounded-md px-3 py-1.5 text-xs font-semibold ${
                      propertyMode === "rent" ? "bg-primary text-white" : "text-muted"
                    }`}
                  >
                    Alugar
                  </button>
                  <button
                    type="button"
                    onClick={() => setPropertyMode("buy")}
                    className={`rounded-md px-3 py-1.5 text-xs font-semibold ${
                      propertyMode === "buy" ? "bg-primary text-white" : "text-muted"
                    }`}
                  >
                    Comprar
                  </button>
                </div>
              </section>

              <section className="mt-4 rounded-panel border border-border p-4 text-sm">
                <h2 className="font-semibold">4) Raio da zona (visual)</h2>
                <p className="mt-1 text-xs text-muted">Ajuste o raio dos círculos exibidos no mapa antes de gerar as zonas ({zoneRadiusM} m).</p>
                <div className="mt-3 flex items-center gap-3">
                  <input
                    type="range"
                    min={ZONE_RADIUS_MIN_M}
                    max={ZONE_RADIUS_MAX_M}
                    step={ZONE_RADIUS_STEP_M}
                    value={zoneRadiusM}
                    onChange={(event) => setZoneRadiusM(clampZoneRadius(Number(event.target.value)))}
                    className="w-full"
                  />
                  <input
                    type="number"
                    min={ZONE_RADIUS_MIN_M}
                    max={ZONE_RADIUS_MAX_M}
                    step={ZONE_RADIUS_STEP_M}
                    value={zoneRadiusM}
                    onChange={(event) => setZoneRadiusM(clampZoneRadius(Number(event.target.value) || ZONE_RADIUS_MIN_M))}
                    className="w-24 rounded-lg border border-border px-2 py-1 text-xs"
                  />
                  <span className="text-xs text-muted">m</span>
                </div>
              </section>

              <button
                type="button"
                onClick={handleCreateRun}
                disabled={!primaryPoint || isCreatingRun || isPolling}
                className="mt-4 w-full rounded-xl bg-[#2563EB] px-4 py-3.5 text-sm font-bold text-white shadow-lg disabled:cursor-not-allowed disabled:opacity-50 hover:bg-blue-700"
              >
                Gerar Zonas Candidatas
              </button>
              </div>

              {/* ETAPAS 2-3 */}
              <div className="block">
              <section className="mt-4 rounded-xl border border-slate-200 p-4 text-sm">
                <h2 className="font-semibold">Status</h2>
                <p className="mt-2 text-muted">{statusMessage}</p>
                <p className="mt-1 text-xs text-muted">zonas: {zonesState} · {zonesStateMessage}</p>
                {runId ? <p className="mt-1 text-xs text-muted">run_id: {runId}</p> : null}
                {runStatus ? (
                  <p className="text-xs text-muted">
                    etapa: {runStatus.stage} · estado: {runStatus.state}
                  </p>
                ) : null}
              </section>

              <section className="mt-4 rounded-panel border border-border p-4 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <h2 className="font-semibold">Execução</h2>
                  <span className="text-[11px] text-muted">{executionProgress.elapsedSec}s</span>
                </div>
                <p className="mt-1 text-xs text-muted">{executionProgress.label}</p>
                <div className="mt-2 h-2 w-full rounded bg-slate-100">
                  <div
                    className="h-2 rounded bg-[#2563EB] transition-all duration-300"
                    style={{ width: `${Math.max(4, Math.min(100, executionProgress.percent || 0))}%` }}
                  />
                </div>
                <p className="mt-2 text-[11px] text-muted">Etapa backend: {runStatus?.stage || "—"}</p>
              </section>

              {activeStep === 2 ? (
              <section className="mt-4 rounded-panel border border-border p-4 text-sm">
                <h2 className="font-semibold">Selecionar zona</h2>
                {zonesCollection.length > 0 ? (
                  <div className="mt-2 space-y-2">
                    <p className="text-xs text-muted">Selecione 1 zona para seguir o fluxo.</p>
                    <ul className="max-h-40 space-y-2 overflow-y-auto">
                      {zonesCollection.map((zone, index) => {
                        const uid = zone.properties.zone_uid;
                        const zoneName = (zone.properties.zone_name as string | undefined) || `Zona ${index + 1}`;
                        const score =
                          typeof zone.properties.score === "number"
                            ? zone.properties.score.toFixed(3)
                            : "n/a";
                        const timeAgg =
                          typeof zone.properties.time_agg === "number"
                            ? `${zone.properties.time_agg} min`
                            : "n/a";

                        return (
                          <li key={uid} className="rounded-lg border border-border px-2 py-2">
                            <label className="flex cursor-pointer items-center gap-2">
                              <input
                                type="radio"
                                name="zone-selection"
                                value={uid}
                                checked={selectedZoneUid === uid}
                                onChange={() => setSelectedZoneUid(uid)}
                                className="h-4 w-4 accent-primary"
                              />
                              <span className="text-xs text-text">
                                <strong>{zoneName}</strong> · score {score} · tempo {timeAgg}
                              </span>
                            </label>
                          </li>
                        );
                      })}
                    </ul>

                    <div className="grid grid-cols-1 gap-2">
                      <button
                        type="button"
                        onClick={handleSelectZone}
                        disabled={!selectedZoneUid || isSelectingZone}
                        className="rounded border border-border px-2 py-1.5 text-xs font-semibold disabled:opacity-50"
                      >
                        {isSelectingZone ? "Selecionando..." : "Selecionar zona"}
                      </button>
                    </div>
                  </div>
                ) : (
                  <p className="mt-2 text-xs text-muted">Gere zonas candidatas para habilitar esta etapa.</p>
                )}

                <p className="mt-2 text-xs text-muted">{zoneSelectionMessage}</p>
              </section>
              ) : null}

              {activeStep === 3 ? (
              <section className="mt-4 rounded-panel border border-border p-4 text-sm">
                <h2 className="font-semibold">Detalhamento da zona</h2>
                <button
                  type="button"
                  onClick={handleDetailZone}
                  disabled={!selectedZoneUid || isDetailingZone}
                  className="mt-2 rounded border border-border px-3 py-1.5 text-xs font-semibold disabled:opacity-50"
                >
                  {isDetailingZone ? "Detalhando..." : "Carregar detalhamento"}
                </button>
                <p className="mt-2 text-xs text-muted">{zoneListingMessage}</p>

                {zoneDetailData ? (
                  <div className="mt-2 rounded-lg border border-border/70 bg-bg px-2 py-2 text-[11px] text-muted">
                    <p className="font-semibold text-text mb-1">{zoneDetailData.zone_name}</p>
                    <div className="grid grid-cols-2 gap-2">
                      <div className="rounded border border-border px-2 py-1.5">
                        <strong>Área verde</strong>
                        <p>{(zoneDetailData.green_area_ratio * 100).toFixed(1)}%</p>
                      </div>
                      <div className="rounded border border-border px-2 py-1.5">
                        <strong>Área alagável</strong>
                        <p>{(zoneDetailData.flood_area_ratio * 100).toFixed(1)}%</p>
                      </div>
                      <div className="rounded border border-border px-2 py-1.5">
                        <strong>Pontos ônibus</strong>
                        <p>{zoneDetailData.bus_stop_count}</p>
                      </div>
                      <div className="rounded border border-border px-2 py-1.5">
                        <strong>Pontos trem/metrô</strong>
                        <p>{zoneDetailData.train_station_count}</p>
                      </div>
                    </div>
                    <p className="mt-2">
                      <strong>Linhas ônibus:</strong> {zoneDetailData.bus_lines_count} · <strong>Linhas trem/metrô:</strong> {zoneDetailData.train_lines_count}
                    </p>
                    <p className="mt-1 font-semibold text-text">POIs por categoria</p>
                    <ul className="space-y-0.5">
                      {Object.entries(zoneDetailData.poi_count_by_category).map(([category, count]) => (
                        <li key={category}>{category}: {count}</li>
                      ))}
                    </ul>
                    <p className="mt-1 text-[11px]">POIs exibidos no mapa: {zoneDetailData.poi_points.length}</p>
                    <p className="mt-1 font-semibold text-text">Linhas usadas para gerar zona</p>
                    <ul className="space-y-0.5">
                      {zoneDetailData.lines_used_for_generation.map((line, idx) => (
                        <li key={`${line.route_id}_${idx}`}>{line.mode.toUpperCase()} · {line.route_id || "sem código"} · {line.line_name || "sem nome"}</li>
                      ))}
                    </ul>
                    <p className="mt-1 font-semibold text-text">Referências de transporte</p>
                    <ul className="space-y-0.5">
                      <li>
                        Seed (mais próximo do ponto principal): {zoneDetailData.seed_transport_point?.name || "não encontrado"}
                      </li>
                      <li>
                        Downstream da zona: {zoneDetailData.downstream_transport_point?.name || "não encontrado"}
                      </li>
                    </ul>
                  </div>
                ) : null}
              </section>
              ) : null}

              {activeStep === 3 ? (
              <section className="mt-4 rounded-panel border border-border p-4 text-sm">
                <h2 className="font-semibold">Buscar imóveis</h2>
                <div className="mt-2 space-y-2">
                  <div className="flex flex-wrap gap-2">
                    <label className="flex cursor-pointer items-center gap-1.5 text-xs">
                      <input
                        type="radio"
                        name="street-mode"
                        checked={streetFilterMode === "all"}
                        onChange={() => setStreetFilterMode("all")}
                        className="accent-primary"
                      />
                      Todas as ruas da zona
                    </label>
                    <label className="flex cursor-pointer items-center gap-1.5 text-xs">
                      <input
                        type="radio"
                        name="street-mode"
                        checked={streetFilterMode === "specific"}
                        onChange={() => setStreetFilterMode("specific")}
                        className="accent-primary"
                      />
                      Rua específica
                    </label>
                  </div>
                  {streetFilterMode === "specific" && zoneStreets.length > 0 ? (
                    <label className="block">
                      <span className="mb-1 block text-[11px] text-muted">Selecione a rua</span>
                      <select
                        value={selectedStreet}
                        onChange={(e) => setSelectedStreet(e.target.value)}
                        className="w-full rounded-lg border border-border px-2 py-1.5 text-sm"
                      >
                        {zoneStreets.map((s) => (
                          <option key={s} value={s}>
                            {s}
                          </option>
                        ))}
                      </select>
                    </label>
                  ) : null}
                  <p className="text-[11px] text-muted">A rua selecionada não é destacada no mapa; o filtro é aplicado somente na busca.</p>
                  <div className="grid grid-cols-1 gap-2">
                    <button
                      type="button"
                      onClick={handleZoneListings}
                      disabled={
                        !selectedZoneUid ||
                        !zoneDetailData ||
                        isListingZone ||
                        (streetFilterMode === "specific" && !selectedStreet)
                      }
                      className="rounded border border-border px-2 py-1.5 text-xs font-semibold disabled:opacity-50"
                    >
                      {isListingZone ? "Buscando..." : "Buscar imóveis"}
                    </button>
                  </div>
                </div>
                <p className="mt-2 text-xs text-muted">{zoneListingMessage}</p>
                <p className="mt-1 text-xs text-muted">{finalizeMessage}</p>
              </section>
              ) : null}

              {activeStep === 3 ? (
              <section className="mt-4 rounded-panel border border-border p-4 text-sm">
                <h2 className="font-semibold">Imóveis finais</h2>
                <p className="mt-2 text-xs text-muted">{finalizeMessage}</p>

                {runId ? (
                  <div className="mt-2 flex flex-wrap gap-2 text-xs">
                    <a
                      href={`${API_BASE}/runs/${runId}/final/listings`}
                      target="_blank"
                      rel="noreferrer"
                      className="rounded border border-border px-2 py-1 font-semibold text-primary"
                    >
                      Export GeoJSON
                    </a>
                    <a
                      href={`${API_BASE}/runs/${runId}/final/listings.csv`}
                      target="_blank"
                      rel="noreferrer"
                      className="rounded border border-border px-2 py-1 font-semibold text-primary"
                    >
                      Export CSV
                    </a>
                    <a
                      href={`${API_BASE}/runs/${runId}/final/listings.json`}
                      target="_blank"
                      rel="noreferrer"
                      className="rounded border border-border px-2 py-1 font-semibold text-primary"
                    >
                      Export JSON
                    </a>
                  </div>
                ) : null}

                {finalListings.length > 0 ? (
                  <>
                    <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                      <label className="col-span-2">
                        <span className="mb-1 block text-[11px] text-muted">Ordenar imóveis</span>
                        <select
                          value={listingSortMode}
                          onChange={(event) => setListingSortMode(event.target.value as ListingSortMode)}
                          className="w-full rounded-lg border border-border px-2 py-1.5 text-xs"
                        >
                          <option value="price-asc">Preço (menor → maior)</option>
                          <option value="price-desc">Preço (maior → menor)</option>
                          <option value="size-desc">Tamanho (maior → menor)</option>
                          <option value="size-asc">Tamanho (menor → maior)</option>
                        </select>
                      </label>
                      <label className="col-span-2">
                        <span className="mb-1 block text-[11px] text-muted">Raio para contagem de POIs (m)</span>
                        <input
                          type="number"
                          min={100}
                          step={50}
                          value={poiCountRadiusM}
                          onChange={(event) => setPoiCountRadiusM(Math.max(100, Number(event.target.value) || 100))}
                          className="w-full rounded-lg border border-border px-2 py-1.5 text-xs"
                        />
                      </label>
                    </div>

                    {selectedListingsForComparison.length > 1 ? (
                      <div className="mt-3 rounded-lg border border-border/70 bg-bg px-3 py-3 text-xs">
                        <h3 className="font-semibold text-text">Comparação ({selectedListingsForComparison.length} imóveis)</h3>
                        <p className="mt-1 text-muted">Comparando preço, tamanho, distância de transporte e POIs em até {poiCountRadiusM} m.</p>
                        <div className="mt-2 overflow-x-auto">
                          <table className="min-w-[760px] w-full border-collapse text-[11px]">
                            <thead>
                              <tr>
                                <th className="border border-border bg-white px-2 py-1.5 text-left font-semibold text-text">Métrica</th>
                                {selectedListingsForComparison.map((item, idx) => (
                                  <th
                                    key={`cmp_head_${item.analytics.listingKey}`}
                                    className="border border-border bg-white px-2 py-1.5 text-left font-semibold text-text"
                                  >
                                    Imóvel {idx + 1}
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              <tr>
                                <td className="border border-border px-2 py-1 text-muted">Preço</td>
                                {selectedListingsForComparison.map((item) => (
                                  <td
                                    key={`cmp_price_${item.analytics.listingKey}`}
                                    className={`border border-border px-2 py-1 ${getComparisonCellClass(
                                      item.analytics.priceValue,
                                      comparisonExtremes.price.min,
                                      comparisonExtremes.price.max,
                                      "lower-better"
                                    )}`}
                                  >
                                    {item.info.priceLabel}
                                  </td>
                                ))}
                              </tr>
                              <tr>
                                <td className="border border-border px-2 py-1 text-muted">Plataforma</td>
                                {selectedListingsForComparison.map((item) => (
                                  <td key={`cmp_platform_${item.analytics.listingKey}`} className="border border-border px-2 py-1 text-text">
                                    {item.analytics.platform}
                                  </td>
                                ))}
                              </tr>
                              <tr>
                                <td className="border border-border px-2 py-1 text-muted">Endereço</td>
                                {selectedListingsForComparison.map((item) => (
                                  <td key={`cmp_address_${item.analytics.listingKey}`} className="border border-border px-2 py-1 text-text">
                                    {item.info.address}
                                  </td>
                                ))}
                              </tr>
                              <tr>
                                <td className="border border-border px-2 py-1 text-muted">Tamanho</td>
                                {selectedListingsForComparison.map((item) => (
                                  <td
                                    key={`cmp_size_${item.analytics.listingKey}`}
                                    className={`border border-border px-2 py-1 ${getComparisonCellClass(
                                      item.analytics.sizeM2,
                                      comparisonExtremes.size.min,
                                      comparisonExtremes.size.max,
                                      "higher-better"
                                    )}`}
                                  >
                                    {item.analytics.sizeM2 ? `${item.analytics.sizeM2.toFixed(0)} m²` : "n/d"}
                                  </td>
                                ))}
                              </tr>
                              <tr>
                                <td className="border border-border px-2 py-1 text-muted">Quartos</td>
                                {selectedListingsForComparison.map((item) => (
                                  <td key={`cmp_beds_${item.analytics.listingKey}`} className="border border-border px-2 py-1 text-text">
                                    {item.analytics.bedrooms ? `${item.analytics.bedrooms}` : "n/d"}
                                  </td>
                                ))}
                              </tr>
                              <tr>
                                <td className="border border-border px-2 py-1 text-muted">Transporte mais próximo</td>
                                {selectedListingsForComparison.map((item) => (
                                  <td
                                    key={`cmp_transport_${item.analytics.listingKey}`}
                                    className={`border border-border px-2 py-1 ${getComparisonCellClass(
                                      item.analytics.distanceTransportM,
                                      comparisonExtremes.transport.min,
                                      comparisonExtremes.transport.max,
                                      "lower-better"
                                    )}`}
                                  >
                                    {formatMeters(item.analytics.distanceTransportM)}
                                  </td>
                                ))}
                              </tr>
                              <tr>
                                <td className="border border-border px-2 py-1 text-muted">POIs até {poiCountRadiusM} m</td>
                                {selectedListingsForComparison.map((item) => (
                                  <td
                                    key={`cmp_poi_count_${item.analytics.listingKey}`}
                                    className={`border border-border px-2 py-1 ${getComparisonCellClass(
                                      item.analytics.poiCountWithinRadius,
                                      comparisonExtremes.poiCount.min,
                                      comparisonExtremes.poiCount.max,
                                      "higher-better"
                                    )}`}
                                  >
                                    {item.analytics.poiCountWithinRadius}
                                  </td>
                                ))}
                              </tr>
                            </tbody>
                          </table>
                        </div>
                      </div>
                    ) : null}

                    <ul className="mt-3 space-y-2">
                    {sortedListings.map(({ feature, index, info, analytics }) => {
                      const isSelected = selectedListingKeys.includes(analytics.listingKey);
                      return (
                        <li
                          key={analytics.listingKey}
                          className={`rounded-lg border px-2 py-2 text-xs cursor-pointer hover:border-primary ${isSelected ? "border-primary" : "border-border"}`}
                          onClick={() => handleListingCardClick(feature, index)}
                        >
                          <p className="font-semibold text-text">{info.priceLabel}</p>
                          <p className="text-muted">Plataforma: {analytics.platform}</p>
                          <p className="text-muted">{info.address}</p>
                          <p className="text-muted">Tamanho: {analytics.sizeM2 ? `${analytics.sizeM2.toFixed(0)} m²` : "n/d"} · Quartos: {analytics.bedrooms ? `${analytics.bedrooms}` : "n/d"}</p>
                          {info.url ? (
                            <a
                              href={info.url}
                              target="_blank"
                              rel="noreferrer"
                              className="text-primary underline"
                            >
                              Abrir anúncio
                            </a>
                          ) : null}
                          {isSelected ? (
                            <div className="mt-2 rounded border border-border/70 bg-bg px-2 py-2 text-[11px] text-muted">
                              <p className="font-semibold text-text">Distâncias para POIs de maior interesse</p>
                              <ul className="mt-1 space-y-0.5">
                                {analytics.nearestPoiByCategory.length > 0 ? (
                                  analytics.nearestPoiByCategory.map((item) => (
                                    <li key={`${analytics.listingKey}_${item.category}`}>
                                      {item.category}: {formatMeters(item.distanceM)}
                                    </li>
                                  ))
                                ) : (
                                  <li>Sem dados de POI para comparação.</li>
                                )}
                              </ul>
                              <p className="mt-1">POIs até {poiCountRadiusM} m: {analytics.poiCountWithinRadius}</p>
                              <p className="mt-1">Transporte mais próximo: {formatMeters(analytics.distanceTransportM)}</p>
                            </div>
                          ) : null}
                        </li>
                      );
                    })}
                    </ul>
                  </>
                ) : null}

                {listingsWithoutCoords.length > 0 ? (
                  <div className="mt-4 rounded-lg border border-border/70 bg-bg px-3 py-3 text-xs">
                    <h3 className="font-semibold text-text">Sem localização no mapa ({listingsWithoutCoords.length})</h3>
                    <ul className="mt-2 space-y-2">
                      {listingsWithoutCoords.map((item, index) => {
                        const info = resolveRawListingText(item);
                        return (
                          <li key={`without_coords_${index}`} className="rounded border border-border px-2 py-2">
                            <p className="font-semibold text-text">{info.priceLabel}</p>
                            <p className="text-muted">
                              Plataforma: {String(item.source || item.platform || item.site || "PLATAFORMA N/D").toUpperCase()}
                            </p>
                            <p className="text-muted">{info.address}</p>
                            <p className="text-muted">
                              Tamanho: {parseFiniteNumber(item.area_m2 ?? item.area ?? item.private_area ?? item.usable_area)?.toFixed(0) || "n/d"} m² · Quartos: {parseFiniteNumber(item.beds ?? item.bedrooms ?? item.quartos)?.toFixed(0) || "n/d"}
                            </p>
                            {info.url ? (
                              <a
                                href={info.url}
                                target="_blank"
                                rel="noreferrer"
                                className="text-primary underline"
                              >
                                Abrir anúncio
                              </a>
                            ) : null}
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                ) : null}
              </section>
              ) : null}
              </div>
            </div>
          ) : null}
        </aside>
      </div>

      {isHelpOpen ? (
        <div className="fixed inset-0 z-40 grid place-items-center bg-slate-900/45 p-4">
          <div className="w-full max-w-lg rounded-panel border border-border bg-panel p-5 shadow-panel">
            <h2 className="text-lg font-semibold">Ajuda</h2>
            <p className="mt-2 text-sm text-muted">
              Selecione um ponto principal no mapa, ajuste o modo Alugar/Comprar e use “Gerar Zonas
              Candidatas” para iniciar o run no backend.
            </p>
            <p className="mt-3 text-sm text-muted">
              Interesses são opcionais e não entram como seed de geração de zonas.
              O painel mostra o status de execução e as ações do fluxo em 3 etapas.
            </p>
            <div className="mt-4 text-right">
              <button
                type="button"
                onClick={() => setIsHelpOpen(false)}
                className="rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white"
              >
                Fechar
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </main>
  );
}