import { useEffect, useId, useMemo, useState } from "react";
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
import { type ListingsPanelFilters } from "../../state";

const DASHBOARD_ANALYTICS_STALE_TIME = 30 * 60_000;
const DASHBOARD_ANALYTICS_GC_TIME = 60 * 60_000;
const PRICE_DASHBOARD_FILTER_DEBOUNCE_MS = 350;

type DashboardPage = "preco" | "seguranca" | "ambiente";

type Step6DashboardProps = {
  journeyId: string;
  zoneFingerprint: string;
  searchType: string;
  listingsFilters: ListingsPanelFilters;
};

type DashboardRankingItem = {
  position: number;
  neighborhood_name: string;
  city_name?: string | null;
  value?: number | null;
  yearly_change_pct?: number | null;
  listing_count?: number | null;
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

function buildPriceDashboardAnalyticsOptions(filters: ListingsPanelFilters, cityName: string | null = null) {
  return {
    cityName,
    minPrice: filters.minPrice || null,
    maxPrice: filters.maxPrice || null,
    usageType: filters.usageType,
    spatialScope: filters.spatialScope,
    minSize: filters.minSize || null,
    maxSize: filters.maxSize || null,
  };
}

function arePriceDashboardFiltersEqual(left: ListingsPanelFilters, right: ListingsPanelFilters) {
  return left.minPrice === right.minPrice
    && left.maxPrice === right.maxPrice
    && left.usageType === right.usageType
    && left.spatialScope === right.spatialScope
    && left.minSize === right.minSize
    && left.maxSize === right.maxSize;
}

function formatFilterIntegerLabel(value: string) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) {
    return value;
  }
  return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 }).format(numericValue);
}

function buildPriceDashboardFilterSummary(filters: ListingsPanelFilters) {
  const parts = [
    filters.spatialScope === "inside_zone" ? "escopo: apenas dentro da zona" : "escopo: todos os imóveis",
    filters.usageType === "residential"
      ? "tipo: residencial"
      : filters.usageType === "commercial"
        ? "tipo: comercial"
        : "tipo: todos",
  ];

  if (filters.minPrice && filters.maxPrice) {
    parts.push(`preço: R$ ${formatFilterIntegerLabel(filters.minPrice)} a R$ ${formatFilterIntegerLabel(filters.maxPrice)}`);
  } else if (filters.minPrice) {
    parts.push(`preço: a partir de R$ ${formatFilterIntegerLabel(filters.minPrice)}`);
  } else if (filters.maxPrice) {
    parts.push(`preço: até R$ ${formatFilterIntegerLabel(filters.maxPrice)}`);
  }

  if (filters.minSize && filters.maxSize) {
    parts.push(`área: ${formatFilterIntegerLabel(filters.minSize)} a ${formatFilterIntegerLabel(filters.maxSize)} m²`);
  } else if (filters.minSize) {
    parts.push(`área: a partir de ${formatFilterIntegerLabel(filters.minSize)} m²`);
  } else if (filters.maxSize) {
    parts.push(`área: até ${formatFilterIntegerLabel(filters.maxSize)} m²`);
  }

  return parts.join(" · ");
}

function priceRankingDescription(selectedCity: string | null | undefined, scopeLabel: string | null | undefined) {
  const scope = scopeLabel || "Valor médio do m² por bairro";
  const cityLabel = selectedCity ? `cidade: ${selectedCity}` : "sem filtro de cidade";
  return `${scope} · ${cityLabel} · exibição resumida com 2 do topo, 2 do entorno do bairro com mais imóveis no recorte atual e 2 da base.`;
}

function priceRankingEmptyMessage(selectedCity: string | null | undefined) {
  if (selectedCity) {
    return "Sem bairros com anúncios ativos na cidade selecionada dentro do recorte atual.";
  }
  return "Sem bairros com anúncios ativos no recorte atual para montar o ranking de preço por m².";
}

function formatListingCountInline(value: number | null | undefined) {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) {
    return "Sem amostra atual";
  }
  return `${formatOccurrenceCount(value)} imóveis no recorte`;
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
    <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3.5 shadow-sm">
      <div className="relative pr-14">
        <p className="text-[10px] font-semibold uppercase leading-tight tracking-[0.16em] text-slate-500">{props.eyebrow}</p>
        <div className={`absolute right-0 top-0 shrink-0 rounded-lg p-1.5 ${toneClass}`}>{props.icon}</div>
        <p className="mt-1 text-[1.9rem] font-bold leading-none text-slate-800">{props.value}</p>
        {props.detail ? <p className="mt-1.5 text-[0.95rem] leading-snug text-slate-500">{props.detail}</p> : null}
      </div>
    </div>
  );
}

function DashboardPriceFiltersHero(props: {
  filters: ListingsPanelFilters;
  activeListingCount: number | null | undefined;
}) {
  const summary = buildPriceDashboardFilterSummary(props.filters);

  return (
    <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600 shadow-sm" data-testid="dashboard-price-filters-hero">
      <p className="leading-relaxed">
        <span className="font-semibold text-slate-800">Filtros aplicados:</span>
        {` ${summary}. ${formatOccurrenceCount(props.activeListingCount)} anúncios ativos considerados no dashboard. A seleção de um anúncio não altera este recorte.`}
      </p>
    </div>
  );
}

export function Step6Dashboard({ journeyId, zoneFingerprint, searchType, listingsFilters }: Step6DashboardProps) {
  const [activePage, setActivePage] = useState<DashboardPage>("preco");
  const [selectedPriceCityFilter, setSelectedPriceCityFilter] = useState<string | null>(null);
  const [selectedSafetyCityFilter, setSelectedSafetyCityFilter] = useState<string | null>(null);
  const [debouncedPriceFilters, setDebouncedPriceFilters] = useState<ListingsPanelFilters>(listingsFilters);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      setDebouncedPriceFilters((current) => (
        arePriceDashboardFiltersEqual(current, listingsFilters) ? current : listingsFilters
      ));
    }, PRICE_DASHBOARD_FILTER_DEBOUNCE_MS);

    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [listingsFilters]);

  const hasPriceFilterUpdatePending = !arePriceDashboardFiltersEqual(debouncedPriceFilters, listingsFilters);
  const tabs: Array<{ key: DashboardPage; label: string }> = [
    { key: "preco", label: "Preço e valor" },
    { key: "seguranca", label: "Segurança" },
    { key: "ambiente", label: "Vegetação e alagamento" },
  ];

  useEffect(() => {
    setSelectedPriceCityFilter(null);
    setSelectedSafetyCityFilter(null);
  }, [journeyId, zoneFingerprint, searchType]);

  const zoneDashboardQuery = useQuery({
    queryKey: ["zone-dashboard-analytics", journeyId, zoneFingerprint, searchType, "zone", activePage],
    queryFn: async () => getZoneDashboardAnalytics(
      journeyId,
      zoneFingerprint,
      searchType,
      { page: activePage },
    ),
    enabled: Boolean(journeyId && zoneFingerprint && activePage !== "preco"),
    staleTime: DASHBOARD_ANALYTICS_STALE_TIME,
    gcTime: DASHBOARD_ANALYTICS_GC_TIME,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  });

  const priceDashboardQuery = useQuery({
    queryKey: [
      "zone-dashboard-analytics",
      journeyId,
      zoneFingerprint,
      searchType,
      "price-panel",
      selectedPriceCityFilter || "default",
      debouncedPriceFilters.spatialScope,
      debouncedPriceFilters.usageType,
      debouncedPriceFilters.minPrice || "",
      debouncedPriceFilters.maxPrice || "",
      debouncedPriceFilters.minSize || "",
      debouncedPriceFilters.maxSize || "",
    ],
    queryFn: async () => getZoneDashboardAnalytics(
      journeyId,
      zoneFingerprint,
      searchType,
      {
        ...buildPriceDashboardAnalyticsOptions(debouncedPriceFilters, selectedPriceCityFilter),
        page: "preco",
      },
    ),
    enabled: Boolean(journeyId && zoneFingerprint && activePage === "preco"),
    staleTime: DASHBOARD_ANALYTICS_STALE_TIME,
    gcTime: DASHBOARD_ANALYTICS_GC_TIME,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
    placeholderData: keepPreviousData,
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
      page: "seguranca",
    }),
    enabled: Boolean(journeyId && zoneFingerprint && activePage === "seguranca" && selectedSafetyCityFilter),
    staleTime: DASHBOARD_ANALYTICS_STALE_TIME,
    gcTime: DASHBOARD_ANALYTICS_GC_TIME,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  });

  const zoneData = zoneDashboardQuery.data;
  const priceData = priceDashboardQuery.data;
  const safetyData = selectedSafetyCityFilter ? safetyDashboardQuery.data : zoneData;
  const activeData = activePage === "preco"
    ? priceData
    : activePage === "seguranca"
      ? safetyData
      : zoneData;
  const priceHistory = useMemo(
    () =>
      (priceData?.price.history || []).map((item) => ({
        day: new Date(item.date).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" }),
        zoneAveragePrice: item.zone_average_price ?? null,
        neighborhoodAveragePrice: item.neighborhood_average_price ?? null,
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
  const isInitialLoading = activePage === "preco"
    ? !priceData && (priceDashboardQuery.isLoading || priceDashboardQuery.isFetching)
    : !activeData && zoneDashboardQuery.isLoading;
  const activeError = activePage === "preco"
    ? priceDashboardQuery.error
    : activePage === "seguranca"
      ? safetyDashboardQuery.error || zoneDashboardQuery.error
      : zoneDashboardQuery.error;

  function handlePriceCityChange(nextCity: string) {
    if (!nextCity) {
      setSelectedPriceCityFilter(null);
      return;
    }
    setSelectedPriceCityFilter(nextCity);
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
          Carregando métricas analíticas diretamente da base...
        </div>
      ) : null}
      {activeError && !activeData ? (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-5 text-sm text-rose-700">{apiActionHint(activeError)}</div>
      ) : null}

      {!activeData || isInitialLoading ? null : activePage === "preco" ? (
        <div className="space-y-4" data-testid="dashboard-page-preco">
          <DashboardPriceFiltersHero
            filters={listingsFilters}
            activeListingCount={priceData?.price.zone_active_listing_count ?? null}
          />

          {hasPriceFilterUpdatePending ? (
            <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-500 shadow-sm">
              Aplicando os filtros do painel ao dashboard de imóveis...
            </div>
          ) : null}

          {selectedPriceCityFilter && priceDashboardQuery.isFetching ? (
            <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-500 shadow-sm">
              Atualizando ranking da cidade selecionada...
            </div>
          ) : null}

          <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(168px,0.62fr)] xl:items-stretch">
            <CompactMetricCard
              icon={<TrendingUp className="h-4 w-4" />}
              eyebrow={listingsFilters.spatialScope === "inside_zone" ? "Preço médio na zona" : "Preço médio do recorte"}
              value={formatCurrencyBr(priceData?.price.zone_average_price ?? null)}
              detail={`${formatOccurrenceCount(priceData?.price.zone_active_listing_count)} anúncios ativos no recorte atual`}
              tone="violet"
              size="sm"
            />
            <CompactMetricCard
              icon={<MapPinned className="h-4 w-4" />}
              eyebrow="Valor médio do m²"
              value={formatCurrencyPerSquareMeter(priceData?.price.zone_average_unit_price)}
              detail={priceData?.price.selected_neighborhood_name
                ? `Bairro destacado no recorte: ${priceData.price.selected_neighborhood_name}`
                : "Sem bairro predominante no recorte atual"}
              tone="emerald"
              size="sm"
            />
            <CompactMetricCard
              icon={<TrendingDown className="h-4 w-4" />}
              eyebrow="Variação média 365d"
              value={formatPercent(priceData?.price.zone_yearly_change_pct)}
              detail="Comparação entre o primeiro e o último ponto diário da série do recorte"
              tone="amber"
              size="sm"
              className="xl:max-w-[190px] xl:justify-self-end"
            />
          </div>

          <DashboardPriceRankingList
            title="Ranking do bairro"
            description={priceRankingDescription(selectedPriceCityFilter, priceData?.price.ranking_scope_label)}
            items={priceData?.price.neighborhood_unit_price_ranking || []}
            cityOptions={priceData?.price.city_options || zoneData?.price.city_options || []}
            selectedCity={selectedPriceCityFilter}
            onChangeCity={handlePriceCityChange}
            isFetching={priceDashboardQuery.isFetching}
            formatValue={formatCurrencyPerSquareMeter}
            secondaryValueFormatter={(item) => `${formatListingCountInline(item.listing_count)} · ${formatYearlyChangeInline(item.yearly_change_pct)}`}
            selectedLabel={listingsFilters.spatialScope === "inside_zone" ? "Bairro com mais imóveis na zona" : "Bairro com mais imóveis no recorte"}
            emptyMessage={priceDashboardQuery.isFetching ? "Atualizando ranking da cidade selecionada..." : priceRankingEmptyMessage(selectedPriceCityFilter)}
            testId="dashboard-price-ranking"
          />

          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <h4 className="text-sm font-bold text-slate-800">Preço médio ao longo do tempo</h4>
                <p className="mt-1 text-xs text-slate-500">Série diária do recorte atual e do bairro destacado nos últimos 365 dias.</p>
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
                  <Line type="monotone" dataKey="zoneAveragePrice" name={listingsFilters.spatialScope === "inside_zone" ? "Zona" : "Recorte"} stroke="#8b5cf6" strokeWidth={2.5} dot={false} connectNulls />
                  <Line type="monotone" dataKey="neighborhoodAveragePrice" name="Bairro destacado" stroke="#16a34a" strokeWidth={2.5} dot={false} connectNulls />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <h4 className="text-sm font-bold text-slate-800">Histograma do bairro destacado</h4>
                <p className="mt-1 text-xs text-slate-500">Distribuição do preço atual por faixa para o bairro com mais imóveis no recorte filtrado atual.</p>
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
              icon={<ShieldAlert className="h-4 w-4" />}
              eyebrow="Taxa de homicídio"
              value={formatDensityPerSquareKm(zoneData?.safety.homicide_density_per_km2)}
              detail={`${zoneData?.safety.homicide_count_365d || 0} homicídios · por km² · ${rankLabel(zoneData?.safety.homicide_rank)}`}
              tone="rose"
              size="sm"
            />
            <CompactMetricCard
              icon={<AlertTriangle className="h-4 w-4" />}
              eyebrow="Taxa de roubo"
              value={formatDensityPerSquareKm(zoneData?.safety.robbery_density_per_km2)}
              detail={`${zoneData?.safety.robbery_count_365d || 0} roubos · por km² · ${rankLabel(zoneData?.safety.robbery_rate_rank)}`}
              tone="amber"
              size="sm"
            />
            <CompactMetricCard
              icon={<TrendingDown className="h-4 w-4" />}
              eyebrow="Relação roubo/furto"
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
        container: "rounded-xl px-3 py-2",
        content: "pr-10",
        eyebrow: "text-[9px] tracking-[0.1em]",
        value: "text-[clamp(1rem,1.45vw,1.28rem)]",
        detail: "mt-auto text-[9.5px] leading-snug",
        icon: "rounded-md p-1",
      }
    : {
        container: "rounded-xl px-3.5 py-2.5",
        content: "pr-12",
        eyebrow: "text-[9.5px] tracking-[0.11em]",
        value: "text-[clamp(1rem,1.45vw,1.28rem)]",
        detail: "mt-auto text-[10px] leading-snug",
        icon: "rounded-md p-1.25",
      };

  return (
    <div className={`${sizeClass.container} ${props.className || ""} flex h-full min-h-[135px] border border-slate-200 bg-white shadow-sm`}>
      <div className="flex min-w-0 flex-1 flex-col">
        <div className={`relative min-w-0 ${sizeClass.content}`}>
          <p className={`${sizeClass.eyebrow} font-semibold uppercase leading-tight text-slate-500`}>{props.eyebrow}</p>
          <div className={`${sizeClass.icon} absolute right-0 top-0 shrink-0 ${toneClass}`}>{props.icon}</div>
        </div>
        <div className="flex flex-1 items-center">
          <p className={`${sizeClass.value} w-full text-center font-bold leading-none tracking-tight text-slate-800 tabular-nums`}>{props.value}</p>
        </div>
        {props.detail ? <p className={`${sizeClass.detail} text-slate-500`}>{props.detail}</p> : null}
      </div>
    </div>
  );
}

function DashboardPriceRankingList(props: {
  title: string;
  description: string;
  items: DashboardRankingItem[];
  cityOptions: string[];
  selectedCity: string | null;
  onChangeCity: (cityName: string) => void;
  isFetching: boolean;
  formatValue: (value: number | null | undefined) => string;
  secondaryValueFormatter?: (item: DashboardRankingItem) => string | null;
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
          ariaLabel="Filtrar ranking de imóveis por cidade"
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
                <div className="min-w-[132px] text-right">
                  <p className="text-xs font-semibold text-slate-700">{props.formatValue(item.value)}</p>
                  {props.secondaryValueFormatter ? (
                    <p className="mt-0.5 text-[11px] text-slate-500">{props.secondaryValueFormatter(item)}</p>
                  ) : null}
                </div>
              </div>
            );
          })}
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
          ariaLabel="Filtrar ranking de segurança por cidade"
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
  ariaLabel: string;
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
          aria-label={props.ariaLabel}
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