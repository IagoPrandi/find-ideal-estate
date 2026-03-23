import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft } from "lucide-react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import {
  API_BASE,
  apiActionHint,
  createJourney,
  createRun,
  createZoneGenerationJob,
  finalizeRun,
  getFinalListings,
  getFinalListingsJson,
  getJourneyTransportPoints,
  getPriceRollups,
  getRunStatus,
  getTransportLayers,
  getTransportStops,
  getZoneDetail,
  getZoneStreets,
  getZones,
  scrapeZoneListings,
  selectZones
} from "../../api/client";
import type {
  PriceRollupRead,
  RunCreateResponse,
  RunStatusResponse,
  TransportPointRead,
  ZoneDetailResponse,
  ZonesCollection
} from "../../api/schemas";
import { FloatingBrand, HelpModal, ProgressTracker } from "../../components/layout";
import {
  AddressSearchBar,
  MapErrorOverlay,
  MapLoadingOverlay,
  MapToolbarRight,
  type InteractionMode
} from "../../components/map";
import { type MapLayerKey } from "../../domain/mapLayers";
import { clampZoneRadius, INTEREST_CATEGORIES, type ZoneInfoKey } from "../../domain/wizardConstants";
import { formatCurrencyBr, parseFiniteNumber } from "../../lib/listingFormat";
import { buildCircleCoordinates, haversineMeters } from "../../lib/geo";
import type {
  InterestPoint,
  ListingSortMode,
  PropertyMode,
  ReferencePoint,
  SearchSuggestion,
  SearchSuggestionType
} from "../steps/types";
import { computeComparisonExtremes } from "../steps/step3Helpers";
import { computeMonthlyVariationFromRollups, computeTopPoiCategories } from "../steps/step3DerivedMetrics";
import { sortDecoratedListings } from "../steps/listingSort";
import { SUGGESTION_TYPE_LABEL } from "../steps/suggestionLabels";
import type { Step3WizardSubStep } from "../steps/step3Types";
import {
  Step1ConfigurePanel,
  Step2TransportPanel,
  Step3GenerationHint,
  Step3ZonePanel,
  WizardSharedStatus
} from "../steps";
import {
  computeListingAnalytics,
  getListingKey,
  resolveListingFeatureText,
  type ListingFeature
} from "./listingAnalytics";
import { createInitialExecutionStages, type ExecutionStageKey } from "./wizardExecution";
import { type WizardStepId, WIZARD_STEPS as STEPS } from "./wizardSteps";

type LayerKey = MapLayerKey;

type ZoneFeature = ZonesCollection["features"][number];
type TransportAnchorPoint = {
  id: string;
  name: string;
  kind: string;
  lon: number;
  lat: number;
  zoneUid?: string;
};

const MAPTILER_KEY =
  import.meta.env.VITE_MAPTILER_API_KEY || (import.meta.env.MODE === "test" ? "test-maptiler-key" : "");

const mapTilerStyleUrl = (key: string) =>
  `https://api.maptiler.com/maps/bright-v2/style.json?key=${encodeURIComponent(key)}`;

export function FindIdealApp() {
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const primaryMarkerRef = useRef<maplibregl.Marker | null>(null);
  const interestMarkerRefs = useRef<Map<string, maplibregl.Marker>>(new Map());
  const progressTrackerMeasureRef = useRef<HTMLDivElement | null>(null);
  const interactionModeRef = useRef<InteractionMode>("primary");
  const interestLabelRef = useRef("");
  const interestCategoryRef = useRef<string>(INTEREST_CATEGORIES[0]);
  const runIdRef = useRef("");

  const [searchValue, setSearchValue] = useState("");
  const [addressSearchLeftPx, setAddressSearchLeftPx] = useState<number | null>(null);
  const [isPanelMinimized, setIsPanelMinimized] = useState(false);
  const [isLayerMenuOpen, setIsLayerMenuOpen] = useState(false);
  const [isHelpOpen, setIsHelpOpen] = useState(false);
  const closeHelpModal = useCallback(() => setIsHelpOpen(false), []);
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
    pois: false,
    transportCandidates: true,
    transportRadius: true
  });

  const [activeStep, setActiveStep] = useState<WizardStepId>(1);
  const [interactionMode, setInteractionMode] = useState<InteractionMode>("primary");
  const [propertyMode, setPropertyMode] = useState<PropertyMode>("rent");
  const [primaryPoint, setPrimaryPoint] = useState<ReferencePoint | null>(null);
  const [interestLabel, setInterestLabel] = useState("");
  const [interestCategory, setInterestCategory] = useState<string>(INTEREST_CATEGORIES[0]);
  const [interests, setInterests] = useState<InterestPoint[]>([]);

  const [runId, setRunId] = useState("");
  const [journeyId, setJourneyId] = useState("");
  const [transportPoints, setTransportPoints] = useState<TransportPointRead[]>([]);
  const [transportPointsLoading, setTransportPointsLoading] = useState(false);
  const [transportPointsMessage, setTransportPointsMessage] = useState("Gere zonas candidatas para carregar os pontos de transporte.");
  const [hoveredTransportPointId, setHoveredTransportPointId] = useState("");
  const [transportHoverPulseOn, setTransportHoverPulseOn] = useState(true);
  const [selectedTransportPointId, setSelectedTransportPointId] = useState("");
  const [isQueueingZoneGeneration, setIsQueueingZoneGeneration] = useState(false);
  const [zoneGenerationJobId, setZoneGenerationJobId] = useState("");
  const [transportSearchRadiusM, setTransportSearchRadiusM] = useState(300);
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
  const [streetFilterMode, setStreetFilterMode] = useState<"all" | "specific">("specific");
  const [selectedStreet, setSelectedStreet] = useState("");
  const [selectedStreetType, setSelectedStreetType] = useState<SearchSuggestionType | null>(null);
  const [streetQuery, setStreetQuery] = useState("");
  const [zoneRadiusM, setZoneRadiusM] = useState(900);
  const [maxTravelTimeMin, setMaxTravelTimeMin] = useState(25);
  const [seedBusSearchMaxDistM, setSeedBusSearchMaxDistM] = useState(250);
  const [seedRailSearchMaxDistM, setSeedRailSearchMaxDistM] = useState(1200);
  const [zoneInfoSelection, setZoneInfoSelection] = useState<Record<ZoneInfoKey, boolean>>({
    pois: true,
    transport: true,
    green: true,
    flood: true,
    publicSafety: true
  });
  const [zoneStreets, setZoneStreets] = useState<string[]>([]);
  const [, setStopsLoading] = useState(false);
  const [loadingText, setLoadingText] = useState("");
  const [originalSeedPoint, setOriginalSeedPoint] = useState<TransportAnchorPoint | null>(null);
  const [zoneSeedPoints, setZoneSeedPoints] = useState<TransportAnchorPoint[]>([]);
  const [zoneDownstreamPoints, setZoneDownstreamPoints] = useState<TransportAnchorPoint[]>([]);
  const [finalListings, setFinalListings] = useState<ListingFeature[]>([]);
  const [listingsWithoutCoords, setListingsWithoutCoords] = useState<Array<Record<string, unknown>>>([]);
  const [freshnessBadgeText, setFreshnessBadgeText] = useState("Dados ainda não carregados.");
  const [listingDiffMessage, setListingDiffMessage] = useState("");
  const [newlyAddedListingKeys, setNewlyAddedListingKeys] = useState<string[]>([]);
  const [focusedListingKey, setFocusedListingKey] = useState<string>("");
  const [selectedListingKeys, setSelectedListingKeys] = useState<string[]>([]);
  const [listingSortMode, setListingSortMode] = useState<ListingSortMode>("price-asc");
  const [poiCountRadiusM, setPoiCountRadiusM] = useState(800);
  const [finalizeMessage, setFinalizeMessage] = useState("Finalize o run para carregar os imóveis.");
  const [activePanelTab, setActivePanelTab] = useState<"listings" | "dashboard">("listings");
  const [priceRollups, setPriceRollups] = useState<PriceRollupRead[]>([]);
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
    const update = () => {
      const el = progressTrackerMeasureRef.current;
      if (!el) return;

      const rect = el.getBoundingClientRect();
      // Posiciona o search imediatamente à direita do ProgressTracker.
      const gapPx = 12;
      const desiredLeft = rect.right + gapPx;
      // Mantém dentro da viewport para evitar corte extremo (w-80 ~ 320px no componente).
      const marginPx = 16;
      const maxLeft = window.innerWidth - marginPx - 320;
      setAddressSearchLeftPx(Math.max(marginPx, Math.min(desiredLeft, maxLeft)));
    };

    update();

    const ResizeObserverCtor = (window as unknown as { ResizeObserver?: typeof ResizeObserver }).ResizeObserver;
    if (typeof ResizeObserverCtor === "function" && progressTrackerMeasureRef.current) {
      const ro = new ResizeObserverCtor(() => update());
      ro.observe(progressTrackerMeasureRef.current);
      window.addEventListener("resize", update);
      window.addEventListener("scroll", update, true);
      return () => {
        ro.disconnect();
        window.removeEventListener("resize", update);
        window.removeEventListener("scroll", update, true);
      };
    }

    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [isPanelMinimized]);

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
    if (!mapContainerRef.current) {
      return;
    }

    if (!MAPTILER_KEY) {
      setMapError("Defina VITE_MAPTILER_API_KEY no .env do frontend para renderizar o mapa (MapLibre + MapTiler).");
      setZonesState("error-fatal");
      setZonesStateMessage("Configuração obrigatória ausente: VITE_MAPTILER_API_KEY.");
      return;
    }

    const interestMarkers = interestMarkerRefs.current;
    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: mapTilerStyleUrl(MAPTILER_KEY),
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
      map.addSource("transport-candidates-source", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] }
      });
      map.addSource("transport-radius-source", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] }
      });

      map.addLayer({
        id: "bus-layer",
        type: "line",
        source: "transport-demo",
        filter: ["==", ["get", "mode"], "bus"],
        paint: { "line-color": "#9775fa", "line-width": 4, "line-dasharray": [1.5, 1.5] }
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
          "circle-color": ["match", ["get", "kind"], "station", "#0f766e", "#845ef7"],
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
          "circle-color": "#7048e8",
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
      map.addLayer({
        id: "transport-radius-fill-layer",
        type: "fill",
        source: "transport-radius-source",
        paint: {
          "fill-color": "#0ea5e9",
          "fill-opacity": 0.1
        }
      });
      map.addLayer({
        id: "transport-radius-outline-layer",
        type: "line",
        source: "transport-radius-source",
        paint: {
          "line-color": "#0284c7",
          "line-width": 2,
          "line-dasharray": [1.4, 1.4]
        }
      });
      map.addLayer({
        id: "transport-candidates-layer",
        type: "circle",
        source: "transport-candidates-source",
        paint: {
          "circle-radius": ["case", ["==", ["get", "isHovered"], 1], 9, ["==", ["get", "isSelected"], 1], 8, 6],
          "circle-color": ["case", ["==", ["get", "isSelected"], 1], "#845ef7", ["==", ["get", "isHovered"], 1], "#f97316", "#ea580c"],
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 2,
          "circle-opacity": 0.95
        }
      });

      map.on("click", "listings-layer", (event) => {
        const feature = event.features?.[0] as maplibregl.MapGeoJSONFeature | undefined;
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
        new maplibregl.Popup({ offset: 12 })
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
        const feature = event.features?.[0] as maplibregl.MapGeoJSONFeature | undefined;
        if (!feature || feature.geometry.type !== "Point") {
          return;
        }
        const coordinates = feature.geometry.coordinates as [number, number];
        const props = feature.properties || {};
        const name = String(props.name || "POI");
        const category = String(props.category || "outros");
        const address = String(props.address || "");
        const description = address ? `${category}<br/>${address}` : category;
        new maplibregl.Popup({ offset: 10 })
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
          "fill-color": "#845ef7",
          "fill-opacity": 0.22,
          "fill-outline-color": "#845ef7"
        }
      });
      map.addLayer({
        id: "zones-outline-layer",
        type: "line",
        source: "zones-source",
        paint: {
          "line-color": "#845ef7",
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
            setActiveStep(4);
            void (async () => {
              setIsSelectingZone(true);
              setIsDetailingZone(true);
              try {
                await selectZones(currentRunId, [uid]);
                const detail = await getZoneDetail(currentRunId, uid);
                setZoneDetailData(detail);
                setLayerVisibility((current) => ({
                  ...current,
                  pois: Boolean(detail.has_poi_data),
                  busStops: Boolean(detail.has_transport_data)
                }));
                setZoneListingMessage("Detalhamento concluído. Escolha como buscar imóveis.");
                setStatusMessage(`Detalhamento finalizado para ${uid}.`);
                setActiveStep(5);
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
    map.setLayoutProperty(
      "transport-candidates-layer",
      "visibility",
      visibility(layerVisibility.transportCandidates && activeStep === 2)
    );
    map.setLayoutProperty(
      "transport-radius-fill-layer",
      "visibility",
      visibility(layerVisibility.transportRadius && activeStep === 2)
    );
    map.setLayoutProperty(
      "transport-radius-outline-layer",
      "visibility",
      visibility(layerVisibility.transportRadius && activeStep === 2)
    );
  }, [
    activeStep,
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
    const source = map.getSource("original-seed-source") as maplibregl.GeoJSONSource | undefined;
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
    const seedSource = map.getSource("zones-seed-source") as maplibregl.GeoJSONSource | undefined;
    const downstreamSource = map.getSource("zones-downstream-source") as maplibregl.GeoJSONSource | undefined;
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

    const busStopSource = map.getSource("bus-stop-demo") as maplibregl.GeoJSONSource | undefined;
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

    const zonesSource = map.getSource("zones-source") as maplibregl.GeoJSONSource | undefined;
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

    const centroidSource = map.getSource("zone-centroid-source") as maplibregl.GeoJSONSource | undefined;
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
    const source = map.getSource("poi-zone-source") as maplibregl.GeoJSONSource | undefined;
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
    const seedSource = map.getSource("reference-transport-source") as maplibregl.GeoJSONSource | undefined;
    const downstreamSource = map.getSource("downstream-transport-source") as maplibregl.GeoJSONSource | undefined;
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
    const source = map.getSource("listings-source") as maplibregl.GeoJSONSource | undefined;
    if (!source) {
      return;
    }
    const features = finalListings
      .map((feature, index) => {
        if (feature.geometry.type !== "Point") {
          return null;
        }
        const listingKey = getListingKey(feature, index);
        const info = resolveListingFeatureText(feature);
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
    if (activeStep !== 2 || !hoveredTransportPointId) {
      setTransportHoverPulseOn(true);
      return;
    }
    const timer = window.setInterval(() => {
      setTransportHoverPulseOn((current) => !current);
    }, 280);
    return () => {
      window.clearInterval(timer);
    };
  }, [activeStep, hoveredTransportPointId]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }

    const source = map.getSource("transport-candidates-source") as maplibregl.GeoJSONSource | undefined;
    if (!source) {
      return;
    }

    if (activeStep !== 2 || transportPoints.length === 0) {
      source.setData({ type: "FeatureCollection", features: [] });
      return;
    }

    source.setData({
      type: "FeatureCollection",
      features: transportPoints
        .filter((point) => Number.isFinite(point.lon) && Number.isFinite(point.lat))
        .map((point) => ({
          type: "Feature" as const,
          geometry: {
            type: "Point" as const,
            coordinates: [point.lon, point.lat] as [number, number]
          },
          properties: {
            id: point.id,
            name: point.name || "Ponto sem nome",
            route_count: point.route_count,
            walk_distance_m: point.walk_distance_m,
            isSelected: point.id === selectedTransportPointId ? 1 : 0,
            isHovered: point.id === hoveredTransportPointId && transportHoverPulseOn ? 1 : 0
          }
        })) as unknown as any[]
    });
  }, [
    activeStep,
    hoveredTransportPointId,
    isMapReady,
    selectedTransportPointId,
    transportHoverPulseOn,
    transportPoints
  ]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }

    const source = map.getSource("transport-radius-source") as maplibregl.GeoJSONSource | undefined;
    if (!source) {
      return;
    }

    if (!primaryPoint || activeStep !== 2) {
      source.setData({ type: "FeatureCollection", features: [] });
      return;
    }

    source.setData({
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          geometry: {
            type: "Polygon",
            coordinates: buildCircleCoordinates(primaryPoint.lon, primaryPoint.lat, transportSearchRadiusM)
          },
          properties: {
            radius_m: transportSearchRadiusM
          }
        }
      ]
    });
  }, [activeStep, isMapReady, primaryPoint, transportSearchRadiusM]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }

    primaryMarkerRef.current?.remove();
    if (!primaryPoint) {
      return;
    }

    primaryMarkerRef.current = new maplibregl.Marker({ color: "#845ef7" })
      .setLngLat([primaryPoint.lon, primaryPoint.lat])
      .setPopup(
        new maplibregl.Popup({ offset: 12 }).setHTML(
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

      const marker = new maplibregl.Marker({ element: markerElement })
        .setLngLat([interest.lon, interest.lat])
        .setPopup(
          new maplibregl.Popup({ offset: 10 }).setHTML(
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

    const routeSource = map.getSource("transport-demo") as maplibregl.GeoJSONSource | undefined;
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

  useEffect(() => {
    if (activeStep !== 2 || !primaryPoint || !runId) {
      return;
    }

    let cancelled = false;

    const loadTransportPoints = async () => {
      setTransportPointsLoading(true);
      setTransportPointsMessage("Carregando pontos de transporte...");
      try {
        let journeyRef = journeyId;
        if (!journeyRef) {
          const createdJourney = await createJourney({
            input_snapshot: {
              reference_point: {
                lat: primaryPoint.lat,
                lon: primaryPoint.lon
              },
              transport_search_radius_m: seedBusSearchMaxDistM,
              run_id: runId
            }
          });
          if (cancelled) {
            return;
          }
          journeyRef = createdJourney.id;
          setJourneyId(createdJourney.id);
          setTransportSearchRadiusM(
            Math.max(100, Number((createdJourney.input_snapshot as Record<string, unknown> | undefined)?.transport_search_radius_m) || seedBusSearchMaxDistM)
          );
        }

        const points = await getJourneyTransportPoints(journeyRef);
        if (cancelled) {
          return;
        }
        setTransportPoints(points);
        if (points.length > 0) {
          setTransportPointsMessage(`${points.length} ponto(s) de transporte encontrado(s).`);
          if (!selectedTransportPointId) {
            setSelectedTransportPointId(points[0].id);
          }
        } else {
          setTransportPointsMessage("Nenhum ponto retornado para esta jornada. Ajuste o ponto principal e tente novamente.");
        }
      } catch (error) {
        if (cancelled) {
          return;
        }
        setTransportPoints([]);
        setTransportPointsMessage(apiActionHint(error));
      } finally {
        if (!cancelled) {
          setTransportPointsLoading(false);
        }
      }
    };

    void loadTransportPoints();

    return () => {
      cancelled = true;
    };
  }, [activeStep, journeyId, primaryPoint, runId, seedBusSearchMaxDistM]);

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
    if (!map || !searchValue.trim() || !MAPTILER_KEY) {
      return;
    }

    try {
      const encodedQuery = encodeURIComponent(searchValue.trim());
      const url = `https://api.maptiler.com/geocoding/${encodedQuery}.json?key=${encodeURIComponent(MAPTILER_KEY)}&limit=1`;
      const response = await fetch(url);
      const data = (await response.json()) as {
        features?: Array<{
          geometry?: { type?: string; coordinates?: [number, number] };
        }>;
      };
      const coords = data.features?.[0]?.geometry?.coordinates;
      if (!coords || coords.length < 2) {
        setStatusMessage("Nenhum resultado encontrado para esta busca. Tente outro endereço/bairro.");
        return;
      }

      const center: [number, number] = [coords[0], coords[1]];
      map.flyTo({ center, zoom: 13, duration: 900 });
    } catch {
      setStatusMessage("Falha na busca. Verifique internet/chave MapTiler e tente novamente.");
    }
  };

  const handleCreateRun = async () => {
    if (!primaryPoint || isCreatingRun || isPolling) {
      return;
    }

    // O botão só é exibido na etapa 1; evita POST /runs espúrio se o handler for acionado fora desse passo.
    if (activeStep !== 1) {
      return;
    }

    setJourneyId("");
    setTransportPoints([]);
    setHoveredTransportPointId("");
    setSelectedTransportPointId("");
    setZoneGenerationJobId("");
    setTransportPointsMessage("Gere zonas candidatas para carregar os pontos de transporte.");
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
          public_safety_enabled: zoneInfoSelection.publicSafety,
          public_safety_fail_on_error: false,
          public_safety_radius_km: 1.0,
          public_safety_year: 2025,
          zone_detail_include_pois: zoneInfoSelection.pois,
          zone_detail_include_transport: zoneInfoSelection.transport,
          zone_detail_include_green: zoneInfoSelection.green,
          zone_detail_include_flood: zoneInfoSelection.flood,
          zone_detail_include_public_safety: zoneInfoSelection.publicSafety,
          zone_dedupe_m: 50,
          zone_radius_m: zoneRadiusM,
          t_bus: maxTravelTimeMin,
          t_rail: maxTravelTimeMin,
          seed_bus_max_dist_m: seedBusSearchMaxDistM,
          seed_rail_max_dist_m: seedRailSearchMaxDistM,
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
    setJourneyId("");
    setTransportPoints([]);
    setHoveredTransportPointId("");
    setSelectedTransportPointId("");
    setZoneGenerationJobId("");
    setTransportPointsMessage("Gere zonas candidatas para carregar os pontos de transporte.");
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
      setSelectedStreetType(null);
      setStreetQuery("");
      setStreetFilterMode("specific");
      setZoneListingMessage("Aguardando seleção e detalhamento da zona.");
    }
    if (step <= 3) {
      setFinalListings([]);
      setListingsWithoutCoords([]);
      setFreshnessBadgeText("Dados ainda não carregados.");
      setListingDiffMessage("");
      setNewlyAddedListingKeys([]);
      setFocusedListingKey("");
      setFinalizeMessage("Finalize o run para carregar os imóveis.");
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

  const streetSuggestions = useMemo<SearchSuggestion[]>(() => {
    const query = streetQuery.trim().toLocaleLowerCase("pt-BR");
    if (!zoneDetailData || query.length === 0) {
      return [];
    }

    const suggestions: SearchSuggestion[] = [];
    const seen = new Set<string>();
    const pushSuggestion = (label: string, type: SearchSuggestionType) => {
      const normalized = label.trim();
      if (!normalized) return;
      const key = `${type}:${normalized.toLocaleLowerCase("pt-BR")}`;
      if (seen.has(key)) return;
      seen.add(key);
      suggestions.push({ label: normalized, normalized: normalized.toLocaleLowerCase("pt-BR"), type });
    };

    pushSuggestion(zoneDetailData.zone_name, "neighborhood");
    zoneStreets.forEach((street) => pushSuggestion(street, "street"));
    (zoneDetailData.poi_points || []).forEach((poi) => {
      const poiName = String((poi as Record<string, unknown>).name || "").trim();
      if (poiName) {
        pushSuggestion(poiName, "reference");
      }
    });

    const rank: Record<SearchSuggestionType, number> = {
      neighborhood: 0,
      street: 1,
      reference: 2
    };

    return suggestions
      .filter((item) => item.label.toLocaleLowerCase("pt-BR").includes(query))
      .sort((a, b) => {
        const byType = rank[a.type] - rank[b.type];
        if (byType !== 0) return byType;
        return a.label.localeCompare(b.label, "pt-BR");
      })
      .slice(0, 12);
  }, [streetQuery, zoneDetailData, zoneStreets]);

  useEffect(() => {
    setActivePanelTab("listings");
    setPriceRollups([]);
  }, [selectedZoneUid]);

  useEffect(() => {
    const rollupScopeId = journeyId || runId;
    if (!rollupScopeId || !selectedZoneUid || !zoneDetailData) {
      return;
    }

    let cancelled = false;
    getPriceRollups(
      rollupScopeId,
      selectedZoneUid,
      propertyMode === "buy" ? "sale" : "rent",
      30
    )
      .then((rows) => {
        if (!cancelled) {
          setPriceRollups(rows);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setPriceRollups([]);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [journeyId, propertyMode, runId, selectedZoneUid, zoneDetailData]);

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
      setLayerVisibility((current) => ({
        ...current,
        pois: Boolean(detail.has_poi_data),
        busStops: Boolean(detail.has_transport_data)
      }));
      setZoneListingMessage("Detalhamento concluído. Escolha como buscar imóveis.");
      setStatusMessage(`Detalhamento finalizado para ${selectedZoneUid}.`);
      setActiveStep(5);
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

    if (!selectedStreet) {
      setZoneListingMessage("Selecione um endereço no autocomplete para habilitar a busca.");
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

      const previousKeys = new Set(finalListings.map((item, idx) => getListingKey(item, idx)));
      const nextKeys = new Set((finalGeo.features || []).map((item, idx) => getListingKey(item, idx)));
      const addedKeys: string[] = [];
      const removedKeys: string[] = [];
      nextKeys.forEach((key) => {
        if (!previousKeys.has(key)) {
          addedKeys.push(key);
        }
      });
      previousKeys.forEach((key) => {
        if (!nextKeys.has(key)) {
          removedKeys.push(key);
        }
      });

      const observedAtCandidates = (finalGeo.features || [])
        .map((feature) => {
          const props = feature.properties || {};
          return String(props.observed_at || props.last_seen_at || props.updated_at || "");
        })
        .filter(Boolean)
        .map((raw) => Date.parse(raw))
        .filter((ts) => Number.isFinite(ts));
      const freshestTimestamp = observedAtCandidates.length > 0 ? Math.max(...observedAtCandidates) : Number.NaN;

      setFinalListings(finalGeo.features || []);
      if (Number.isFinite(freshestTimestamp)) {
        const elapsedHours = Math.max(0, Math.round((Date.now() - freshestTimestamp) / 3600000));
        setFreshnessBadgeText(`Dados de ${elapsedHours}h atrás`);
      } else {
        setFreshnessBadgeText("Dados recém-atualizados");
      }
      if (addedKeys.length > 0 || removedKeys.length > 0) {
        setListingDiffMessage(`Revalidação concluída: +${addedKeys.length} novos / -${removedKeys.length} removidos.`);
      } else {
        setListingDiffMessage("Revalidação concluída sem mudanças nos cards.");
      }
      setNewlyAddedListingKeys(addedKeys);
      window.setTimeout(() => setNewlyAddedListingKeys([]), 3500);

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
      setActiveStep(6);
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

  const navigateToStep = (targetStep: WizardStepId) => {
    if (targetStep === 1 && activeStep > 1) {
      removePrimaryPoint();
      return;
    }

    if (targetStep < activeStep) {
      if (targetStep === 2) {
        resetFromStep(3);
      }
      if (targetStep <= 4 && activeStep >= 5) {
        setStreetQuery("");
        setSelectedStreet("");
        setSelectedStreetType(null);
        setStreetFilterMode("specific");
      }
      if (targetStep <= 3 && activeStep >= 4) {
        setSelectedZoneUid("");
        setZoneSelectionMessage("Selecione uma zona consolidada.");
        setZoneDetailData(null);
        setZoneStreets([]);
        setZoneListingMessage("Aguardando seleção e detalhamento da zona.");
        setFinalListings([]);
        setListingsWithoutCoords([]);
        setFreshnessBadgeText("Dados ainda não carregados.");
        setListingDiffMessage("");
        setNewlyAddedListingKeys([]);
        setFocusedListingKey("");
        setFinalizeMessage("Finalize o run para carregar os imóveis.");
      }
      setActiveStep(targetStep);
      return;
    }

    if (targetStep > activeStep && isStepLocked(targetStep)) {
      return;
    }

    setActiveStep(targetStep);
  };

  const isStepLocked = (stepId: WizardStepId): boolean => {
    if (stepId <= activeStep) {
      return false;
    }
    if (stepId === 2) {
      return !(runId && zonesCollection.length > 0);
    }
    if (stepId === 3) {
      return !(journeyId || (runId && zonesCollection.length > 0));
    }
    if (stepId === 4) {
      return zonesCollection.length === 0;
    }
    if (stepId === 5 || stepId === 6) {
      return !(selectedZoneUid && zoneDetailData);
    }
    return true;
  };

  const panelWidth = activeStep >= 5 ? 600 : 420;
  const zonesReadyForCompare = zonesState === "ready" && zonesCollection.length > 0;

  const toggleLayer = (key: LayerKey) => {
    setLayerVisibility((current) => ({ ...current, [key]: !current[key] }));
  };

  const zoomIn = () => mapRef.current?.zoomIn({ duration: 180 });
  const zoomOut = () => mapRef.current?.zoomOut({ duration: 180 });
  const rightUiOffsetClass = "right-6";

  const handleGenerateZonesFromTransportStep = async () => {
    if (!journeyId || !selectedTransportPointId || isQueueingZoneGeneration) {
      return;
    }

    setIsQueueingZoneGeneration(true);
    setTransportPointsMessage("Enfileirando job de geração de zonas...");
    try {
      const job = await createZoneGenerationJob(journeyId);
      setZoneGenerationJobId(job.id);
      setTransportPointsMessage(`Job ${job.id} enfileirado com sucesso.`);
      setStatusMessage("Geração de zonas enfileirada. Avance para a etapa 3.");
      setActiveStep(3);
    } catch (error) {
      const hint = apiActionHint(error);
      setTransportPointsMessage(hint);
      setStatusMessage(hint);
    } finally {
      setIsQueueingZoneGeneration(false);
    }
  };

  const sortedListings = useMemo(() => {
    const decorated = finalListings.map((feature, index) => ({
      feature,
      index,
      info: resolveListingFeatureText(feature),
      analytics: computeListingAnalytics(feature, index, {
        interests,
        zoneDetailData,
        poiCountRadiusM
      })
    }));
    return sortDecoratedListings(decorated, listingSortMode);
  }, [finalListings, interests, listingSortMode, poiCountRadiusM, zoneDetailData]);

  const selectedListingsForComparison = useMemo(
    () => sortedListings.filter((item) => selectedListingKeys.includes(item.analytics.listingKey)),
    [selectedListingKeys, sortedListings]
  );

  const comparisonExtremes = useMemo(
    () => computeComparisonExtremes(selectedListingsForComparison),
    [selectedListingsForComparison]
  );

  const selectedZoneFeature = useMemo(
    () => zonesCollection.find((feature) => String(feature.properties?.zone_uid || "") === selectedZoneUid) || null,
    [selectedZoneUid, zonesCollection]
  );

  const seedTravelTimeMin = useMemo(() => {
    const raw = selectedZoneFeature?.properties?.time_agg;
    const value = typeof raw === "number" ? raw : Number(raw);
    return Number.isFinite(value) ? Math.max(0, value) : null;
  }, [selectedZoneFeature]);

  const topPoiCategories = useMemo(() => computeTopPoiCategories(zoneDetailData), [zoneDetailData]);

  const monthlyVariation = useMemo(() => computeMonthlyVariationFromRollups(priceRollups), [priceRollups]);

  const focusListingOnMap = (feature: ListingFeature, index: number) => {
    if (feature.geometry.type !== "Point") {
      return;
    }
    const [lon, lat] = feature.geometry.coordinates;
    const listingKey = getListingKey(feature, index);
    setFocusedListingKey(listingKey);
    const info = resolveListingFeatureText(feature);
    mapRef.current?.flyTo({ center: [lon, lat], zoom: 14.8, duration: 700 });
    if (mapRef.current) {
      new maplibregl.Popup({ offset: 12 })
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
    <main className="relative h-screen w-full overflow-hidden bg-slate-100 font-sans text-slate-800 select-none">
      <div className="absolute inset-0 bg-[#e5e7eb]">
        <section className="relative h-full w-full overflow-hidden">
          <div ref={mapContainerRef} className="h-full w-full" aria-label="Mapa principal" />

          <div className="pointer-events-none absolute inset-0">
            <AddressSearchBar
              value={searchValue}
              onChange={setSearchValue}
              onSubmit={handleSearch}
              containerStyle={{
                left: addressSearchLeftPx
                  ? `${addressSearchLeftPx}px`
                  : isPanelMinimized
                    ? "6rem"
                    : `calc(min(${panelWidth}px, calc(100vw - 2rem)) + 2rem)`
              }}
            />
            <MapToolbarRight
              rightOffsetClass={rightUiOffsetClass}
              isLayerMenuOpen={isLayerMenuOpen}
              onLayerMenuToggle={() => setIsLayerMenuOpen((o) => !o)}
              onLayerMenuClose={() => setIsLayerMenuOpen(false)}
              layerVisibility={layerVisibility}
              onToggleLayer={toggleLayer}
              hasRouteData={hasRouteData}
              onZoomIn={zoomIn}
              onZoomOut={zoomOut}
              onOpenHelp={() => setIsHelpOpen(true)}
            />
            <MapLoadingOverlay
              visible={Boolean(isLoading || mapBusyMessage)}
              loadingText={loadingText}
              mapBusyMessage={mapBusyMessage}
            />
            <MapErrorOverlay message={mapError} />
          </div>
        </section>
      </div>

      <FloatingBrand />

      {/* Painel flutuante: tracker + conteúdo */}
      <div
        className="pointer-events-none absolute bottom-4 left-4 top-4 z-10 flex max-h-full flex-col gap-3 max-lg:bottom-4 max-lg:left-4 max-lg:right-4 max-lg:top-4 max-lg:h-[min(48vh,560px)] max-lg:w-auto"
        style={{
          width: isPanelMinimized ? "11rem" : `min(${panelWidth}px, calc(100vw - 2rem))`
        }}
      >
        <div ref={progressTrackerMeasureRef} className="pointer-events-auto">
          <ProgressTracker
            steps={STEPS}
            activeStep={activeStep}
            isStepLocked={isStepLocked}
            onNavigateToStep={navigateToStep}
            isPanelMinimized={isPanelMinimized}
            onTogglePanelMinimized={() => setIsPanelMinimized((current) => !current)}
          />
        </div>

        <aside
          className={`pointer-events-auto flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl transition-all duration-500 ${
            isPanelMinimized ? "max-h-0 flex-none opacity-0" : "opacity-100"
          } max-lg:max-h-none`}
          style={{ display: isPanelMinimized ? "none" : "flex" }}
          aria-label="Painel lateral"
        >
          <div className="flex shrink-0 items-center justify-between gap-2 border-b border-slate-100 bg-white px-4 py-3">
            <button
              type="button"
              onClick={() => navigateToStep(Math.max(1, activeStep - 1) as WizardStepId)}
              disabled={activeStep === 1}
              className="flex items-center text-xs font-bold text-pastel-violet-600 hover:underline disabled:opacity-50"
            >
              <ChevronLeft className="mr-1 h-4 w-4" /> Voltar
            </button>
            <span className="text-xs font-semibold text-slate-500">{STEPS[activeStep - 1]?.title ?? ""}</span>
          </div>

          {!isPanelMinimized ? (
            <div className="panel-scroll flex-1 overflow-y-auto px-5 pb-6 pt-4">
              <Step1ConfigurePanel
                visible={activeStep === 1}
                viewport={viewport}
                primaryPoint={primaryPoint}
                setPrimaryPoint={setPrimaryPoint}
                removePrimaryPoint={removePrimaryPoint}
                setInteractionMode={setInteractionMode}
                setStatusMessage={setStatusMessage}
                isOptionalInterestsExpanded={isOptionalInterestsExpanded}
                setIsOptionalInterestsExpanded={setIsOptionalInterestsExpanded}
                interestCategory={interestCategory}
                setInterestCategory={setInterestCategory}
                interestLabel={interestLabel}
                setInterestLabel={setInterestLabel}
                interests={interests}
                removeInterest={removeInterest}
                propertyMode={propertyMode}
                setPropertyMode={setPropertyMode}
                zoneRadiusM={zoneRadiusM}
                setZoneRadiusM={setZoneRadiusM}
                maxTravelTimeMin={maxTravelTimeMin}
                setMaxTravelTimeMin={setMaxTravelTimeMin}
                seedBusSearchMaxDistM={seedBusSearchMaxDistM}
                setSeedBusSearchMaxDistM={setSeedBusSearchMaxDistM}
                seedRailSearchMaxDistM={seedRailSearchMaxDistM}
                setSeedRailSearchMaxDistM={setSeedRailSearchMaxDistM}
                zoneInfoSelection={zoneInfoSelection}
                setZoneInfoSelection={setZoneInfoSelection}
                onCreateRun={handleCreateRun}
                isCreatingRun={isCreatingRun}
                isPolling={isPolling}
              />

              <div className="block">
              {activeStep >= 2 ? (
                <WizardSharedStatus
                  statusMessage={statusMessage}
                  zonesState={zonesState}
                  zonesStateMessage={zonesStateMessage}
                  zoneSelectionMessage={zoneSelectionMessage}
                  runId={runId}
                  runStatus={runStatus}
                  executionProgress={executionProgress}
                />
              ) : (
                // Mantém a mensagem principal visível na Etapa 1 (tests esperam o texto), sem renderizar o bloco legado completo.
                <p className="mt-4 text-sm text-slate-600">{statusMessage}</p>
              )}

              {activeStep === 3 ? (
                <Step3GenerationHint
                  zonesReady={zonesReadyForCompare}
                  onContinueToCompare={() => setActiveStep(4)}
                />
              ) : null}

              <Step2TransportPanel
                visible={activeStep === 2}
                transportSearchRadiusM={transportSearchRadiusM}
                transportPointsLoading={transportPointsLoading}
                transportPoints={transportPoints}
                transportPointsMessage={transportPointsMessage}
                selectedTransportPointId={selectedTransportPointId}
                setSelectedTransportPointId={setSelectedTransportPointId}
                setHoveredTransportPointId={setHoveredTransportPointId}
                onTransportPointHover={(lon, lat) =>
                  mapRef.current?.flyTo({ center: [lon, lat], zoom: 14, duration: 450 })
                }
                onGenerateZones={handleGenerateZonesFromTransportStep}
                journeyId={journeyId}
                isQueueingZoneGeneration={isQueueingZoneGeneration}
                zoneGenerationJobId={zoneGenerationJobId}
                hoveredTransportPointId={hoveredTransportPointId}
                transportHoverPulseOn={transportHoverPulseOn}
              />

              {activeStep >= 4 && activeStep <= 6 ? (
              <Step3ZonePanel
                visible
                wizardSubStep={activeStep as Step3WizardSubStep}
                zoneDetailData={zoneDetailData}
                zoneInfoSelection={zoneInfoSelection}
                selectedZoneUid={selectedZoneUid}
                isDetailingZone={isDetailingZone}
                zoneListingMessage={zoneListingMessage}
                onDetailZone={handleDetailZone}
                activePanelTab={activePanelTab}
                onActivePanelTabChange={setActivePanelTab}
                streetQuery={streetQuery}
                onStreetQueryChange={(value) => {
                  setStreetFilterMode("specific");
                  setStreetQuery(value);
                  setSelectedStreet("");
                  setSelectedStreetType(null);
                }}
                streetSuggestions={streetSuggestions}
                selectedStreet={selectedStreet}
                selectedStreetType={selectedStreetType}
                suggestionTypeLabel={SUGGESTION_TYPE_LABEL}
                onStreetSuggestionSelect={(item) => {
                  setStreetFilterMode("specific");
                  setSelectedStreet(item.label);
                  setSelectedStreetType(item.type);
                  setStreetQuery(item.label);
                }}
                onZoneListings={handleZoneListings}
                isListingZone={isListingZone}
                finalizeMessage={finalizeMessage}
                runId={runId}
                apiBase={API_BASE}
                freshnessBadgeText={freshnessBadgeText}
                listingDiffMessage={listingDiffMessage}
                listingSortMode={listingSortMode}
                onListingSortModeChange={setListingSortMode}
                poiCountRadiusM={poiCountRadiusM}
                onPoiCountRadiusChange={setPoiCountRadiusM}
                selectedListingsForComparison={selectedListingsForComparison}
                comparisonExtremes={comparisonExtremes}
                sortedListings={sortedListings}
                onListingCardClick={handleListingCardClick}
                selectedListingKeys={selectedListingKeys}
                newlyAddedListingKeys={newlyAddedListingKeys}
                listingsWithoutCoords={listingsWithoutCoords}
                parseFiniteNumber={parseFiniteNumber}
                formatCurrencyBr={formatCurrencyBr}
                finalListings={finalListings}
                priceRollups={priceRollups}
                monthlyVariation={monthlyVariation}
                seedTravelTimeMin={seedTravelTimeMin}
                topPoiCategories={topPoiCategories}
              />
              ) : null}
              </div>
            </div>
          ) : null}
        </aside>
      </div>

      <HelpModal open={isHelpOpen} onClose={closeHelpModal} />
    </main>
  );
}