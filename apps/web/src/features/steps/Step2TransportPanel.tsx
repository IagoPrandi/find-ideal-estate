import type { TransportPointRead } from "../../api/schemas";
import { formatMeters, formatModalTypes, formatWalkTime } from "../../lib/formatTransport";

export type Step2TransportPanelProps = {
  visible: boolean;
  transportSearchRadiusM: number;
  transportPointsLoading: boolean;
  transportPoints: TransportPointRead[];
  transportPointsMessage: string;
  selectedTransportPointId: string;
  setSelectedTransportPointId: (id: string) => void;
  setHoveredTransportPointId: (id: string) => void;
  onTransportPointHover: (lon: number, lat: number) => void;
  onGenerateZones: () => void;
  journeyId: string;
  isQueueingZoneGeneration: boolean;
  zoneGenerationJobId: string;
  hoveredTransportPointId: string;
  transportHoverPulseOn: boolean;
};

export function Step2TransportPanel(props: Step2TransportPanelProps) {
  const {
    visible,
    transportSearchRadiusM,
    transportPointsLoading,
    transportPoints,
    transportPointsMessage,
    selectedTransportPointId,
    setSelectedTransportPointId,
    setHoveredTransportPointId,
    onTransportPointHover,
    onGenerateZones,
    journeyId,
    isQueueingZoneGeneration,
    zoneGenerationJobId,
    hoveredTransportPointId,
    transportHoverPulseOn
  } = props;

  if (!visible) return null;

  return (
    <section className="gem-panel-section animate-[fadeInRight_0.3s_ease-out] text-sm">
      <div className="gem-panel-header">
        <p className="gem-eyebrow">Etapa 2</p>
        <h3 className="gem-title mt-1">Escolher o transporte elegível</h3>
        <p className="gem-subtitle mt-1">
          Estes pontos foram encontrados no raio de {transportSearchRadiusM} m. Passe o mouse para localizar no mapa e
          selecione o seed que deve originar as zonas.
        </p>
      </div>

      <div className="gem-panel-body space-y-3">
        <div className="flex flex-wrap gap-2">
          <span className="gem-chip">Ponto-semente obrigatório</span>
          <span className="gem-chip">Mapa continua ativo durante a seleção</span>
        </div>

        {transportPointsLoading ? <p className="text-xs text-slate-500">Carregando pontos de transporte...</p> : null}

        {transportPoints.length > 0 ? (
          <div className="space-y-2">
            <p className="text-xs text-slate-500">Selecione 1 ponto para registrar a escolha antes de gerar zonas.</p>
            <ul className="max-h-[22rem] space-y-2 overflow-y-auto pr-1">
              {transportPoints.map((point, index) => {
                const label = point.name || `Ponto ${index + 1}`;
                const isSelected = selectedTransportPointId === point.id;
                const modalLabel = formatModalTypes(point.modal_types);
                return (
                  <li
                    key={point.id}
                    className={`rounded-[22px] border px-4 py-3 transition ${
                      isSelected
                        ? "border-pastel-violet-300 bg-gradient-to-br from-pastel-violet-50 to-white shadow-sm"
                        : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50"
                    }`}
                    onMouseEnter={() => {
                      setHoveredTransportPointId(point.id);
                      onTransportPointHover(point.lon, point.lat);
                    }}
                    onMouseLeave={() => setHoveredTransportPointId("")}
                  >
                    <label className="flex cursor-pointer items-start gap-3">
                      <input
                        type="radio"
                        name="transport-selection"
                        value={point.id}
                        checked={isSelected}
                        onChange={() => setSelectedTransportPointId(point.id)}
                        className="h-4 w-4 accent-pastel-violet-500"
                      />
                      <span className="min-w-0 flex-1 text-xs text-slate-800">
                        <span className="flex items-start justify-between gap-3">
                          <span>
                            <strong className="block text-sm text-slate-900">{label}</strong>
                            <span className="mt-1 inline-flex rounded-full bg-slate-100 px-2 py-1 text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">
                              #{index + 1}
                            </span>
                          </span>
                          <span className="gem-chip shrink-0">{modalLabel || "transporte"}</span>
                        </span>

                        <div className="mt-3 grid grid-cols-3 gap-2">
                          <span className="gem-soft-card">
                            <span className="block text-[10px] font-bold uppercase tracking-[0.18em] text-slate-400">Caminhada</span>
                            <span className="mt-1 block text-sm font-bold text-slate-900">{formatMeters(point.walk_distance_m)}</span>
                          </span>
                          <span className="gem-soft-card">
                            <span className="block text-[10px] font-bold uppercase tracking-[0.18em] text-slate-400">Tempo</span>
                            <span className="mt-1 block text-sm font-bold text-slate-900">{formatWalkTime(point.walk_time_sec)}</span>
                          </span>
                          <span className="gem-soft-card">
                            <span className="block text-[10px] font-bold uppercase tracking-[0.18em] text-slate-400">Linhas</span>
                            <span className="mt-1 block text-sm font-bold text-slate-900">{point.route_count}</span>
                          </span>
                        </div>
                      </span>
                    </label>
                  </li>
                );
              })}
            </ul>

            <button
              type="button"
              onClick={onGenerateZones}
              disabled={
                !journeyId ||
                !selectedTransportPointId ||
                transportPointsLoading ||
                transportPoints.length === 0 ||
                isQueueingZoneGeneration
              }
              className="gem-primary-button w-full justify-between disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isQueueingZoneGeneration ? "Enfileirando..." : "Gerar zonas"}
            </button>

            {zoneGenerationJobId ? <p className="text-[11px] text-slate-500">job_id: {zoneGenerationJobId}</p> : null}
            {import.meta.env.VITE_E2E_DEBUG === "1" ? (
              <div data-testid="m3-8-hover-debug" className="hidden">
                hovered={hoveredTransportPointId || "none"};pulse={transportHoverPulseOn ? "1" : "0"}
              </div>
            ) : null}
          </div>
        ) : (
          <p className="text-xs text-slate-500">{transportPointsMessage}</p>
        )}
      </div>
    </section>
  );
}
