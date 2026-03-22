"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import { useSSEEvents } from "../hooks/useSSEEvents";

export type Etapa3Props = {
  journeyId: string;
  selectedTransportPointIds: string[];
  onNext: () => void;
};

type ZoneSnapshot = {
  id: string;
  travel_time_minutes: number | null;
  walk_distance_meters: number | null;
  isochrone_geom: GeoJSON.Geometry | null;
};

type ZonesApiResponse = {
  zones: ZoneSnapshot[];
  total_count: number;
  completed_count: number;
};

const DEFAULT_CENTER: [number, number] = [-46.633308, -23.55052];

export function Etapa3ZoneGeneration({
  journeyId,
  selectedTransportPointIds,
  onNext,
}: Etapa3Props) {
  const [jobId, setJobId] = useState<string | null>(null);
  const [progressPercent, setProgressPercent] = useState(0);
  const [zones, setZones] = useState<ZoneSnapshot[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isCancelling, setIsCancelling] = useState(false);
  const [statusMessage, setStatusMessage] = useState("Preparando geracao de zonas...");
  const [isJobFinished, setIsJobFinished] = useState(false);

  const { events } = useSSEEvents(jobId);
  const processedEventIdsRef = useRef<Set<string>>(new Set());
  const jobStartRequestedRef = useRef(false);

  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const zoneLabelMarkersRef = useRef<maplibregl.Marker[]>([]);

  const maptilerKey = process.env.NEXT_PUBLIC_MAPTILER_API_KEY ?? "";

  const sortedZones = useMemo(
    () =>
      [...zones].sort((a, b) => {
        const tA = a.travel_time_minutes ?? Number.MAX_SAFE_INTEGER;
        const tB = b.travel_time_minutes ?? Number.MAX_SAFE_INTEGER;
        if (tA !== tB) {
          return tA - tB;
        }
        return (a.walk_distance_meters ?? Number.MAX_SAFE_INTEGER) - (b.walk_distance_meters ?? Number.MAX_SAFE_INTEGER);
      }),
    [zones],
  );

  const refreshZones = useCallback(async () => {
    try {
      const response = await fetch(`/api/journeys/${journeyId}/zones`, { cache: "no-store" });
      if (!response.ok) {
        return;
      }
      const data = (await response.json()) as ZonesApiResponse;
      setZones(data.zones ?? []);
    } catch {
      // non-blocking refresh
    }
  }, [journeyId]);

  useEffect(() => {
    const startJob = async () => {
      try {
        setError(null);
        setStatusMessage("Enfileirando geracao de zonas...");
        const response = await fetch("/api/jobs", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            journey_id: journeyId,
            job_type: "zone_generation",
            current_stage: "zone_generation",
          }),
        });

        if (!response.ok) {
          throw new Error("Falha ao iniciar geracao de zonas");
        }

        const jobData = await response.json();
        setJobId(jobData.id);
        setStatusMessage("Geracao iniciada. Aguardando primeiras zonas...");
      } catch (e) {
        const message = e instanceof Error ? e.message : "Erro desconhecido";
        setError(message);
      }
    };

    if (!jobStartRequestedRef.current && journeyId && selectedTransportPointIds.length > 0) {
      jobStartRequestedRef.current = true;
      startJob();
    }
  }, [journeyId, selectedTransportPointIds.length]);

  useEffect(() => {
    for (const event of events) {
      if (event.id && processedEventIdsRef.current.has(event.id)) {
        continue;
      }
      if (event.id) {
        processedEventIdsRef.current.add(event.id);
      }

      const payload = (event.data?.payload_json ?? {}) as Record<string, unknown>;

      if (event.event === "job.started") {
        setStatusMessage(event.data?.message ?? "Geracao de zonas em andamento...");
        setIsJobFinished(false);
      }

      if (event.event === "job.stage.progress") {
        const progress = Number(payload.progress_percent ?? 0);
        setProgressPercent(Number.isFinite(progress) ? Math.max(0, Math.min(100, progress)) : 0);
        setStatusMessage(event.data?.message ?? "Processando zonas...");
      }

      if (event.event === "job.partial_result.ready" || event.event === "zone.generated" || event.event === "zone.reused") {
        setStatusMessage("Resultado parcial disponivel. Mantendo lista atualizada...");
        void refreshZones();
      }

      if (event.event === "job.cancelled") {
        setIsCancelling(false);
        setIsJobFinished(true);
        setStatusMessage("Geracao cancelada. Zonas ja recebidas permanecem disponiveis.");
        void refreshZones();
      }

      if (event.event === "job.completed") {
        setProgressPercent(100);
        setIsCancelling(false);
        setIsJobFinished(true);
        setStatusMessage(event.data?.message ?? "Geracao concluida. Avancando para comparacao...");
        void refreshZones();
        setTimeout(() => onNext(), 900);
      }

      if (event.event === "job.failed") {
        setIsCancelling(false);
        setIsJobFinished(true);
        setError("Geracao de zonas falhou. Tente novamente.");
      }
    }
  }, [events, onNext, refreshZones]);

  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current || !maptilerKey) {
      return;
    }

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: `https://api.maptiler.com/maps/streets-v2/style.json?key=${maptilerKey}`,
      center: DEFAULT_CENTER,
      zoom: 10.8,
      attributionControl: false,
    });

    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");

    map.on("load", () => {
      map.addSource("zones-src", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });

      map.addLayer({
        id: "zones-fill",
        type: "fill",
        source: "zones-src",
        paint: {
          "fill-color": "#145c52",
          "fill-opacity": 0.24,
        },
      });

      map.addLayer({
        id: "zones-line",
        type: "line",
        source: "zones-src",
        paint: {
          "line-color": "#0d413a",
          "line-width": 2,
        },
      });
    });

    mapRef.current = map;
    return () => {
      zoneLabelMarkersRef.current.forEach((marker) => marker.remove());
      zoneLabelMarkersRef.current = [];
      map.remove();
      mapRef.current = null;
    };
  }, [maptilerKey]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) {
      return;
    }

    const source = map.getSource("zones-src") as maplibregl.GeoJSONSource | undefined;
    if (!source) {
      return;
    }

    const features = sortedZones
      .filter((zone) => zone.isochrone_geom)
      .map((zone) => ({
        type: "Feature" as const,
        id: zone.id,
        properties: {
          zoneId: zone.id,
          travel_time_minutes: zone.travel_time_minutes,
        },
        geometry: zone.isochrone_geom as GeoJSON.Geometry,
      }));

    source.setData({ type: "FeatureCollection", features });

    zoneLabelMarkersRef.current.forEach((marker) => marker.remove());
    zoneLabelMarkersRef.current = [];

    for (let i = 0; i < features.length; i += 1) {
      const feature = features[i];
      const bounds = new maplibregl.LngLatBounds();
      const geometry = feature.geometry;

      const pushCoords = (coords: number[][] | number[][][]) => {
        for (const point of coords as number[][]) {
          if (Array.isArray(point) && point.length >= 2) {
            bounds.extend([point[0], point[1]]);
          }
        }
      };

      if (geometry.type === "Polygon") {
        pushCoords(geometry.coordinates[0] as number[][]);
      }
      if (geometry.type === "MultiPolygon") {
        for (const polygon of geometry.coordinates) {
          pushCoords(polygon[0] as number[][]);
        }
      }

      if (!bounds.isEmpty()) {
        const center = bounds.getCenter();
        const el = document.createElement("div");
        el.style.width = "26px";
        el.style.height = "26px";
        el.style.borderRadius = "50%";
        el.style.background = "#0d413a";
        el.style.color = "#ffffff";
        el.style.display = "grid";
        el.style.placeItems = "center";
        el.style.fontWeight = "700";
        el.style.fontSize = "12px";
        el.style.border = "2px solid #fdf9f2";
        el.textContent = String(i + 1);

        const marker = new maplibregl.Marker({ element: el }).setLngLat(center).addTo(map);
        zoneLabelMarkersRef.current.push(marker);
      }
    }

    if (features.length > 0) {
      const fitBounds = new maplibregl.LngLatBounds();
      for (const marker of zoneLabelMarkersRef.current) {
        fitBounds.extend(marker.getLngLat());
      }
      if (!fitBounds.isEmpty()) {
        map.fitBounds(fitBounds, { padding: 60, duration: 500, maxZoom: 13 });
      }
    }
  }, [sortedZones]);

  const handleCancel = async () => {
    if (!jobId || isCancelling || isJobFinished) {
      return;
    }

    setIsCancelling(true);
    setError(null);
    setStatusMessage("Solicitando cancelamento...");
    try {
      const response = await fetch(`/api/jobs/${jobId}/cancel`, { method: "POST" });
      if (response.ok) {
        setStatusMessage("Cancelamento solicitado. Aguardando confirmacao do worker...");
      } else {
        setError("Falha ao cancelar. Tente novamente.");
        setStatusMessage("Nao foi possivel cancelar a geracao.");
        setIsCancelling(false);
      }
    } catch {
      setError("Falha ao cancelar. Tente novamente.");
      setStatusMessage("Nao foi possivel cancelar a geracao.");
      setIsCancelling(false);
    }
  };

  return (
    <div className="layout">
      <section className="panel etapa-panel">
        <div className="etapa-header">
          <p className="eyebrow">Fase 4 | M4.6</p>
          <h2>Etapa 3: Geracao de zonas</h2>
          <p className="panel-intro">Barra de progresso em tempo real e cancelamento ativo.</p>
        </div>

        {error && <p className="error-message">{error}</p>}

        <div className="progress-section">
          <div className="progress-header">
            <span className="progress-label">Progresso geral</span>
            <span className="progress-percent">{progressPercent}%</span>
          </div>
          <div className="progress-bar-container">
            <div className="progress-bar" style={{ width: `${progressPercent}%` }} />
          </div>
          <p className="progress-message" aria-live="polite">
            {statusMessage}
          </p>
        </div>

        <div className="zones-status">
          <h3 className="status-title">Zonas recebidas via SSE</h3>
          {sortedZones.length === 0 ? (
            <p className="status-empty">Aguardando primeira zona...</p>
          ) : (
            <div className="zones-list">
              {sortedZones.map((zone, index) => (
                <div key={zone.id} className="zone-item">
                  <div className="zone-badge">{index + 1}</div>
                  <div className="zone-details">
                    <strong>Zona {index + 1}</strong>
                    <p className="zone-meta">
                      {(zone.travel_time_minutes ?? 0)} min | {(zone.walk_distance_meters ?? 0)} m
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <button
          type="button"
          className="cancel-button"
          onClick={handleCancel}
          disabled={isCancelling || isJobFinished || !jobId}
        >
          {isCancelling ? "Cancelando..." : "Cancelar geracao"}
        </button>
      </section>

      <section className="panel map-panel">
        <div className="map-header">
          <h3>Mapa progressivo</h3>
          <p>Zonas aparecem no mapa conforme eventos `job.partial_result.ready`.</p>
        </div>
        <div ref={mapContainerRef} className="map-canvas" />
      </section>

      <style jsx>{`
        .layout {
          display: grid;
          grid-template-columns: minmax(320px, 460px) minmax(0, 1fr);
          gap: 20px;
          align-items: start;
        }

        @media (max-width: 1080px) {
          .layout {
            grid-template-columns: 1fr;
          }
        }

        .panel {
          background: var(--panel);
          border: 1px solid var(--line);
          border-radius: var(--radius-xl);
        }

        .etapa-panel {
          display: grid;
          gap: 18px;
          padding: 22px;
        }

        .map-panel {
          display: grid;
          gap: 10px;
          padding: 16px;
        }

        .map-header h3 {
          margin: 0;
          font-family: var(--font-display), sans-serif;
        }

        .map-header p {
          margin: 4px 0 0;
          color: var(--muted);
          font-size: 0.9rem;
        }

        .map-canvas {
          min-height: 70vh;
          border: 1px solid var(--line-strong);
          border-radius: 14px;
          overflow: hidden;
        }

        .eyebrow {
          margin: 0;
          color: var(--accent);
          font-size: 0.78rem;
          font-weight: 700;
          letter-spacing: 0.14em;
          text-transform: uppercase;
        }

        h2 {
          margin: 4px 0;
          font-family: var(--font-display), sans-serif;
          font-size: 1.6rem;
        }

        .panel-intro {
          margin: 0;
          color: var(--muted);
          font-size: 0.95rem;
          line-height: 1.45;
        }

        .error-message {
          margin: 0;
          padding: 10px 12px;
          background: rgba(159, 43, 34, 0.14);
          color: var(--danger);
          border-radius: var(--radius-md);
          font-size: 0.92rem;
        }

        .progress-section {
          display: grid;
          gap: 7px;
        }

        .progress-header {
          display: flex;
          justify-content: space-between;
          font-size: 0.9rem;
          font-weight: 600;
        }

        .progress-bar-container {
          width: 100%;
          height: 8px;
          background: rgba(38, 25, 12, 0.12);
          border-radius: 999px;
          overflow: hidden;
        }

        .progress-bar {
          height: 100%;
          background: linear-gradient(90deg, #145c52, #0d413a);
          transition: width 260ms ease;
        }

        .progress-message {
          margin: 0;
          color: var(--muted);
          font-size: 0.88rem;
          line-height: 1.4;
        }

        .zones-status {
          display: grid;
          gap: 10px;
        }

        .status-title {
          margin: 0;
          font-size: 0.95rem;
          font-weight: 600;
        }

        .status-empty {
          margin: 0;
          color: var(--muted);
          padding: 10px;
          text-align: center;
          border: 1px dashed var(--line);
          border-radius: 10px;
        }

        .zones-list {
          display: grid;
          gap: 8px;
          max-height: 260px;
          overflow: auto;
        }

        .zone-item {
          display: grid;
          grid-template-columns: auto 1fr;
          gap: 10px;
          align-items: center;
          padding: 10px;
          background: var(--accent-soft);
          border-radius: 10px;
        }

        .zone-badge {
          width: 28px;
          height: 28px;
          display: grid;
          place-items: center;
          border-radius: 50%;
          color: #fff;
          background: #0d413a;
          font-size: 0.82rem;
          font-weight: 700;
        }

        .zone-details strong {
          font-size: 0.92rem;
        }

        .zone-meta {
          margin: 2px 0 0;
          color: var(--muted);
          font-size: 0.82rem;
        }

        .cancel-button {
          margin-top: 2px;
          padding: 10px 12px;
          border-radius: 10px;
          border: 1px solid var(--line);
          background: transparent;
          font-weight: 600;
        }

        .cancel-button:hover:not(:disabled) {
          border-color: var(--danger);
          color: var(--danger);
        }

        .cancel-button:disabled {
          opacity: 0.55;
          cursor: not-allowed;
        }
      `}</style>
    </div>
  );
}
