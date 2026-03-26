import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  Home,
  MapIcon,
  ShieldAlert,
  Trees,
  Droplets,
  Building2
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import { apiActionHint, getJourneyZonesList, getPriceRollups, getZoneListings } from "../../api/client";
import { parseFiniteNumber, formatCurrencyBr } from "../../lib/listingFormat";
import { useJourneyStore, useUIStore } from "../../state";

function toDistribution(values: number[]) {
  if (values.length === 0) {
    return [];
  }
  const buckets = [
    { label: "até 3k", min: 0, max: 3000 },
    { label: "3k-4k", min: 3000, max: 4000 },
    { label: "4k-5k", min: 4000, max: 5000 },
    { label: "5k-6k", min: 5000, max: 6000 },
    { label: "6k+", min: 6000, max: Number.POSITIVE_INFINITY }
  ];
  return buckets.map((bucket) => ({
    range: bucket.label,
    count: values.filter((value) => value >= bucket.min && value < bucket.max).length
  }));
}

function platformLabel(value: string | null | undefined) {
  if (!value) {
    return "Plataforma";
  }
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function freshnessLabel(value: string | null | undefined) {
  if (value === "no_cache") {
    return "Scraping em andamento";
  }
  if (value === "queued_for_next_prewarm") {
    return "Busca iniciada";
  }
  return value || "Sem cache consolidado";
}

export function Step6Analysis() {
  const journeyId = useJourneyStore((state) => state.journeyId);
  const zoneFingerprint = useJourneyStore((state) => state.selectedZoneFingerprint);
  const config = useJourneyStore((state) => state.config);
  const activeTab = useUIStore((state) => state.activeTab);
  const setActiveTab = useUIStore((state) => state.setActiveTab);

  const listingsQuery = useQuery({
    queryKey: ["zone-listings", journeyId, zoneFingerprint, config.type],
    queryFn: async () => getZoneListings(journeyId as string, zoneFingerprint as string, config.type, "residential"),
    enabled: Boolean(journeyId && zoneFingerprint),
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) {
        return 5000;
      }
      return data.source === "none" || data.freshness_status === "no_cache" ? 5000 : false;
    }
  });

  const pricesQuery = useQuery({
    queryKey: ["zone-price-rollups", journeyId, zoneFingerprint, config.type],
    queryFn: async () => getPriceRollups(journeyId as string, zoneFingerprint as string, config.type, 30),
    enabled: Boolean(journeyId && zoneFingerprint)
  });

  const zonesQuery = useQuery({
    queryKey: ["journey-zones-for-analysis", journeyId],
    queryFn: async () => getJourneyZonesList(journeyId as string),
    enabled: Boolean(journeyId)
  });

  const selectedZone = zonesQuery.data?.zones.find((zone) => zone.fingerprint === zoneFingerprint);
  const listingPrices = (listingsQuery.data?.listings || [])
    .map((listing) => parseFiniteNumber(listing.current_best_price))
    .filter((value): value is number => value !== null);
  const listingUnitPrices = (listingsQuery.data?.listings || [])
    .map((listing) => {
      const price = parseFiniteNumber(listing.current_best_price);
      const area = typeof listing.area_m2 === "number" && listing.area_m2 > 0 ? listing.area_m2 : null;
      if (price === null || area === null) {
        return null;
      }
      return price / area;
    })
    .filter((value): value is number => value !== null);
  const priceDistribution = toDistribution(listingPrices);
  const priceHistory = (pricesQuery.data || []).map((item) => ({
    day: new Date(item.date).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" }),
    price: parseFiniteNumber(item.median_price) || 0
  }));
  const medianCurrentPrice = listingPrices.length > 0 ? listingPrices.reduce((acc, value) => acc + value, 0) / listingPrices.length : null;
  const averageUnitPrice = listingUnitPrices.length > 0 ? listingUnitPrices.reduce((acc, value) => acc + value, 0) / listingUnitPrices.length : null;

  return (
    <div className="flex h-full flex-col bg-slate-50 animate-[fadeInRight_0.5s_ease-out]">
      <div className="shrink-0 border-b border-slate-200 bg-white">
        <div className="p-5 pb-0">
          <div className="mb-4 flex items-center justify-between gap-4">
            <div>
              <h2 className="text-2xl font-bold tracking-tight text-slate-800">Resultados</h2>
              <p className="mt-1 flex items-center gap-2 text-sm text-slate-500">
                <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                {freshnessLabel(listingsQuery.data?.freshness_status)}
              </p>
            </div>
            <button type="button" className="rounded-lg bg-pastel-violet-50 px-3 py-1.5 text-sm font-medium text-pastel-violet-600 transition-colors hover:bg-pastel-violet-100" disabled>
              Gerar Relatório PDF
            </button>
          </div>

          <div className="flex gap-6 border-b border-transparent">
            <button type="button" onClick={() => setActiveTab("imoveis")} className={`pb-3 text-sm font-medium border-b-2 transition-colors ${activeTab === "imoveis" ? "border-pastel-violet-500 text-pastel-violet-600" : "border-transparent text-slate-500 hover:text-slate-700"}`}>
              Imóveis ({listingsQuery.data?.total_count || 0})
            </button>
            <button type="button" onClick={() => setActiveTab("dashboard")} className={`pb-3 text-sm font-medium border-b-2 transition-colors ${activeTab === "dashboard" ? "border-pastel-violet-500 text-pastel-violet-600" : "border-transparent text-slate-500 hover:text-slate-700"}`}>
              Dashboard Analítico
            </button>
          </div>
        </div>
      </div>

      <div className="panel-scroll flex-1 overflow-y-auto p-5">
        {activeTab === "imoveis" ? (
          <div className="space-y-4 animate-[fadeIn_0.3s_ease-out]">
            {listingsQuery.isLoading ? <p className="rounded-xl bg-white p-4 text-sm text-slate-500">Carregando imóveis...</p> : null}
            {listingsQuery.error ? <p className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">{apiActionHint(listingsQuery.error)}</p> : null}
            {!listingsQuery.isLoading && (listingsQuery.data?.listings || []).length === 0 ? (
              <div className="rounded-2xl border border-slate-200 bg-white p-5 text-sm text-slate-600 shadow-sm">
                {listingsQuery.data?.freshness_status === "no_cache"
                  ? "O scraping foi iniciado. Esta tela atualiza automaticamente assim que os primeiros imóveis estiverem prontos."
                  : "Nenhum imóvel disponível ainda para esta busca."}
              </div>
            ) : null}
            {(listingsQuery.data?.listings || []).map((listing, index) => {
              const price = parseFiniteNumber(listing.current_best_price);
              return (
                <div key={`${listing.platform_listing_id || index}-${listing.platform || "platform"}`} className="group flex flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white transition-shadow hover:shadow-lg sm:flex-row">
                  <div className="relative h-40 shrink-0 bg-gradient-to-br from-pastel-violet-100 via-white to-slate-100 sm:h-auto sm:w-48">
                    <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-400">
                      <Building2 className="h-9 w-9" />
                      <span className="mt-2 text-xs font-semibold uppercase tracking-[0.16em]">{platformLabel(listing.platform)}</span>
                    </div>
                    <div className="absolute left-2 top-2 rounded bg-white/90 px-2 py-1 text-xs font-bold text-slate-700 shadow-sm backdrop-blur-sm">
                      {platformLabel(listing.platform)}
                    </div>
                  </div>
                  <div className="flex flex-1 flex-col p-4">
                    <div className="mb-1 flex items-start justify-between gap-3">
                      <p className="text-sm text-slate-500">{config.type === "rent" ? "Locação" : "Compra"}</p>
                      <h3 className="text-xl font-bold text-slate-800">{formatCurrencyBr(price)}</h3>
                    </div>
                    <h4 className="mb-2 text-sm font-medium text-slate-700">{listing.address_normalized || "Endereço não informado"}</h4>
                    <div className="mb-4 flex flex-wrap items-center gap-4 text-sm text-slate-600">
                      <span className="inline-flex items-center gap-1"><MapIcon className="h-3.5 w-3.5" /> {listing.area_m2 ? `${Math.round(listing.area_m2)}m²` : "Área n/d"}</span>
                      <span className="inline-flex items-center gap-1"><Home className="h-3.5 w-3.5" /> {listing.bedrooms ?? "--"} dorms</span>
                    </div>
                    {listing.duplication_badge ? (
                      <div className="mb-3 inline-flex items-center gap-1.5 rounded-md border border-amber-100 bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-700">
                        <AlertTriangle className="h-3 w-3" />
                        {listing.duplication_badge}
                      </div>
                    ) : null}
                    <div className="mt-auto flex gap-2 border-t border-slate-100 pt-3">
                      <button type="button" className="flex-1 rounded-lg bg-slate-50 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-100">
                        Ver Acessibilidade
                      </button>
                      <a href={listing.url || "#"} target="_blank" rel="noreferrer" className="flex w-10 items-center justify-center rounded-lg bg-pastel-violet-50 text-pastel-violet-500 transition-colors hover:bg-pastel-violet-100">
                        <ExternalLink className="h-4 w-4" />
                      </a>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="space-y-6 animate-[fadeIn_0.3s_ease-out]">
            {pricesQuery.error ? <p className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">{apiActionHint(pricesQuery.error)}</p> : null}
            <div className="grid grid-cols-2 gap-4">
              <div className="rounded-xl border border-slate-200 bg-white p-4">
                <p className="mb-1 text-xs font-medium uppercase tracking-wider text-slate-500">Preço Mediano</p>
                <div className="flex items-baseline gap-2">
                  <h3 className="text-2xl font-bold text-slate-800">{formatCurrencyBr(medianCurrentPrice)}</h3>
                </div>
              </div>
              <div className="rounded-xl border border-slate-200 bg-white p-4">
                <p className="mb-1 text-xs font-medium uppercase tracking-wider text-slate-500">Custo / m²</p>
                <h3 className="text-2xl font-bold text-slate-800">{averageUnitPrice ? formatCurrencyBr(averageUnitPrice) : "Sem base"}</h3>
              </div>
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-5">
              <div className="mb-4 flex items-center justify-between">
                <h4 className="text-sm font-bold text-slate-800">Evolução do Preço</h4>
                <span className="rounded bg-slate-50 px-2 py-1 text-xs font-medium text-slate-400">Últimos 30 dias</span>
              </div>
              <div className="h-40 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={priceHistory}>
                    <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="day" tick={{ fontSize: 10 }} stroke="#94a3b8" />
                    <YAxis tickFormatter={(value) => `${Math.round(value / 1000)}k`} tick={{ fontSize: 10 }} stroke="#94a3b8" />
                    <Tooltip formatter={(value) => formatCurrencyBr(typeof value === "number" ? value : parseFiniteNumber(value))} />
                    <Line type="monotone" dataKey="price" stroke="#9775fa" strokeWidth={2} dot={priceHistory.length <= 12} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-5">
              <h4 className="mb-4 text-sm font-bold text-slate-800">Distribuição por faixa</h4>
              <div className="h-40 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={priceDistribution}>
                    <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="range" tick={{ fontSize: 10 }} stroke="#94a3b8" />
                    <YAxis allowDecimals={false} tick={{ fontSize: 10 }} stroke="#94a3b8" />
                    <Tooltip />
                    <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                      {priceDistribution.map((entry) => (
                        <Cell key={entry.range} fill="#c4b5fd" />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            <h4 className="pt-2 text-sm font-bold text-slate-800">Indicadores da Zona</h4>
            <div className="grid grid-cols-2 gap-3">
              <div className="flex items-center gap-3 rounded-lg border border-slate-100 bg-white p-3">
                <div className="rounded-lg bg-pastel-violet-50 p-2 text-pastel-violet-600"><ShieldAlert className="h-4 w-4" /></div>
                <div>
                  <p className="text-xs font-medium text-slate-500">Segurança</p>
                  <p className="text-sm font-semibold text-slate-800">{selectedZone?.safety_incidents_count ?? 0} ocorrências</p>
                </div>
              </div>
              <div className="flex items-center gap-3 rounded-lg border border-slate-100 bg-white p-3">
                <div className="rounded-lg bg-emerald-50 p-2 text-emerald-600"><Trees className="h-4 w-4" /></div>
                <div>
                  <p className="text-xs font-medium text-slate-500">Área Verde</p>
                  <p className="text-sm font-semibold text-slate-800">{Math.round(selectedZone?.green_area_m2 || 0)} m²</p>
                </div>
              </div>
              <div className="flex items-center gap-3 rounded-lg border border-slate-100 bg-white p-3">
                <div className="rounded-lg bg-emerald-50 p-2 text-emerald-600"><Droplets className="h-4 w-4" /></div>
                <div>
                  <p className="text-xs font-medium text-slate-500">Alagamento</p>
                  <p className="text-sm font-semibold text-slate-800">{Math.round(selectedZone?.flood_area_m2 || 0)} m²</p>
                </div>
              </div>
              <div className="flex items-center gap-3 rounded-lg border border-slate-100 bg-white p-3">
                <div className="rounded-lg bg-pastel-violet-50 p-2 text-pastel-violet-600"><MapIcon className="h-4 w-4" /></div>
                <div>
                  <p className="text-xs font-medium text-slate-500">POIs</p>
                  <p className="text-sm font-semibold text-slate-800">{selectedZone?.poi_counts ? Object.values(selectedZone.poi_counts).reduce((acc, value) => acc + value, 0) : 0} itens</p>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}