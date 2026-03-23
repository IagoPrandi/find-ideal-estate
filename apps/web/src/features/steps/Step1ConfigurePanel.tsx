import type { Dispatch, SetStateAction } from "react";
import { ArrowRight, Bus, Car, Droplets, Footprints, Lock, MapPin, Search, ShieldAlert, Trees } from "lucide-react";
import { INTEREST_CATEGORIES, ZONE_INFO_LABELS, ZONE_RADIUS_MAX_M, ZONE_RADIUS_MIN_M, ZONE_RADIUS_STEP_M, clampZoneRadius, type ZoneInfoKey } from "../../domain/wizardConstants";
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
      <div className="mb-5 border-b border-slate-100 pb-4">
        <h2 className="text-xl font-semibold tracking-tight text-slate-800">Configurar Busca</h2>
        <p className="mt-1 text-sm text-slate-500">Defina o seu perfil de deslocacao.</p>
      </div>

      <div className="space-y-4">
        <section className="rounded-xl border border-slate-200 bg-white p-4 text-sm shadow-sm">
          <label className="mb-2 block text-sm font-medium text-slate-700">Ponto de Referencia (Trabalho/Escola)</label>
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              readOnly
              value={
                primaryPoint
                  ? `${primaryPoint.name} (${primaryPoint.lat.toFixed(5)}, ${primaryPoint.lon.toFixed(5)})`
                  : "Clique no mapa em \"Definir principal\""
              }
              className="w-full rounded-xl border border-slate-200 bg-slate-50 py-2.5 pl-10 pr-3 text-sm text-slate-700"
            />
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setInteractionMode("primary")}
              className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:border-pastel-violet-300 hover:bg-pastel-violet-50"
            >
              Definir no mapa
            </button>
            {primaryPoint ? (
              <button
                type="button"
                onClick={removePrimaryPoint}
                className="rounded-lg border border-danger/40 px-3 py-1.5 text-xs font-semibold text-danger"
              >
                Remover
              </button>
            ) : null}
          </div>
        </section>

        <section className="rounded-xl border border-slate-200 bg-white p-4 text-sm shadow-sm">
          <div className="inline-flex w-full rounded-xl bg-slate-100 p-1">
            <button
              type="button"
              onClick={() => setPropertyMode("rent")}
              className={`flex-1 rounded-lg px-4 py-2 text-sm font-medium transition ${
                propertyMode === "rent" ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"
              }`}
            >
              Aluguel
            </button>
            <button
              type="button"
              onClick={() => setPropertyMode("buy")}
              className={`flex-1 rounded-lg px-4 py-2 text-sm font-medium transition ${
                propertyMode === "buy" ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"
              }`}
            >
              Compra
            </button>
          </div>
        </section>

        <section className="rounded-xl border border-slate-200 bg-white p-4 text-sm shadow-sm">
          <label className="mb-2 block text-sm font-medium text-slate-700">Como se pretende deslocar?</label>
          <div className="grid grid-cols-3 gap-2">
            <button
              type="button"
              className="flex flex-col items-center justify-center rounded-xl border border-pastel-violet-400 bg-pastel-violet-50 p-3 text-pastel-violet-600"
            >
              <Bus className="mb-1 h-5 w-5" />
              <span className="text-xs font-medium">Publico</span>
            </button>
            <button
              type="button"
              className="flex flex-col items-center justify-center rounded-xl border border-slate-200 p-3 text-slate-600 hover:border-slate-300"
            >
              <Footprints className="mb-1 h-5 w-5" />
              <span className="text-xs font-medium">A pe</span>
            </button>
            <button
              type="button"
              disabled
              className="relative flex cursor-not-allowed flex-col items-center justify-center overflow-hidden rounded-xl border border-slate-100 bg-slate-50 p-3 text-slate-400"
            >
              <Lock className="absolute right-1 top-1 h-3 w-3" />
              <Car className="mb-1 h-5 w-5" />
              <span className="text-xs font-medium">Carro (Pro)</span>
            </button>
          </div>
        </section>

        <section className="rounded-xl border border-slate-200 bg-white p-4 text-sm shadow-sm">
          <div className="mb-2 flex items-center justify-between">
            <label className="text-sm font-medium text-slate-700">Tempo maximo de viagem</label>
            <span className="text-sm font-bold text-pastel-violet-600">{maxTravelTimeMin} min</span>
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
        </section>

        <section className="rounded-xl border border-slate-200 bg-white p-4 text-sm shadow-sm">
          <div className="mb-2 flex items-center justify-between">
            <label className="text-sm font-medium text-slate-700">Raio da zona</label>
            <span className="text-sm font-bold text-pastel-violet-600">{zoneRadiusM} m</span>
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
        </section>

        <section className="rounded-xl border border-slate-200 bg-white p-4 text-sm shadow-sm">
          <label className="mb-2 block text-sm font-medium text-slate-700">Analisar nas zonas (Enriquecimento)</label>
          <div className="grid grid-cols-2 gap-3">
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
                  className="flex cursor-pointer items-center gap-2 rounded-lg border border-slate-200 p-2 text-xs text-slate-800 hover:bg-slate-50"
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
                    className="h-4 w-4 accent-pastel-violet-500"
                  />
                  <span className="text-slate-500">{icon}</span>
                  <span>{ZONE_INFO_LABELS[key]}</span>
                </label>
              );
            })}
          </div>
        </section>

        <section className="rounded-xl border border-slate-200 bg-white p-4 text-sm shadow-sm">
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-sm font-semibold text-slate-800">Interesses opcionais</h3>
            <button
              type="button"
              onClick={() => setIsOptionalInterestsExpanded((current) => !current)}
              className="rounded-xl border border-slate-200 px-2 py-1 text-xs font-semibold text-slate-600 transition hover:border-pastel-violet-300 hover:bg-pastel-violet-50"
            >
              {isOptionalInterestsExpanded ? "Minimizar" : "Adicionar interesse"}
            </button>
          </div>
          {isOptionalInterestsExpanded ? (
            <div className="mt-2 space-y-2">
              <label className="block">
                <span className="mb-1 block text-xs text-slate-500">Categoria</span>
                <select
                  value={interestCategory}
                  onChange={(event) => setInterestCategory(event.target.value)}
                  className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-800"
                >
                  {INTEREST_CATEGORIES.map((category) => (
                    <option key={category} value={category}>
                      {category}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="mb-1 block text-xs text-slate-500">Rotulo (opcional)</span>
                <input
                  value={interestLabel}
                  onChange={(event) => setInterestLabel(event.target.value)}
                  placeholder="Ex.: Academia XYZ"
                  className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-800"
                />
              </label>
              <button
                type="button"
                onClick={() => setInteractionMode("interest")}
                className="rounded-xl border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:border-pastel-violet-300 hover:bg-pastel-violet-50"
              >
                Selecionar no mapa
              </button>
            </div>
          ) : (
            <p className="mt-2 text-xs text-slate-500">Minimizado. Clique em "Adicionar interesse" para abrir.</p>
          )}

          {interests.length > 0 ? (
            <ul className="mt-3 space-y-2">
              {interests.map((interest) => (
                <li key={interest.id} className="rounded-lg border border-slate-200 px-2 py-2 text-xs text-slate-500">
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <p className="font-semibold text-slate-800">{interest.label}</p>
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

        <details className="rounded-xl border border-slate-200 bg-white p-4 text-sm shadow-sm">
          <summary className="cursor-pointer text-xs font-semibold text-slate-700">Configuracoes avancadas de seed</summary>
          <div className="mt-3 grid grid-cols-1 gap-3">
            <label className="block">
              <span className="mb-1 block text-xs text-slate-500">Distancia maxima seed onibus (m)</span>
              <input
                type="number"
                min={50}
                step={50}
                value={seedBusSearchMaxDistM}
                onChange={(event) => setSeedBusSearchMaxDistM(Math.max(50, Number(event.target.value) || 50))}
                className="w-full rounded-xl border border-slate-200 px-2 py-1.5 text-xs text-slate-800"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-slate-500">Distancia maxima seed trem/metro (m)</span>
              <input
                type="number"
                min={100}
                step={50}
                value={seedRailSearchMaxDistM}
                onChange={(event) => setSeedRailSearchMaxDistM(Math.max(100, Number(event.target.value) || 100))}
                className="w-full rounded-xl border border-slate-200 px-2 py-1.5 text-xs text-slate-800"
              />
            </label>
          </div>
        </details>

        <button
          type="button"
          onClick={onCreateRun}
          disabled={!primaryPoint || isCreatingRun || isPolling}
          className="w-full rounded-xl bg-pastel-violet-500 px-4 py-3.5 text-sm font-bold text-white shadow-lg shadow-pastel-violet-200 transition-colors hover:bg-pastel-violet-600 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <span className="inline-flex items-center gap-2">
            Achar pontos de transporte
            <ArrowRight className="h-4 w-4" />
          </span>
        </button>
      </div>
    </div>
  );
}
