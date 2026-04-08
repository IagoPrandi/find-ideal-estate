import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  CircleDot,
  ExternalLink,
  Home,
  Loader2,
  MapIcon,
  Minus,
  ShieldX,
  SlidersHorizontal,
  Building2,
  X,
} from "lucide-react";
import { getJob, getZoneDashboardAnalytics, getZoneListings, type ListingCardRead, type ListingPlatformVariantRead } from "../../api/client";
import { ListingsScrapeDiagnosticsSchema, type ListingsScrapeDiagnostics, type ListingsScrapePlatformDiagnostics } from "../../api/schemas";
import { applyListingsPanelFilters, formatCurrencyBr, getListingDisplayPrice, getListingSelectionKey, parseFiniteNumber, resolvePlatformImageUrl, resolvePlatformUrl } from "../../lib/listingFormat";
import { defaultListingsPanelFilters, useJourneyStore, useUIStore, type ListingsPanelFilters } from "../../state";
import { Step6Dashboard } from "./Step6Dashboard";

const DASHBOARD_ANALYTICS_STALE_TIME = 30 * 60_000;
const DASHBOARD_ANALYTICS_GC_TIME = 60 * 60_000;

function platformLabel(value: string | null | undefined) {
  if (!value) {
    return "Plataforma";
  }
  const normalized = value.trim().toLowerCase();
  if (normalized === "quintoandar") {
    return "QuintoAndar";
  }
  if (normalized === "vivareal") {
    return "VivaReal";
  }
  if (normalized === "zapimoveis") {
    return "ZapImóveis";
  }
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function availablePlatformsLabel(platforms: string[] | null | undefined, primary: string | null | undefined) {
  const normalized = (platforms || []).filter(Boolean);
  if (normalized.length > 1) {
    return `${normalized.length} plataformas`;
  }
  return platformLabel(normalized[0] || primary);
}

function freshnessLabel(value: string | null | undefined) {
  if (value === "no_cache") {
    return "Scraping em andamento";
  }
  if (value === "queued_for_next_prewarm") {
    return "Busca iniciada";
  }
  if (value === "fresh") {
    return "Resultado consolidado";
  }
  if (value === "stale") {
    return "Cache reutilizado";
  }
  return value || "Sem cache consolidado";
}

function formatDuration(ms: number | null | undefined) {
  if (typeof ms !== "number" || !Number.isFinite(ms) || ms <= 0) {
    return null;
  }
  const totalSeconds = Math.round(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes <= 0) {
    return `${seconds}s`;
  }
  return `${minutes}m ${String(seconds).padStart(2, "0")}s`;
}

function platformStatusMeta(status: string | null | undefined) {
  switch (status) {
    case "completed":
      return {
        label: "Concluída",
        className: "border-emerald-200 bg-emerald-50 text-emerald-700",
        Icon: CheckCircle2
      };
    case "failed":
      return {
        label: "Falhou",
        className: "border-rose-200 bg-rose-50 text-rose-700",
        Icon: ShieldX
      };
    case "persisting":
      return {
        label: "Persistindo",
        className: "border-amber-200 bg-amber-50 text-amber-700",
        Icon: CircleDot
      };
    case "scraping":
      return {
        label: "Raspando",
        className: "border-pastel-violet-200 bg-pastel-violet-50 text-pastel-violet-700",
        Icon: Loader2
      };
    default:
      return {
        label: "Na fila",
        className: "border-slate-200 bg-slate-50 text-slate-600",
        Icon: CircleDot
      };
  }
}

function extractListingsScrapeDiagnostics(resultRef: Record<string, unknown> | null | undefined): ListingsScrapeDiagnostics | null {
  const candidate = resultRef?.scrape_diagnostics;
  const parsed = ListingsScrapeDiagnosticsSchema.safeParse(candidate);
  return parsed.success ? parsed.data : null;
}

function formatPlatformVariantHint(variant: ListingPlatformVariantRead, primaryPlatform: string | null | undefined) {
  if (variant.platform === primaryPlatform) {
    return "Menor preço consolidado";
  }
  return "Também encontrado nesta plataforma";
}

function formatPercentDelta(value: number | null | undefined) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "Sem base";
  }
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function hasPriceDashboardPanelFilterOverrides(filters: ListingsPanelFilters) {
  return filters.minPrice !== defaultListingsPanelFilters.minPrice
    || filters.maxPrice !== defaultListingsPanelFilters.maxPrice
    || filters.usageType !== defaultListingsPanelFilters.usageType
    || filters.spatialScope !== defaultListingsPanelFilters.spatialScope
    || filters.minSize !== defaultListingsPanelFilters.minSize
    || filters.maxSize !== defaultListingsPanelFilters.maxSize;
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

function ListingAccessibilityPopover(props: {
  open: boolean;
  onClose: () => void;
  popoverId: string;
  listing: ListingCardRead | null;
}) {
  if (!props.open) {
    return null;
  }

  const selectedUnitPrice = props.listing?.current_unit_price;
  const neighborhoodDelta = props.listing?.current_vs_neighborhood_pct;
  const neighborhoodName = props.listing?.neighborhood_name;
  const deltaDetail = neighborhoodName
    ? `Comparação frente à mediana de ${neighborhoodName}`
    : "Comparação frente à mediana do bairro do imóvel";

  return (
    <div
      id={props.popoverId}
      role="dialog"
      aria-modal="false"
      aria-label="Preço do imóvel versus bairro"
      data-testid={props.popoverId}
      className="absolute inset-x-0 bottom-0 z-30 animate-[fadeIn_0.18s_ease-out] overflow-hidden rounded-[24px] border border-slate-200 bg-slate-100/95 shadow-2xl backdrop-blur-sm"
      onClick={(event) => event.stopPropagation()}
    >
      <div className="border-b border-slate-200 bg-white/90 px-3 py-2.5">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">Acessibilidade do imóvel</p>
            <p className="mt-1 truncate text-xs font-semibold text-slate-800">Preço do imóvel versus bairro</p>
            <p className="mt-1 truncate text-[11px] leading-snug text-slate-500">{props.listing?.address_normalized || "Endereço do anúncio indisponível"}</p>
          </div>
          <button
            type="button"
            onClick={props.onClose}
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700"
            aria-label="Fechar acessibilidade do imóvel"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      <div className="grid gap-2 p-2.5 md:grid-cols-2">
        <div className="rounded-xl border border-slate-200 bg-white/95 px-2.5 py-2.5 shadow-sm">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">Valor por m²</p>
              <p className="mt-1 text-xs font-semibold text-slate-800">{formatCurrencyBr(selectedUnitPrice)}</p>
              <p className="mt-1 text-[11px] leading-snug text-slate-500">Valor atual por m² do anúncio selecionado</p>
            </div>
            <div className="rounded-lg bg-pastel-violet-50 p-2 text-pastel-violet-600">
              <Building2 className="h-3.5 w-3.5" />
            </div>
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white/95 px-2.5 py-2.5 shadow-sm">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">Diferença vs bairro</p>
              <p className="mt-1 text-xs font-semibold text-slate-800">{formatPercentDelta(neighborhoodDelta)}</p>
              <p className="mt-1 text-[11px] leading-snug text-slate-500">{neighborhoodDelta === null || neighborhoodDelta === undefined ? "Sem base comparativa" : deltaDetail}</p>
            </div>
            <div className="rounded-lg bg-amber-50 p-2 text-amber-600">
              {typeof neighborhoodDelta === "number" && neighborhoodDelta > 0 ? <ArrowUpRight className="h-3.5 w-3.5" /> : <ArrowDownRight className="h-3.5 w-3.5" />}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function Step6Analysis() {
  const queryClient = useQueryClient();
  const journeyId = useJourneyStore((state) => state.journeyId);
  const zoneFingerprint = useJourneyStore((state) => state.selectedZoneFingerprint);
  const listingsJobId = useJourneyStore((state) => state.listingsJobId);
  const listingsFilters = useJourneyStore((state) => state.listingsFilters);
  const selectedListingKey = useJourneyStore((state) => state.selectedListingKey);
  const setListingsFilters = useJourneyStore((state) => state.setListingsFilters);
  const setSelectedListingKey = useJourneyStore((state) => state.setSelectedListingKey);
  const config = useJourneyStore((state) => state.config);
  const activeTab = useUIStore((state) => state.activeTab);
  const setActiveTab = useUIStore((state) => state.setActiveTab);
  const listingCardRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const listingsPanelScrollRef = useRef<HTMLDivElement | null>(null);
  const lastScrolledListingKeyRef = useRef<string | null>(null);
  const lastProgressRunKeyRef = useRef<string | null>(null);
  const autoCollapsedProgressRunKeyRef = useRef<string | null>(null);
  const [isProgressCollapsed, setIsProgressCollapsed] = useState(false);
  const [isFiltersCollapsed, setIsFiltersCollapsed] = useState(false);
  const [isPreparingDashboard, setIsPreparingDashboard] = useState(false);
  const [openAvailabilityPopoverKey, setOpenAvailabilityPopoverKey] = useState<string | null>(null);
  const [openAccessibilityPopoverKey, setOpenAccessibilityPopoverKey] = useState<string | null>(null);

  const persistedListingsJobId = listingsJobId;

  const listingsQuery = useQuery({
    queryKey: ["zone-listings", journeyId, zoneFingerprint, config.type, "all"],
    queryFn: async () => getZoneListings(journeyId as string, zoneFingerprint as string, config.type, "all", "all"),
    enabled: Boolean(journeyId && zoneFingerprint),
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) {
        return 5000;
      }
      const emptyResults = (data.total_count || 0) === 0;
      return data.source === "none" || data.freshness_status === "no_cache" || emptyResults || Boolean(persistedListingsJobId) ? 5000 : false;
    }
  });

  const effectiveListingsJobId = persistedListingsJobId || listingsQuery.data?.job_id || null;

  const listingsJobQuery = useQuery({
    queryKey: ["listings-job", effectiveListingsJobId],
    queryFn: async () => getJob(effectiveListingsJobId as string),
    enabled: Boolean(effectiveListingsJobId),
    refetchInterval: (query) => {
      const state = query.state.data?.state;
      return state === "completed" || state === "failed" || state === "cancelled" ? false : 5000;
    }
  });

  const rawListings = listingsQuery.data?.listings || [];
  const listingsInZone = rawListings.filter((listing) => listing.inside_zone);
  const listingsOutsideZone = rawListings.filter((listing) => listing.has_coordinates && !listing.inside_zone);
  const listingsWithoutCoordinates = rawListings.filter((listing) => !listing.has_coordinates);

  const scrapeDiagnostics = extractListingsScrapeDiagnostics((listingsJobQuery.data?.result_ref as Record<string, unknown> | null | undefined) || undefined);
  const platformEntries = useMemo(() => {
    if (!scrapeDiagnostics) {
      return [] as Array<{ platform: string; details: ListingsScrapePlatformDiagnostics }>;
    }
    const platformMap = scrapeDiagnostics.platforms || {};
    const orderedPlatforms = scrapeDiagnostics.platform_order.length > 0
      ? scrapeDiagnostics.platform_order
      : Object.keys(platformMap).sort((left, right) => {
          const leftSequence = platformMap[left]?.sequence ?? Number.MAX_SAFE_INTEGER;
          const rightSequence = platformMap[right]?.sequence ?? Number.MAX_SAFE_INTEGER;
          return leftSequence - rightSequence;
        });
    return orderedPlatforms.map((platform) => ({
      platform,
      details: platformMap[platform] || {}
    }));
  }, [scrapeDiagnostics]);

  const isScraping = listingsQuery.isLoading || listingsQuery.data?.freshness_status === "no_cache" || listingsJobQuery.data?.state === "running";
  const diagnosticsSummary = scrapeDiagnostics?.summary;
  const overallDuration = formatDuration(scrapeDiagnostics?.total_duration_ms);
  const progressRunKey = [
    journeyId || "no-journey",
    zoneFingerprint || "no-zone",
    effectiveListingsJobId || "no-job",
    listingsQuery.data?.freshness_status || "unknown"
  ].join(":");
  const hasCompletedListingsGeneration = Boolean(platformEntries.length)
    && !isScraping
    && (listingsJobQuery.data?.state === "completed"
      || listingsQuery.data?.freshness_status === "fresh"
      || listingsQuery.data?.freshness_status === "stale");
  const scrapedButNoCards = (listingsQuery.data?.source === "cache")
    && rawListings.length === 0
    && (diagnosticsSummary?.total_scraped || 0) > 0
    && listingsJobQuery.data?.state === "completed";

  const listingsForScope = listingsFilters.spatialScope === "inside_zone" ? listingsInZone : rawListings;
  const noMatchesInZoneForScope = listingsFilters.spatialScope === "inside_zone"
    && rawListings.length > 0
    && listingsForScope.length === 0;

  const displayedListings = applyListingsPanelFilters(rawListings, listingsFilters);
  const selectedDashboardListing = useMemo(
    () => rawListings.find((listing) => getListingSelectionKey(listing) === selectedListingKey) || null,
    [rawListings, selectedListingKey],
  );
  const hasPriceDashboardOverrides = hasPriceDashboardPanelFilterOverrides(listingsFilters);

  function buildPriceDashboardQueryKey(cityName: string | null = null) {
    return [
      "zone-dashboard-analytics",
      journeyId,
      zoneFingerprint,
      config.type,
      "price-panel",
      cityName || "default",
      listingsFilters.spatialScope,
      listingsFilters.usageType,
      listingsFilters.minPrice || "",
      listingsFilters.maxPrice || "",
      listingsFilters.minSize || "",
      listingsFilters.maxSize || "",
    ] as const;
  }

  function buildDashboardPricePageQueryKey() {
    return ["zone-dashboard-analytics", journeyId, zoneFingerprint, config.type, "zone", "preco"] as const;
  }

  async function fetchDashboardQueryIfMissing<T>(queryKey: readonly unknown[], queryFn: () => Promise<T>) {
    const cached = queryClient.getQueryData<T>(queryKey);
    if (cached !== undefined) {
      return cached;
    }
    return queryClient.fetchQuery({
      queryKey,
      queryFn,
      staleTime: DASHBOARD_ANALYTICS_STALE_TIME,
      gcTime: DASHBOARD_ANALYTICS_GC_TIME,
    });
  }

  async function prefetchDashboardQueryIfMissing<T>(queryKey: readonly unknown[], queryFn: () => Promise<T>) {
    if (queryClient.getQueryData<T>(queryKey) !== undefined) {
      return;
    }
    await queryClient.prefetchQuery({
      queryKey,
      queryFn,
      staleTime: DASHBOARD_ANALYTICS_STALE_TIME,
      gcTime: DASHBOARD_ANALYTICS_GC_TIME,
    });
  }

  function hasDashboardBaseCache() {
    if (!journeyId || !zoneFingerprint) {
      return false;
    }

    const zoneQueryKey = buildDashboardPricePageQueryKey();
    if (queryClient.getQueryData(zoneQueryKey) === undefined) {
      return false;
    }

    if (!hasPriceDashboardOverrides) {
      return true;
    }

    return queryClient.getQueryData(buildPriceDashboardQueryKey()) !== undefined;
  }

  async function primeDashboardAnalytics() {
    if (!journeyId || !zoneFingerprint) {
      return;
    }

    const zoneQueryKey = buildDashboardPricePageQueryKey();

    await fetchDashboardQueryIfMissing(
      zoneQueryKey,
      async () => getZoneDashboardAnalytics(journeyId, zoneFingerprint, config.type, { page: "preco" }),
    );

    if (hasPriceDashboardOverrides) {
      await fetchDashboardQueryIfMissing(
        buildPriceDashboardQueryKey(),
        async () => getZoneDashboardAnalytics(
          journeyId,
          zoneFingerprint,
          config.type,
          {
            ...buildPriceDashboardAnalyticsOptions(listingsFilters),
            page: "preco",
          },
        ),
      );
    }
  }

  async function handleOpenDashboardTab() {
    if (activeTab === "dashboard") {
      return;
    }

    if (hasDashboardBaseCache()) {
      setActiveTab("dashboard");
      void primeDashboardAnalytics().catch(() => {
        // Warm-up complementar em background nao deve bloquear a aba.
      });
      return;
    }

    setIsPreparingDashboard(true);
    try {
      await primeDashboardAnalytics();
    } catch {
      // Se o warm-up falhar, ainda abrimos a aba para exibir o estado de erro normal.
    } finally {
      setIsPreparingDashboard(false);
      setActiveTab("dashboard");
    }
  }

  useEffect(() => {
    if (!journeyId || !zoneFingerprint) {
      return;
    }
    let cancelled = false;

    const warmDashboardQueries = async () => {
      await primeDashboardAnalytics();
    };

    void warmDashboardQueries().catch(() => {
      if (!cancelled) {
        // Warm-up em background é oportunista; falha aqui não bloqueia a tela.
      }
    });

    return () => {
      cancelled = true;
    };
  }, [config.type, journeyId, queryClient, zoneFingerprint]);

  useEffect(() => {
    if (!selectedListingKey) {
      lastScrolledListingKeyRef.current = null;
      return;
    }
    if (lastScrolledListingKeyRef.current === selectedListingKey) {
      return;
    }
    const listContainer = listingsPanelScrollRef.current;
    const selectedCard = listingCardRefs.current[selectedListingKey];
    if (!selectedCard || !listContainer) {
      return;
    }
    const targetTop = Math.max(0, selectedCard.offsetTop - listContainer.offsetTop - 12);
    listContainer.scrollTo({ top: targetTop, behavior: "smooth" });
    lastScrolledListingKeyRef.current = selectedListingKey;
  }, [displayedListings, selectedListingKey]);

  useEffect(() => {
    if (lastProgressRunKeyRef.current === progressRunKey) {
      return;
    }
    lastProgressRunKeyRef.current = progressRunKey;
    autoCollapsedProgressRunKeyRef.current = null;
    setIsProgressCollapsed((current) => (current ? false : current));
  }, [progressRunKey]);

  useEffect(() => {
    if (!hasCompletedListingsGeneration) {
      return;
    }
    if (autoCollapsedProgressRunKeyRef.current === progressRunKey) {
      return;
    }
    autoCollapsedProgressRunKeyRef.current = progressRunKey;
    setIsProgressCollapsed((current) => (current ? current : true));
  }, [hasCompletedListingsGeneration, progressRunKey]);

  useEffect(() => {
    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpenAccessibilityPopoverKey(null);
      }
    }

    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, []);

  function toggleListingsSort(sortField: "price" | "size") {
    setListingsFilters({
      sortField,
      sortDirection: listingsFilters.sortField === sortField
        ? (listingsFilters.sortDirection === "asc" ? "desc" : "asc")
        : "asc"
    });
  }

  function sortButtonLabel(sortField: "price" | "size") {
    const isActive = listingsFilters.sortField === sortField;
    const criterion = sortField === "price" ? "preço" : "tamanho";
    if (!isActive) {
      return `Ativar ordenação por ${criterion}`;
    }
    const ordering = listingsFilters.sortDirection === "asc" ? "crescente" : "decrescente";
    return `Ordenar por ${criterion} ${ordering}`;
  }

  function handleAvailabilityPopoverBlur(cardKey: string, event: React.FocusEvent<HTMLDivElement>) {
    const nextFocused = event.relatedTarget;
    if (nextFocused instanceof Node && event.currentTarget.contains(nextFocused)) {
      return;
    }
    setOpenAvailabilityPopoverKey((current) => (current === cardKey ? null : current));
  }

  function handleAccessibilityPopoverBlur(cardKey: string, event: React.FocusEvent<HTMLDivElement>) {
    const nextFocused = event.relatedTarget;
    if (nextFocused instanceof Node && event.currentTarget.contains(nextFocused)) {
      return;
    }
    setOpenAccessibilityPopoverKey((current) => (current === cardKey ? null : current));
  }

  return (
    <div className="flex h-full flex-col bg-slate-50 animate-[fadeInRight_0.5s_ease-out]">
      <div className="shrink-0 border-b border-slate-200 bg-white">
        <div className="p-5 pb-0">
          <div className="mb-4 flex items-center justify-between gap-4">
            <div>
              <h2 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-slate-800">
                Resultados
                {isScraping ? <Loader2 className="h-5 w-5 animate-spin text-pastel-violet-400" /> : null}
              </h2>
              <p className="mt-1 flex items-center gap-2 text-sm text-slate-500">
                <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                {freshnessLabel(listingsQuery.data?.freshness_status)}
              </p>
              {listingsJobQuery.data ? (
                <p className="mt-1 text-xs font-medium text-slate-500">
                  Job de listings: {listingsJobQuery.data.progress_percent}%
                  {scrapeDiagnostics?.active_platform ? ` · ativo em ${platformLabel(scrapeDiagnostics.active_platform)}` : ""}
                  {overallDuration ? ` · ${overallDuration}` : ""}
                </p>
              ) : null}
            </div>
            <button type="button" className="rounded-lg bg-pastel-violet-50 px-3 py-1.5 text-sm font-medium text-pastel-violet-600 transition-colors hover:bg-pastel-violet-100" disabled>
              Gerar Relatório PDF
            </button>
          </div>

          {platformEntries.length > 0 ? (
            <div className="mb-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm" data-testid="listings-platform-progress">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Progresso por plataforma</p>
                  <p className="mt-1 text-sm text-slate-600">
                    {diagnosticsSummary?.total_scraped ? `${diagnosticsSummary.total_scraped} anúncios raspados no worker` : "Acompanhando o scrape em tempo real."}
                  </p>
                </div>
                <div className="flex items-center gap-2 self-start">
                  <div className="flex flex-wrap items-center justify-end gap-2 text-xs text-slate-500">
                    <span className="rounded-full bg-slate-100 px-2.5 py-1 font-medium text-slate-600">
                      {diagnosticsSummary?.platforms_completed?.length || 0} concluídas
                    </span>
                    <span className="rounded-full bg-slate-100 px-2.5 py-1 font-medium text-slate-600">
                      {diagnosticsSummary?.platforms_failed?.length || 0} falhas
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setIsProgressCollapsed((value) => !value)}
                    className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 text-slate-500 transition-colors hover:bg-pastel-violet-50 hover:text-pastel-violet-600"
                    aria-expanded={!isProgressCollapsed}
                    aria-controls="listings-platform-progress-body"
                    aria-label={isProgressCollapsed ? "Expandir progresso do scraping" : "Recolher progresso do scraping"}
                  >
                    {isProgressCollapsed ? <ChevronDown className="h-4 w-4" /> : <ChevronUp className="h-4 w-4" />}
                  </button>
                </div>
              </div>

              {!isProgressCollapsed ? (
                <div id="listings-platform-progress-body" className="mt-4 grid grid-cols-1 gap-3" data-testid="listings-platform-progress-grid">
                  {platformEntries.map(({ platform, details }) => {
                    const meta = platformStatusMeta(details.status);
                    const duration = formatDuration(details.total_duration_ms);
                    const Icon = meta.Icon;
                    const isActivePlatform = scrapeDiagnostics?.active_platform === platform && details.status !== "completed";
                    return (
                      <div key={platform} className="rounded-2xl border border-slate-200 bg-slate-50/70 p-3">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="text-sm font-semibold text-slate-800">{platformLabel(platform)}</p>
                            <p className="mt-1 text-xs text-slate-500">
                              {details.scraped_count || details.persisted_count
                                ? `${details.persisted_count ?? details.scraped_count ?? 0} anúncios processados`
                                : "Sem contagem ainda"}
                            </p>
                          </div>
                          <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-1 text-[11px] font-semibold ${meta.className}`}>
                            <Icon className={`h-3.5 w-3.5 ${details.status === "scraping" ? "animate-spin" : ""}`} />
                            {meta.label}
                          </span>
                        </div>

                        <div className="mt-3 space-y-1.5 text-xs text-slate-600">
                          {isActivePlatform ? <p className="font-medium text-pastel-violet-700">Raspando agora nesta plataforma.</p> : null}
                          {duration ? <p>Duração: {duration}</p> : null}
                          {details.scrape_duration_ms ? <p>Scrape: {formatDuration(details.scrape_duration_ms)}</p> : null}
                          {details.persist_duration_ms ? <p>Persistência: {formatDuration(details.persist_duration_ms)}</p> : null}
                          {details.error_message ? <p className="text-rose-700">{details.error_message}</p> : null}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : null}
            </div>
          ) : null}

          <div className="flex gap-6 border-b border-transparent">
            <button type="button" onClick={() => setActiveTab("imoveis")} className={`pb-3 text-sm font-medium border-b-2 transition-colors ${activeTab === "imoveis" ? "border-pastel-violet-500 text-pastel-violet-600" : "border-transparent text-slate-500 hover:text-slate-700"}`}>
              Imóveis ({displayedListings.length}{displayedListings.length !== (listingsQuery.data?.total_count || 0) ? ` de ${listingsQuery.data?.total_count || 0}` : ""})
            </button>
            <button type="button" onClick={() => { void handleOpenDashboardTab(); }} disabled={isPreparingDashboard} className={`pb-3 text-sm font-medium border-b-2 transition-colors disabled:cursor-wait disabled:opacity-80 ${activeTab === "dashboard" ? "border-pastel-violet-500 text-pastel-violet-600" : "border-transparent text-slate-500 hover:text-slate-700"}`}>
              {isPreparingDashboard ? "Preparando dashboard..." : "Dashboard Analítico"}
            </button>
          </div>
        </div>
      </div>

      <div ref={listingsPanelScrollRef} className="panel-scroll flex-1 overflow-y-auto p-5">
        {activeTab === "imoveis" ? (
          <div className="space-y-4 animate-[fadeIn_0.3s_ease-out]">
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-500">
                  <SlidersHorizontal className="h-3.5 w-3.5" />
                  Filtros
                </div>
                <button
                  type="button"
                  onClick={() => setIsFiltersCollapsed((value) => !value)}
                  className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 text-slate-500 transition-colors hover:bg-pastel-violet-50 hover:text-pastel-violet-600"
                  aria-expanded={!isFiltersCollapsed}
                  aria-controls="listings-filters-body"
                  aria-label={isFiltersCollapsed ? "Expandir filtros de imóveis" : "Recolher filtros de imóveis"}
                >
                  {isFiltersCollapsed ? <ChevronDown className="h-4 w-4" /> : <ChevronUp className="h-4 w-4" />}
                </button>
              </div>
              {!isFiltersCollapsed ? (
                <div id="listings-filters-body" className="mt-3" data-testid="listings-filters-body">
                  <div className="grid grid-cols-2 gap-3">
                    <div className="col-span-2 flex flex-col gap-1">
                      <label className="text-xs text-slate-500">Escopo espacial</label>
                      <select
                        aria-label="Escopo espacial"
                        value={listingsFilters.spatialScope}
                        onChange={(e) => setListingsFilters({ spatialScope: e.target.value as "all" | "inside_zone" })}
                        className="rounded-md border border-slate-200 px-2 py-1.5 text-sm text-slate-700 outline-none focus:border-pastel-violet-400 focus:ring-1 focus:ring-pastel-violet-200"
                      >
                        <option value="all">Todos os imóveis</option>
                        <option value="inside_zone">Apenas dentro da zona</option>
                      </select>
                      <p className="text-xs text-slate-500">
                        {listingsInZone.length} dentro da zona · {listingsOutsideZone.length} fora da zona · {listingsWithoutCoordinates.length} sem coordenadas
                      </p>
                    </div>
                    <div className="col-span-2 grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] sm:items-end">
                      <div className="flex flex-col gap-1">
                        <label className="text-xs text-slate-500">Preço mín. (R$)</label>
                        <input
                          type="number"
                          min={0}
                          value={listingsFilters.minPrice}
                          onChange={(e) => setListingsFilters({ minPrice: e.target.value })}
                          placeholder="0"
                          className="rounded-md border border-slate-200 px-2 py-1.5 text-sm text-slate-700 outline-none focus:border-pastel-violet-400 focus:ring-1 focus:ring-pastel-violet-200"
                        />
                      </div>
                      <div className="flex flex-col gap-1">
                        <label className="text-xs text-slate-500">Preço máx. (R$)</label>
                        <input
                          type="number"
                          min={0}
                          value={listingsFilters.maxPrice}
                          onChange={(e) => setListingsFilters({ maxPrice: e.target.value })}
                          placeholder="Sem limite"
                          className="rounded-md border border-slate-200 px-2 py-1.5 text-sm text-slate-700 outline-none focus:border-pastel-violet-400 focus:ring-1 focus:ring-pastel-violet-200"
                        />
                      </div>
                      <button
                        type="button"
                        aria-label={sortButtonLabel("price")}
                        aria-pressed={listingsFilters.sortField === "price"}
                        data-testid="listings-sort-price"
                        onClick={() => toggleListingsSort("price")}
                        className={`flex h-10 w-10 items-center justify-center self-start rounded-md border transition-colors focus:outline-none focus:ring-2 focus:ring-pastel-violet-200 sm:self-auto ${listingsFilters.sortField === "price" ? "border-pastel-violet-300 bg-pastel-violet-50 text-pastel-violet-700" : "border-slate-200 text-slate-500 hover:bg-pastel-violet-50 hover:text-pastel-violet-700"}`}
                      >
                        {listingsFilters.sortField !== "price" ? (
                          <Minus className="h-4 w-4" />
                        ) : listingsFilters.sortDirection === "desc" ? (
                          <ChevronDown className="h-4 w-4" />
                        ) : (
                          <ChevronUp className="h-4 w-4" />
                        )}
                      </button>
                    </div>
                    <div className="col-span-2 grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] sm:items-end">
                      <div className="flex flex-col gap-1">
                        <label className="text-xs text-slate-500">Área mín. (m²)</label>
                        <input
                          type="number"
                          min={0}
                          value={listingsFilters.minSize}
                          onChange={(e) => setListingsFilters({ minSize: e.target.value })}
                          placeholder="0"
                          className="rounded-md border border-slate-200 px-2 py-1.5 text-sm text-slate-700 outline-none focus:border-pastel-violet-400 focus:ring-1 focus:ring-pastel-violet-200"
                        />
                      </div>
                      <div className="flex flex-col gap-1">
                        <label className="text-xs text-slate-500">Área máx. (m²)</label>
                        <input
                          type="number"
                          min={0}
                          value={listingsFilters.maxSize}
                          onChange={(e) => setListingsFilters({ maxSize: e.target.value })}
                          placeholder="Sem limite"
                          className="rounded-md border border-slate-200 px-2 py-1.5 text-sm text-slate-700 outline-none focus:border-pastel-violet-400 focus:ring-1 focus:ring-pastel-violet-200"
                        />
                      </div>
                      <button
                        type="button"
                        aria-label={sortButtonLabel("size")}
                        aria-pressed={listingsFilters.sortField === "size"}
                        data-testid="listings-sort-size"
                        onClick={() => toggleListingsSort("size")}
                        className={`flex h-10 w-10 items-center justify-center self-start rounded-md border transition-colors focus:outline-none focus:ring-2 focus:ring-pastel-violet-200 sm:self-auto ${listingsFilters.sortField === "size" ? "border-pastel-violet-300 bg-pastel-violet-50 text-pastel-violet-700" : "border-slate-200 text-slate-500 hover:bg-pastel-violet-50 hover:text-pastel-violet-700"}`}
                      >
                        {listingsFilters.sortField !== "size" ? (
                          <Minus className="h-4 w-4" />
                        ) : listingsFilters.sortDirection === "desc" ? (
                          <ChevronDown className="h-4 w-4" />
                        ) : (
                          <ChevronUp className="h-4 w-4" />
                        )}
                      </button>
                    </div>
                  </div>
                  <div className="mt-3 flex flex-col gap-1">
                    <label className="text-xs text-slate-500">Tipo de imóvel</label>
                    <select
                      value={listingsFilters.usageType}
                      onChange={(e) => setListingsFilters({ usageType: e.target.value as "all" | "residential" | "commercial" })}
                      className="rounded-md border border-slate-200 px-2 py-1.5 text-sm text-slate-700 outline-none focus:border-pastel-violet-400 focus:ring-1 focus:ring-pastel-violet-200"
                    >
                      <option value="all">Todos</option>
                      <option value="residential">Residencial</option>
                      <option value="commercial">Comercial</option>
                    </select>
                  </div>
                </div>
              ) : null}
            </div>
            {listingsQuery.isLoading ? <p className="rounded-xl bg-white p-4 text-sm text-slate-500">Carregando imóveis...</p> : null}
            {listingsQuery.error ? <p className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">{apiActionHint(listingsQuery.error)}</p> : null}
            {!listingsQuery.isLoading && rawListings.length === 0 ? (
              <div className="rounded-2xl border border-slate-200 bg-white p-5 text-sm text-slate-600 shadow-sm">
                {listingsQuery.data?.freshness_status === "no_cache"
                  ? "O scraping foi iniciado. Esta tela atualiza automaticamente assim que os primeiros imóveis estiverem prontos."
                  : scrapedButNoCards
                    ? `O scraping terminou e raspou ${diagnosticsSummary?.total_scraped || 0} anúncios, mas nenhum permaneceu elegível para esta busca após os filtros do backend. Tente outra rua ou outra zona.`
                    : "Nenhum imóvel disponível ainda para esta busca."}
              </div>
            ) : null}
            {!listingsQuery.isLoading && rawListings.length > 0 && displayedListings.length === 0 ? (
              <div className="rounded-2xl border border-slate-200 bg-white p-5 text-sm text-slate-600 shadow-sm">
                {noMatchesInZoneForScope
                  ? `Existem ${rawListings.length} imóveis raspados para esta busca, mas nenhum com coordenadas dentro da zona selecionada. Troque o escopo para 'Todos os imóveis' para inspecionar o conjunto completo.`
                  : "Nenhum imóvel corresponde aos filtros aplicados."}
              </div>
            ) : null}
            {displayedListings.map((listing, index) => {
              const listingKey = getListingSelectionKey(listing);
              const cardInstanceKey = listingKey || `${listing.platform || "platform"}:${listing.platform_listing_id || index}`;
              const price = getListingDisplayPrice(listing);
              const adUrl = resolvePlatformUrl(listing.url, listing.platform);
              const imageUrl = resolvePlatformImageUrl(listing.image_url, listing.platform);
              const platformVariants = listing.platform_variants || [];
              const hasAvailabilityPopover = Boolean(listing.duplication_badge && platformVariants.length > 1);
              const isSelected = listingKey !== "" && listingKey === selectedListingKey;
              const spatialBadge = !listing.has_coordinates
                ? {
                    className: "border-slate-200 bg-slate-50 text-slate-600",
                    label: "Sem coordenadas"
                  }
                : listing.inside_zone
                  ? {
                      className: "border-emerald-200 bg-emerald-50 text-emerald-700",
                      label: "Dentro da zona"
                    }
                  : {
                      className: "border-amber-200 bg-amber-50 text-amber-700",
                      label: "Fora da zona"
                    };
              return (
                <div
                  key={`${listing.platform_listing_id || index}-${listing.platform || "platform"}`}
                  ref={(node) => {
                    if (!listingKey) {
                      return;
                    }
                    if (node) {
                      listingCardRefs.current[listingKey] = node;
                    } else {
                      delete listingCardRefs.current[listingKey];
                    }
                  }}
                  data-testid={listingKey ? `listing-card-${listingKey}` : undefined}
                  role="button"
                  tabIndex={0}
                  aria-pressed={isSelected}
                  onClick={() => {
                    if (listingKey) {
                      setSelectedListingKey(listingKey);
                    }
                  }}
                  onKeyDown={(event) => {
                    if ((event.key === "Enter" || event.key === " ") && listingKey) {
                      event.preventDefault();
                      setSelectedListingKey(listingKey);
                    }
                  }}
                  className={`group flex cursor-pointer flex-col overflow-hidden rounded-2xl border bg-white text-left transition-all hover:shadow-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-pastel-violet-300 sm:flex-row ${isSelected ? "border-pastel-violet-300 ring-2 ring-pastel-violet-100 shadow-lg" : "border-slate-200"}`}
                >
                  <div className="relative h-40 shrink-0 bg-gradient-to-br from-pastel-violet-100 via-white to-slate-100 sm:h-auto sm:w-48">
                    {imageUrl ? (
                      <img
                        src={imageUrl}
                        alt={listing.address_normalized || "Imagem do imóvel"}
                        className="absolute inset-0 h-full w-full object-cover"
                        loading="lazy"
                        onError={(event) => {
                          event.currentTarget.style.display = "none";
                        }}
                      />
                    ) : null}
                    <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-400">
                      <Building2 className="h-9 w-9" />
                      <span className="mt-2 text-xs font-semibold uppercase tracking-[0.16em]">{availablePlatformsLabel(listing.platforms_available, listing.platform)}</span>
                    </div>
                    <div className="absolute left-2 top-2 rounded bg-white/90 px-2 py-1 text-xs font-bold text-slate-700 shadow-sm backdrop-blur-sm">
                      {availablePlatformsLabel(listing.platforms_available, listing.platform)}
                    </div>
                  </div>
                  <div className="flex flex-1 flex-col p-4">
                    <div className="mb-1 flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm text-slate-500">{config.type === "rent" ? "Locação" : "Compra"}</p>
                        {(listing.platforms_available || []).length > 1 ? (
                          <p className="text-xs text-slate-400">Menor preço em {platformLabel(listing.platform)}</p>
                        ) : null}
                      </div>
                      <h3 className="text-xl font-bold text-slate-800">{formatCurrencyBr(price)}</h3>
                    </div>
                    <h4 className="mb-2 text-sm font-medium text-slate-700">{listing.address_normalized || "Endereço não informado"}</h4>
                    <div className="mb-4 flex flex-wrap items-center gap-4 text-sm text-slate-600">
                      <span className="inline-flex items-center gap-1"><MapIcon className="h-3.5 w-3.5" /> {listing.area_m2 ? `${Math.round(listing.area_m2)}m²` : "Área n/d"}</span>
                      <span className="inline-flex items-center gap-1"><Home className="h-3.5 w-3.5" /> {listing.bedrooms ?? "--"} dorms</span>
                    </div>
                    <div className={`mb-3 inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-medium ${spatialBadge.className}`}>
                      <MapIcon className="h-3 w-3" />
                      {spatialBadge.label}
                    </div>
                    {listing.duplication_badge ? (
                      <div
                        className={`relative mb-3 w-full max-w-full ${openAvailabilityPopoverKey === cardInstanceKey ? "z-20" : ""}`}
                        onMouseEnter={hasAvailabilityPopover ? () => setOpenAvailabilityPopoverKey(cardInstanceKey) : undefined}
                        onMouseLeave={hasAvailabilityPopover ? () => setOpenAvailabilityPopoverKey((current) => (current === cardInstanceKey ? null : current)) : undefined}
                        onFocusCapture={hasAvailabilityPopover ? () => setOpenAvailabilityPopoverKey(cardInstanceKey) : undefined}
                        onBlurCapture={hasAvailabilityPopover ? (event) => handleAvailabilityPopoverBlur(cardInstanceKey, event) : undefined}
                      >
                        <button
                          type="button"
                          aria-haspopup={hasAvailabilityPopover ? "dialog" : undefined}
                          aria-expanded={hasAvailabilityPopover ? openAvailabilityPopoverKey === cardInstanceKey : undefined}
                          onClick={(event) => {
                            event.stopPropagation();
                            if (!hasAvailabilityPopover) {
                              return;
                            }
                            setOpenAvailabilityPopoverKey((current) => (current === cardInstanceKey ? null : cardInstanceKey));
                          }}
                          onKeyDown={(event) => event.stopPropagation()}
                          className="inline-flex w-full items-center gap-1.5 rounded-md border border-amber-100 bg-amber-50 px-2.5 py-1 text-left text-xs font-medium text-amber-700 transition-colors hover:bg-amber-100/80"
                        >
                          <AlertTriangle className="h-3 w-3 shrink-0" />
                          <span className="min-w-0 truncate">{listing.duplication_badge}</span>
                        </button>
                        {hasAvailabilityPopover && openAvailabilityPopoverKey === cardInstanceKey ? (
                          <div data-testid={`listing-platform-popover-${cardInstanceKey}`} className="mt-2 animate-[fadeIn_0.18s_ease-out] overflow-hidden rounded-xl border border-amber-200 bg-white shadow-lg">
                            <div className="border-b border-amber-100 bg-amber-50/60 px-3 py-2">
                              <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-amber-700">Preços por plataforma</p>
                            </div>
                            <div className="space-y-1.5 p-2.5">
                              {platformVariants.map((variant) => {
                                const variantPrice = getListingDisplayPrice(variant);
                                const variantUrl = resolvePlatformUrl(variant.url, variant.platform);
                                return (
                                  <div key={`${variant.platform || "platform"}:${variant.platform_listing_id || "listing"}`} className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-2 rounded-lg border border-slate-200 bg-slate-50/80 px-2.5 py-2">
                                    <div className="min-w-0">
                                      <p className="truncate text-xs font-semibold text-slate-800">{platformLabel(variant.platform)}</p>
                                      <p className="text-[11px] leading-snug text-slate-500">{formatPlatformVariantHint(variant, listing.platform)}</p>
                                    </div>
                                    <p className="text-xs font-semibold text-slate-700">{formatCurrencyBr(variantPrice)}</p>
                                    {variantUrl ? (
                                      <a
                                        href={variantUrl}
                                        target="_blank"
                                        rel="noreferrer"
                                        aria-label={`Abrir anúncio na ${platformLabel(variant.platform)}`}
                                        onClick={(event) => event.stopPropagation()}
                                        onKeyDown={(event) => event.stopPropagation()}
                                        className="flex h-8 w-8 items-center justify-center rounded-lg bg-pastel-violet-50 text-pastel-violet-500 transition-colors hover:bg-pastel-violet-100"
                                      >
                                        <ExternalLink className="h-3.5 w-3.5" />
                                      </a>
                                    ) : (
                                      <span className="rounded-lg bg-slate-200 px-2 py-1 text-[10px] font-medium text-slate-500">Sem link</span>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                    <div
                      className={`relative mt-auto border-t border-slate-100 pt-3 ${openAccessibilityPopoverKey === cardInstanceKey ? "z-20" : ""}`}
                      onBlurCapture={(event) => handleAccessibilityPopoverBlur(cardInstanceKey, event)}
                    >
                      {openAccessibilityPopoverKey === cardInstanceKey ? (
                        <ListingAccessibilityPopover
                          open
                          popoverId={`listing-accessibility-popover-${cardInstanceKey}`}
                          listing={listing}
                          onClose={() => setOpenAccessibilityPopoverKey((current) => (current === cardInstanceKey ? null : current))}
                        />
                      ) : null}

                      <div className="flex gap-2">
                        <button
                          type="button"
                          aria-haspopup="dialog"
                          aria-expanded={openAccessibilityPopoverKey === cardInstanceKey}
                          aria-controls={`listing-accessibility-popover-${cardInstanceKey}`}
                          onClick={(event) => {
                            event.stopPropagation();
                            if (listingKey) {
                              setSelectedListingKey(listingKey);
                            }
                            setOpenAccessibilityPopoverKey((current) => (current === cardInstanceKey ? null : cardInstanceKey));
                          }}
                          className="flex-1 rounded-lg bg-slate-50 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-100"
                        >
                          Ver Acessibilidade
                        </button>
                        {adUrl ? (
                          <a href={adUrl} target="_blank" rel="noreferrer" aria-label="Ver anúncio" onClick={(event) => event.stopPropagation()} className="flex w-10 items-center justify-center rounded-lg bg-pastel-violet-50 text-pastel-violet-500 transition-colors hover:bg-pastel-violet-100">
                            <ExternalLink className="h-4 w-4" />
                          </a>
                        ) : (
                          <button type="button" disabled aria-label="Anúncio indisponível" onClick={(event) => event.stopPropagation()} className="flex w-10 cursor-not-allowed items-center justify-center rounded-lg bg-slate-100 text-slate-300">
                            <ExternalLink className="h-4 w-4" />
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          journeyId && zoneFingerprint ? (
            <Step6Dashboard
              journeyId={journeyId}
              zoneFingerprint={zoneFingerprint}
              searchType={config.type}
              listingsFilters={listingsFilters}
            />
          ) : null
        )}
      </div>
    </div>
  );
}