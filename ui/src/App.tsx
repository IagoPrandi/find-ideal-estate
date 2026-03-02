import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
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

type LayerKey = "routes" | "train" | "busStops" | "flood" | "green" | "pois";
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
  { id: 1, label: "Referências" },
  { id: 2, label: "Zonas" },
  { id: 3, label: "Imóveis" }
] as const;

const LAYER_INFO: Record<LayerKey, { label: string; color: string }> = {
  routes: { label: "Rotas de ônibus", color: "#2563eb" },
  train: { label: "Metrô/Trem", color: "#0f766e" },
  busStops: { label: "Pontos de ônibus", color: "#f97316" },
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
  const progressStartRef = useRef<number>(0);
  const progressExpectedRef = useRef<number>(0);

  const hasRouteData = Boolean(primaryPoint && zonesCollection.length > 0);

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
        type: "circle",
        source: "bus-stop-demo",
        paint: {
          "circle-radius": 5,
          "circle-color": "#f97316",
          "circle-stroke-color": "#fff",
          "circle-stroke-width": 1.5
        }
      });

      map.on("moveend", () => {
        const center = map.getCenter();
        setViewport({ lat: center.lat, lon: center.lng, zoom: map.getZoom() });
      });

      map.on("click", (event) => {
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
    map.setLayoutProperty("flood-layer", "visibility", visibility(layerVisibility.flood));
    map.setLayoutProperty("green-layer", "visibility", visibility(layerVisibility.green));
    map.setLayoutProperty("poi-layer", "visibility", visibility(layerVisibility.pois));
  }, [hasRouteData, isMapReady, layerVisibility]);

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

    const loadDefaultStops = async () => {
      try {
        const stops = await getTransportStops(viewport.lon, viewport.lat, 2800);
        if (cancelled) {
          return;
        }
        busStopSource.setData(stops);
      } catch {
        if (cancelled) {
          return;
        }
        busStopSource.setData({
          type: "FeatureCollection",
          features: []
        });
      }
    };

    void loadDefaultStops();

    return () => {
      cancelled = true;
    };
  }, [isMapReady, viewport.lat, viewport.lon]);

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
          return layerVisibility[key];
        })
        .map((key) => ({ key, ...LAYER_INFO[key] })),
    [hasRouteData, layerVisibility]
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

  const handleDetailZone = async () => {
    if (!runId || !selectedZoneUid || isDetailingZone) {
      return;
    }

    let succeeded = false;
    startExecutionProgress("detailZone", "Detalhando zona...", 60);
    setIsDetailingZone(true);
    setZoneListingMessage("Executando detalhamento da zona...");
    try {
      const detail = await getZoneDetail(runId, selectedZoneUid);
      setZoneDetailData(detail);
      setZoneListingMessage("Detalhamento concluído. Próximo: buscar imóveis da zona.");
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

    let succeeded = false;
    startExecutionProgress("zoneListings", "Coletando imóveis por rua...", 180);
    setIsListingZone(true);
    setZoneListingMessage("Buscando imóveis para a zona selecionada...");
    try {
      const result = await scrapeZoneListings(runId, selectedZoneUid);
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

  const panelDesktopWidth = isPanelMinimized ? "w-16" : "w-[400px]";
  const panelMobileHeight = isPanelMinimized ? "max-lg:h-14" : "max-lg:h-[48vh]";
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
    <main className="h-full w-full bg-bg text-text">
      <div className="relative flex h-full w-full overflow-hidden max-lg:flex-col">
        <section className="relative h-full min-w-0 flex-1 max-lg:h-[55vh] max-lg:flex-none">
          <div ref={mapContainerRef} className="h-full w-full" aria-label="Mapa principal" />

          <div className="pointer-events-none absolute inset-0">
            <div className="pointer-events-auto absolute left-4 top-4 z-20 w-[min(460px,calc(100%-2rem))] rounded-panel border border-border bg-panel/95 p-3 shadow-panel backdrop-blur-sm">
              <form className="flex gap-2" onSubmit={handleSearch}>
                <label htmlFor="map-search" className="sr-only">
                  Buscar endereço
                </label>
                <input
                  id="map-search"
                  value={searchValue}
                  onChange={(event) => setSearchValue(event.target.value)}
                  placeholder="Buscar endereço ou bairro"
                  className="w-full rounded-xl border border-border px-3 py-2 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/25"
                />
                <button
                  type="submit"
                  className="rounded-xl bg-primary px-3 py-2 text-sm font-semibold text-white transition hover:brightness-105"
                >
                  Buscar
                </button>
              </form>
            </div>

            <div className="pointer-events-auto absolute left-4 top-32 z-20 rounded-panel border border-border bg-panel/95 p-2 shadow-panel backdrop-blur-sm">
              <div className="flex gap-2 text-xs">
                <button
                  type="button"
                  onClick={() => setInteractionMode("primary")}
                  className={`rounded-lg px-2.5 py-1.5 font-semibold ${
                    interactionMode === "primary"
                      ? "bg-primary text-white"
                      : "border border-border bg-white text-muted"
                  }`}
                >
                  Definir principal
                </button>
                <button
                  type="button"
                  onClick={() => setInteractionMode("interest")}
                  className={`rounded-lg px-2.5 py-1.5 font-semibold ${
                    interactionMode === "interest"
                      ? "bg-primary text-white"
                      : "border border-border bg-white text-muted"
                  }`}
                >
                  Adicionar interesse
                </button>
              </div>
            </div>

            <div className="pointer-events-auto absolute left-4 top-56 z-20 flex flex-col items-start gap-2">
              {STEPS.map((stepItem, index) => {
                const isReached = activeStep >= stepItem.id;
                return (
                  <div key={stepItem.id} className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setActiveStep(stepItem.id as 1 | 2 | 3)}
                      className={`h-9 w-9 rounded-full border text-xs font-bold transition ${
                        isReached
                          ? "border-primary bg-primary text-white"
                          : "border-border bg-white text-muted"
                      }`}
                      aria-label={`Ir para passo ${stepItem.id}`}
                    >
                      {stepItem.id}
                    </button>
                    <span className={`text-xs font-medium ${isReached ? "text-text" : "text-muted"}`}>
                      {stepItem.label}
                    </span>
                    {index < STEPS.length - 1 ? <span className="ml-2 mr-1 h-6 w-px bg-border" /> : null}
                  </div>
                );
              })}
            </div>

            <div className="pointer-events-auto absolute right-4 top-4 z-20 flex flex-col items-end gap-2">
              <button
                type="button"
                onClick={() => setIsLayerMenuOpen((open) => !open)}
                className="rounded-xl border border-border bg-panel px-3 py-2 text-sm font-medium shadow-panel"
                aria-label="Abrir menu de camadas"
              >
                Camadas
              </button>
              {isLayerMenuOpen ? (
                <div className="w-56 rounded-panel border border-border bg-panel p-3 shadow-panel">
                  <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted">Mostrar / ocultar</p>
                  {(Object.keys(LAYER_INFO) as LayerKey[]).map((key) => (
                    <label key={key} className="mb-2 flex cursor-pointer items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={layerVisibility[key]}
                        onChange={() => toggleLayer(key)}
                        className="h-4 w-4 accent-primary"
                      />
                      <span className={(key === "routes" || key === "train") && !hasRouteData ? "text-muted" : ""}>
                        {LAYER_INFO[key].label}
                      </span>
                    </label>
                  ))}
                  {!hasRouteData ? (
                    <p className="mt-1 text-xs text-muted">
                      Rotas só aparecem após selecionar referência e carregar zonas.
                    </p>
                  ) : null}
                </div>
              ) : null}

              <div className="flex overflow-hidden rounded-xl border border-border bg-panel shadow-panel">
                <button type="button" onClick={zoomIn} className="px-3 py-2 text-lg" aria-label="Aumentar zoom">
                  +
                </button>
                <button
                  type="button"
                  onClick={zoomOut}
                  className="border-l border-border px-3 py-2 text-lg"
                  aria-label="Diminuir zoom"
                >
                  −
                </button>
              </div>

              <button
                type="button"
                onClick={() => setIsHelpOpen(true)}
                className="rounded-xl border border-border bg-panel px-3 py-2 text-sm font-medium shadow-panel"
                aria-label="Abrir ajuda"
              >
                Ajuda
              </button>
            </div>

            <div className="pointer-events-auto absolute bottom-4 left-4 z-20 rounded-panel border border-border bg-panel/95 p-3 shadow-panel backdrop-blur-sm">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Legenda</p>
              {activeLegendItems.length ? (
                <ul className="space-y-1">
                  {activeLegendItems.map((item) => (
                    <li key={item.key} className="flex items-center gap-2 text-xs text-text">
                      <span
                        className="inline-block h-2.5 w-2.5 rounded-full"
                        style={{ backgroundColor: item.color }}
                        aria-hidden="true"
                      />
                      {item.label}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-muted">Ative camadas para visualizar a legenda.</p>
              )}
            </div>

            {mapBusyMessage ? (
              <div className="pointer-events-none absolute inset-0 z-30 grid place-items-center bg-slate-950/25 p-6">
                <div className="pointer-events-auto rounded-panel border border-border bg-panel px-4 py-3 text-sm font-medium text-text shadow-panel">
                  <span className="mr-2 inline-block h-2 w-2 animate-pulse rounded-full bg-primary" />
                  {mapBusyMessage}
                </div>
              </div>
            ) : null}

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
          className={`relative h-full border-l border-border bg-panel shadow-panel transition-all duration-300 ${panelDesktopWidth} ${panelMobileHeight} max-lg:fixed max-lg:bottom-0 max-lg:left-0 max-lg:right-0 max-lg:z-30 max-lg:w-full max-lg:border-l-0 max-lg:border-t`}
          aria-label="Painel lateral"
        >
          <button
            type="button"
            onClick={() => setIsPanelMinimized((value) => !value)}
            className="absolute left-2 top-2 z-20 rounded-lg border border-border bg-white px-2 py-1 text-xs font-semibold text-muted"
            aria-expanded={!isPanelMinimized}
          >
            {isPanelMinimized ? "Abrir" : "Minimizar"}
          </button>

          {!isPanelMinimized ? (
            <div className="panel-scroll h-full overflow-y-auto px-5 pb-6 pt-12">
              <h1 className="text-xl font-bold">Imóvel Ideal</h1>
              <p className="mt-1 text-sm text-muted">Milestone FE1 — referências e criação de run.</p>

              <section className="mt-5 rounded-panel border border-border p-4 text-sm">
                <h2 className="font-semibold">1) Ponto principal</h2>
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
                className="mt-4 w-full rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                Gerar Zonas Candidatas
              </button>

              <section className="mt-4 rounded-panel border border-border p-4 text-sm">
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
                        disabled={!selectedZoneUid || !zoneDetailData || isListingZone}
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
          ) : (
            <div className="grid h-full place-items-center pt-8">
              <span className="-rotate-90 text-xs font-semibold tracking-[0.18em] text-muted">PAINEL</span>
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