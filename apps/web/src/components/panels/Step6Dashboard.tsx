import { useEffect, useId, useMemo, useRef, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ChevronDown,
  Droplets,
  Loader2,
  MapPinned,
  ShieldAlert,
  Trees,
  TrendingDown,
  TrendingUp,
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
  YAxis,
} from "recharts";
import { apiActionHint, getZoneDashboardAnalytics } from "../../api/client";
import { formatCurrencyBr } from "../../lib/listingFormat";

type DashboardPage = "preco" | "seguranca" | "ambiente";

type Step6DashboardProps = {
  journeyId: string;
  zoneFingerprint: string;
  propertyId: string | null;
  hasExplicitPropertySelection: boolean;
  searchType: string;
};

type DashboardRankingItem = {
  position: number;
  neighborhood_name: string;
  city_name?: string | null;
  value?: number | null;
  yearly_change_pct?: number | null;
  is_selected?: boolean;
};

type DashboardRankingDisplayEntry =
  | { type: "item"; key: string; item: DashboardRankingItem }
  | { type: "gap"; key: string };

function formatPercent(value: number | null | undefined) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "Sem base";
  }
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function formatPlainPercent(value: number | null | undefined) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "Sem base";
  }
  return `${value.toFixed(1)}%`;
}

function formatRate(value: number | null | undefined) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "Sem base";
  }
  return `${value.toFixed(2)}/km²`;
}

function formatDensityPerSquareKm(value: number | null | undefined) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "Sem base";
  }
  const digits = Math.abs(value) >= 10 ? 2 : Math.abs(value) >= 1 ? 3 : 5;
  return new Intl.NumberFormat("pt-BR", { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value);
}

function formatDensityPerSquareKmWithUnit(value: number | null | undefined) {
  const formatted = formatDensityPerSquareKm(value);
  return formatted === "Sem base" ? formatted : `${formatted}/km²`;
}

function formatCurrencyPerSquareMeter(value: number | null | undefined) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "Sem base";
  }
  return `${new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)}/m²`;
}

function formatOccurrenceCount(value: number | null | undefined) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "Sem base";
  }
  return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 }).format(Math.round(value));
}

function formatRatio(value: number | null | undefined) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "Sem base";
  }
  return `${value.toFixed(2)}x`;
}

function rankLabel(rank: { position?: number | null; total?: number | null } | null | undefined) {
  if (!rank?.position || !rank?.total || rank.total <= 1) {
    return "Sem ranking";
  }
  return `${rank.position}º de ${rank.total}`;
}

function rankHint(rank: { scope_label?: string | null; note?: string | null } | null | undefined) {
  return rank?.scope_label || rank?.note || null;
}

function formatHourLabel(hour: number) {
  return `${String(hour).padStart(2, "0")}h`;
}

function priceRankExplanation(rank: { scope_label?: string | null; direction?: string | null } | null | undefined) {
  const base = rank?.scope_label || "Sem base";
  if (rank?.direction === "lower_better") {
    return `${base} · 1º = bairro mais barato por m²`;
  }
  if (rank?.direction === "higher_better") {
    return `${base} · 1º = bairro mais caro por m²`;
  }
  return base;
}

function yearlyChangeRankExplanation(rank: { scope_label?: string | null; direction?: string | null } | null | undefined) {
  const base = rank?.scope_label || "Sem base";
  if (rank?.direction === "lower_better") {
    return `${base} · 1º = menor oscilação no período`;
  }
  if (rank?.direction === "higher_better") {
    return `${base} · 1º = maior oscilação no período`;
  }
  return base;
}

function safetyRankingTitle(scopeLabel: string | null | undefined) {
  if (scopeLabel?.includes("Densidade")) {
    return "Ranking de densidade de roubos por bairro";
  }
  return scopeLabel?.includes("Zonas da jornada atual") ? "Ranking da zona" : "Ranking do bairro";
}

function safetyRankingDescription(selectedCity: string | null | undefined, scopeLabel: string | null | undefined) {
  const scope = scopeLabel || "Densidade de roubos por km² por bairro";
  const cityLabel = selectedCity ? `cidade: ${selectedCity}` : "sem filtro de cidade";
  return `${scope} · ${cityLabel} · exibição resumida com 2 do topo, 2 do entorno do bairro predominante e 2 da base.`;
}

function safetyRankingEmptyMessage(selectedCity: string | null | undefined) {
  if (selectedCity) {
    return "Sem bairros com ao menos 3 pontos SSP georreferenciados para montar o ranking da cidade selecionada.";
  }
  return "Sem bairros com ao menos 3 pontos SSP georreferenciados para montar o ranking geral.";
}

function safetySelectedLabel(scopeLabel: string | null | undefined) {
  if (scopeLabel?.includes("Densidade")) {
    return "Bairro predominante";
  }
  return scopeLabel?.includes("Zonas da jornada atual") ? "Zona analisada" : "Bairro analisado";
}

function formatYearlyChangeInline(value: number | null | undefined) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "Sem série em 365 dias";
  }
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}% em 365 dias`;
}

function normalizeComboboxText(value: string) {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function buildSegmentedRankingEntries(items: DashboardRankingItem[]): DashboardRankingDisplayEntry[] {
  if (items.length === 0) {
    return [];
  }

  if (items.length <= 6) {
    return items.map((item) => ({
      type: "item" as const,
      key: `${item.position}-${item.neighborhood_name}`,
      item,
    }));
  }

  const selectedIndex = Math.max(items.findIndex((item) => item.is_selected), 0);
  const middleStart = Math.max(0, Math.min(selectedIndex - 1, items.length - 2));
  const highlightedIndices = Array.from(new Set([
    0,
    1,
    middleStart,
    middleStart + 1,
    items.length - 2,
    items.length - 1,
  ]))
    .filter((index) => index >= 0 && index < items.length)
    .sort((left, right) => left - right);

  const entries: DashboardRankingDisplayEntry[] = [];
  let previousIndex = -1;
  for (const index of highlightedIndices) {
    if (previousIndex >= 0 && index - previousIndex > 1) {
      entries.push({ type: "gap", key: `gap-${previousIndex}-${index}` });
    }
    const item = items[index];
    entries.push({
      type: "item",
      key: `${item.position}-${item.neighborhood_name}`,
      item,
    });
    previousIndex = index;
  }

  return entries;
}

function SafetyPeakHoursTooltip(props: {
  active?: boolean;
  label?: string;
  payload?: Array<{ dataKey?: string; value?: number; color?: string }>;
}) {
  if (!props.active || !props.payload || props.payload.length === 0) {
    return null;
  }

  const labels: Record<string, string> = {
    homicide: "homicídio",
    robbery: "roubo",
    theft: "furto",
  };

  const rows = props.payload.filter((entry) => typeof entry.value === "number");

  return (
    <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-lg">
      <p className="text-sm font-semibold text-slate-800">{props.label}</p>
      <div className="mt-3 space-y-2 text-sm">
        {rows.map((entry) => (
          <div key={entry.dataKey} className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: entry.color || "#64748b" }} />
            <span className="text-slate-600">{labels[entry.dataKey || ""] || entry.dataKey}</span>
            <span className="font-medium text-slate-800">{entry.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function MetricCard(props: {
  icon: React.ReactNode;
  eyebrow: string;
  value: string;
  detail?: string | null;
  tone?: "violet" | "emerald" | "amber" | "rose";
}) {
  const toneClass = {
    violet: "bg-pastel-violet-50 text-pastel-violet-600",
    emerald: "bg-emerald-50 text-emerald-600",
    amber: "bg-amber-50 text-amber-600",
    rose: "bg-rose-50 text-rose-600",
  }[props.tone || "violet"];

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">{props.eyebrow}</p>
          <p className="mt-2 text-2xl font-bold text-slate-800">{props.value}</p>
          {props.detail ? <p className="mt-2 text-sm text-slate-500">{props.detail}</p> : null}
        </div>
        <div className={`rounded-xl p-2.5 ${toneClass}`}>{props.icon}</div>
      </div>
    </div>
  );
}

export function Step6Dashboard({ journeyId, zoneFingerprint, propertyId, hasExplicitPropertySelection, searchType }: Step6DashboardProps) {
  const [activePage, setActivePage] = useState<DashboardPage>("preco");
  const [selectedPriceFilter, setSelectedPriceFilter] = useState<{ neighborhoodName: string; cityName: string } | null>(null);
  const [selectedSafetyCityFilter, setSelectedSafetyCityFilter] = useState<string | null>(null);
  const tabs: Array<{ key: DashboardPage; label: string }> = [
    { key: "preco", label: "Preço e valor" },
    { key: "seguranca", label: "Segurança" },
    { key: "ambiente", label: "Vegetação e alagamento" },
  ];

  useEffect(() => {
    setSelectedPriceFilter(null);
    setSelectedSafetyCityFilter(null);
  }, [journeyId, zoneFingerprint, propertyId, searchType]);

  const zoneDashboardQuery = useQuery({
    queryKey: ["zone-dashboard-analytics", journeyId, zoneFingerprint, searchType, "zone"],
    queryFn: async () => getZoneDashboardAnalytics(journeyId, zoneFingerprint, searchType),
    enabled: Boolean(journeyId && zoneFingerprint),
    staleTime: 60_000,
  });

  const basePriceDashboardQuery = useQuery({
    queryKey: ["zone-dashboard-analytics", journeyId, zoneFingerprint, searchType, propertyId || "none"],
    queryFn: async () => getZoneDashboardAnalytics(journeyId, zoneFingerprint, searchType, propertyId),
    enabled: Boolean(journeyId && zoneFingerprint && propertyId && activePage === "preco"),
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });

  const filteredPriceDashboardQuery = useQuery({
    queryKey: [
      "zone-dashboard-analytics",
      journeyId,
      zoneFingerprint,
      searchType,
      "price-filter",
      selectedPriceFilter?.cityName || "no-city",
      selectedPriceFilter?.neighborhoodName || "no-neighborhood",
      propertyId || "none",
    ],
    queryFn: async () =>
      getZoneDashboardAnalytics(journeyId, zoneFingerprint, searchType, {
        propertyId,
        cityName: selectedPriceFilter?.cityName || null,
        neighborhoodName: selectedPriceFilter?.neighborhoodName || null,
      }),
    enabled: Boolean(
      journeyId
        && zoneFingerprint
        && activePage === "preco"
        && selectedPriceFilter?.cityName
        && selectedPriceFilter?.neighborhoodName,
    ),
    staleTime: 60_000,
    placeholderData: (previousData) => previousData ?? basePriceDashboardQuery.data,
  });

  const safetyDashboardQuery = useQuery({
    queryKey: [
      "zone-dashboard-analytics",
      journeyId,
      zoneFingerprint,
      searchType,
      "safety-city",
      selectedSafetyCityFilter || "default",
    ],
    queryFn: async () => getZoneDashboardAnalytics(journeyId, zoneFingerprint, searchType, {
      cityName: selectedSafetyCityFilter,
    }),
    enabled: Boolean(journeyId && zoneFingerprint && activePage === "seguranca" && selectedSafetyCityFilter),
    staleTime: 60_000,
  });

  const zoneData = zoneDashboardQuery.data;
  const basePriceData = basePriceDashboardQuery.data || zoneData;
  const priceData = filteredPriceDashboardQuery.data || basePriceData;
  const safetyData = selectedSafetyCityFilter ? safetyDashboardQuery.data : zoneData;
  const activeData = activePage === "preco"
    ? priceData
    : activePage === "seguranca"
      ? safetyData
      : zoneData;
  const propertyNeighborhoodName = basePriceData?.context.neighborhood_name || null;
  const propertyCityName = basePriceData?.context.city_name || null;
  const isPriceFilterActive = Boolean(selectedPriceFilter?.neighborhoodName && selectedPriceFilter?.cityName);
  const priceHistory = useMemo(
    () =>
      (priceData?.price.history || []).map((item) => ({
        day: new Date(item.date).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" }),
        neighborhoodPrice: item.neighborhood_median_price ?? null,
      })),
    [priceData?.price.history],
  );
  const peakHours = useMemo(
    () =>
      (zoneData?.safety.peak_hours || []).map((item) => ({
        hour: formatHourLabel(item.hour),
        total: item.total_count,
        robbery: item.robbery_count,
        theft: item.theft_count,
        homicide: item.homicide_count,
      })),
    [zoneData?.safety.peak_hours],
  );
  const isInitialLoading = !activeData && (zoneDashboardQuery.isLoading || basePriceDashboardQuery.isLoading || filteredPriceDashboardQuery.isLoading);
  const activeError = activePage === "preco"
    ? filteredPriceDashboardQuery.error || basePriceDashboardQuery.error || zoneDashboardQuery.error
    : activePage === "seguranca"
      ? safetyDashboardQuery.error || zoneDashboardQuery.error
      : zoneDashboardQuery.error;

  function handlePriceRankingSelect(item: DashboardRankingItem) {
    if (!propertyCityName) {
      return;
    }
    if (item.neighborhood_name === propertyNeighborhoodName) {
      setSelectedPriceFilter(null);
      return;
    }
    setSelectedPriceFilter({
      cityName: propertyCityName,
      neighborhoodName: item.neighborhood_name,
    });
  }

  function handleSafetyCityChange(nextCity: string) {
    if (!nextCity) {
      setSelectedSafetyCityFilter(null);
      return;
    }
    setSelectedSafetyCityFilter(nextCity);
  }

  return (
    <div className="space-y-6 animate-[fadeIn_0.3s_ease-out]">
      <div className="overflow-x-auto border-b border-transparent" data-testid="dashboard-page-tabs">
        <div className="flex min-w-max gap-6">
          {tabs.map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => setActivePage(item.key)}
              className={`pb-3 text-sm font-medium border-b-2 transition-colors ${activePage === item.key ? "border-pastel-violet-500 text-pastel-violet-600" : "border-transparent text-slate-500 hover:text-slate-700"}`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      {isInitialLoading ? (
        <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-5 text-sm text-slate-600 shadow-sm">
          <Loader2 className="h-4 w-4 animate-spin text-pastel-violet-500" />
          Carregando métricas analíticas direto da base...
        </div>
      ) : null}
      {activeError && !activeData ? (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-5 text-sm text-rose-700">{apiActionHint(activeError)}</div>
      ) : null}

      {!activeData || isInitialLoading ? null : activePage === "preco" ? (
        <div className="space-y-4" data-testid="dashboard-page-preco">
          {isPriceFilterActive && filteredPriceDashboardQuery.isFetching ? (
            <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-500 shadow-sm">
              Atualizando métricas do bairro filtrado...
            </div>
          ) : null}

          <DashboardRankingList
            title="Ranking do bairro"
            description={`${priceRankExplanation(priceData?.price.neighborhood_unit_price_rank)} · clique em um bairro para atualizar o dashboard.`}
            items={priceData?.price.neighborhood_unit_price_ranking || []}
            formatValue={formatCurrencyPerSquareMeter}
            secondaryValueFormatter={(item) => formatYearlyChangeInline(item.yearly_change_pct)}
            selectedLabel={(item) => {
              if (item.neighborhood_name !== propertyNeighborhoodName) {
                return "Filtro ativo";
              }
              return hasExplicitPropertySelection ? "Imóvel selecionado" : "Bairro de referência";
            }}
            onSelectItem={propertyCityName ? handlePriceRankingSelect : undefined}
            emptyMessage="Sem bairros suficientes com anúncios ativos para montar o ranking de preço por m²."
            testId="dashboard-price-ranking"
            heightClassName="h-[320px]"
          />

          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <h4 className="text-sm font-bold text-slate-800">Preço do bairro</h4>
                <p className="mt-1 text-xs text-slate-500">Mediana diária dos anúncios persistidos para o bairro ativo nos últimos 365 dias.</p>
              </div>
              <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600">365 dias</span>
            </div>
            <div className="h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={priceHistory}>
                  <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="day" tick={{ fontSize: 10 }} stroke="#94a3b8" />
                  <YAxis tickFormatter={(value) => `${Math.round(Number(value) / 1000)}k`} tick={{ fontSize: 10 }} stroke="#94a3b8" />
                  <Tooltip formatter={(value) => formatCurrencyBr(typeof value === "number" ? value : null)} />
                  <Line type="monotone" dataKey="neighborhoodPrice" name="Bairro" stroke="#16a34a" strokeWidth={2.5} dot={false} connectNulls />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <h4 className="text-sm font-bold text-slate-800">Histograma do bairro</h4>
                <p className="mt-1 text-xs text-slate-500">Distribuição do preço atual por faixa para o bairro selecionado no ranking.</p>
              </div>
              <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600">Preço atual</span>
            </div>
            <div className="h-60 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={priceData?.price.price_distribution}>
                  <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="label" tick={{ fontSize: 10 }} stroke="#94a3b8" />
                  <YAxis allowDecimals={false} tick={{ fontSize: 10 }} stroke="#94a3b8" />
                  <Tooltip />
                  <Bar dataKey="count" radius={[8, 8, 0, 0]}>
                    {(priceData?.price.price_distribution || []).map((entry) => (
                      <Cell key={entry.label} fill="#c4b5fd" />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {priceData?.price.note ? <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">{priceData.price.note}</div> : null}
        </div>
      ) : activePage === "seguranca" ? (
        <div className="space-y-4" data-testid="dashboard-page-seguranca">
          <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(168px,0.62fr)] xl:items-stretch">
            <CompactMetricCard
              icon={<ShieldAlert className="h-4.5 w-4.5" />}
              eyebrow="Taxa de homicídio"
              value={formatDensityPerSquareKm(zoneData?.safety.homicide_density_per_km2)}
              detail={`${zoneData?.safety.homicide_count_365d || 0} homicídios · por km² · ${rankLabel(zoneData?.safety.homicide_rank)}`}
              tone="rose"
              size="sm"
            />
            <CompactMetricCard
              icon={<AlertTriangle className="h-4.5 w-4.5" />}
              eyebrow="Taxa de roubo"
              value={formatDensityPerSquareKm(zoneData?.safety.robbery_density_per_km2)}
              detail={`${zoneData?.safety.robbery_count_365d || 0} roubos · por km² · ${rankLabel(zoneData?.safety.robbery_rate_rank)}`}
              tone="amber"
              size="sm"
            />
            <CompactMetricCard
              icon={<TrendingDown className="h-4 w-4" />}
              eyebrow="Roubo vs furto"
              value={formatRatio(zoneData?.safety.robbery_to_theft_ratio)}
              detail={`${zoneData?.safety.robbery_count_365d || 0} roubos · ${zoneData?.safety.theft_count_365d || 0} furtos`}
              tone="violet"
              size="xs"
              className="xl:max-w-[190px] xl:justify-self-end"
            />
          </div>

          <DashboardSafetyRankingList
            title={safetyRankingTitle(safetyData?.safety.ranking_scope_label || zoneData?.safety.ranking_scope_label)}
            description={safetyRankingDescription(selectedSafetyCityFilter, safetyData?.safety.ranking_scope_label || zoneData?.safety.ranking_scope_label)}
            items={safetyData?.safety.robbery_rate_ranking || []}
            cityOptions={safetyData?.safety.city_options || zoneData?.safety.city_options || []}
            selectedCity={selectedSafetyCityFilter}
            onChangeCity={handleSafetyCityChange}
            isFetching={safetyDashboardQuery.isFetching}
            formatValue={formatDensityPerSquareKmWithUnit}
            selectedLabel={safetySelectedLabel(safetyData?.safety.ranking_scope_label || zoneData?.safety.ranking_scope_label)}
            emptyMessage={safetyDashboardQuery.isFetching ? "Atualizando ranking da cidade selecionada..." : safetyRankingEmptyMessage(selectedSafetyCityFilter)}
            testId="dashboard-safety-ranking"
          />

          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <h4 className="text-sm font-bold text-slate-800">Horários de maior risco</h4>
                <p className="mt-1 text-xs text-slate-500">Distribuição horária das ocorrências da zona nos últimos 365 dias.</p>
              </div>
              <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600">Por tipo</span>
            </div>
            <div className="h-72 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={peakHours}>
                  <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="hour" tick={{ fontSize: 10 }} stroke="#94a3b8" />
                  <YAxis allowDecimals={false} tick={{ fontSize: 10 }} stroke="#94a3b8" />
                  <Tooltip content={<SafetyPeakHoursTooltip />} />
                  <Bar dataKey="theft" stackId="risk" fill="#eab308" radius={[0, 0, 0, 0]} />
                  <Bar dataKey="robbery" stackId="risk" fill="#ef4444" radius={[0, 0, 0, 0]} />
                  <Bar dataKey="homicide" stackId="risk" fill="#7f1d1d" radius={[8, 8, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {zoneData?.safety.ranking_scope_note ? (
            <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-[11px] leading-snug text-slate-500 shadow-sm">
              {zoneData.safety.ranking_scope_note}
            </div>
          ) : null}
        </div>
      ) : (
        <div className="space-y-5" data-testid="dashboard-page-ambiente">
          <div className="grid gap-4 md:grid-cols-2">
            <MetricCard
              icon={<Trees className="h-5 w-5" />}
              eyebrow="Arborização"
              value={formatPlainPercent(zoneData?.environment.green_percentage)}
              detail={`${Math.round(zoneData?.environment.green_area_m2 || 0)} m² de vegetação relevante`}
              tone="emerald"
            />
            <MetricCard
              icon={<MapPinned className="h-5 w-5" />}
              eyebrow="Ranking verde"
              value={rankLabel(zoneData?.environment.green_rank)}
              detail={rankHint(zoneData?.environment.green_rank)}
              tone="violet"
            />
            <MetricCard
              icon={<Droplets className="h-5 w-5" />}
              eyebrow="Risco de alagamento"
              value={zoneData?.environment.flood_risk_label || "Sem base"}
              detail={`${formatPlainPercent(zoneData?.environment.flood_percentage)} da zona em mancha de inundação`}
              tone="amber"
            />
            <MetricCard
              icon={<AlertTriangle className="h-5 w-5" />}
              eyebrow="Ranking de alagamento"
              value={rankLabel(zoneData?.environment.flood_rank)}
              detail={rankHint(zoneData?.environment.flood_rank)}
              tone="rose"
            />
          </div>

          <div className="space-y-5">
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">Leitura verde</p>
              <h4 className="mt-2 text-xl font-bold text-slate-800">Percentual de arborização da zona</h4>
              <div className="mt-5 overflow-hidden rounded-full bg-slate-100">
                <div
                  className="h-3 rounded-full bg-gradient-to-r from-emerald-400 to-emerald-600"
                  style={{ width: `${Math.max(4, Math.min(100, zoneData?.environment.green_percentage || 0))}%` }}
                />
              </div>
              <p className="mt-3 text-sm text-slate-500">A barra mostra quanto da área útil da zona intercepta a camada ambiental carregada no PostGIS.</p>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">Leitura de alagamento</p>
              <h4 className="mt-2 text-xl font-bold text-slate-800">Exposição qualitativa</h4>
              <div className="mt-5 overflow-hidden rounded-full bg-slate-100">
                <div
                  className="h-3 rounded-full bg-gradient-to-r from-amber-300 to-amber-600"
                  style={{ width: `${Math.max(4, Math.min(100, zoneData?.environment.flood_percentage || 0))}%` }}
                />
              </div>
              <p className="mt-3 text-sm text-slate-500">{Math.round(zoneData?.environment.flood_area_m2 || 0)} m² da zona cruzam a camada de mancha de inundação hoje disponível na base.</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function CompactMetricCard(props: {
  icon: React.ReactNode;
  eyebrow: string;
  value: string;
  detail?: string | null;
  tone?: "violet" | "emerald" | "amber" | "rose";
  size?: "sm" | "xs";
  className?: string;
}) {
  const toneClass = {
    violet: "bg-pastel-violet-50 text-pastel-violet-600",
    emerald: "bg-emerald-50 text-emerald-600",
    amber: "bg-amber-50 text-amber-600",
    rose: "bg-rose-50 text-rose-600",
  }[props.tone || "violet"];
  const sizeClass = props.size === "xs"
    ? {
        container: "rounded-xl px-3 py-2.5",
        eyebrow: "text-[8px] tracking-[0.11em]",
        value: "mt-1 text-[clamp(0.95rem,1.45vw,1.2rem)]",
        detail: "mt-1 text-[8.5px] leading-snug",
        icon: "rounded-lg p-1.5",
      }
    : {
        container: "rounded-xl px-3.5 py-3",
        eyebrow: "text-[8px] tracking-[0.12em]",
        value: "mt-1.5 text-[clamp(1rem,1.8vw,1.45rem)]",
        detail: "mt-1 text-[8.5px] leading-snug",
        icon: "rounded-lg p-2",
      };

  return (
    <div className={`${sizeClass.container} ${props.className || ""} border border-slate-200 bg-white shadow-sm`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className={`${sizeClass.eyebrow} font-semibold uppercase text-slate-500`}>{props.eyebrow}</p>
          <p className={`${sizeClass.value} truncate font-bold leading-none tracking-tight text-slate-800 tabular-nums`}>{props.value}</p>
          {props.detail ? <p className={`${sizeClass.detail} text-slate-500`}>{props.detail}</p> : null}
        </div>
        <div className={`${sizeClass.icon} ${toneClass}`}>{props.icon}</div>
      </div>
    </div>
  );
}

function DashboardRankingList(props: {
  title: string;
  description: string;
  items: DashboardRankingItem[];
  formatValue: (value: number | null | undefined) => string;
  secondaryValueFormatter?: (item: DashboardRankingItem) => string | null;
  selectedLabel?: string | ((item: DashboardRankingItem) => string | null);
  onSelectItem?: (item: DashboardRankingItem) => void;
  emptyMessage: string;
  testId: string;
  heightClassName?: string;
}) {
  const listContainerRef = useRef<HTMLDivElement | null>(null);
  const itemRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const selectedItem = props.items.find((item) => item.is_selected);

  useEffect(() => {
    if (!selectedItem) {
      return;
    }
    const listContainer = listContainerRef.current;
    const node = itemRefs.current[selectedItem.neighborhood_name];
    if (!node || !listContainer) {
      return;
    }
    const targetTop = Math.max(0, node.offsetTop - (listContainer.clientHeight / 2) + (node.clientHeight / 2));
    listContainer.scrollTo({ top: targetTop, behavior: "auto" });
  }, [selectedItem?.neighborhood_name, props.items]);

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm" data-testid={props.testId}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h4 className="text-sm font-bold text-slate-800">{props.title}</h4>
          <p className="mt-1 text-xs text-slate-500">{props.description}</p>
        </div>
        <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-medium text-slate-600">
          {`${props.items.length} no ranking`}
        </span>
      </div>

      {props.items.length === 0 ? (
        <div className="mt-4 rounded-xl border border-dashed border-slate-200 bg-slate-50 px-3 py-4 text-sm text-slate-500">{props.emptyMessage}</div>
      ) : (
        <div ref={listContainerRef} className={`mt-4 overflow-y-auto pr-1 ${props.heightClassName || "h-[290px]"}`}>
          <div className="space-y-2">
            {props.items.map((item) => (
              <button
                key={`${item.position}-${item.neighborhood_name}`}
                type="button"
                onClick={() => props.onSelectItem?.(item)}
                ref={(node) => {
                  itemRefs.current[item.neighborhood_name] = node;
                }}
                className={`grid w-full grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 rounded-xl border px-3 py-2.5 text-left transition-colors ${item.is_selected ? "border-pastel-violet-200 bg-pastel-violet-50/60" : "border-slate-200 bg-slate-50/70"} ${props.onSelectItem ? "hover:border-pastel-violet-200 hover:bg-pastel-violet-50/40" : "cursor-default"}`}
                disabled={!props.onSelectItem}
              >
                <div className="flex h-8 w-8 items-center justify-center rounded-full bg-white text-xs font-semibold text-slate-600 shadow-sm">
                  {item.position}º
                </div>
                <div className="min-w-0">
                  {item.city_name ? <p className="text-[10px] font-medium uppercase tracking-[0.08em] text-slate-400">{item.city_name}</p> : null}
                  <p className="truncate text-sm font-semibold text-slate-800">{item.neighborhood_name}</p>
                  {item.is_selected ? (
                    <p className="mt-0.5 text-[11px] font-medium text-pastel-violet-700">
                      {typeof props.selectedLabel === "function"
                        ? props.selectedLabel(item)
                        : props.selectedLabel || "Selecionado"}
                    </p>
                  ) : null}
                </div>
                <div className="min-w-[110px] text-right">
                  <p className="text-xs font-semibold text-slate-700">{props.formatValue(item.value)}</p>
                  {props.secondaryValueFormatter ? (
                    <p className="mt-0.5 text-[11px] text-slate-500">{props.secondaryValueFormatter(item)}</p>
                  ) : null}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function DashboardSafetyRankingList(props: {
  title: string;
  description: string;
  items: DashboardRankingItem[];
  cityOptions: string[];
  selectedCity: string | null;
  onChangeCity: (cityName: string) => void;
  isFetching: boolean;
  formatValue: (value: number | null | undefined) => string;
  selectedLabel?: string | ((item: DashboardRankingItem) => string | null);
  emptyMessage: string;
  testId: string;
}) {
  const entries = useMemo(() => buildSegmentedRankingEntries(props.items), [props.items]);

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm" data-testid={props.testId}>
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0">
          <h4 className="text-sm font-bold text-slate-800">{props.title}</h4>
          <p className="mt-1 text-xs text-slate-500">{props.description}</p>
        </div>
        <div className="flex items-center gap-2 self-start">
          {props.isFetching ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-medium text-slate-600">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Atualizando
            </span>
          ) : null}
          <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-medium text-slate-600">
            {`${props.items.length} bairros`}
          </span>
        </div>
      </div>

      <div className="mt-4">
        <DashboardCityCombobox
          label="Cidade do ranking"
          cityOptions={props.cityOptions}
          selectedCity={props.selectedCity}
          onChangeCity={props.onChangeCity}
        />
      </div>

      {entries.length === 0 ? (
        <div className="mt-4 rounded-xl border border-dashed border-slate-200 bg-slate-50 px-3 py-4 text-sm text-slate-500">{props.emptyMessage}</div>
      ) : (
        <div className="mt-4 space-y-2">
          {entries.map((entry) => {
            if (entry.type === "gap") {
              return (
                <div key={entry.key} className="flex justify-center py-1 text-slate-400" aria-hidden="true">
                  <span className="text-lg leading-none">...</span>
                </div>
              );
            }

            const item = entry.item;
            return (
              <div
                key={entry.key}
                className={`grid w-full grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 rounded-xl border px-3 py-2.5 text-left ${item.is_selected ? "border-pastel-violet-200 bg-pastel-violet-50/60" : "border-slate-200 bg-slate-50/70"}`}
              >
                <div className="flex h-8 w-8 items-center justify-center rounded-full bg-white text-xs font-semibold text-slate-600 shadow-sm">
                  {item.position}º
                </div>
                <div className="min-w-0">
                  {item.city_name ? <p className="text-[10px] font-medium uppercase tracking-[0.08em] text-slate-400">{item.city_name}</p> : null}
                  <p className="truncate text-sm font-semibold text-slate-800">{item.neighborhood_name}</p>
                  {item.is_selected ? (
                    <p className="mt-0.5 text-[11px] font-medium text-pastel-violet-700">
                      {typeof props.selectedLabel === "function"
                        ? props.selectedLabel(item)
                        : props.selectedLabel || "Selecionado"}
                    </p>
                  ) : null}
                </div>
                <div className="min-w-[88px] text-right">
                  <p className="text-xs font-semibold text-slate-700">{props.formatValue(item.value)}</p>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function DashboardCityCombobox(props: {
  label: string;
  cityOptions: string[];
  selectedCity: string | null;
  onChangeCity: (cityName: string) => void;
}) {
  const inputId = useId();
  const listboxId = `${inputId}-listbox`;
  const [inputValue, setInputValue] = useState(props.selectedCity || "");
  const [isOpen, setIsOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);

  const filteredOptions = useMemo(() => {
    const trimmedValue = inputValue.trim();
    if (!trimmedValue) {
      return props.cityOptions;
    }

    const lookupValue = normalizeComboboxText(trimmedValue);
    return props.cityOptions.filter((cityName) => normalizeComboboxText(cityName).includes(lookupValue));
  }, [props.cityOptions, inputValue]);

  useEffect(() => {
    setInputValue(props.selectedCity || "");
  }, [props.selectedCity]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    setActiveIndex(filteredOptions.length > 0 ? 0 : -1);
  }, [filteredOptions, isOpen]);

  function resetToSelection() {
    setInputValue(props.selectedCity || "");
    setIsOpen(false);
    setActiveIndex(-1);
  }

  function selectCity(cityName: string) {
    setInputValue(cityName);
    setIsOpen(false);
    setActiveIndex(-1);
    props.onChangeCity(cityName);
  }

  function clearSelection() {
    setInputValue("");
    setIsOpen(true);
    setActiveIndex(props.cityOptions.length > 0 ? 0 : -1);
    props.onChangeCity("");
  }

  return (
    <div className="space-y-1.5">
      <label htmlFor={inputId} className="block text-xs font-medium text-slate-600">{props.label}</label>
      <div className="relative">
        <input
          id={inputId}
          type="text"
          role="combobox"
          aria-label="Filtrar ranking de segurança por cidade"
          aria-autocomplete="list"
          aria-expanded={isOpen}
          aria-controls={listboxId}
          aria-activedescendant={activeIndex >= 0 ? `${listboxId}-${activeIndex}` : undefined}
          value={inputValue}
          placeholder=""
          className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700 outline-none transition placeholder:text-slate-300 focus:border-pastel-violet-300 focus:bg-white"
          onFocus={() => setIsOpen(true)}
          onBlur={() => {
            window.setTimeout(() => {
              resetToSelection();
            }, 120);
          }}
          onChange={(event) => {
            const nextValue = event.target.value;
            setInputValue(nextValue);
            setIsOpen(true);
            if (!nextValue.trim()) {
              clearSelection();
            }
          }}
          onKeyDown={(event) => {
            if (!isOpen && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
              event.preventDefault();
              setIsOpen(true);
              return;
            }

            if (event.key === "ArrowDown") {
              event.preventDefault();
              if (filteredOptions.length === 0) {
                return;
              }
              setActiveIndex((current) => (current + 1) % filteredOptions.length);
              return;
            }

            if (event.key === "ArrowUp") {
              event.preventDefault();
              if (filteredOptions.length === 0) {
                return;
              }
              setActiveIndex((current) => (current <= 0 ? filteredOptions.length - 1 : current - 1));
              return;
            }

            if (event.key === "Enter") {
              if (activeIndex >= 0 && activeIndex < filteredOptions.length) {
                event.preventDefault();
                selectCity(filteredOptions[activeIndex]);
              }
              return;
            }

            if (event.key === "Escape") {
              event.preventDefault();
              resetToSelection();
            }
          }}
        />
        <button
          type="button"
          aria-label={isOpen ? "Fechar lista de cidades" : "Abrir lista de cidades"}
          className="absolute inset-y-0 right-0 flex w-10 items-center justify-center text-slate-500"
          onMouseDown={(event) => event.preventDefault()}
          onClick={() => setIsOpen((current) => !current)}
        >
          <ChevronDown className={`h-4 w-4 transition-transform ${isOpen ? "rotate-180" : "rotate-0"}`} />
        </button>

        {isOpen ? (
          <div className="absolute left-0 right-0 top-[calc(100%+0.5rem)] z-20 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-[0_18px_48px_rgba(15,23,42,0.16)] animate-[fadeInDown_0.18s_ease-out]">
            {filteredOptions.length > 0 ? (
              <div id={listboxId} role="listbox" className="max-h-72 overflow-y-auto py-1">
                {filteredOptions.map((cityName, index) => (
                  <button
                    id={`${listboxId}-${index}`}
                    key={cityName}
                    type="button"
                    role="option"
                    aria-selected={cityName === props.selectedCity}
                    className={`flex w-full items-center justify-between px-3 py-2 text-left text-sm transition ${index === activeIndex ? "bg-pastel-violet-50 text-pastel-violet-700" : "text-slate-700 hover:bg-slate-50"}`}
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => selectCity(cityName)}
                  >
                    <span>{cityName}</span>
                    {cityName === props.selectedCity ? <span className="text-[11px] font-medium text-pastel-violet-700">Selecionada</span> : null}
                  </button>
                ))}
              </div>
            ) : (
              <div className="px-3 py-3 text-sm text-slate-500">Nenhuma cidade encontrada.</div>
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
}