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

  if (!visible) {
    return null;
  }

  return (
    <section className="mt-4 rounded-xl border border-slate-200 bg-white p-4 text-sm shadow-sm">
      <h3 className="text-sm font-semibold text-slate-800">Ponto de transporte</h3>
      <p className="mt-2 text-xs text-slate-500">
        Passe o mouse em um item para piscar o ponto no mapa e revisar alcance ({transportSearchRadiusM} m).
      </p>
      {transportPointsLoading ? (
        <p className="mt-2 text-xs text-slate-500">Carregando pontos de transporte...</p>
      ) : null}
      {transportPoints.length > 0 ? (
        <div className="mt-2 space-y-2">
          <p className="text-xs text-slate-500">Selecione 1 ponto para registrar a escolha antes de gerar zonas.</p>
          <ul className="max-h-40 space-y-2 overflow-y-auto">
            {transportPoints.map((point, index) => {
              const label = point.name || `Ponto ${index + 1}`;
              const isSelected = selectedTransportPointId === point.id;

              return (
                <li
                  key={point.id}
                  className={`rounded-lg border px-2 py-2 ${
                    isSelected ? "border-pastel-violet-400 bg-pastel-violet-500/5" : "border-slate-200"
                  }`}
                  onMouseEnter={() => {
                    setHoveredTransportPointId(point.id);
                    onTransportPointHover(point.lon, point.lat);
                  }}
                  onMouseLeave={() => setHoveredTransportPointId("")}
                >
                  <label className="flex cursor-pointer items-start gap-2">
                    <input
                      type="radio"
                      name="transport-selection"
                      value={point.id}
                      checked={isSelected}
                      onChange={() => setSelectedTransportPointId(point.id)}
                      className="h-4 w-4 accent-pastel-violet-500"
                    />
                    <span className="text-xs text-slate-800">
                      <strong>{label}</strong>
                      <br />
                      caminhada: {formatMeters(point.walk_distance_m)} ({formatWalkTime(point.walk_time_sec)})
                      <br />
                      modal: {formatModalTypes(point.modal_types)} · linhas: {point.route_count}
                    </span>
                  </label>
                </li>
              );
            })}
          </ul>

          <div className="grid grid-cols-1 gap-2">
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
              className="rounded-xl border border-slate-900 bg-slate-900 px-3 py-2 text-xs font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isQueueingZoneGeneration ? "Enfileirando..." : "Gerar zonas"}
            </button>
          </div>
          {zoneGenerationJobId ? (
            <p className="text-[11px] text-slate-500">job_id: {zoneGenerationJobId}</p>
          ) : null}
          {import.meta.env.VITE_E2E_DEBUG === "1" ? (
            <div data-testid="m3-8-hover-debug" className="hidden">
              hovered={hoveredTransportPointId || "none"};pulse={transportHoverPulseOn ? "1" : "0"}
            </div>
          ) : null}
        </div>
      ) : (
        <p className="mt-2 text-xs text-slate-500">{transportPointsMessage}</p>
      )}
    </section>
  );
}
