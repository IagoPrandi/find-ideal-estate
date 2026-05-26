import { Crosshair, MapPin, Route, ShieldAlert, Trees, Droplets, Search, ArrowRight, Bus, Train, Blend, CarFront, Lock, PencilLine } from "lucide-react";
import { useEffect, useState } from "react";
import { apiActionHint, createJourney, geocodeReferenceAddress } from "../../api/client";
import type { ReferenceAddressSuggestion } from "../../api/client";
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
  const isPickingReferencePoint = useJourneyStore((state) => state.isPickingReferencePoint);
  const primaryReferenceLabel = useJourneyStore((state) => state.primaryReferenceLabel);
  const referenceInputMode = useJourneyStore((state) => state.referenceInputMode);
  const setConfig = useJourneyStore((state) => state.setConfig);
  const setEnrichment = useJourneyStore((state) => state.setEnrichment);
  const setPickedCoord = useJourneyStore((state) => state.setPickedCoord);
  const setReferenceInputMode = useJourneyStore((state) => state.setReferenceInputMode);
  const requestManualAreaDrawing = useJourneyStore((state) => state.requestManualAreaDrawing);
  const setIsPickingReferencePoint = useJourneyStore((state) => state.setIsPickingReferencePoint);
  const setJourneyId = useJourneyStore((state) => state.setJourneyId);
  const setPrimaryReferenceLabel = useJourneyStore((state) => state.setPrimaryReferenceLabel);
  const goToStep = useUIStore((state) => state.goToStep);
  const setMaxStep = useUIStore((state) => state.setMaxStep);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [referenceSuggestions, setReferenceSuggestions] = useState<ReferenceAddressSuggestion[]>([]);
  const [isReferenceSuggestOpen, setIsReferenceSuggestOpen] = useState(false);
  const [isLoadingReferenceSuggestions, setIsLoadingReferenceSuggestions] = useState(false);
  const [activeReferenceSuggestionIndex, setActiveReferenceSuggestionIndex] = useState(-1);
  const [isGreenPopoverOpen, setIsGreenPopoverOpen] = useState(false);
  const { can_customize_distance, can_customize_max_time, max_walk_minutes_cap, max_car_minutes_cap } = useEntitlements();
  const greenEnabled = config.enrichments.green;
  const isWalkingMode = config.modal === "walk";
  const isDrivingMode = config.modal === "car";
  const isDirectIsochroneMode = isWalkingMode || isDrivingMode;
  const referenceListboxId = "primary-reference-address-listbox";

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

  function selectReferenceSuggestion(suggestion: ReferenceAddressSuggestion) {
    setPrimaryReferenceLabel(suggestion.label);
    setPickedCoord({
      lat: suggestion.lat,
      lon: suggestion.lon,
      label: suggestion.label,
    });
    setIsPickingReferencePoint(false);
    setReferenceSuggestions([]);
    setActiveReferenceSuggestionIndex(-1);
    setIsReferenceSuggestOpen(false);
    setError(null);
  }

  useEffect(() => {
    const query = primaryReferenceLabel.trim();
    if (!isReferenceSuggestOpen || query.length < 3) {
      setReferenceSuggestions([]);
      setActiveReferenceSuggestionIndex(-1);
      return;
    }

    let cancelled = false;
    const timeoutId = window.setTimeout(() => {
      setIsLoadingReferenceSuggestions(true);
      void geocodeReferenceAddress(query)
        .then((items) => {
          if (cancelled) return;
          setReferenceSuggestions(items);
          setActiveReferenceSuggestionIndex(items.length > 0 ? 0 : -1);
        })
        .catch((caughtError) => {
          if (cancelled) return;
          setReferenceSuggestions([]);
          setActiveReferenceSuggestionIndex(-1);
          setError(apiActionHint(caughtError));
        })
        .finally(() => {
          if (!cancelled) setIsLoadingReferenceSuggestions(false);
        });
    }, 300);

    return () => {
      cancelled = true;
      window.clearTimeout(timeoutId);
    };
  }, [isReferenceSuggestOpen, primaryReferenceLabel, setPrimaryReferenceLabel]);

  async function handleSubmit() {
    if (referenceInputMode === "point" && !pickedCoord) {
      setError("Selecione um endereço ou posicione o ponto no mapa antes de continuar.");
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const journey = await createJourney({
        input_snapshot: {
          reference_point: referenceInputMode === "point" && pickedCoord
            ? {
                lat: pickedCoord.lat,
                lon: pickedCoord.lon,
                label: primaryReferenceLabel || pickedCoord.label || "Ponto selecionado no mapa"
              }
            : {
                lat: -23.55052,
                lon: -46.63331,
                label: "Área desenhada no mapa"
              },
          journey_input_mode: referenceInputMode,
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
      if (referenceInputMode === "area") {
        setMaxStep(1);
        requestManualAreaDrawing();
        return;
      }
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
        <p className="mt-1 text-sm text-slate-500">Defina o perfil da jornada e selecione o endereço principal da análise.</p>
      </div>

      <div className="panel-scroll min-h-0 flex-1 overflow-y-auto bg-slate-50/50 px-5 py-5">
        <div className="space-y-6">
        <div className="rounded-2xl border border-slate-200 bg-white p-1">
          <div className="grid grid-cols-2 gap-1">
            <button
              type="button"
              onClick={() => setReferenceInputMode("point")}
              className={`flex min-w-0 items-center justify-center gap-2 rounded-xl px-3 py-2.5 text-sm font-semibold transition ${referenceInputMode === "point" ? "bg-pastel-violet-500 text-white shadow-sm" : "text-slate-600 hover:bg-slate-50"}`}
              aria-pressed={referenceInputMode === "point"}
            >
              <MapPin className="h-4 w-4 shrink-0" />
              Selecionar ponto
            </button>
            <button
              type="button"
              onClick={() => setReferenceInputMode("area")}
              className={`flex min-w-0 items-center justify-center gap-2 rounded-xl px-3 py-2.5 text-sm font-semibold transition ${referenceInputMode === "area" ? "bg-pastel-violet-500 text-white shadow-sm" : "text-slate-600 hover:bg-slate-50"}`}
              aria-pressed={referenceInputMode === "area"}
            >
              <PencilLine className="h-4 w-4 shrink-0" />
              Desenhar área
            </button>
          </div>
        </div>

        <div className="space-y-3">
          <label className="text-sm font-medium text-slate-700">
            {referenceInputMode === "point" ? "Ponto de referência principal" : "Área da análise"}
          </label>
          {referenceInputMode === "point" ? (
          <>
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              type="search"
              value={primaryReferenceLabel}
              onChange={(event) => {
                const nextValue = event.target.value;
                if (pickedCoord?.label === primaryReferenceLabel && nextValue !== primaryReferenceLabel) {
                  setPickedCoord(null);
                }
                setPrimaryReferenceLabel(nextValue);
                setIsReferenceSuggestOpen(true);
                setError(null);
              }}
              onFocus={() => setIsReferenceSuggestOpen(true)}
              onBlur={() => {
                window.setTimeout(() => setIsReferenceSuggestOpen(false), 160);
              }}
              onKeyDown={(event) => {
                if (!isReferenceSuggestOpen || referenceSuggestions.length === 0) return;
                if (event.key === "ArrowDown") {
                  event.preventDefault();
                  setActiveReferenceSuggestionIndex((current) => Math.min(current + 1, referenceSuggestions.length - 1));
                } else if (event.key === "ArrowUp") {
                  event.preventDefault();
                  setActiveReferenceSuggestionIndex((current) => Math.max(current - 1, 0));
                } else if (event.key === "Enter" && activeReferenceSuggestionIndex >= 0) {
                  event.preventDefault();
                  selectReferenceSuggestion(referenceSuggestions[activeReferenceSuggestionIndex]);
                } else if (event.key === "Escape") {
                  setIsReferenceSuggestOpen(false);
                }
              }}
              role="combobox"
              aria-expanded={isReferenceSuggestOpen}
              aria-controls={referenceListboxId}
              aria-autocomplete="list"
              placeholder="Busque um endereço"
              className="gem-input pl-10"
            />
            {isReferenceSuggestOpen && (primaryReferenceLabel.trim().length >= 3 || isLoadingReferenceSuggestions) ? (
              <div
                id={referenceListboxId}
                role="listbox"
                className="absolute left-0 right-0 top-[calc(100%+0.4rem)] z-30 max-h-64 overflow-y-auto rounded-2xl border border-slate-200 bg-white py-2 shadow-xl"
              >
                {isLoadingReferenceSuggestions ? (
                  <p className="px-4 py-3 text-sm text-slate-500">Buscando endereços...</p>
                ) : referenceSuggestions.length === 0 ? (
                  <p className="px-4 py-3 text-sm text-slate-500">Nenhum endereço encontrado.</p>
                ) : (
                  referenceSuggestions.map((suggestion, index) => (
                    <button
                      key={suggestion.id || `${suggestion.label}:${suggestion.lat}:${suggestion.lon}`}
                      type="button"
                      role="option"
                      aria-selected={index === activeReferenceSuggestionIndex}
                      onMouseEnter={() => setActiveReferenceSuggestionIndex(index)}
                      onClick={() => selectReferenceSuggestion(suggestion)}
                      className={`flex w-full items-start gap-3 px-4 py-3 text-left transition-colors ${index === activeReferenceSuggestionIndex ? "bg-pastel-violet-50" : "hover:bg-slate-50"}`}
                    >
                      <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-pastel-violet-500" />
                      <span className="min-w-0">
                        <span className="block text-sm font-semibold text-slate-800">{suggestion.label}</span>
                        <span className="mt-0.5 block text-xs text-slate-500">
                          {suggestion.normalized || `${suggestion.lat.toFixed(5)}, ${suggestion.lon.toFixed(5)}`}
                        </span>
                      </span>
                    </button>
                  ))
                )}
              </div>
            ) : null}
          </div>

          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <div className="flex items-start gap-3">
              <div className="rounded-xl bg-pastel-violet-50 p-2 text-pastel-violet-600">
                <Crosshair className="h-5 w-5" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-slate-700">
                  {isPickingReferencePoint ? "Clique no mapa para posicionar." : "Alternativa: posicionar manualmente no mapa."}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  {pickedCoord
                    ? `Selecionado: ${pickedCoord.label || `${pickedCoord.lat.toFixed(5)}, ${pickedCoord.lon.toFixed(5)}`}`
                    : "Nenhum ponto selecionado ainda."}
                </p>
              </div>
            </div>
            <button
              type="button"
              aria-pressed={isPickingReferencePoint}
              onClick={() => setIsPickingReferencePoint(!isPickingReferencePoint)}
              className={`mt-3 inline-flex w-full items-center justify-center gap-2 rounded-xl border px-3 py-2 text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-pastel-violet-400 focus:ring-offset-2 ${isPickingReferencePoint ? "border-pastel-violet-300 bg-pastel-violet-500 text-white shadow-sm hover:bg-pastel-violet-600" : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"}`}
            >
              <Crosshair className="h-4 w-4" />
              {isPickingReferencePoint ? "Clique no mapa para posicionar" : pickedCoord ? "Reposicionar no mapa" : "Colocar ponto no mapa"}
            </button>
          </div>
          </>
          ) : (
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <div className="flex items-start gap-3">
                <div className="rounded-xl bg-pastel-violet-50 p-2 text-pastel-violet-600">
                  <PencilLine className="h-5 w-5" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-slate-800">Desenhe a área no mapa.</p>
                  <p className="mt-1 text-xs leading-relaxed text-slate-500">
                    Ao continuar, clique no mapa para criar os vértices da área. A zona desenhada será enviada diretamente para comparação.
                  </p>
                </div>
              </div>
            </div>
          )}

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
              min="200"
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
          {isSubmitting
            ? "Criando jornada..."
            : referenceInputMode === "area"
              ? "Desenhar área no mapa"
              : isWalkingMode
                ? "Gerar área acessível a pé"
                : isDrivingMode
                  ? "Gerar área acessível de carro"
                  : "Encontrar pontos de transporte próximos"}
          <ArrowRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
