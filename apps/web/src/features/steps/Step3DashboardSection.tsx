import {
  Bar,
  BarChart,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import type { PriceRollupRead, ZoneDetailResponse } from "../../api/schemas";
import type { Step3MonthlyVariation } from "./types";
import type { ListingFeature } from "./step3Types";

export type Step3DashboardSectionProps = {
  priceRollups: PriceRollupRead[];
  monthlyVariation: Step3MonthlyVariation;
  seedTravelTimeMin: number | null;
  finalListings: ListingFeature[];
  zoneDetailData: ZoneDetailResponse | null;
  topPoiCategories: Array<[string, number]>;
};

export function Step3DashboardSection({
  priceRollups,
  monthlyVariation,
  seedTravelTimeMin,
  finalListings,
  zoneDetailData,
  topPoiCategories
}: Step3DashboardSectionProps) {
  return (
    <section
      className="mt-4 rounded-xl border border-slate-200 bg-white p-4 text-sm shadow-sm"
      data-testid="m6-dashboard-panel"
    >
      <h2 className="font-semibold">Dashboard da zona</h2>
      <p className="mt-1 text-xs text-slate-500">Resumo urbano e histórico de preços (FREE: 30 dias).</p>

      <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
        <div className="rounded border border-slate-200 px-2 py-2">
          <p className="text-slate-500">Preço mediano atual</p>
          <p className="font-semibold text-slate-800">
            {priceRollups[0]?.median_price ? `R$ ${Number(priceRollups[0].median_price).toLocaleString("pt-BR")}` : "n/d"}
          </p>
        </div>
        <div className="rounded border border-slate-200 px-2 py-2">
          <p className="text-slate-500">Amostra</p>
          <p className="font-semibold text-slate-800">{priceRollups[0]?.sample_count ?? 0} imóveis</p>
        </div>
        <div className="rounded border border-slate-200 px-2 py-2" data-testid="m6-monthly-variation">
          <p className="text-slate-500">Variação vs mês anterior</p>
          <p className="font-semibold text-slate-800">
            {monthlyVariation.pct === null
              ? "n/d"
              : `${monthlyVariation.trend === "up" ? "↑" : monthlyVariation.trend === "down" ? "↓" : "→"} ${Math.abs(
                  monthlyVariation.pct
                ).toFixed(1)}%`}
          </p>
        </div>
        <div className="rounded border border-slate-200 px-2 py-2" data-testid="m6-seed-travel">
          <p className="text-slate-500">Tempo médio ao ponto-semente</p>
          <p className="font-semibold text-slate-800">
            {seedTravelTimeMin === null ? "n/d" : `${seedTravelTimeMin.toFixed(0)} min`}
          </p>
        </div>
      </div>

      <div className="mt-3 rounded border border-slate-200/80 bg-slate-50 p-2">
        <p className="mb-1 text-[11px] font-semibold text-slate-800">Histórico mediano (30 dias)</p>
        <p className="mb-2 text-[10px] text-slate-500" data-testid="m6-linechart-points">
          Pontos exibidos: {Math.min(priceRollups.length, 30)}
        </p>
        <div className="h-40 min-h-40 w-full min-w-0" data-testid="m6-linechart-wrapper">
          <ResponsiveContainer width="100%" height={160}>
            <LineChart
              data={priceRollups
                .slice(0, 30)
                .map((row) => ({ day: row.date.slice(5), median: Number(row.median_price || 0) }))
                .reverse()}
            >
              <XAxis dataKey="day" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
              <YAxis tick={{ fontSize: 10 }} width={60} />
              <Tooltip />
              <Line type="monotone" dataKey="median" stroke="#9775fa" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="mt-3 rounded border border-slate-200/80 bg-slate-50 p-2">
        <p className="mb-1 text-[11px] font-semibold text-slate-800">Distribuição por faixas (10 buckets)</p>
        <div className="h-40 min-h-40 w-full min-w-0">
          <ResponsiveContainer width="100%" height={160}>
            <BarChart
              data={(() => {
                const prices = finalListings
                  .map((item) => Number(item.properties?.current_best_price || item.properties?.price || 0))
                  .filter((value) => Number.isFinite(value) && value > 0);
                if (prices.length === 0) {
                  return Array.from({ length: 10 }, (_, idx) => ({ bucket: `${idx + 1}`, count: 0 }));
                }
                const min = Math.min(...prices);
                const max = Math.max(...prices);
                const span = Math.max(1, max - min);
                const step = span / 10;
                const counts = Array.from({ length: 10 }, () => 0);
                prices.forEach((price) => {
                  const index = Math.min(9, Math.floor((price - min) / step));
                  counts[index] += 1;
                });
                return counts.map((count, idx) => ({ bucket: `${idx + 1}`, count }));
              })()}
            >
              <XAxis dataKey="bucket" tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 10 }} width={35} />
              <Tooltip />
              <Bar dataKey="count" fill="#16a34a" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {zoneDetailData ? (
        <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
          <div className="rounded border border-slate-200 px-2 py-1.5">
            <p className="text-slate-500">Segurança</p>
            <p className="font-semibold text-slate-800">
              {zoneDetailData.public_safety?.summary?.ocorrencias_no_raio_total ?? "n/d"} ocorrências
            </p>
          </div>
          <div className="rounded border border-slate-200 px-2 py-1.5">
            <p className="text-slate-500">Área verde</p>
            <p className="font-semibold text-slate-800">{((zoneDetailData.green_area_ratio ?? 0) * 100).toFixed(1)}%</p>
          </div>
          <div className="rounded border border-slate-200 px-2 py-1.5">
            <p className="text-slate-500">Risco alagamento</p>
            <p className="font-semibold text-slate-800">{((zoneDetailData.flood_area_ratio ?? 0) * 100).toFixed(1)}%</p>
          </div>
          <div className="rounded border border-slate-200 px-2 py-1.5">
            <p className="text-slate-500">Transporte</p>
            <p className="font-semibold text-slate-800">
              {zoneDetailData.bus_lines_count + zoneDetailData.train_lines_count} linhas ({zoneDetailData.lines_used_for_generation.length}{" "}
              usadas)
            </p>
          </div>
        </div>
      ) : null}

      <div className="mt-3 rounded border border-slate-200/80 bg-slate-50 p-2 text-xs" data-testid="m6-top-pois">
        <p className="mb-1 font-semibold text-slate-800">POIs por categoria (top 6)</p>
        {topPoiCategories.length > 0 ? (
          <ul className="grid grid-cols-2 gap-x-3 gap-y-1">
            {topPoiCategories.map(([category, count]) => (
              <li key={category} className="text-slate-500">
                <span className="text-slate-800">{category}</span>: {count}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-slate-500">Sem categorias de POI para esta zona.</p>
        )}
      </div>
    </section>
  );
}
