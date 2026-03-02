import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  Search,
  MapPin,
  Bus,
  Train,
  Layers,
  ChevronRight,
  Loader2,
  Home,
  HelpCircle,
  Minus,
  Maximize2,
  Plus,
  MapPinOff,
  SlidersHorizontal,
  Info,
  CheckSquare,
  Square,
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

const MAPBOX_TOKEN =
  import.meta.env.VITE_MAPBOX_ACCESS_TOKEN || (import.meta.env.MODE === "test" ? "test-token" : "");

const STEPS = [
  { id: 1, title: "Referências", desc: "Defina seu local base" },
  { id: 2, title: "Zonas", desc: "Regiões recomendadas" },
  { id: 3, title: "Imóveis", desc: "Encontre o seu novo lar" }
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

  const [searchValue, setSearchValue] = useState("");
  const [isPanelMinimized, setIsPanelMinimized] = useState(false);
  const [isLayerMenuOpen, setIsLayerMenuOpen] = useState(false);
  const [isHelpOpen, setIsHelpOpen] = useState(false);
  const [isMapReady, setIsMapReady] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);
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
  const [zoneStreets, setZoneStreets] = useState<string[]>([]);
  const [stopsLoading, setStopsLoading] = useState(false);
  const [loadingText, setLoadingText] = useState("");
  const [finalListings, setFinalListings] = useState<ListingFeature[]>([]);
  const [finalizeMessage, setFinalizeMessage] = useState("Finalize o run para carregar os imóveis.");
  const [isSelectingZone, setIsSelectingZone] = useState(false);
  const [isDetailingZone, setIsDetailingZone] = useState(false);
  const [isListingZone, setIsListingZone] = useState(false);
  const [isFinalizingRun, setIsFinalizingRun] = useState(false);
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
  const [executionStages, setExecutionStages] = useState(createInitialExecutionStages);
  const [activeExecutionStage, setActiveExecutionStage] = useState<ExecutionStageKey | null>(null);
  const [executionHistory, setExecutionHistory] = useState<Array<{ label: string; durationSec: number }>>([]);

  const initialViewport = useRef(viewport);
  const progressTimerRef = useRef<number | null>(null);
  const stopsDebounceRef = useRef<number | null>(null);
  const progressStartRef = useRef<number>(0);
  const progressExpectedRef = useRef<number>(0);

  const hasRouteData = Boolean(primaryPoint && zonesCollection.length > 0);

  const isLoading =
    isCreatingRun ||
    isPolling ||
    isSelectingZone ||
    isDetailingZone ||
    isListingZone ||
    isFinalizingRun;

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

      map.addSource("poi-demo", {
        type: "geojson",
        data: {
          type: "FeatureCollection",
          features: [
            {
              type: "Feature",
              geometry: { type: "Point", coordinates: [-46.621, -23.534] },
              properties: { name: "POI Exemplo" }
            }
          ]
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
        source: "poi-demo",
        paint: {
          "circle-radius": 7,
          "circle-color": "#d97706",
          "circle-stroke-color": "#fff",
          "circle-stroke-width": 2
        }
      });
      map.addLayer({
        id: "bus-stop-layer",
        type: "symbol",
        source: "bus-stop-demo",
        layout: {
          "text-field": ["match", ["get", "kind"], "bus_stop", "🚌", "station", "🚆", "🚏"],
          "text-size": 16,
          "text-allow-overlap": true,
          "text-ignore-placement": true
        },
        paint: {
          "text-halo-color": "#fff",
          "text-halo-width": 2
        }
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
  }, [hasRouteData, isMapReady, layerVisibility, zonesCollection.length]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }

    const busStopSource = map.getSource("bus-stop-demo") as mapboxgl.GeoJSONSource | undefined;
    if (!busStopSource) {
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
  }, [isMapReady, viewport.lat, viewport.lon, viewport.zoom]);

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

    zonesSource.setData({
      type: "FeatureCollection",
      features: zonesCollection
    });
  }, [isMapReady, zonesCollection]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady || !map.getLayer("zones-fill-layer")) {
      return;
    }

    if (selectedZoneUid) {
      map.setPaintProperty("zones-fill-layer", "fill-opacity", [
        "case",
        ["==", ["get", "zone_uid"], selectedZoneUid],
        0.45,
        0.15
      ]);
      map.setPaintProperty("zones-outline-layer", "line-width", [
        "case",
        ["==", ["get", "zone_uid"], selectedZoneUid],
        3,
        2
      ]);
    } else {
      map.setPaintProperty("zones-fill-layer", "fill-opacity", 0.2);
      map.setPaintProperty("zones-outline-layer", "line-width", 2);
    }
  }, [isMapReady, selectedZoneUid]);

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
          max_streets_per_zone: 1,
          listing_max_pages: 1,
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
    setFinalizeMessage("Finalize o run para carregar os imóveis.");
    resetExecutionTracking();
    setActiveStep(1);
    setStatusMessage("Ponto principal removido.");
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
      setActiveStep(2);
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
      setZoneListingMessage("Detalhamento concluído. Escolha como buscar imóveis.");
      setStatusMessage(`Detalhamento finalizado para ${selectedZoneUid}.`);
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
      setZoneListingMessage(`Coleta concluída: ${result.listing_files.length} artifact(s) de listings.`);
      setActiveStep(3);
      setStatusMessage(`Listings coletados para ${selectedZoneUid}.`);
      succeeded = true;
    } catch (error) {
      const hint = apiActionHint(error);
      setZoneListingMessage(hint);
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

  const handleFinalizeRun = async () => {
    if (!runId || !selectedZoneUid || isFinalizingRun) {
      return;
    }

    let succeeded = false;
    startExecutionProgress("finalize", "Finalizando run e consolidando resultado...", 90);
    setIsFinalizingRun(true);
    setLoadingText("Finalizando run e consolidando resultado...");
    setFinalizeMessage("Finalizando run e carregando resultado final...");
    try {
      await finalizeRun(runId);
      const finalGeo = await getFinalListings(runId);
      setFinalListings(finalGeo.features || []);
      setFinalizeMessage(`Resultado final pronto: ${finalGeo.features.length} imóveis carregados.`);
      setStatusMessage("Finalização concluída. Cards e exports disponíveis no painel.");
      setActiveStep(3);
      succeeded = true;
    } catch (error) {
      const hint = apiActionHint(error);
      setFinalizeMessage(hint);
      setStatusMessage(hint);
      stopExecutionProgress("Falha na finalização.", "error");
    } finally {
      setIsFinalizingRun(false);
      if (succeeded) {
        setExecutionProgress((current) => ({
          ...current,
          percent: 100,
          etaSec: 0,
          label: "Finalização concluída."
        }));
        window.setTimeout(() => stopExecutionProgress("Finalização concluída."), 700);
      }
    }
  };

  const removeInterest = (id: string) => {
    setInterests((current) => current.filter((item) => item.id !== id));
  };

  const navigateToStep = (targetStep: 1 | 2 | 3) => {
    if (targetStep === 1 && activeStep > 1) {
      removePrimaryPoint();
    } else if (targetStep === 2 && activeStep > 2) {
      setActiveStep(2);
    } else if (targetStep === 3 && (activeStep >= 3 || (activeStep === 2 && selectedZoneUid && finalListings.length > 0))) {
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

  const totalRemainingSec = EXECUTION_STAGE_ORDER.reduce((acc, key) => {
    const stage = executionStages[key];
    if (stage.status === "done") {
      return acc;
    }
    if (stage.status === "running") {
      return acc + stage.etaSec;
    }
    if (stage.status === "idle") {
      return acc + EXECUTION_STAGE_META[key].expectedSec;
    }
    return acc;
  }, 0);

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

            {/* Stepper vertical expandível - estilo esboço */}
            <div className="pointer-events-none absolute top-24 left-6 z-40 flex flex-col items-start">
              {STEPS.map((s, idx) => (
                <div key={s.id} className="flex flex-col items-start">
                  <button
                    type="button"
                    onClick={() => navigateToStep(s.id as 1 | 2 | 3)}
                    className={`group flex items-center h-10 rounded-full shadow-md transition-all duration-300 ease-out overflow-hidden pointer-events-auto
                      ${activeStep >= s.id ? "bg-[#2563EB] text-white" : "bg-white text-slate-400 border border-slate-200"}
                      ${s.id <= activeStep || (s.id === 3 && selectedZoneUid) ? "cursor-pointer hover:border-blue-300 w-10 hover:w-48" : "opacity-50 cursor-not-allowed w-10"}
                    `}
                  >
                    <div className="w-10 h-10 flex-shrink-0 flex items-center justify-center font-bold">
                      {s.id}
                    </div>
                    <div className="flex flex-col whitespace-nowrap pr-4 opacity-0 group-hover:opacity-100 transition-opacity duration-300 delay-100">
                      <span className={`text-sm font-bold leading-tight ${activeStep >= s.id ? "text-white" : "text-slate-700"}`}>
                        {s.title}
                      </span>
                      <span className={`text-[10px] font-medium mt-0.5 leading-tight ${activeStep >= s.id ? "text-blue-200" : "text-slate-500"}`}>
                        {s.desc}
                      </span>
                    </div>
                  </button>
                  {idx < 2 && (
                    <div className={`w-1 h-8 my-1 ml-[18px] rounded transition-colors ${activeStep > s.id ? "bg-[#2563EB]" : "bg-slate-300"}`} />
                  )}
                </div>
              ))}
            </div>

            <div className="pointer-events-auto absolute right-6 top-6 z-40 flex flex-col items-end gap-2">
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
            <div className="pointer-events-auto absolute bottom-6 right-6 z-40 flex flex-col gap-2">
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
                  {layerVisibility.busStops && <div className="flex items-center gap-2"><span className="text-base">🚌</span> Paradas</div>}
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

        {isPanelMinimized && (
          <button
            onClick={() => setIsPanelMinimized(false)}
            className="absolute top-6 right-6 z-50 bg-white/95 backdrop-blur-md p-3.5 rounded-full shadow-xl border border-slate-200 text-[#2563EB] hover:bg-slate-50 transition-all flex items-center justify-center"
            title="Restaurar painel"
          >
            <Maximize2 size={24} />
          </button>
        )}

        <aside
          className={`w-[400px] bg-white h-full shadow-2xl z-40 flex flex-col border-l border-slate-200 shrink-0 relative transition-all duration-300 ${isPanelMinimized ? "-mr-[400px]" : "mr-0"} max-lg:fixed max-lg:bottom-0 max-lg:left-0 max-lg:right-0 max-lg:z-30 max-lg:w-full max-lg:border-l-0 max-lg:border-t max-lg:h-[48vh]`}
          aria-label="Painel lateral"
        >
          <button
            type="button"
            onClick={() => setIsPanelMinimized(true)}
            className="absolute top-5 right-5 z-50 p-2 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-md transition-colors"
            title="Minimizar painel"
          >
            <Minus size={20} />
          </button>

          {activeStep > 1 && (
            <div className="px-6 py-4 border-b border-slate-100 flex items-center gap-2 bg-slate-50">
              <button onClick={() => navigateToStep((activeStep - 1) as 1 | 2 | 3)} className="text-[#2563EB] text-sm font-bold flex items-center hover:underline pr-8">
                <ChevronRight className="w-4 h-4 rotate-180 mr-1" /> Voltar
              </button>
              <span className="text-slate-400 text-sm">| Passo {activeStep} de 3</span>
            </div>
          )}

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
                <h2 className="font-semibold">2) Interesses (opcional)</h2>
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
                  <p className="text-xs text-muted">Mude para “Adicionar interesse” e clique no mapa.</p>
                </div>

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

              <button
                type="button"
                onClick={handleCreateRun}
                disabled={!primaryPoint || isCreatingRun || isPolling}
                className="mt-4 w-full rounded-xl bg-[#2563EB] px-4 py-3.5 text-sm font-bold text-white shadow-lg disabled:cursor-not-allowed disabled:opacity-50 hover:bg-blue-700"
              >
                Gerar Zonas Candidatas
              </button>
              </div>

              {/* ETAPA 2 e 3 - conteúdo existente */}
              <div className={activeStep >= 2 ? "block" : "hidden"}>
              <section className="mt-4 rounded-xl border border-slate-200 p-4 text-sm">
                <h2 className="font-semibold">Status</h2>
                <p className="mt-2 text-muted">{statusMessage}</p>
                {runId ? <p className="mt-1 text-xs text-muted">run_id: {runId}</p> : null}
                {runStatus ? (
                  <p className="text-xs text-muted">
                    etapa: {runStatus.stage} · estado: {runStatus.state}
                  </p>
                ) : null}
              </section>

              <section className="mt-4 rounded-panel border border-border p-4 text-sm">
                <h2 className="font-semibold">Progresso da execução</h2>
                <p className="mt-2 text-xs text-muted">{executionProgress.label}</p>
                <div className="mt-2 h-2 w-full rounded bg-slate-100">
                  <div
                    className="h-2 rounded bg-primary transition-all"
                    style={{ width: `${Math.max(0, Math.min(100, executionProgress.percent))}%` }}
                  />
                </div>
                <div className="mt-1 flex items-center justify-between text-xs text-muted">
                  <span>{executionProgress.percent}%</span>
                  <span>Decorrido: {executionProgress.elapsedSec}s</span>
                  <span>
                    Tempo restante estimado:
                    {" "}
                    {executionProgress.active ? `${executionProgress.etaSec}s` : "—"}
                  </span>
                </div>
                <p className="mt-2 text-xs text-muted">ETA total do fluxo: {totalRemainingSec}s</p>
                <ul className="mt-2 space-y-1 text-[11px] text-muted">
                  {EXECUTION_STAGE_ORDER.map((key) => {
                    const stage = executionStages[key];
                    const statusLabel =
                      stage.status === "done"
                        ? "concluída"
                        : stage.status === "running"
                          ? "em execução"
                          : stage.status === "error"
                            ? "erro"
                            : "pendente";
                    return (
                      <li key={key} className="rounded border border-border/70 px-2 py-1.5">
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-semibold text-text">{EXECUTION_STAGE_META[key].label}</span>
                          <span className="text-[10px] uppercase tracking-wide">{statusLabel}</span>
                        </div>
                        <div className="mt-0.5 flex items-center justify-between">
                          <span>Decorrido: {stage.elapsedSec}s</span>
                          <span>
                            Restante: {stage.status === "done" || stage.status === "error" ? "—" : `${stage.etaSec}s`}
                          </span>
                        </div>
                      </li>
                    );
                  })}
                </ul>
                {executionHistory.length > 0 ? (
                  <ul className="mt-2 space-y-1 text-[11px] text-muted">
                    {executionHistory.map((item, index) => (
                      <li key={`${item.label}_${index}`}>
                        {item.label} · {item.durationSec}s
                      </li>
                    ))}
                  </ul>
                ) : null}
              </section>

              <section className="mt-4 rounded-panel border border-border p-4 text-sm">
                <h2 className="font-semibold">Contrato FE4 (zonas)</h2>
                <p className="mt-2 text-xs text-muted">
                  Estado:
                  {" "}
                  {zonesState === "idle" && "idle"}
                  {zonesState === "loading" && "loading"}
                  {zonesState === "ready" && "ready"}
                  {zonesState === "empty" && "empty"}
                  {zonesState === "error-recoverable" && "erro recuperável"}
                  {zonesState === "error-fatal" && "erro fatal"}
                </p>
                <p
                  className={`mt-1 text-xs ${
                    zonesState === "ready"
                      ? "text-success"
                      : zonesState === "error-recoverable" || zonesState === "error-fatal"
                        ? "text-danger"
                        : "text-muted"
                  }`}
                >
                  {zonesStateMessage}
                </p>
                {zonesState === "error-recoverable" ? (
                  <button
                    type="button"
                    onClick={() => {
                      if (runId) {
                        setIsPolling(true);
                        setStatusMessage("Retomando polling com backoff...");
                      }
                    }}
                    className="mt-2 rounded border border-border px-2 py-1 text-xs font-semibold"
                  >
                    Tentar novamente
                  </button>
                ) : null}
              </section>

              <section className="mt-4 rounded-panel border border-border p-4 text-sm">
                <h2 className="font-semibold">FE2 — Seleção e detalhamento de zona</h2>
                {zonesCollection.length > 0 ? (
                  <div className="mt-2 space-y-2">
                    <p className="text-xs text-muted">Selecione exatamente 1 zona para o fluxo smoke.</p>
                    <ul className="max-h-40 space-y-2 overflow-y-auto">
                      {zonesCollection.map((zone) => {
                        const uid = zone.properties.zone_uid;
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
                                <strong>{uid}</strong> · score {score} · tempo {timeAgg}
                              </span>
                            </label>
                          </li>
                        );
                      })}
                    </ul>

                    <div className="mt-2 space-y-2">
                      <h3 className="text-xs font-semibold text-muted">Buscar imóveis</h3>
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
                      ) : streetFilterMode === "specific" && zoneDetailData ? (
                        <p className="text-xs text-muted">Carregando ruas...</p>
                      ) : null}
                    </div>

                    <div className="grid grid-cols-2 gap-2">
                      <button
                        type="button"
                        onClick={handleSelectZone}
                        disabled={!selectedZoneUid || isSelectingZone}
                        className="rounded border border-border px-2 py-1.5 text-xs font-semibold disabled:opacity-50"
                      >
                        {isSelectingZone ? "Selecionando..." : "Selecionar zona"}
                      </button>
                      <button
                        type="button"
                        onClick={handleDetailZone}
                        disabled={!selectedZoneUid || isDetailingZone}
                        className="rounded border border-border px-2 py-1.5 text-xs font-semibold disabled:opacity-50"
                      >
                        {isDetailingZone ? "Detalhando..." : "Detalhar zona"}
                      </button>
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
                      <button
                        type="button"
                        onClick={handleFinalizeRun}
                        disabled={!selectedZoneUid || isFinalizingRun}
                        className="rounded bg-primary px-2 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
                      >
                        {isFinalizingRun ? "Finalizando..." : "Finalizar run"}
                      </button>
                    </div>
                  </div>
                ) : (
                  <p className="mt-2 text-xs text-muted">Gere zonas candidatas para habilitar esta etapa.</p>
                )}

                <p className="mt-2 text-xs text-muted">{zoneSelectionMessage}</p>
                <p className="mt-1 text-xs text-muted">{zoneListingMessage}</p>

                {zoneDetailData ? (
                  <div className="mt-2 rounded-lg border border-border/70 bg-bg px-2 py-2 text-[11px] text-muted">
                    <p>
                      <strong>Zona:</strong> {zoneDetailData.zone_uid}
                    </p>
                    <p>
                      <strong>Ruas:</strong> {zoneDetailData.streets_path}
                    </p>
                    <p>
                      <strong>POIs:</strong> {zoneDetailData.pois_path}
                    </p>
                    <p>
                      <strong>Transporte:</strong> {zoneDetailData.transport_path}
                    </p>
                  </div>
                ) : null}
              </section>

              <section className="mt-4 rounded-panel border border-border p-4 text-sm">
                <h2 className="font-semibold">FE3 — Imóveis finais</h2>
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
                  <ul className="mt-3 space-y-2">
                    {finalListings.slice(0, 5).map((feature, index) => {
                      const info = resolveListingText(feature);
                      return (
                        <li key={`${index}_${feature.geometry.coordinates.join("_")}`} className="rounded-lg border border-border px-2 py-2 text-xs">
                          <p className="font-semibold text-text">{info.priceLabel}</p>
                          <p className="text-muted">{info.address}</p>
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
                ) : null}
              </section>
              </div>
            </div>
          ) : (
            <div className="grid h-full place-items-center pt-8">
              <span className="-rotate-90 text-xs font-semibold tracking-[0.18em] text-slate-400">PAINEL</span>
            </div>
          )}
        </aside>
      </div>

      {isHelpOpen ? (
        <div className="fixed inset-0 z-40 grid place-items-center bg-slate-900/45 p-4">
          <div className="w-full max-w-lg rounded-panel border border-border bg-panel p-5 shadow-panel">
            <h2 className="text-lg font-semibold">Ajuda — FE1 + FE4</h2>
            <p className="mt-2 text-sm text-muted">
              Selecione um ponto principal no mapa, ajuste o modo Alugar/Comprar e use “Gerar Zonas
              Candidatas” para iniciar o run no backend.
            </p>
            <p className="mt-3 text-sm text-muted">
              Interesses são opcionais e não entram como seed de geração de zonas.
              O painel também valida o contrato de zonas com Zod e mostra estado loading/empty/error/fatal.
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