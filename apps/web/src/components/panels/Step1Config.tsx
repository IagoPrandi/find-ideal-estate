import { MapPin, Route, ShieldAlert, Trees, Droplets, Search, ArrowRight, Bus, Train, Blend, CarFront, Lock } from "lucide-react";
import { useState } from "react";
import { apiActionHint, createJourney } from "../../api/client";
import { GREEN_VEGETATION_LABELS, GREEN_VEGETATION_LEVELS, useJourneyStore } from "../../state";
import { useUIStore } from "../../state";
import { useEntitlements } from "../../features/auth/useEntitlements";

const PUBLIC_TRANSPORT_OPTIONS = [
  {
    id: "bus",
    label: "Ônibus",
    Icon: Bus,
  },
  {
    id: "rail",
    label: "Trem/Metrô",
    Icon: Train,
  },
  {
    id: "mixed",
    label: "Ônibus + trem/metrô",
    Icon: Blend,
  },
] as const;

export function Step1Config() {
  const config = useJourneyStore((state) => state.config);
  const pickedCoord = useJourneyStore((state) => state.pickedCoord);
  const primaryReferenceLabel = useJourneyStore((state) => state.primaryReferenceLabel);
  const setConfig = useJourneyStore((state) => state.setConfig);
  const setEnrichment = useJourneyStore((state) => state.setEnrichment);
  const setJourneyId = useJourneyStore((state) => state.setJourneyId);
  const setPrimaryReferenceLabel = useJourneyStore((state) => state.setPrimaryReferenceLabel);
  const goToStep = useUIStore((state) => state.goToStep);
  const setMaxStep = useUIStore((state) => state.setMaxStep);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isGreenPopoverOpen, setIsGreenPopoverOpen] = useState(false);
  const { can_customize_distance, can_customize_max_time, max_walk_minutes_cap, max_car_minutes_cap } = useEntitlements();
  const greenEnabled = config.enrichments.green;
  const isWalkingMode = config.modal === "walk";
  const isDrivingMode = config.modal === "car";
  const isDirectIsochroneMode = isWalkingMode || isDrivingMode;

  const zoneToggleCards = [
    { id: "safety", label: "Segurança", icon: ShieldAlert },
    { id: "flood", label: "Alagamento", icon: Droplets },
    { id: "pois", label: "Serviços", icon: MapPin }
  ] as const;

  function renderZoneToggleCard(item: (typeof zoneToggleCards)[number]) {
    const Icon = item.icon;
    const checked = config.enrichments[item.id as keyof typeof config.enrichments];

    return (
      <label
        key={item.id}
        className={`flex min-h-[56px] cursor-pointer items-center gap-3 rounded-2xl border px-4 py-3 transition-colors ${checked ? "border-pastel-violet-300 bg-pastel-violet-50 text-pastel-violet-700" : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"}`}
      >
        <input
          type="checkbox"
          checked={checked}
          onChange={(event) => setEnrichment(item.id as keyof typeof config.enrichments, event.target.checked)}
          className="rounded text-pastel-violet-500 focus:ring-pastel-violet-400"
        />
        <Icon className="h-4 w-4" />
        <span className="text-sm font-medium">{item.label}</span>
      </label>
    );
  }

  function handleGreenPopoverBlur(event: React.FocusEvent<HTMLDivElement>) {
    const nextFocused = event.relatedTarget;
    if (nextFocused instanceof Node && event.currentTarget.contains(nextFocused)) {
      return;
    }
    setIsGreenPopoverOpen(false);
  }

  function handleSelectGreenVegetationLevel(level: (typeof GREEN_VEGETATION_LEVELS)[number]) {
    setConfig({ greenVegetationLevel: level });
    if (!config.enrichments.green) {
      setEnrichment("green", true);
    }
  }

  function renderGreenToggleCard(className: string) {
    return (
      <label className={className}>
        <input
          type="checkbox"
          checked={greenEnabled}
          onChange={(event) => setEnrichment("green", event.target.checked)}
          className="rounded text-pastel-violet-500 focus:ring-pastel-violet-400"
        />
        <Trees className="h-4 w-4" />
        <span className="flex min-w-0 flex-1 flex-col">
          <span className="text-sm font-medium leading-tight">Áreas verdes</span>
        </span>
      </label>
    );
  }

  async function handleSubmit() {
    if (!pickedCoord) {
      setError("Selecione um ponto no mapa antes de continuar.");
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const journey = await createJourney({
        input_snapshot: {
          reference_point: {
            lat: pickedCoord.lat,
            lon: pickedCoord.lon,
            label: primaryReferenceLabel || pickedCoord.label || "Ponto selecionado no mapa"
          },
          search_type: config.type,
          property_usage_type: config.propertyUsageType,
          transport_mode: config.modal,
          public_transport_mode: config.modal === "transit" ? config.publicTransportMode : null,
          max_travel_minutes: config.time,
          zone_radius_meters: isDirectIsochroneMode ? null : config.zoneRadiusMeters,
          transport_search_radius_meters: isDirectIsochroneMode ? null : config.transportSearchRadiusMeters,
          enrichments: {
            ...config.enrichments,
            green_vegetation_level: config.greenVegetationLevel
          }
        }
      });

      setJourneyId(journey.id);
      setMaxStep(isDirectIsochroneMode ? 3 : 2);
      goToStep(isDirectIsochroneMode ? 3 : 2);
    } catch (caughtError) {
      setError(apiActionHint(caughtError));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="flex h-full w-full min-w-0 flex-col animate-[fadeIn_0.3s_ease-out]">
      <div className="border-b border-slate-100 p-5">
        <h2 className="text-xl font-semibold tracking-tight text-slate-800">Configurar busca</h2>
        <p className="mt-1 text-sm text-slate-500">Defina o perfil da jornada e escolha o ponto principal diretamente no mapa.</p>
      </div>

      <div className="panel-scroll min-h-0 flex-1 overflow-y-auto bg-slate-50/50 px-5 py-5">
        <div className="space-y-6">
        <div className="space-y-3">
          <label className="text-sm font-medium text-slate-700">Ponto de referência principal</label>
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <div className="flex items-start gap-3">
              <div className="rounded-xl bg-pastel-violet-50 p-2 text-pastel-violet-600">
                <MapPin className="h-5 w-5" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-slate-700">Clique no mapa para definir o ponto principal.</p>
                <p className="mt-1 text-xs text-slate-500">
                  {pickedCoord
                    ? `Selecionado: ${pickedCoord.lat.toFixed(5)}, ${pickedCoord.lon.toFixed(5)}`
                    : "Nenhum ponto selecionado ainda."}
                </p>
              </div>
            </div>
          </div>

          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              value={primaryReferenceLabel}
              onChange={(event) => setPrimaryReferenceLabel(event.target.value)}
              placeholder="Ex.: trabalho, escola ou ponto de referência"
              className="gem-input pl-10"
            />
          </div>
        </div>

        <div className="flex rounded-xl bg-slate-100 p-1">
          <button
            type="button"
            onClick={() => setConfig({ type: "rent" })}
            className={`flex-1 rounded-lg py-2 text-sm font-medium transition-all ${config.type === "rent" ? "bg-white text-slate-800 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
          >
            Aluguel
          </button>
          <button
            type="button"
            onClick={() => setConfig({ type: "sale" })}
            className={`flex-1 rounded-lg py-2 text-sm font-medium transition-all ${config.type === "sale" ? "bg-white text-slate-800 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
          >
            Compra
          </button>
        </div>

        <div className="space-y-3">
          <label className="text-sm font-medium text-slate-700">Tipo de imóvel para analisar</label>
          <div className="grid grid-cols-3 gap-2 rounded-2xl border border-slate-200 bg-white p-2">
            <button
              type="button"
              onClick={() => setConfig({ propertyUsageType: "all" })}
              className={`rounded-xl px-3 py-2 text-sm font-medium transition-all ${config.propertyUsageType === "all" ? "bg-pastel-violet-500 text-white shadow-sm" : "text-slate-600 hover:bg-slate-50"}`}
            >
              Todos
            </button>
            <button
              type="button"
              onClick={() => setConfig({ propertyUsageType: "residential" })}
              className={`rounded-xl px-3 py-2 text-sm font-medium transition-all ${config.propertyUsageType === "residential" ? "bg-pastel-violet-500 text-white shadow-sm" : "text-slate-600 hover:bg-slate-50"}`}
            >
              Residencial
            </button>
            <button
              type="button"
              onClick={() => setConfig({ propertyUsageType: "commercial" })}
              className={`rounded-xl px-3 py-2 text-sm font-medium transition-all ${config.propertyUsageType === "commercial" ? "bg-pastel-violet-500 text-white shadow-sm" : "text-slate-600 hover:bg-slate-50"}`}
            >
              Comercial
            </button>
          </div>
        </div>

        <div className="space-y-3">
          <label className="text-sm font-medium text-slate-700">Como pretende se deslocar?</label>
          <div className="grid grid-cols-3 gap-2">
            <button
              type="button"
              onClick={() => setConfig({ modal: "transit" })}
              className={`flex flex-col items-center justify-center rounded-xl border p-3 transition-all ${config.modal === "transit" ? "border-pastel-violet-400 bg-pastel-violet-50 text-pastel-violet-600" : "border-slate-200 text-slate-600 hover:border-slate-300"}`}
            >
              <Bus className="mb-1 h-5 w-5" />
              <span className="text-xs font-medium">Público</span>
            </button>
            <button
              type="button"
              onClick={() => setConfig({ modal: "walk" })}
              className={`flex flex-col items-center justify-center rounded-xl border p-3 transition-all ${config.modal === "walk" ? "border-pastel-violet-400 bg-pastel-violet-50 text-pastel-violet-600" : "border-slate-200 text-slate-600 hover:border-slate-300"}`}
            >
              <Route className="mb-1 h-5 w-5" />
              <span className="text-xs font-medium">A pé</span>
            </button>
            <button
              type="button"
              onClick={() => setConfig({ modal: "car" })}
              className={`flex flex-col items-center justify-center rounded-xl border p-3 transition-all ${config.modal === "car" ? "border-pastel-violet-400 bg-pastel-violet-50 text-pastel-violet-600" : "border-slate-200 text-slate-600 hover:border-slate-300"}`}
            >
              <CarFront className="mb-1 h-5 w-5" />
              <span className="text-xs font-medium">Carro</span>
            </button>
          </div>

          {config.modal === "transit" ? (
            <div className="grid grid-cols-2 gap-2 rounded-2xl border border-pastel-violet-100 bg-pastel-violet-50/60 p-2 animate-[fadeIn_0.2s_ease-out]">
              {PUBLIC_TRANSPORT_OPTIONS.map((option, index) => {
                const isActive = config.publicTransportMode === option.id;
                const Icon = option.Icon;
                const isLastOddItem = PUBLIC_TRANSPORT_OPTIONS.length % 2 === 1 && index === PUBLIC_TRANSPORT_OPTIONS.length - 1;
                return (
                  <button
                    key={option.id}
                    type="button"
                    onClick={() => setConfig({ publicTransportMode: option.id })}
                    className={`flex min-w-0 items-center justify-center gap-2 rounded-xl border px-3 py-3 text-center text-xs font-medium transition-all ${isLastOddItem ? "col-span-2 mx-auto w-full max-w-[220px]" : "w-full"} ${isActive ? "border-pastel-violet-400 bg-white text-pastel-violet-700 shadow-sm" : "border-transparent bg-white/70 text-slate-600 hover:border-pastel-violet-200 hover:bg-white"}`}
                    aria-pressed={isActive}
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    <span className="leading-tight">{option.label}</span>
                  </button>
                );
              })}
            </div>
          ) : null}
        </div>

        {isDirectIsochroneMode ? (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <label htmlFor="direct-travel-time-minutes" className="text-sm font-medium text-slate-700">{isWalkingMode ? "Tempo de caminhada" : "Tempo de carro"}</label>
                {!can_customize_max_time && (
                  <span title="Disponível a partir do plano Básico" className="inline-flex cursor-help items-center text-slate-400">
                    <Lock className="h-3.5 w-3.5" />
                  </span>
                )}
              </div>
              <span className="text-sm font-bold text-pastel-violet-600">{config.time} min</span>
            </div>
            {(() => {
              const cap = isWalkingMode ? max_walk_minutes_cap : max_car_minutes_cap;
              const maxVal = cap ?? 60;
              return (
                <>
                  <input
                    id="direct-travel-time-minutes"
                    type="range"
                    min="5"
                    max={maxVal}
                    step="5"
                    value={config.time}
                    disabled={!can_customize_max_time}
                    onChange={can_customize_max_time ? (event) => setConfig({ time: Math.min(Number(event.target.value), maxVal) }) : undefined}
                    className={`w-full accent-pastel-violet-500 ${!can_customize_max_time ? "cursor-not-allowed opacity-50" : ""}`}
                  />
                  {!can_customize_max_time
                    ? <p className="text-xs text-slate-400">Disponível a partir do plano Básico.</p>
                    : cap !== null
                      ? <p className="text-xs text-slate-400">Máximo de {cap} min no seu plano.</p>
                      : null
                  }
                </>
              );
            })()}
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <label htmlFor="transport-search-radius" className="text-sm font-medium text-slate-700">Raio de busca do transporte</label>
                {!can_customize_distance && (
                  <span title="Disponível a partir do plano Básico" className="inline-flex cursor-help items-center text-slate-400">
                    <Lock className="h-3.5 w-3.5" />
                  </span>
                )}
              </div>
              <span className="text-sm font-bold text-pastel-violet-600">{config.transportSearchRadiusMeters} m</span>
            </div>
            <input
              id="transport-search-radius"
              type="range"
              min="300"
              max="2500"
              step="100"
              value={config.transportSearchRadiusMeters}
              disabled={!can_customize_distance}
              onChange={can_customize_distance ? (event) => setConfig({ transportSearchRadiusMeters: Number(event.target.value) }) : undefined}
              className={`w-full accent-pastel-violet-500 ${!can_customize_distance ? "cursor-not-allowed opacity-50" : ""}`}
            />
            {!can_customize_distance && (
              <p className="text-xs text-slate-400">Disponível a partir do plano Básico.</p>
            )}
          </div>
        )}

        <section aria-labelledby="zone-analysis-heading" className="space-y-3 border-t border-slate-100 pt-2">
          <h3 id="zone-analysis-heading" className="text-sm font-medium text-slate-700">Análises nas zonas</h3>
          <div className="grid grid-cols-2 gap-3">
            {renderZoneToggleCard(zoneToggleCards[0])}
            <div
              className={`relative min-h-[56px] overflow-visible ${isGreenPopoverOpen ? "z-20" : "z-10"}`}
              onMouseEnter={() => setIsGreenPopoverOpen(true)}
              onMouseLeave={() => setIsGreenPopoverOpen(false)}
              onFocusCapture={() => setIsGreenPopoverOpen(true)}
              onBlurCapture={handleGreenPopoverBlur}
            >
              {isGreenPopoverOpen ? (
                <div className="absolute right-0 top-0 w-[calc(200%+0.75rem)] animate-[fadeIn_0.18s_ease-out]">
                  <div className="grid grid-cols-2 gap-x-3">
                    <div aria-hidden="true" />
                    <div className="min-w-0">
                      {renderGreenToggleCard(
                        `flex min-h-[56px] cursor-pointer items-center gap-3 rounded-[22px] border px-4 py-3 transition-all ${greenEnabled ? "border-pastel-violet-300 bg-pastel-violet-100/90 text-pastel-violet-700 shadow-sm" : "border-slate-200 bg-white text-slate-700 shadow-sm"}`
                      )}
                    </div>
                    <div className="col-span-2 -mt-px overflow-hidden rounded-[30px] rounded-tr-none border border-slate-200 bg-slate-100/95 shadow-2xl">
                      <div className="bg-white/95 px-6 py-6 backdrop-blur-sm">
                        <div className="grid grid-cols-3 gap-3 text-xs font-medium text-slate-500">
                          {GREEN_VEGETATION_LEVELS.map((level) => {
                            const active = config.greenVegetationLevel === level;
                            return (
                              <button
                                type="button"
                                key={level}
                                onClick={() => handleSelectGreenVegetationLevel(level)}
                                className={`rounded-[22px] border px-3 py-3 text-center text-sm leading-tight transition-colors ${active ? "border-pastel-violet-300 bg-pastel-violet-500 text-white shadow-sm" : "border-slate-200 bg-white text-slate-600 hover:border-pastel-violet-200 hover:bg-pastel-violet-50/50"}`}
                                aria-pressed={active}
                              >
                                {GREEN_VEGETATION_LABELS[level]}
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                renderGreenToggleCard(
                  `relative flex min-h-[56px] cursor-pointer items-center gap-3 rounded-2xl border px-4 py-3 transition-all ${greenEnabled ? "border-pastel-violet-300 bg-pastel-violet-50 text-pastel-violet-700" : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"}`
                )
              )}
            </div>

            {renderZoneToggleCard(zoneToggleCards[1])}
            {renderZoneToggleCard(zoneToggleCards[2])}
          </div>
        </section>

        {error ? <p className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p> : null}
        </div>
      </div>

      <div className="border-t border-slate-100 bg-white p-5">
        <button type="button" onClick={handleSubmit} disabled={isSubmitting} className="gem-primary-button w-full disabled:cursor-not-allowed disabled:opacity-60">
          {isSubmitting ? "Criando jornada..." : isWalkingMode ? "Gerar área acessível a pé" : isDrivingMode ? "Gerar área acessível de carro" : "Encontrar pontos de transporte próximos"}
          <ArrowRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}