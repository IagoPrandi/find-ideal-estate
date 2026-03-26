import type { Dispatch, SetStateAction } from "react";
import {
  ArrowRight,
  Bus,
  Car,
  Droplets,
  Footprints,
  Lock,
  MapPin,
  Search,
  ShieldAlert,
  Trees
} from "lucide-react";
import {
  INTEREST_CATEGORIES,
  ZONE_INFO_LABELS,
  ZONE_RADIUS_MAX_M,
  ZONE_RADIUS_MIN_M,
  ZONE_RADIUS_STEP_M,
  clampZoneRadius,
  type ZoneInfoKey
} from "../../domain/wizardConstants";
import type { InteractionMode } from "../../components/map";
import type { InterestPoint, PropertyMode, ReferencePoint } from "./types";

export type Step1ConfigurePanelProps = {
  visible: boolean;
  viewport: { lat: number; lon: number };
  primaryPoint: ReferencePoint | null;
  setPrimaryPoint: Dispatch<SetStateAction<ReferencePoint | null>>;
  removePrimaryPoint: () => void;
  setInteractionMode: Dispatch<SetStateAction<InteractionMode>>;
  setStatusMessage: (message: string) => void;
  isOptionalInterestsExpanded: boolean;
  setIsOptionalInterestsExpanded: Dispatch<SetStateAction<boolean>>;
  interestCategory: string;
  setInterestCategory: (value: string) => void;
  interestLabel: string;
  setInterestLabel: (value: string) => void;
  interests: InterestPoint[];
  removeInterest: (id: string) => void;
  propertyMode: PropertyMode;
  setPropertyMode: Dispatch<SetStateAction<PropertyMode>>;
  zoneRadiusM: number;
  setZoneRadiusM: Dispatch<SetStateAction<number>>;
  maxTravelTimeMin: number;
  setMaxTravelTimeMin: Dispatch<SetStateAction<number>>;
  seedBusSearchMaxDistM: number;
  setSeedBusSearchMaxDistM: Dispatch<SetStateAction<number>>;
  seedRailSearchMaxDistM: number;
  setSeedRailSearchMaxDistM: Dispatch<SetStateAction<number>>;
  zoneInfoSelection: Record<ZoneInfoKey, boolean>;
  setZoneInfoSelection: Dispatch<SetStateAction<Record<ZoneInfoKey, boolean>>>;
  onCreateRun: () => void;
  isCreatingRun: boolean;
  isPolling: boolean;
};

export function Step1ConfigurePanel(props: Step1ConfigurePanelProps) {
  const {
    visible,
    primaryPoint,
    removePrimaryPoint,
    setInteractionMode,
    isOptionalInterestsExpanded,
    setIsOptionalInterestsExpanded,
    interestCategory,
    setInterestCategory,
    interestLabel,
    setInterestLabel,
    interests,
    removeInterest,
    propertyMode,
    setPropertyMode,
    zoneRadiusM,
    setZoneRadiusM,
    maxTravelTimeMin,
    setMaxTravelTimeMin,
    seedBusSearchMaxDistM,
    setSeedBusSearchMaxDistM,
    seedRailSearchMaxDistM,
    setSeedRailSearchMaxDistM,
    zoneInfoSelection,
    setZoneInfoSelection,
    onCreateRun,
    isCreatingRun,
    isPolling
  } = props;

  return (
    <div className={visible ? "block" : "hidden"}>
      <div className="mb-5 rounded-[24px] border border-slate-200/80 bg-gradient-to-br from-white via-[#fcfbff] to-[#f3f0ff] p-5 shadow-sm">
        <p className="gem-eyebrow">Etapa 1</p>
        <h2 className="mt-1 text-2xl font-extrabold tracking-tight text-slate-900">Configurar jornada de decisão</h2>
        <p className="mt-2 text-sm leading-relaxed text-slate-500">
          O mapa é o plano principal. Este painel define o ponto de referência, o perfil de deslocamento e as bases urbanas
          que serão usadas nas etapas seguintes.
        </p>
      </div>

      <div className="space-y-4">
        <section className="gem-panel-section">
          <div className="gem-panel-header">
            <p className="gem-eyebrow">Referência principal</p>
            <h3 className="gem-title mt-1">Onde a análise começa</h3>
            <p className="gem-subtitle mt-1">Use trabalho, escola ou qualquer ponto que organize a rotina de deslocamento.</p>
          </div>
          <div className="gem-panel-body space-y-3 text-sm">
            <label className="block">
              <span className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-700">
                <MapPin className="h-4 w-4 text-pastel-violet-600" /> Ponto de referência
              </span>
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input
                  readOnly
                  value={
                    primaryPoint
                      ? `${primaryPoint.name} (${primaryPoint.lat.toFixed(5)}, ${primaryPoint.lon.toFixed(5)})`
                      : 'Clique no mapa em "Definir principal"'
                  }
                  className="gem-input pl-10"
                />
              </div>
            </label>
            <div className="flex flex-wrap gap-2">
              <button type="button" onClick={() => setInteractionMode("primary")} className="gem-secondary-button">
                Definir no mapa
              </button>
              {primaryPoint ? (
                <button
                  type="button"
                  onClick={removePrimaryPoint}
                  className="inline-flex items-center justify-center gap-2 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700"
                >
                  Remover ponto
                </button>
              ) : null}
            </div>
          </div>
        </section>

        <section className="gem-panel-section">
          <div className="gem-panel-header">
            <p className="gem-eyebrow">Perfil de busca</p>
            <h3 className="gem-title mt-1">Modo do imóvel e deslocamento</h3>
            <p className="gem-subtitle mt-1">As decisões das etapas seguintes usam estas definições como contrato da jornada.</p>
          </div>
          <div className="gem-panel-body space-y-4 text-sm">
            <div className="rounded-2xl bg-slate-100 p-1.5">
              <div className="grid grid-cols-2 gap-1.5">
                <button
                  type="button"
                  onClick={() => setPropertyMode("rent")}
                  className={`rounded-2xl px-4 py-3 text-sm font-bold transition ${
                    propertyMode === "rent" ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"
                  }`}
                >
                  Aluguel
                </button>
                <button
                  type="button"
                  onClick={() => setPropertyMode("buy")}
                  className={`rounded-2xl px-4 py-3 text-sm font-bold transition ${
                    propertyMode === "buy" ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"
                  }`}
                >
                  Compra
                </button>
              </div>
            </div>

            <div>
              <p className="mb-2 text-sm font-semibold text-slate-700">Modal considerado</p>
              <div className="grid grid-cols-3 gap-2">
                <button
                  type="button"
                  className="rounded-2xl border border-pastel-violet-300 bg-pastel-violet-50 p-3 text-left text-pastel-violet-700"
                >
                  <Bus className="mb-2 h-5 w-5" />
                  <p className="text-sm font-bold">Transporte público</p>
                  <p className="mt-1 text-[11px] text-pastel-violet-700/80">Metrô, trem e ônibus elegíveis</p>
                </button>
                <button type="button" className="rounded-2xl border border-slate-200 bg-white p-3 text-left text-slate-600">
                  <Footprints className="mb-2 h-5 w-5" />
                  <p className="text-sm font-bold">A pé</p>
                  <p className="mt-1 text-[11px] text-slate-500">Disponível só como referência visual</p>
                </button>
                <button
                  type="button"
                  disabled
                  className="relative rounded-2xl border border-slate-100 bg-slate-50 p-3 text-left text-slate-400"
                >
                  <Lock className="absolute right-3 top-3 h-3.5 w-3.5" />
                  <Car className="mb-2 h-5 w-5" />
                  <p className="text-sm font-bold">Carro</p>
                  <p className="mt-1 text-[11px] text-slate-400">Escopo futuro</p>
                </button>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <div className="gem-soft-card">
                <div className="mb-2 flex items-center justify-between gap-3">
                  <label className="text-sm font-semibold text-slate-700">Tempo máximo de viagem</label>
                  <span className="text-sm font-extrabold text-pastel-violet-700">{maxTravelTimeMin} min</span>
                </div>
                <input
                  type="range"
                  min={5}
                  max={90}
                  step={1}
                  value={maxTravelTimeMin}
                  onChange={(event) => setMaxTravelTimeMin(Math.max(1, Number(event.target.value) || 1))}
                  className="h-2 w-full accent-pastel-violet-500"
                />
              </div>
              <div className="gem-soft-card">
                <div className="mb-2 flex items-center justify-between gap-3">
                  <label className="text-sm font-semibold text-slate-700">Raio analítico da zona</label>
                  <span className="text-sm font-extrabold text-pastel-violet-700">{zoneRadiusM} m</span>
                </div>
                <input
                  type="range"
                  min={ZONE_RADIUS_MIN_M}
                  max={ZONE_RADIUS_MAX_M}
                  step={ZONE_RADIUS_STEP_M}
                  value={zoneRadiusM}
                  onChange={(event) => setZoneRadiusM(clampZoneRadius(Number(event.target.value)))}
                  className="h-2 w-full accent-pastel-violet-500"
                />
              </div>
            </div>
          </div>
        </section>

        <section className="gem-panel-section">
          <div className="gem-panel-header">
            <p className="gem-eyebrow">Enriquecimento</p>
            <h3 className="gem-title mt-1">Quais bases entram na comparação</h3>
            <p className="gem-subtitle mt-1">Sem score opaco: cada indicador urbano permanece explicável e separado.</p>
          </div>
          <div className="gem-panel-body grid grid-cols-1 gap-3 sm:grid-cols-2">
            {(Object.keys(ZONE_INFO_LABELS) as ZoneInfoKey[]).map((key) => {
              const icon =
                key === "publicSafety" ? (
                  <ShieldAlert className="h-4 w-4" />
                ) : key === "green" ? (
                  <Trees className="h-4 w-4" />
                ) : key === "flood" ? (
                  <Droplets className="h-4 w-4" />
                ) : (
                  <MapPin className="h-4 w-4" />
                );
              return (
                <label
                  key={key}
                  className={`flex cursor-pointer items-start gap-3 rounded-2xl border p-3 transition ${
                    zoneInfoSelection[key]
                      ? "border-pastel-violet-200 bg-pastel-violet-50/70"
                      : "border-slate-200 bg-white hover:bg-slate-50"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={zoneInfoSelection[key]}
                    onChange={(event) =>
                      setZoneInfoSelection((current) => ({
                        ...current,
                        [key]: event.target.checked
                      }))
                    }
                    className="mt-0.5 h-4 w-4 accent-pastel-violet-500"
                  />
                  <span className="mt-0.5 text-pastel-violet-600">{icon}</span>
                  <span>
                    <span className="block text-sm font-semibold text-slate-900">{ZONE_INFO_LABELS[key]}</span>
                    <span className="block text-[11px] text-slate-500">Inclui esse eixo no detalhamento e no dashboard.</span>
                  </span>
                </label>
              );
            })}
          </div>
        </section>

        <section className="gem-panel-section">
          <div className="gem-panel-header">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="gem-eyebrow">Interesses opcionais</p>
                <h3 className="gem-title mt-1">Pontos complementares do usuário</h3>
              </div>
              <button
                type="button"
                onClick={() => setIsOptionalInterestsExpanded((current) => !current)}
                className="gem-secondary-button px-3 py-2 text-xs"
              >
                {isOptionalInterestsExpanded ? "Recolher" : "Adicionar interesse"}
              </button>
            </div>
          </div>
          <div className="gem-panel-body space-y-3 text-sm">
            {isOptionalInterestsExpanded ? (
              <div className="grid grid-cols-1 gap-3">
                <label className="block">
                  <span className="mb-1 block text-xs font-semibold text-slate-500">Categoria</span>
                  <select value={interestCategory} onChange={(event) => setInterestCategory(event.target.value)} className="gem-select">
                    {INTEREST_CATEGORIES.map((category) => (
                      <option key={category} value={category}>
                        {category}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block">
                  <span className="mb-1 block text-xs font-semibold text-slate-500">Rótulo opcional</span>
                  <input
                    value={interestLabel}
                    onChange={(event) => setInterestLabel(event.target.value)}
                    placeholder="Ex.: academia, escola, familiar"
                    className="gem-input"
                  />
                </label>
                <button type="button" onClick={() => setInteractionMode("interest")} className="gem-secondary-button">
                  Selecionar interesse no mapa
                </button>
              </div>
            ) : (
              <p className="text-xs text-slate-500">Interesses não alteram a geração da zona. Servem apenas como camada complementar para leitura.</p>
            )}

            {interests.length > 0 ? (
              <ul className="space-y-2">
                {interests.map((interest) => (
                  <li key={interest.id} className="gem-soft-card flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-bold text-slate-900">{interest.label}</p>
                      <p className="text-xs text-slate-500">
                        {interest.category} · {interest.lat.toFixed(5)}, {interest.lon.toFixed(5)}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => removeInterest(interest.id)}
                      className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs font-semibold text-red-700"
                    >
                      Remover
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        </section>

        <details className="gem-panel-section overflow-hidden">
          <summary className="cursor-pointer list-none px-5 py-4 text-sm font-bold text-slate-800">
            Configurações avançadas de seed
          </summary>
          <div className="gem-panel-body grid grid-cols-1 gap-3 md:grid-cols-2">
            <label className="block">
              <span className="mb-1 block text-xs font-semibold text-slate-500">Distância máxima seed ônibus (m)</span>
              <input
                type="number"
                min={50}
                step={50}
                value={seedBusSearchMaxDistM}
                onChange={(event) => setSeedBusSearchMaxDistM(Math.max(50, Number(event.target.value) || 50))}
                className="gem-input"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs font-semibold text-slate-500">Distância máxima seed trem/metrô (m)</span>
              <input
                type="number"
                min={100}
                step={50}
                value={seedRailSearchMaxDistM}
                onChange={(event) => setSeedRailSearchMaxDistM(Math.max(100, Number(event.target.value) || 100))}
                className="gem-input"
              />
            </label>
          </div>
        </details>

        <div className="rounded-[24px] bg-slate-950 px-5 py-5 text-white shadow-2xl shadow-slate-950/20">
          <p className="text-[10px] font-extrabold uppercase tracking-[0.24em] text-white/50">Próxima ação</p>
          <h3 className="mt-1 text-lg font-extrabold tracking-tight">Encontrar transportes elegíveis</h3>
          <p className="mt-2 text-sm leading-relaxed text-white/75">
            A busca vai procurar pontos de ônibus, estações de trem e metrô próximos do ponto principal com o raio e tempo
            definidos acima.
          </p>
          <button
            type="button"
            onClick={onCreateRun}
            disabled={!primaryPoint || isCreatingRun || isPolling}
            className="gem-primary-button mt-4 w-full justify-between bg-white text-slate-900 shadow-none hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            <span>Encontrar pontos de transporte</span>
            <ArrowRight className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}