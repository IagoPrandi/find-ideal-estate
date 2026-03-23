import type { ZoneDetailResponse } from "../../api/schemas";
import type { ZoneInfoKey } from "../../domain/wizardConstants";

export type Step3ZoneDetailSectionProps = {
  zoneDetailData: ZoneDetailResponse | null;
  zoneInfoSelection: Record<ZoneInfoKey, boolean>;
  selectedZoneUid: string;
  isDetailingZone: boolean;
  zoneListingMessage: string;
  onDetailZone: () => void;
};

export function Step3ZoneDetailSection({
  zoneDetailData,
  zoneInfoSelection,
  selectedZoneUid,
  isDetailingZone,
  zoneListingMessage,
  onDetailZone
}: Step3ZoneDetailSectionProps) {
  return (
    <section className="mt-4 rounded-xl border border-slate-200 bg-white p-4 text-sm shadow-sm">
      <h3 className="text-sm font-semibold text-slate-800">Detalhe da zona</h3>
      <button
        type="button"
        onClick={onDetailZone}
        disabled={!selectedZoneUid || isDetailingZone}
        className="mt-3 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-800 transition hover:border-pastel-violet-300 hover:bg-pastel-violet-50 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {isDetailingZone ? "Detalhando..." : "Carregar detalhamento"}
      </button>
      <p className="mt-2 text-xs text-slate-500">{zoneListingMessage}</p>

      {zoneDetailData ? (
        <div className="mt-2 rounded-lg border border-slate-200/80 bg-slate-50 px-2 py-2 text-[11px] text-slate-500">
          <p className="mb-1 font-semibold text-slate-800">{zoneDetailData.zone_name}</p>
          {zoneInfoSelection.green || zoneInfoSelection.flood ? (
            <div className="grid grid-cols-2 gap-2">
              {zoneInfoSelection.green ? (
                <div className="rounded border border-slate-200 px-2 py-1.5">
                  <strong>Área verde</strong>
                  <p>{((zoneDetailData.green_area_ratio ?? 0) * 100).toFixed(1)}%</p>
                </div>
              ) : null}
              {zoneInfoSelection.flood ? (
                <div className="rounded border border-slate-200 px-2 py-1.5">
                  <strong>Área alagável</strong>
                  <p>{((zoneDetailData.flood_area_ratio ?? 0) * 100).toFixed(1)}%</p>
                </div>
              ) : null}
            </div>
          ) : null}
          {zoneInfoSelection.transport ? (
            <>
              <div className="mt-2 grid grid-cols-2 gap-2">
                <div className="rounded border border-slate-200 px-2 py-1.5">
                  <strong>Pontos ônibus</strong>
                  <p>{zoneDetailData.bus_stop_count}</p>
                </div>
                <div className="rounded border border-slate-200 px-2 py-1.5">
                  <strong>Pontos trem/metrô</strong>
                  <p>{zoneDetailData.train_station_count}</p>
                </div>
              </div>
              <p className="mt-2">
                <strong>Linhas ônibus:</strong> {zoneDetailData.bus_lines_count} · <strong>Linhas trem/metrô:</strong>{" "}
                {zoneDetailData.train_lines_count}
              </p>
              <p className="mt-1 font-semibold text-slate-800">Linhas usadas para gerar zona</p>
              <ul className="space-y-0.5">
                {zoneDetailData.lines_used_for_generation.map((line, idx) => (
                  <li key={`${line.route_id}_${idx}`}>
                    {line.mode.toUpperCase()} · {line.route_id || "sem código"} · {line.line_name || "sem nome"}
                  </li>
                ))}
              </ul>
              <p className="mt-1 font-semibold text-slate-800">Referências de transporte</p>
              <ul className="space-y-0.5">
                <li>
                  Seed (mais próximo do ponto principal): {zoneDetailData.seed_transport_point?.name || "não encontrado"}
                </li>
                <li>Downstream da zona: {zoneDetailData.downstream_transport_point?.name || "não encontrado"}</li>
              </ul>
            </>
          ) : null}

          {zoneInfoSelection.pois ? (
            <>
              <p className="mt-1 font-semibold text-slate-800">POIs por categoria</p>
              <ul className="space-y-0.5">
                {Object.entries(zoneDetailData.poi_count_by_category).map(([category, count]) => (
                  <li key={category}>
                    {category}: {count}
                  </li>
                ))}
              </ul>
              <p className="mt-1 text-[11px]">POIs exibidos no mapa: {zoneDetailData.poi_points.length}</p>
            </>
          ) : null}

          {zoneInfoSelection.publicSafety ? (
            <>
              <p className="mt-2 font-semibold text-slate-800">Segurança pública</p>
              {zoneDetailData.public_safety?.enabled ? (
                <>
                  <p className="mt-0.5">
                    Ano: {zoneDetailData.public_safety?.year ?? "N/A"} · Raio: {zoneDetailData.public_safety?.radius_km ?? "N/A"}{" "}
                    km
                  </p>
                  <p className="mt-0.5">
                    <strong>Total de ocorrências no raio:</strong>{" "}
                    {zoneDetailData.public_safety?.summary?.ocorrencias_no_raio_total ?? "N/A"}
                  </p>
                  <p className="mt-0.5">
                    <strong>Comparativo vs cidade (média/dia):</strong>{" "}
                    {typeof zoneDetailData.public_safety?.summary?.delta_pct_vs_cidade === "number"
                      ? `${(zoneDetailData.public_safety.summary.delta_pct_vs_cidade * 100).toFixed(1)}%`
                      : "N/A"}
                  </p>
                  <p className="mt-1 font-semibold text-slate-800">Top delitos no raio</p>
                  <ul className="space-y-0.5">
                    {(zoneDetailData.public_safety?.summary?.top_delitos_no_raio || []).slice(0, 5).map((item) => (
                      <li key={item.tipo_delito}>
                        {item.tipo_delito}: {item.qtd}
                      </li>
                    ))}
                  </ul>
                  <p className="mt-1 font-semibold text-slate-800">2 DPs mais próximas</p>
                  <ul className="space-y-0.5">
                    {(zoneDetailData.public_safety?.summary?.delegacias_mais_proximas || []).slice(0, 2).map((dp) => (
                      <li key={dp.nome}>
                        {dp.nome} · {typeof dp.dist_km === "number" ? `${dp.dist_km.toFixed(2)} km` : "distância N/A"}
                      </li>
                    ))}
                  </ul>
                </>
              ) : (
                <p className="mt-0.5 text-xs">
                  {zoneDetailData.public_safety?.error
                    ? `Não foi possível carregar segurança pública: ${zoneDetailData.public_safety.error}`
                    : "Segurança pública desabilitada para este run."}
                </p>
              )}
            </>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
