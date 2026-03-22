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
  // Etapa state
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

  // Etapa 1 state
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
  const [statusMessage, setStatusMessage] = useState(
    "Selecione o ponto principal no mapa ou informe as coordenadas.",
  );
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const primaryPreview = useMemo(() => {
    const lat = numberFromText(primaryPoint.lat);
    const lon = numberFromText(primaryPoint.lon);
    if (lat === null || lon === null) {
      return null;
    }
    return { lat, lon, label: primaryPoint.label || "Referência principal" };
  }, [primaryPoint]);

  const secondaryPreview = useMemo(() => {
    const lat = numberFromText(secondaryPoint.lat);
    const lon = numberFromText(secondaryPoint.lon);
    if (lat === null || lon === null) {
      return null;
    }
    return { lat, lon, label: secondaryPoint.label || "Ponto secundário" };
  }, [secondaryPoint]);

  const handlePointPick = (target: PointTarget, coords: { lat: number; lon: number }) => {
    const patch = {
      lat: coords.lat.toFixed(6),
      lon: coords.lon.toFixed(6),
    };

    if (target === "primary") {
      setPrimaryPoint((current) => ({ ...current, ...patch }));
      setStatusMessage("Ponto principal atualizado a partir do mapa.");
      return;
    }

    setSecondaryPoint((current) => ({ ...current, ...patch }));
    setStatusMessage("Ponto secundário atualizado a partir do mapa.");
  };

  const updatePointField = (target: PointTarget, field: keyof PointForm, value: string) => {
    if (target === "primary") {
      setPrimaryPoint((current) => ({ ...current, [field]: value }));
      return;
    }
    setSecondaryPoint((current) => ({ ...current, [field]: value }));
  };

  const toggleAnalysis = (analysis: AnalysisKey) => {
    setAnalyses((current) => ({ ...current, [analysis]: !current[analysis] }));
  };

  const handleEtapa1Submit = async () => {
    setSubmitError(null);

    const primaryLat = numberFromText(primaryPoint.lat);
    const primaryLon = numberFromText(primaryPoint.lon);

    if (primaryLat === null || primaryLon === null) {
      setSubmitError("Defina um ponto principal válido antes de criar a jornada.");
      return;
    }

    const payload = {
      input_snapshot: {
        step: 1,
        reference_point: {
          lat: primaryLat,
          lon: primaryLon,
          label: primaryPoint.label || "Referência principal",
        },
        property_mode: housingMode,
        travel_mode: travelMode,
        zone_radius_meters: zoneRadiusMeters,
        max_travel_minutes: maxTravelMinutes,
        seed_search_distance_meters: seedDistanceMeters,
        analyses,
      },
      secondary_reference_label: secondaryPreview?.label ?? null,
      secondary_reference_point: secondaryPreview
        ? {
            lat: secondaryPreview.lat,
            lon: secondaryPreview.lon,
          }
        : null,
    };

    setIsSubmitting(true);
    setStatusMessage("Persistindo configuração inicial da jornada...");

    try {
      const response = await fetch("/api/journeys", {
        method: "POST",
        headers: {
          "content-type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      const data = (await response.json()) as JourneyResponse | { detail?: string };
      if (!response.ok) {
        throw new Error(
          "detail" in data && data.detail ? data.detail : "A API recusou a criação da jornada.",
        );
      }

      const journey = data as JourneyResponse;
      setJourneyId(journey.id);
      setCurrentEtapa(2);
      setStatusMessage("Jornada criada com sucesso. Avançando para Etapa 2...");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Falha inesperada ao criar a jornada.";
      setSubmitError(message);
      setStatusMessage("Não foi possível salvar a jornada. Revise os campos e tente novamente.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleEtapa2Next = (selectedIds: string[]) => {
    setSelectedTransportPointIds(selectedIds);
    setCurrentEtapa(3);
  };

  const handleEtapa3Next = () => {
    setCurrentEtapa(4);
  };

  const handleEtapa4SelectZone = (fingerprint: string) => {
    setSelectedZoneFingerprint(fingerprint);
    setCurrentEtapa(5);
  };

  const handleListingsReady = (result: {
    listings: unknown[];
    total_count: number;
    cache_age_hours?: number;
    freshness_status?: string;
    job_id?: string;
  }) => {
    setListingsResult(result);
    setCurrentEtapa(6);
  };

  const pointCard = (title: string, target: PointTarget, values: PointForm, hint: string) => (
    <div className="card pointCard">
      <div className="pointCardHeader">
        <div>
          <p className="eyebrow">{title}</p>
          <h3>{hint}</h3>
        </div>
        <button
          className={`ghostButton ${activePointTarget === target ? "ghostButtonActive" : ""}`}
          type="button"
          onClick={() => setActivePointTarget(target)}
        >
          {activePointTarget === target ? "Clique ativo" : "Definir no mapa"}
        </button>
      </div>

      <label className="fieldLabel">
        Nome exibido
        <input
          className="fieldInput"
          value={values.label}
          onChange={(event) => updatePointField(target, "label", event.target.value)}
          placeholder="Ex.: Escritório na Paulista"
        />
      </label>

      <div className="fieldGrid compactGrid">
        <label className="fieldLabel">
          Latitude
          <input
            className="fieldInput"
            value={values.lat}
            onChange={(event) => updatePointField(target, "lat", event.target.value)}
            inputMode="decimal"
            placeholder="-23.550520"
          />
        </label>
        <label className="fieldLabel">
          Longitude
          <input
            className="fieldInput"
            value={values.lon}
            onChange={(event) => updatePointField(target, "lon", event.target.value)}
            inputMode="decimal"
            placeholder="-46.633308"
          />
        </label>
      </div>
    </div>
  );

  return (
    <main className="shell">
      {currentEtapa === 1 && (
        <>
          <section className="hero card">
            <div>
              <p className="eyebrow">Fase 3 · M3.1</p>
              <h1>Etapa 1: Configuração inicial da jornada</h1>
            </div>
            <p className="heroCopy">
              Defina seu ponto de referência no mapa e configure os parâmetros de busca. Todos os dados são salvos
              automaticamente.
            </p>
          </section>

          <section className="studioLayout">
            <div className="mapColumn card">
              <div className="mapHeader">
                <div>
                  <p className="eyebrow">Mapa vivo</p>
                  <h2>
                    {activePointTarget === "primary"
                      ? "Clique para definir a referência principal"
                      : "Clique para definir o ponto secundário"}
                  </h2>
                </div>
                <p className="mapHint">Centro inicial em São Paulo. O painel permanece responsivo.</p>
              </div>

              <MapShell
                primaryPoint={primaryPreview}
                secondaryPoint={secondaryPreview}
                activePointTarget={activePointTarget}
                onPickPoint={handlePointPick}
              />

              <div className="statusRibbon">
                <strong>Status:</strong>
                <span>{statusMessage}</span>
              </div>
            </div>

            <aside className="panelColumn">
              <section className="card">
                <p className="eyebrow">Configuração inicial</p>
                <h2>Defina os parâmetros</h2>
                <p className="panelIntro">Configure tempo máximo de deslocamento e análises desejadas.</p>

                <div className="segmentedRow" role="radiogroup" aria-label="Tipo de busca">
                  {[
                    { key: "rent", label: "Aluguel" },
                    { key: "buy", label: "Compra" },
                  ].map((option) => (
                    <button
                      key={option.key}
                      type="button"
                      className={`segmentButton ${housingMode === option.key ? "segmentButtonActive" : ""}`}
                      onClick={() => setHousingMode(option.key as HousingMode)}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>

                <div className="segmentedRow" role="radiogroup" aria-label="Modal de deslocamento">
                  {[
                    { key: "transit", label: "Transporte público", disabled: false },
                    { key: "walking", label: "A pé", disabled: false },
                    { key: "car", label: "Carro · Pro", disabled: true },
                  ].map((option) => (
                    <button
                      key={option.key}
                      type="button"
                      className={`segmentButton ${travelMode === option.key ? "segmentButtonActive" : ""}`}
                      onClick={() => !option.disabled && setTravelMode(option.key as TravelMode)}
                      disabled={option.disabled}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>

                <div className="fieldGrid">
                  <label className="fieldLabel">
                    Raio da zona (m)
                    <input
                      className="fieldInput"
                      type="range"
                      min={300}
                      max={2500}
                      step={50}
                      value={zoneRadiusMeters}
                      onChange={(event: ChangeEvent<HTMLInputElement>) =>
                        setZoneRadiusMeters(Number(event.target.value))
                      }
                    />
                    <span className="fieldValue">{zoneRadiusMeters} m</span>
                  </label>

                  <label className="fieldLabel">
                    Tempo máximo
                    <input
                      className="fieldInput"
                      type="range"
                      min={10}
                      max={90}
                      step={5}
                      value={maxTravelMinutes}
                      onChange={(event: ChangeEvent<HTMLInputElement>) =>
                        setMaxTravelMinutes(Number(event.target.value))
                      }
                    />
                    <span className="fieldValue">{maxTravelMinutes} min</span>
                  </label>

                  <label className="fieldLabel">
                    Distância ao seed
                    <input
                      className="fieldInput"
                      type="range"
                      min={100}
                      max={1600}
                      step={50}
                      value={seedDistanceMeters}
                      onChange={(event: ChangeEvent<HTMLInputElement>) =>
                        setSeedDistanceMeters(Number(event.target.value))
                      }
                    />
                    <span className="fieldValue">{seedDistanceMeters} m</span>
                  </label>
                </div>

                <div className="analysisGrid" aria-label="Análises ativadas">
                  {[
                    { key: "green", title: "Área verde", note: "Vegetação e respiro urbano" },
                    { key: "flood", title: "Alagamento", note: "Manchas e exposição hídrica" },
                    { key: "safety", title: "Segurança", note: "Ocorrências e leitura pública" },
                    { key: "pois", title: "POIs", note: "Supermercados, parques, farmácias" },
                  ].map((item) => (
                    <button
                      key={item.key}
                      type="button"
                      className={`analysisCard ${analyses[item.key as AnalysisKey] ? "analysisCardActive" : ""}`}
                      onClick={() => toggleAnalysis(item.key as AnalysisKey)}
                    >
                      <strong>{item.title}</strong>
                      <span>{item.note}</span>
                    </button>
                  ))}
                </div>
              </section>

              {pointCard("Referência principal", "primary", primaryPoint, "Origem da análise")}
              {pointCard("Referência secundária", "secondary", secondaryPoint, "Opcional para contexto")}

              <section className="card submitCard">
                <div>
                  <p className="eyebrow">Persistência</p>
                  <h2>Salvar Etapa 1</h2>
                </div>

                {submitError && <p className="feedback feedbackError">{submitError}</p>}

                <button
                  className="primaryButton"
                  type="button"
                  onClick={handleEtapa1Submit}
                  disabled={isSubmitting}
                >
                  {isSubmitting ? "Salvando jornada..." : "Criar jornada e continuar"}
                </button>
              </section>
            </aside>
          </section>
        </>
      )}

      {currentEtapa === 2 && journeyId && (
        <div className="etapa-container">
          <Etapa2TransportSelection journeyId={journeyId} onNext={handleEtapa2Next} />
        </div>
      )}

      {currentEtapa === 3 && journeyId && (
        <div className="etapa-container">
          <Etapa3ZoneGeneration
            journeyId={journeyId}
            selectedTransportPointIds={selectedTransportPointIds}
            onNext={handleEtapa3Next}
          />
        </div>
      )}

      {currentEtapa === 4 && journeyId && (
        <div className="etapa-container">
          <Etapa4ZoneComparison journeyId={journeyId} onSelectZone={handleEtapa4SelectZone} />
        </div>
      )}

      {currentEtapa === 5 && journeyId && selectedZoneFingerprint && (
        <div className="etapa-container">
          <Etapa5ListingsSearch
            journeyId={journeyId}
            zoneFingerprint={selectedZoneFingerprint}
            zoneLabel={selectedZoneFingerprint}
            searchType={housingMode}
            onListingsReady={handleListingsReady}
          />
        </div>
      )}

      {currentEtapa === 6 && journeyId && selectedZoneFingerprint && (
        <div className="etapa-container">
          <Etapa6Listings
            journeyId={journeyId}
            zoneFingerprint={selectedZoneFingerprint}
            searchType={housingMode}
            initialListings={
              listingsResult?.listings as import("./etapa6-listings").Etapa6Props["initialListings"]
            }
            cacheAgeHours={listingsResult?.cache_age_hours}
            freshnessStatus={listingsResult?.freshness_status}
            jobId={listingsResult?.job_id}
          />
        </div>
      )}

      <style jsx>{`
        .shell {
          display: grid;
          gap: 24px;
          padding: 24px;
          max-width: 1920px;
          margin: 0 auto;
        }

        .etapa-container {
          max-width: 1400px;
          margin: 0 auto;
          width: 100%;
        }

        .card {
          border: 1px solid var(--line);
          background: var(--panel);
          box-shadow: var(--shadow);
          backdrop-filter: blur(18px);
          border-radius: var(--radius-xl);
        }

        .hero {
          display: grid;
          gap: 12px;
          padding: 28px;
        }

        .hero h1,
        .mapHeader h2,
        .panelColumn h2,
        .pointCard h3 {
          margin: 0;
          font-family: var(--font-display), sans-serif;
          font-weight: 700;
          letter-spacing: -0.04em;
        }

        .hero h1 {
          font-size: clamp(2rem, 4vw, 3.8rem);
          max-width: 14ch;
        }

        .heroCopy,
        .panelIntro,
        .mapHint {
          margin: 0;
          color: var(--muted);
          font-size: 1rem;
          line-height: 1.5;
          max-width: 70ch;
        }

        .eyebrow {
          margin: 0 0 8px;
          color: var(--accent);
          font-size: 0.78rem;
          font-weight: 700;
          letter-spacing: 0.14em;
          text-transform: uppercase;
        }

        .studioLayout {
          display: grid;
          grid-template-columns: minmax(0, 1.3fr) minmax(320px, 460px);
          gap: 24px;
          align-items: start;
        }

        @media (max-width: 1024px) {
          .studioLayout {
            grid-template-columns: 1fr;
          }
        }

        .mapColumn {
          display: grid;
          gap: 18px;
          padding: 20px;
        }

        .mapHeader {
          display: flex;
          justify-content: space-between;
          gap: 16px;
          align-items: end;
        }

        .mapCanvas {
          min-height: 68vh;
          border-radius: calc(var(--radius-xl) - 6px);
          overflow: hidden;
          border: 1px solid var(--line-strong);
          background: linear-gradient(135deg, rgba(20, 92, 82, 0.16), transparent 50%),
            linear-gradient(180deg, #f3ecdd 0%, #e8efe8 100%);
        }

        .statusRibbon {
          display: flex;
          gap: 10px;
          align-items: center;
          padding: 14px 16px;
          border-radius: var(--radius-md);
          background: var(--accent-soft);
          color: var(--accent-strong);
          font-size: 0.95rem;
        }

        .panelColumn {
          display: grid;
          gap: 18px;
          grid-auto-rows: max-content;
        }

        .panelColumn h2 {
          font-size: 1.4rem;
          margin-bottom: 8px;
        }

        .panelColumn .card {
          padding: 20px;
        }

        .fieldLabel {
          display: flex;
          flex-direction: column;
          gap: 8px;
          font-weight: 500;
          font-size: 0.95rem;
          cursor: pointer;
        }

        .fieldInput {
          padding: 10px 12px;
          border: 1px solid var(--line);
          border-radius: var(--radius-md);
          background: var(--panel);
          font-size: 1rem;
          transition: border 200ms ease;
        }

        .fieldInput:focus {
          outline: none;
          border-color: var(--accent);
          box-shadow: 0 0 0 3px var(--accent-soft);
        }

        .fieldGrid {
          display: grid;
          gap: 16px;
        }

        .compactGrid {
          grid-template-columns: 1fr 1fr;
        }

        .fieldValue {
          font-weight: 700;
          color: var(--accent-strong);
          font-size: 0.9rem;
        }

        .segmentedRow {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
          gap: 8px;
          margin-bottom: 16px;
        }

        .segmentButton {
          padding: 10px;
          border: 1px solid var(--line);
          background: transparent;
          border-radius: var(--radius-md);
          cursor: pointer;
          font-weight: 500;
          transition: all 200ms ease;
        }

        .segmentButton:hover:not(:disabled) {
          border-color: var(--accent);
          background: var(--accent-soft);
        }

        .segmentButtonActive {
          border-color: var(--accent-strong);
          background: var(--accent);
          color: var(--panel);
        }

        .segmentButton:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        .analysisGrid {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 12px;
          margin-top: 16px;
        }

        .analysisCard {
          padding: 12px;
          border: 1px solid var(--line);
          background: transparent;
          border-radius: var(--radius-md);
          cursor: pointer;
          text-align: left;
          transition: all 200ms ease;
        }

        .analysisCard:hover {
          border-color: var(--accent);
          background: var(--accent-soft);
        }

        .analysisCardActive {
          border-color: var(--accent-strong);
          background: var(--accent-soft);
        }

        .analysisCard strong {
          display: block;
          font-size: 0.95rem;
          margin-bottom: 4px;
        }

        .analysisCard span {
          font-size: 0.8rem;
          color: var(--muted);
        }

        .pointCard {
          padding: 20px;
        }

        .pointCardHeader {
          display: flex;
          justify-content: space-between;
          align-items: start;
          margin-bottom: 16px;
        }

        .pointCard h3 {
          font-size: 1.2rem;
          margin-bottom: 4px;
        }

        .ghostButton {
          padding: 8px 12px;
          border: 1px solid var(--line);
          background: transparent;
          border-radius: var(--radius-md);
          cursor: pointer;
          font-size: 0.85rem;
          font-weight: 500;
          color: var(--muted);
          transition: all 200ms ease;
          white-space: nowrap;
        }

        .ghostButton:hover {
          border-color: var(--accent);
          color: var(--accent);
        }

        .ghostButtonActive {
          border-color: var(--accent-strong);
          background: var(--accent-soft);
          color: var(--accent-strong);
        }

        .submitCard {
          padding: 20px;
        }

        .submitCard h2 {
          font-size: 1.2rem;
          margin-bottom: 12px;
        }

        .primaryButton {
          width: 100%;
          padding: 12px 24px;
          background: var(--accent);
          color: var(--panel);
          border: none;
          border-radius: var(--radius-md);
          font-weight: 600;
          font-size: 1rem;
          cursor: pointer;
          transition: background 200ms ease;
        }

        .primaryButton:hover:not(:disabled) {
          background: var(--accent-strong);
        }

        .primaryButton:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }

        .feedback {
          padding: 12px;
          border-radius: var(--radius-md);
          margin-bottom: 12px;
          font-size: 0.95rem;
          display: grid;
          gap: 4px;
        }

        .feedbackError {
          background: rgba(159, 43, 34, 0.14);
          color: var(--danger);
        }

        .feedbackSuccess {
          background: rgba(20, 92, 82, 0.14);
          color: var(--accent-strong);
        }

        .feedbackSuccess strong {
          display: block;
        }

        .feedbackSuccess span {
          font-size: 0.85rem;
          opacity: 0.9;
        }
      `}</style>
    </main>
  );
}
