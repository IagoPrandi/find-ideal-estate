"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useSSEEvents } from "../hooks/useSSEEvents";

export type Etapa4Props = {
  journeyId: string;
  onSelectZone?: (zoneFingerprint: string) => void;
};

type ZoneForComparison = {
  id: string;
  travel_time_minutes: number;
  walk_distance_meters: number;
  green_area_m2?: number;
  flood_area_m2?: number;
  safety_incidents_count?: number;
  poi_counts?: Record<string, number>;
  badges?: {
    green_badge?: { tier: string; percentile: number };
    flood_badge?: { tier: string; percentile: number };
    safety_badge?: { tier: string; percentile: number };
    poi_badge?: { tier: string; percentile: number };
  };
  badges_provisional?: boolean;
};

type ZonesComparisonResponse = {
  zones: ZoneForComparison[];
  total_count: number;
  completed_count: number;
};

type FilterState = {
  minTravelTime: number;
  maxTravelTime: number;
  minBadgePercentile: number;
};

export function Etapa4ZoneComparison({ journeyId, onSelectZone }: Etapa4Props) {
  const [zones, setZones] = useState<ZoneForComparison[]>([]);
  const [filteredZones, setFilteredZones] = useState<ZoneForComparison[]>([]);
  const [selectedZoneId, setSelectedZoneId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [badges_provisional, setBadgesProvisional] = useState(true);
  const [enrichmentJobId, setEnrichmentJobId] = useState<string | null>(null);
  const [isEnrichmentRunning, setIsEnrichmentRunning] = useState(false);
  const [enrichmentProgress, setEnrichmentProgress] = useState(0);
  const [enrichmentMessage, setEnrichmentMessage] = useState<string | null>(null);
  const [filters, setFilters] = useState<FilterState>({
    minTravelTime: 0,
    maxTravelTime: 90,
    minBadgePercentile: 0,
  });
  const enrichmentRequestedRef = useRef(false);
  const { addListener } = useSSEEvents(enrichmentJobId);

  const startZoneEnrichment = useCallback(async () => {
    if (enrichmentRequestedRef.current) {
      return;
    }

    enrichmentRequestedRef.current = true;
    setIsEnrichmentRunning(true);
    setEnrichmentProgress(0);
    setEnrichmentMessage("Iniciando enriquecimento das zonas...");

    try {
      const response = await fetch("/api/jobs", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          journey_id: journeyId,
          job_type: "zone_enrichment",
          current_stage: "zone_enrichment",
        }),
      });

      if (!response.ok) {
        throw new Error("Falha ao iniciar enriquecimento das zonas");
      }

      const job = await response.json();
      setEnrichmentJobId(job.id);
    } catch (e) {
      enrichmentRequestedRef.current = false;
      setIsEnrichmentRunning(false);
      setEnrichmentMessage(null);
      const message = e instanceof Error ? e.message : "Erro desconhecido";
      setError(message);
    }
  }, [journeyId]);

  const loadZones = useCallback(async () => {
    const response = await fetch(`/api/journeys/${journeyId}/zones`, { cache: "no-store" });
    if (!response.ok) {
      throw new Error("Falha ao carregar zonas");
    }

    const data = (await response.json()) as ZonesComparisonResponse;
    const zonesList = data.zones || [];

    const sorted = zonesList.sort(
      (a: ZoneForComparison, b: ZoneForComparison) =>
        a.travel_time_minutes - b.travel_time_minutes ||
        (a.walk_distance_meters || 0) - (b.walk_distance_meters || 0),
    );

    setZones(sorted);
    setFilteredZones(sorted);

    const hasProvisionalBadges = sorted.some((zone: ZoneForComparison) => zone.badges_provisional);
    const needsEnrichment = (data.total_count ?? sorted.length) > (data.completed_count ?? 0);

    setBadgesProvisional(hasProvisionalBadges || needsEnrichment);

    if (sorted.length > 0) {
      setSelectedZoneId((current) => current ?? sorted[0].id);
    }

    if (sorted.length > 0 && needsEnrichment && !enrichmentRequestedRef.current) {
      void startZoneEnrichment();
    }

    if (!needsEnrichment) {
      setIsEnrichmentRunning(false);
      setEnrichmentProgress(100);
      setEnrichmentMessage(null);
    }
  }, [journeyId, startZoneEnrichment]);

  // Load zones
  useEffect(() => {
    const initializeZones = async () => {
      try {
        await loadZones();
      } catch (e) {
        const message = e instanceof Error ? e.message : "Erro desconhecido";
        setError(message);
      } finally {
        setIsLoading(false);
      }
    };

    initializeZones();
  }, [loadZones]);

  useEffect(() => {
    if (!enrichmentJobId) {
      return;
    }

    const unregisterStarted = addListener("job.started", (event) => {
      if (event.data.stage !== "zone_enrichment") {
        return;
      }
      setIsEnrichmentRunning(true);
      setEnrichmentMessage(event.data.message ?? "Enriquecimento iniciado.");
    });

    const unregisterProgress = addListener("job.stage.progress", (event) => {
      if (event.data.stage !== "zone_enrichment") {
        return;
      }

      const progress = Number(event.data.payload_json?.progress_percent ?? 0);
      setEnrichmentProgress(Number.isFinite(progress) ? Math.max(0, Math.min(100, progress)) : 0);
      setEnrichmentMessage(event.data.message ?? "Atualizando indicadores das zonas...");
      setIsEnrichmentRunning(true);
    });

    const unregisterBadgeUpdate = addListener("zone.badges.updated", () => {
      void loadZones();
    });

    const unregisterFinalized = addListener("zones.badges.finalized", () => {
      void loadZones();
    });

    const unregisterCompleted = addListener("job.completed", (event) => {
      if (event.data.stage !== "zone_enrichment") {
        return;
      }

      setEnrichmentProgress(100);
      setIsEnrichmentRunning(false);
      setEnrichmentMessage("Badges finalizados.");
      void loadZones();
    });

    const unregisterFailed = addListener("job.failed", (event) => {
      if (event.data.stage !== "zone_enrichment") {
        return;
      }

      setIsEnrichmentRunning(false);
      enrichmentRequestedRef.current = false;
      setEnrichmentMessage(null);
      setError(event.data.message ?? "Falha ao enriquecer zonas.");
    });

    return () => {
      unregisterStarted();
      unregisterProgress();
      unregisterBadgeUpdate();
      unregisterFinalized();
      unregisterCompleted();
      unregisterFailed();
    };
  }, [addListener, enrichmentJobId, loadZones]);

  useEffect(() => {
    if (zones.length === 0 || !badges_provisional || enrichmentJobId || enrichmentRequestedRef.current) {
      return;
    }

    void startZoneEnrichment();
  }, [badges_provisional, enrichmentJobId, startZoneEnrichment, zones.length]);

  // Apply filters
  useEffect(() => {
    const filtered = zones.filter((zone) => {
      const travelTime = zone.travel_time_minutes ?? 0;
      const badgePercentile = Math.max(
        zone.badges?.green_badge?.percentile ?? 0,
        zone.badges?.flood_badge?.percentile ?? 0,
        zone.badges?.safety_badge?.percentile ?? 0,
        zone.badges?.poi_badge?.percentile ?? 0,
      );
      return (
        travelTime >= filters.minTravelTime &&
        travelTime <= filters.maxTravelTime &&
        badgePercentile >= filters.minBadgePercentile
      );
    });
    setFilteredZones(filtered);
  }, [zones, filters]);

  const badgeTierColor = (tier: string): string => {
    switch (tier) {
      case "excellent":
        return "#10b981"; // green
      case "good":
        return "#3b82f6"; // blue
      case "fair":
        return "#f59e0b"; // amber
      case "poor":
        return "#ef4444"; // red
      default:
        return "#6b7280"; // gray
    }
  };

  const badgeTierLabel = (tier: string): string => {
    switch (tier) {
      case "excellent":
        return "Excelente";
      case "good":
        return "Bom";
      case "fair":
        return "Regular";
      case "poor":
        return "Fraco";
      default:
        return tier;
    }
  };

  const selectedZone = zones.find((z) => z.id === selectedZoneId);

  return (
    <div className="etapa-panel">
      <div className="etapa-header">
        <p className="eyebrow">Fase 4 · M4.5</p>
        <h2>Etapa 4: Comparação de zonas</h2>
        <p className="panel-intro">
          {badges_provisional
            ? "Badges calculados com dados parciais"
            : "Comparar zonas e ver indicadores de qualidade urbana"}
        </p>
      </div>

      {error && <p className="error-message">{error}</p>}

      {isLoading && <p className="loading">Carregando zonas...</p>}

      {!isLoading && isEnrichmentRunning && (
        <div className="loading enrichment-status">
          <strong>{enrichmentMessage ?? "Enriquecendo zonas..."}</strong>
          <span>{enrichmentProgress}% concluido</span>
        </div>
      )}

      {!isLoading && zones.length === 0 && (
        <p className="empty-state">Nenhuma zona encontrada. Verifique a geração.</p>
      )}

      {!isLoading && zones.length > 0 && (
        <div className="comparison-layout">
          <div className="zones-column">
            <div className="filters-section">
              <h3 className="section-title">Filtros</h3>
              <div className="filter-group">
                <label className="filter-label">
                  Tempo máximo: {filters.maxTravelTime} min
                  <input
                    type="range"
                    min="10"
                    max="90"
                    value={filters.maxTravelTime}
                    onChange={(e) =>
                      setFilters({ ...filters, maxTravelTime: Number(e.target.value) })
                    }
                    className="filter-slider"
                  />
                </label>
                <label className="filter-label">
                  Badge minimo: {filters.minBadgePercentile}%
                  <input
                    type="range"
                    min="0"
                    max="100"
                    value={filters.minBadgePercentile}
                    onChange={(e) =>
                      setFilters({ ...filters, minBadgePercentile: Number(e.target.value) })
                    }
                    className="filter-slider"
                  />
                </label>
              </div>
            </div>

            <div className="zones-list-section">
              <h3 className="section-title">Zonas ({filteredZones.length})</h3>
              <div className="zones-list">
                {filteredZones.map((zone, index) => (
                  <button
                    key={zone.id}
                    type="button"
                    className={`zone-list-item ${selectedZoneId === zone.id ? "selected" : ""}`}
                    onClick={() => setSelectedZoneId(zone.id)}
                  >
                    <div className="zone-number">{index + 1}</div>
                    <div className="zone-list-info">
                      <strong>{zone.travel_time_minutes} min</strong>
                      <p className="zone-distance">{zone.walk_distance_meters || 0} m</p>
                    </div>
                    {zone.badges && (
                      <div className="zone-badges-compact">
                        {zone.badges.green_badge && (
                          <div
                            className="badge-dot"
                            style={{
                              backgroundColor: badgeTierColor(zone.badges.green_badge.tier),
                            }}
                            title={`Verde: ${badgeTierLabel(zone.badges.green_badge.tier)}`}
                          />
                        )}
                        {zone.badges.flood_badge && (
                          <div
                            className="badge-dot"
                            style={{
                              backgroundColor: badgeTierColor(zone.badges.flood_badge.tier),
                            }}
                            title={`Alagamento: ${badgeTierLabel(zone.badges.flood_badge.tier)}`}
                          />
                        )}
                      </div>
                    )}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="details-column">
            {selectedZone && (
              <>
                <div className="details-header">
                  <h3 className="section-title">Detalhes da zona</h3>
                </div>

                <div className="zone-details-grid">
                  <div className="detail-item">
                    <span className="detail-label">Tempo de viagem</span>
                    <span className="detail-value">{selectedZone.travel_time_minutes} min</span>
                  </div>
                  <div className="detail-item">
                    <span className="detail-label">Distância a pé</span>
                    <span className="detail-value">{selectedZone.walk_distance_meters || 0} m</span>
                  </div>
                </div>

                {selectedZone.badges && (
                  <div className="badges-section">
                    <h4 className="subsection-title">Indicadores</h4>
                    <div className="badges-grid">
                      {selectedZone.badges.green_badge && (
                        <div className="badge-card">
                          <div className="badge-header">
                            <span className="badge-name">Área Verde</span>
                            <span
                              className="badge-tier"
                              style={{ color: badgeTierColor(selectedZone.badges.green_badge.tier) }}
                            >
                              {badgeTierLabel(selectedZone.badges.green_badge.tier)}
                            </span>
                          </div>
                          <div className="badge-bar">
                            <div
                              className="badge-fill"
                              style={{
                                width: `${selectedZone.badges.green_badge.percentile}%`,
                                backgroundColor: badgeTierColor(selectedZone.badges.green_badge.tier),
                              }}
                            />
                          </div>
                          <p className="badge-meta">
                            {selectedZone.green_area_m2 ? `${(selectedZone.green_area_m2 / 1000000).toFixed(2)} km²` : "—"}
                          </p>
                        </div>
                      )}
                      {selectedZone.badges.safety_badge && (
                        <div className="badge-card">
                          <div className="badge-header">
                            <span className="badge-name">Segurança</span>
                            <span
                              className="badge-tier"
                              style={{ color: badgeTierColor(selectedZone.badges.safety_badge.tier) }}
                            >
                              {badgeTierLabel(selectedZone.badges.safety_badge.tier)}
                            </span>
                          </div>
                          <div className="badge-bar">
                            <div
                              className="badge-fill"
                              style={{
                                width: `${selectedZone.badges.safety_badge.percentile}%`,
                                backgroundColor: badgeTierColor(selectedZone.badges.safety_badge.tier),
                              }}
                            />
                          </div>
                          <p className="badge-meta">
                            {selectedZone.safety_incidents_count || 0} ocorrências
                          </p>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {selectedZone.poi_counts && Object.keys(selectedZone.poi_counts).length > 0 && (
                  <div className="pois-section">
                    <h4 className="subsection-title">POIs na zona</h4>
                    <div className="pois-grid">
                      {Object.entries(selectedZone.poi_counts).map(([category, count]) => (
                        <div key={category} className="poi-item">
                          <span className="poi-category">{category}</span>
                          <strong className="poi-count">{count}</strong>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <button
                  type="button"
                  className="primary-button"
                  disabled={!selectedZoneId}
                  onClick={() => {
                    if (selectedZoneId && onSelectZone) {
                      onSelectZone(selectedZoneId);
                    }
                  }}
                >
                  Buscar imóveis nesta zona
                </button>
              </>
            )}
          </div>
        </div>
      )}

      <style jsx>{`
        .etapa-panel {
          display: grid;
          gap: 24px;
          padding: 28px;
          background: var(--panel);
          border: 1px solid var(--line);
          border-radius: var(--radius-xl);
        }

        .etapa-header {
          display: grid;
          gap: 12px;
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
          margin: 0;
          font-family: var(--font-display), sans-serif;
          font-size: 1.8rem;
          font-weight: 700;
        }

        .panel-intro {
          margin: 0;
          color: var(--muted);
          font-size: 1rem;
          line-height: 1.5;
        }

        .error-message,
        .empty-state,
        .loading {
          padding: 16px;
          border-radius: var(--radius-md);
          text-align: center;
        }

        .enrichment-status {
          display: grid;
          gap: 6px;
          background: var(--accent-soft);
          color: var(--ink);
        }

        .error-message {
          background: rgba(159, 43, 34, 0.14);
          color: var(--danger);
        }

        .comparison-layout {
          display: grid;
          grid-template-columns: 1fr 1.5fr;
          gap: 24px;
        }

        @media (max-width: 1024px) {
          .comparison-layout {
            grid-template-columns: 1fr;
          }
        }

        .zones-column,
        .details-column {
          display: grid;
          gap: 20px;
        }

        .section-title {
          margin: 0;
          font-size: 1rem;
          font-weight: 600;
        }

        .filters-section {
          display: grid;
          gap: 12px;
          padding: 16px;
          background: var(--accent-soft);
          border-radius: var(--radius-md);
        }

        .filter-group {
          display: grid;
          gap: 8px;
        }

        .filter-label {
          display: flex;
          flex-direction: column;
          gap: 8px;
          font-size: 0.95rem;
          font-weight: 500;
        }

        .filter-slider {
          width: 100%;
          cursor: pointer;
        }

        .zones-list-section {
          display: grid;
          gap: 12px;
        }

        .zones-list {
          display: grid;
          gap: 8px;
          max-height: 400px;
          overflow-y: auto;
        }

        .zone-list-item {
          display: grid;
          grid-template-columns: auto 1fr auto;
          gap: 12px;
          align-items: center;
          padding: 12px;
          border: 1px solid var(--line);
          border-radius: var(--radius-md);
          background: transparent;
          cursor: pointer;
          transition: all 200ms ease;
        }

        .zone-list-item:hover {
          border-color: var(--accent);
          background: var(--accent-soft);
        }

        .zone-list-item.selected {
          border-color: var(--accent-strong);
          background: var(--accent-soft);
          font-weight: 600;
        }

        .zone-number {
          min-width: 28px;
          height: 28px;
          display: flex;
          align-items: center;
          justify-content: center;
          background: var(--line);
          border-radius: 50%;
          font-size: 0.85rem;
          font-weight: 600;
        }

        .zone-list-item.selected .zone-number {
          background: var(--accent);
          color: var(--panel);
        }

        .zone-list-info {
          display: grid;
          gap: 2px;
        }

        .zone-list-info strong {
          margin: 0;
          font-size: 0.95rem;
        }

        .zone-distance {
          margin: 0;
          font-size: 0.8rem;
          color: var(--muted);
        }

        .zone-badges-compact {
          display: flex;
          gap: 4px;
        }

        .badge-dot {
          width: 12px;
          height: 12px;
          border-radius: 50%;
          opacity: 0.8;
        }

        .details-header {
          padding-bottom: 12px;
          border-bottom: 1px solid var(--line);
        }

        .zone-details-grid {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 12px;
        }

        .detail-item {
          padding: 12px;
          background: var(--accent-soft);
          border-radius: var(--radius-md);
          display: grid;
          gap: 4px;
        }

        .detail-label {
          font-size: 0.85rem;
          color: var(--muted);
          font-weight: 500;
        }

        .detail-value {
          font-size: 1.2rem;
          font-weight: 700;
        }

        .badges-section {
          display: grid;
          gap: 12px;
        }

        .subsection-title {
          margin: 0;
          font-size: 0.95rem;
          font-weight: 600;
        }

        .badges-grid {
          display: grid;
          gap: 12px;
        }

        .badge-card {
          padding: 12px;
          border: 1px solid var(--line);
          border-radius: var(--radius-md);
          display: grid;
          gap: 8px;
        }

        .badge-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
        }

        .badge-name {
          font-size: 0.95rem;
          font-weight: 600;
        }

        .badge-tier {
          font-size: 0.85rem;
          font-weight: 600;
        }

        .badge-bar {
          width: 100%;
          height: 6px;
          background: var(--line);
          border-radius: var(--radius-sm);
          overflow: hidden;
        }

        .badge-fill {
          height: 100%;
          transition: width 300ms ease;
        }

        .badge-meta {
          margin: 0;
          font-size: 0.8rem;
          color: var(--muted);
        }

        .pois-section {
          display: grid;
          gap: 12px;
        }

        .pois-grid {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 8px;
        }

        .poi-item {
          padding: 8px;
          background: var(--accent-soft);
          border-radius: var(--radius-md);
          display: flex;
          justify-content: space-between;
          align-items: center;
        }

        .poi-category {
          font-size: 0.85rem;
          color: var(--muted);
        }

        .poi-count {
          font-size: 1rem;
          color: var(--accent-strong);
        }

        .primary-button {
          padding: 12px 24px;
          background: var(--accent);
          color: var(--panel);
          border: none;
          border-radius: var(--radius-md);
          font-weight: 600;
          cursor: pointer;
          width: 100%;
          transition: background 200ms ease;
        }

        .primary-button:hover {
          background: var(--accent-strong);
        }
      `}</style>
    </div>
  );
}
