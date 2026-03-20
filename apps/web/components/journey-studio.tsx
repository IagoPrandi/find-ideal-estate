"use client";

import { ChangeEvent, useMemo, useState } from "react";

import { MapShell } from "./map-shell";

type PointTarget = "primary" | "secondary";
type HousingMode = "rent" | "buy";
type TravelMode = "transit" | "walking" | "car";
type AnalysisKey = "green" | "flood" | "safety" | "pois";

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
  const [statusMessage, setStatusMessage] = useState("Selecione o ponto principal no mapa ou informe as coordenadas.");
  const [createdJourney, setCreatedJourney] = useState<JourneyResponse | null>(null);
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

  const handleSubmit = async () => {
    setSubmitError(null);
    setCreatedJourney(null);

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
        throw new Error("detail" in data && data.detail ? data.detail : "A API recusou a criação da jornada.");
      }

      setCreatedJourney(data as JourneyResponse);
      setStatusMessage("Jornada criada com sucesso. A Etapa 1 já está persistida no backend atual.");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Falha inesperada ao criar a jornada.";
      setSubmitError(message);
      setStatusMessage("Não foi possível salvar a jornada. Revise os campos e tente novamente.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const pointCard = (
    title: string,
    target: PointTarget,
    values: PointForm,
    hint: string,
  ) => (
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
      <section className="hero card">
        <div>
          <p className="eyebrow">Fase 3 · M3.1</p>
          <h1>Etapa 1 portada para Next.js App Router com mapa como plano principal.</h1>
        </div>
        <p className="heroCopy">
          O app novo já captura a configuração inicial da jornada, permite posicionar ponto principal e secundário no
          mapa, e persiste tudo no backend atual via `POST /journeys`.
        </p>
      </section>

      <section className="studioLayout">
        <div className="mapColumn card">
          <div className="mapHeader">
            <div>
              <p className="eyebrow">Mapa vivo</p>
              <h2>{activePointTarget === "primary" ? "Clique para definir a referência principal" : "Clique para definir o ponto secundário"}</h2>
            </div>
            <p className="mapHint">Centro inicial em São Paulo. O painel continua responsivo no desktop e no mobile.</p>
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
            <h2>Defina os parâmetros da jornada</h2>
            <p className="panelIntro">
              Esta versão já grava o snapshot de entrada no backend. Geocoding e busca textual ficam para os próximos
              marcos da Fase 3.
            </p>

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
                  onChange={(event: ChangeEvent<HTMLInputElement>) => setZoneRadiusMeters(Number(event.target.value))}
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
                  onChange={(event: ChangeEvent<HTMLInputElement>) => setMaxTravelMinutes(Number(event.target.value))}
                />
                <span className="fieldValue">{maxTravelMinutes} min</span>
              </label>

              <label className="fieldLabel">
                Distância máxima até seed
                <input
                  className="fieldInput"
                  type="range"
                  min={100}
                  max={1600}
                  step={50}
                  value={seedDistanceMeters}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => setSeedDistanceMeters(Number(event.target.value))}
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

            {submitError ? <p className="feedback feedbackError">{submitError}</p> : null}
            {createdJourney ? (
              <div className="feedback feedbackSuccess">
                <strong>Jornada criada.</strong>
                <span>ID: {createdJourney.id}</span>
                <span>Estado inicial: {createdJourney.state}</span>
              </div>
            ) : null}

            <button className="primaryButton" type="button" onClick={handleSubmit} disabled={isSubmitting}>
              {isSubmitting ? "Salvando jornada..." : "Criar jornada e continuar"}
            </button>
          </section>
        </aside>
      </section>

      <style jsx>{`
        .shell {
          display: grid;
          gap: 24px;
          padding: 24px;
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
        .pointCard h3,
        .mapFallback h3 {
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
        .mapHint,
        .mapFallback p {
          margin: 0;
          color: var(--muted);
          font-size: 1rem;
          line-height: 1.5;
          max-width: 70ch;
        }

        .eyebrow,
        .mapEyebrow {
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

        .mapCanvas,
        .mapFallback {
          min-height: 68vh;
          border-radius: calc(var(--radius-xl) - 6px);
          overflow: hidden;
          border: 1px solid var(--line-strong);
          background:
            linear-gradient(135deg, rgba(20, 92, 82, 0.16), transparent 50%),
            linear-gradient(180deg, #f3ecdd 0%, #e8efe8 100%);
        }

        .mapFallback {
          display: grid;
          place-items: center;
          padding: 40px;
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
        }

        .panelColumn > .card,
        .submitCard,
        .pointCard {
          padding: 20px;
        }

        .segmentedRow {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 10px;
          margin-bottom: 12px;
        }

        .segmentButton,
        .ghostButton,
        .analysisCard,
        .primaryButton {
          border: 1px solid var(--line);
          transition: transform 0.18s ease, border-color 0.18s ease, background 0.18s ease;
        }

        .segmentButton,
        .ghostButton {
          min-width: 0;
          border-radius: 999px;
          padding: 12px 16px;
          background: rgba(255, 255, 255, 0.68);
          color: var(--text);
        }

        .segmentButton:disabled {
          cursor: not-allowed;
          opacity: 0.56;
        }

        .segmentButtonActive,
        .ghostButtonActive {
          border-color: transparent;
          background: var(--accent);
          color: white;
        }

        .fieldGrid {
          display: grid;
          gap: 14px;
          margin-top: 18px;
        }

        .compactGrid {
          grid-template-columns: repeat(2, minmax(0, 1fr));
        }

        .fieldLabel {
          display: grid;
          gap: 8px;
          color: var(--muted);
          font-size: 0.95rem;
        }

        .fieldInput {
          width: 100%;
          min-width: 0;
          border: 1px solid var(--line-strong);
          border-radius: 12px;
          background: var(--panel-strong);
          color: var(--text);
          padding: 12px 14px;
        }

        .fieldValue {
          color: var(--accent-strong);
          font-weight: 700;
        }

        .analysisGrid {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 10px;
          margin-top: 20px;
        }

        .analysisCard {
          display: grid;
          gap: 6px;
          border-radius: 18px;
          background: rgba(255, 255, 255, 0.68);
          padding: 16px;
          text-align: left;
        }

        .analysisCard span {
          color: var(--muted);
          line-height: 1.4;
        }

        .analysisCardActive {
          border-color: rgba(20, 92, 82, 0.35);
          background: rgba(20, 92, 82, 0.1);
        }

        .pointCard {
          display: grid;
          gap: 16px;
        }

        .pointCardHeader {
          display: flex;
          gap: 16px;
          justify-content: space-between;
          align-items: start;
        }

        .submitCard {
          display: grid;
          gap: 16px;
        }

        .feedback {
          display: grid;
          gap: 4px;
          border-radius: 14px;
          padding: 14px;
          font-size: 0.96rem;
        }

        .feedbackError {
          background: rgba(159, 43, 34, 0.1);
          color: var(--danger);
        }

        .feedbackSuccess {
          background: rgba(20, 92, 82, 0.1);
          color: var(--accent-strong);
        }

        .primaryButton {
          border-radius: 16px;
          background: linear-gradient(135deg, var(--accent) 0%, #1f7d6f 100%);
          color: white;
          padding: 16px 18px;
          font-family: var(--font-display), sans-serif;
          font-size: 1rem;
          font-weight: 700;
        }

        .primaryButton:disabled {
          cursor: wait;
          opacity: 0.7;
        }

        .segmentButton:hover:not(:disabled),
        .ghostButton:hover,
        .analysisCard:hover,
        .primaryButton:hover:not(:disabled) {
          transform: translateY(-1px);
        }

        @media (max-width: 1180px) {
          .studioLayout {
            grid-template-columns: 1fr;
          }

          .mapCanvas,
          .mapFallback {
            min-height: 54vh;
          }
        }

        @media (max-width: 720px) {
          .shell {
            padding: 16px;
          }

          .hero,
          .mapColumn,
          .panelColumn > .card,
          .submitCard,
          .pointCard {
            padding: 18px;
          }

          .mapHeader,
          .pointCardHeader {
            flex-direction: column;
            align-items: stretch;
          }

          .segmentedRow,
          .analysisGrid,
          .compactGrid {
            grid-template-columns: 1fr;
          }
        }
      `}</style>
    </main>
  );
}