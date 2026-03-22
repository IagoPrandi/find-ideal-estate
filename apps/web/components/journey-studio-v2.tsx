"use client";

import { ChangeEvent, useMemo, useState } from "react";
import { MapShell } from "./map-shell";
import { Etapa2TransportSelection } from "./etapa2-transport";
import { Etapa3ZoneGeneration } from "./etapa3-zones";
import { Etapa4ZoneComparison } from "./etapa4-comparison";
import { Etapa5ListingsSearch } from "./etapa5-listings-search";
import { Etapa6Listings } from "./etapa6-listings";

type PointTarget = "primary" | "secondary";
type HousingMode = "rent" | "buy";
type TravelMode = "transit" | "walking" | "car";
type AnalysisKey = "green" | "flood" | "safety" | "pois";
type EtapaStep = 1 | 2 | 3 | 4 | 5 | 6;

type PointForm = {
  lat: string;
  lon: string;
  label: string;
};

type JourneyResponse = {
  id: string;
  state: string;
  anonymous_session_id?: string | null;
};

const INITIAL_PRIMARY: PointForm = {
  lat: "",
  lon: "",
  label: "Referência principal",
};

const INITIAL_SECONDARY: PointForm = {
  lat: "",
  lon: "",
  label: "Trabalho ou escola",
};

const numberFromText = (value: string) => {
  if (!value.trim()) {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

export function JourneyStudio() {
  const [currentEtapa, setCurrentEtapa] = useState<EtapaStep>(1);
  const [journeyId, setJourneyId] = useState<string | null>(null);
  const [selectedTransportPointIds, setSelectedTransportPointIds] = useState<string[]>([]);
  const [selectedZoneFingerprint, setSelectedZoneFingerprint] = useState<string | null>(null);
  const [listingsResult, setListingsResult] = useState<{
    listings: unknown[];
    total_count: number;
    cache_age_hours?: number;
    freshness_status?: string;
    job_id?: string;
  } | null>(null);

  const [primaryPoint, setPrimaryPoint] = useState<PointForm>(INITIAL_PRIMARY);
  const [secondaryPoint, setSecondaryPoint] = useState<PointForm>(INITIAL_SECONDARY);
  const [activePointTarget, setActivePointTarget] = useState<PointTarget>("primary");
  const [housingMode, setHousingMode] = useState<HousingMode>("rent");
  const [travelMode, setTravelMode] = useState<TravelMode>("transit");
  const [zoneRadiusMeters, setZoneRadiusMeters] = useState(900);
  const [maxTravelMinutes, setMaxTravelMinutes] = useState(30);
  const [seedDistanceMeters, setSeedDistanceMeters] = useState(500);
  const [analyses, setAnalyses] = useState<Record<AnalysisKey, boolean>>({
    green: true,
    flood: true,
    safety: true,
    pois: true,
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const primaryPreview = useMemo(() => {
    const lat = numberFromText(primaryPoint.lat);
    const lon = numberFromText(primaryPoint.lon);
    if (lat === null || lon === null) return null;
    return { lat, lon, label: primaryPoint.label || "Referência principal" };
  }, [primaryPoint]);

  const secondaryPreview = useMemo(() => {
    const lat = numberFromText(secondaryPoint.lat);
    const lon = numberFromText(secondaryPoint.lon);
    if (lat === null || lon === null) return null;
    return { lat, lon, label: secondaryPoint.label || "Ponto secundário" };
  }, [secondaryPoint]);

  const handlePointPick = (target: PointTarget, coords: { lat: number; lon: number }) => {
    const patch = { lat: coords.lat.toFixed(6), lon: coords.lon.toFixed(6) };
    if (target === "primary") {
      setPrimaryPoint((c) => ({ ...c, ...patch }));
    } else {
      setSecondaryPoint((c) => ({ ...c, ...patch }));
    }
  };

  const updatePointField = (target: PointTarget, field: keyof PointForm, value: string) => {
    if (target === "primary") {
      setPrimaryPoint((c) => ({ ...c, [field]: value }));
    } else {
      setSecondaryPoint((c) => ({ ...c, [field]: value }));
    }
  };

  const toggleAnalysis = (key: AnalysisKey) => {
    setAnalyses((c) => ({ ...c, [key]: !c[key] }));
  };

  const handleEtapa1Submit = async () => {
    setSubmitError(null);
    const primaryLat = numberFromText(primaryPoint.lat);
    const primaryLon = numberFromText(primaryPoint.lon);
    if (primaryLat === null || primaryLon === null) {
      setSubmitError("Defina um ponto principal válido antes de continuar.");
      return;
    }

    const payload = {
      input_snapshot: {
        step: 1,
        reference_point: { lat: primaryLat, lon: primaryLon, label: primaryPoint.label || "Referência principal" },
        property_mode: housingMode,
        travel_mode: travelMode,
        zone_radius_meters: zoneRadiusMeters,
        max_travel_minutes: maxTravelMinutes,
        seed_search_distance_meters: seedDistanceMeters,
        analyses,
      },
      secondary_reference_label: secondaryPreview?.label ?? null,
      secondary_reference_point: secondaryPreview ? { lat: secondaryPreview.lat, lon: secondaryPreview.lon } : null,
    };

    setIsSubmitting(true);
    try {
      const res = await fetch("/api/journeys", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = (await res.json()) as JourneyResponse | { detail?: string };
      if (!res.ok) throw new Error("detail" in data && data.detail ? data.detail : "Erro ao criar jornada.");
      const journey = data as JourneyResponse;
      setJourneyId(journey.id);
      setCurrentEtapa(2);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Falha inesperada.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleEtapa2Next = (ids: string[]) => { setSelectedTransportPointIds(ids); setCurrentEtapa(3); };
  const handleEtapa3Next = () => { setCurrentEtapa(4); };
  const handleEtapa4SelectZone = (fp: string) => { setSelectedZoneFingerprint(fp); setCurrentEtapa(5); };
  const handleListingsReady = (result: {
    listings: unknown[]; total_count: number;
    cache_age_hours?: number; freshness_status?: string; job_id?: string;
  }) => { setListingsResult(result); setCurrentEtapa(6); };

  return (
    <main className="app">
      {/* Map — always visible, always full screen */}
      <section className="mapArea">
        <MapShell
          primaryPoint={primaryPreview}
          secondaryPoint={secondaryPreview}
          activePointTarget={activePointTarget}
          onPickPoint={handlePointPick}
        />
      </section>

      {/* Panel — right sidebar */}
      <aside className="panel">
        <div className="panelScroll">
          {currentEtapa === 1 && (
            <>
              <div className="panelHeader">
                <h1 className="panelTitle">Ponto de Referência</h1>
              </div>

              {/* Primary point */}
              <div className="section">
                <div className="sectionHeader">
                  <span className="sectionIcon">📍</span>
                  <h2 className="sectionTitle">Ponto Principal</h2>
                </div>
                <p className="hint">
                  Clique no mapa em &quot;{activePointTarget === "primary" ? "Definir principal" : "Adicionar Interesse"}&quot;.
                </p>

                <div className="btnRow">
                  <button
                    className={`toggleBtn ${activePointTarget === "primary" ? "toggleBtnActive" : ""}`}
                    type="button"
                    onClick={() => setActivePointTarget("primary")}
                  >
                    Definir principal
                  </button>
                  <button
                    className={`toggleBtn ${activePointTarget === "secondary" ? "toggleBtnActive" : ""}`}
                    type="button"
                    onClick={() => setActivePointTarget("secondary")}
                  >
                    Adicionar Interesse
                  </button>
                </div>

                {primaryPreview && (
                  <div className="coordDisplay">
                    <span>Lat: {primaryPreview.lat.toFixed(5)}</span>
                    <span>Lon: {primaryPreview.lon.toFixed(5)}</span>
                  </div>
                )}
                {!primaryPreview && (
                  <button className="outlineBtn" type="button" onClick={() => setActivePointTarget("primary")}>
                    Usar centro atual
                  </button>
                )}
              </div>

              {/* Secondary point (minimized) */}
              <div className="section">
                <div className="sectionHeader">
                  <h2 className="sectionTitle">Interesses (opcional)</h2>
                </div>
                <p className="hint">
                  Clique em &quot;Adicionar Interesse&quot; para abrir o mapa e marcar pontos de interesse.
                </p>
                {secondaryPreview && (
                  <div className="coordDisplay">
                    <span>Lat: {secondaryPreview.lat.toFixed(5)}</span>
                    <span>Lon: {secondaryPreview.lon.toFixed(5)}</span>
                  </div>
                )}
              </div>

              <div className="divider" />

              {/* Housing mode */}
              <div className="section">
                <h2 className="sectionTitle">Tipo de busca</h2>
                <div className="segRow">
                  <button
                    className={`segBtn ${housingMode === "rent" ? "segBtnActive" : ""}`}
                    type="button"
                    onClick={() => setHousingMode("rent")}
                  >
                    Alugar
                  </button>
                  <button
                    className={`segBtn ${housingMode === "buy" ? "segBtnActive" : ""}`}
                    type="button"
                    onClick={() => setHousingMode("buy")}
                  >
                    Comprar
                  </button>
                </div>
              </div>

              {/* Zone radius */}
              <div className="section">
                <h2 className="sectionTitle">Raio da zona (visual)</h2>
                <p className="hint">Ajuste o raio dos círculos exibidos no mapa antes de gerar as zonas ({zoneRadiusMeters} m).</p>
                <div className="sliderRow">
                  <input
                    className="slider"
                    type="range"
                    min={300}
                    max={2500}
                    step={50}
                    value={zoneRadiusMeters}
                    onChange={(e: ChangeEvent<HTMLInputElement>) => setZoneRadiusMeters(Number(e.target.value))}
                  />
                  <span className="sliderValue">{zoneRadiusMeters}<small> m</small></span>
                </div>
              </div>

              {/* Transport config */}
              <div className="section">
                <h2 className="sectionTitle">Transporte (configuração)</h2>
                <p className="hint">
                  Defina tempo máximo de viagem e distância máxima para buscar seeds de ônibus e trem/metrô.
                </p>

                <label className="fieldLabel">
                  Tempo máximo de viagem (min)
                  <div className="sliderRow">
                    <input
                      className="slider"
                      type="range"
                      min={10}
                      max={90}
                      step={5}
                      value={maxTravelMinutes}
                      onChange={(e: ChangeEvent<HTMLInputElement>) => setMaxTravelMinutes(Number(e.target.value))}
                    />
                    <span className="sliderValue">{maxTravelMinutes}</span>
                  </div>
                </label>

                <label className="fieldLabel">
                  Distância máxima seed ônibus (m)
                  <div className="sliderRow">
                    <input
                      className="slider"
                      type="range"
                      min={100}
                      max={1600}
                      step={50}
                      value={seedDistanceMeters}
                      onChange={(e: ChangeEvent<HTMLInputElement>) => setSeedDistanceMeters(Number(e.target.value))}
                    />
                    <span className="sliderValue">{seedDistanceMeters}</span>
                  </div>
                </label>

                <label className="fieldLabel">
                  Distância máxima seed trem/metrô (m)
                  <div className="sliderRow">
                    <input className="slider" type="range" min={300} max={3000} step={100} value={1200} readOnly />
                    <span className="sliderValue">1200</span>
                  </div>
                </label>
              </div>

              <div className="divider" />

              {/* Analysis toggles */}
              <div className="section">
                <h2 className="sectionTitle">Análises</h2>
                <div className="analysisGrid">
                  {([
                    { key: "green" as AnalysisKey, label: "Área verde" },
                    { key: "flood" as AnalysisKey, label: "Alagamento" },
                    { key: "safety" as AnalysisKey, label: "Segurança" },
                    { key: "pois" as AnalysisKey, label: "POIs" },
                  ]).map((item) => (
                    <label key={item.key} className="checkItem">
                      <input
                        type="checkbox"
                        checked={analyses[item.key]}
                        onChange={() => toggleAnalysis(item.key)}
                      />
                      {item.label}
                    </label>
                  ))}
                </div>
              </div>

              {/* Submit */}
              {submitError && <div className="errorMsg">{submitError}</div>}

              <button
                className="primaryBtn"
                type="button"
                onClick={handleEtapa1Submit}
                disabled={isSubmitting || !primaryPreview}
              >
                {isSubmitting ? "Criando jornada..." : "Criar jornada e continuar →"}
              </button>
            </>
          )}

          {currentEtapa === 2 && journeyId && (
            <Etapa2TransportSelection journeyId={journeyId} onNext={handleEtapa2Next} />
          )}
          {currentEtapa === 3 && journeyId && (
            <Etapa3ZoneGeneration
              journeyId={journeyId}
              selectedTransportPointIds={selectedTransportPointIds}
              onNext={handleEtapa3Next}
            />
          )}
          {currentEtapa === 4 && journeyId && (
            <Etapa4ZoneComparison journeyId={journeyId} onSelectZone={handleEtapa4SelectZone} />
          )}
          {currentEtapa === 5 && journeyId && selectedZoneFingerprint && (
            <Etapa5ListingsSearch
              journeyId={journeyId}
              zoneFingerprint={selectedZoneFingerprint}
              zoneLabel={selectedZoneFingerprint}
              searchType={housingMode}
              onListingsReady={handleListingsReady}
            />
          )}
          {currentEtapa === 6 && journeyId && selectedZoneFingerprint && (
            <Etapa6Listings
              journeyId={journeyId}
              zoneFingerprint={selectedZoneFingerprint}
              searchType={housingMode}
              initialListings={listingsResult?.listings as import("./etapa6-listings").Etapa6Props["initialListings"]}
              cacheAgeHours={listingsResult?.cache_age_hours}
              freshnessStatus={listingsResult?.freshness_status}
              jobId={listingsResult?.job_id}
            />
          )}
        </div>
      </aside>

      <style jsx>{`
        .app {
          display: flex;
          height: 100vh;
          width: 100%;
          overflow: hidden;
        }

        .mapArea {
          position: relative;
          flex: 1;
          min-width: 0;
          height: 100%;
          background: #e5e3df;
        }

        .panel {
          width: 400px;
          height: 100%;
          background: var(--color-panel);
          border-left: 1px solid var(--color-border);
          box-shadow: -4px 0 24px rgba(15, 23, 42, 0.06);
          flex-shrink: 0;
        }

        @media (max-width: 1024px) {
          .app {
            flex-direction: column;
          }
          .mapArea {
            height: 55vh;
          }
          .panel {
            width: 100%;
            height: 45vh;
            border-left: none;
            border-top: 1px solid var(--color-border);
          }
        }

        .panelScroll {
          height: 100%;
          overflow-y: auto;
          padding: 24px 20px;
          display: flex;
          flex-direction: column;
          gap: 16px;
        }

        .panelHeader {
          margin-bottom: 4px;
        }

        .panelTitle {
          margin: 0;
          font-size: 1.25rem;
          font-weight: 700;
          color: var(--color-text);
        }

        .section {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }

        .sectionHeader {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .sectionIcon {
          font-size: 1rem;
        }

        .sectionTitle {
          margin: 0;
          font-size: 0.95rem;
          font-weight: 600;
          color: var(--color-text);
        }

        .hint {
          margin: 0;
          font-size: 0.82rem;
          color: var(--color-muted);
          line-height: 1.4;
        }

        .divider {
          height: 1px;
          background: var(--color-border);
          margin: 4px 0;
        }

        .btnRow {
          display: flex;
          gap: 8px;
        }

        .toggleBtn {
          flex: 1;
          padding: 8px 12px;
          border: 1px solid var(--color-border);
          background: var(--color-panel);
          border-radius: var(--radius-md);
          font-size: 0.82rem;
          font-weight: 500;
          color: var(--color-muted);
          transition: all 150ms;
        }

        .toggleBtn:hover {
          border-color: var(--color-primary);
          color: var(--color-primary);
        }

        .toggleBtnActive {
          border-color: var(--color-primary);
          background: var(--color-primary);
          color: white;
        }

        .coordDisplay {
          display: flex;
          gap: 16px;
          font-size: 0.82rem;
          color: var(--color-muted);
          font-variant-numeric: tabular-nums;
        }

        .outlineBtn {
          padding: 8px 14px;
          border: 1px solid var(--color-border);
          background: transparent;
          border-radius: var(--radius-md);
          font-size: 0.82rem;
          font-weight: 500;
          color: var(--color-muted);
          transition: all 150ms;
        }

        .outlineBtn:hover {
          border-color: var(--color-primary);
          color: var(--color-primary);
        }

        .segRow {
          display: flex;
          gap: 8px;
        }

        .segBtn {
          padding: 7px 16px;
          border: 1px solid var(--color-border);
          background: var(--color-panel);
          border-radius: var(--radius-sm);
          font-size: 0.82rem;
          font-weight: 600;
          color: var(--color-text);
          transition: all 150ms;
        }

        .segBtn:hover:not(:disabled) {
          border-color: var(--color-primary);
        }

        .segBtnActive {
          background: var(--color-primary);
          border-color: var(--color-primary);
          color: white;
        }

        .fieldLabel {
          display: flex;
          flex-direction: column;
          gap: 6px;
          font-size: 0.82rem;
          font-weight: 500;
          color: var(--color-muted);
        }

        .sliderRow {
          display: flex;
          align-items: center;
          gap: 12px;
        }

        .slider {
          flex: 1;
          accent-color: var(--color-primary);
          cursor: pointer;
        }

        .sliderValue {
          min-width: 50px;
          text-align: right;
          font-size: 0.9rem;
          font-weight: 700;
          color: var(--color-text);
          font-variant-numeric: tabular-nums;
        }

        .sliderValue small {
          font-weight: 400;
          color: var(--color-muted);
        }

        .analysisGrid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 8px;
        }

        .checkItem {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 0.85rem;
          font-weight: 500;
          color: var(--color-text);
          cursor: pointer;
        }

        .checkItem input[type="checkbox"] {
          accent-color: var(--color-primary);
          width: 16px;
          height: 16px;
        }

        .errorMsg {
          padding: 10px 12px;
          border-radius: var(--radius-sm);
          background: rgba(220, 38, 38, 0.08);
          color: var(--color-danger);
          font-size: 0.85rem;
          border: 1px solid rgba(220, 38, 38, 0.2);
        }

        .primaryBtn {
          width: 100%;
          padding: 12px 24px;
          background: var(--color-primary);
          color: white;
          border: none;
          border-radius: var(--radius-md);
          font-weight: 600;
          font-size: 0.95rem;
          transition: background 150ms;
          margin-top: 4px;
        }

        .primaryBtn:hover:not(:disabled) {
          background: var(--color-primary-hover);
        }

        .primaryBtn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
      `}</style>
    </main>
  );
}
