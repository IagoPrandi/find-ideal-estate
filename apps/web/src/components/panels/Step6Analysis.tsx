import { useEffect, useMemo, useRef, useState } from "react";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  CircleDot,
  ExternalLink,
  Heart,
  Home,
  Loader2,
  MapIcon,
  Minus,
  ShieldX,
  SlidersHorizontal,
  Building2,
} from "lucide-react";
import { apiActionHint, getJob, getZoneDashboardAnalytics, getZoneFavoriteAnalytics, getZoneListings, type ListingPlatformVariantRead } from "../../api/client";
import { ListingsScrapeDiagnosticsSchema, type ListingsScrapeDiagnostics, type ListingsScrapePlatformDiagnostics } from "../../api/schemas";
import { useAuth } from "../../features/auth/AuthContext";
import { buildZoneFavoriteAnalyticsQueryKey } from "../../lib/favorites";
import { applyListingsPanelFilters, formatCurrencyBr, getListingDisplayPrice, getListingSelectionKey, resolveListingCardImageUrls, resolvePlatformUrl } from "../../lib/listingFormat";
import { useFavoritesStore, useJourneyStore, useUIStore, type ListingsPanelFilters } from "../../state";
import { Step6Dashboard } from "./Step6Dashboard";

const DASHBOARD_ANALYTICS_STALE_TIME = 30 * 60_000;
const DASHBOARD_ANALYTICS_GC_TIME = 60 * 60_000;
const FAVORITES_ANALYTICS_STALE_TIME = 30 * 60_000;
const FAVORITES_ANALYTICS_GC_TIME = 60 * 60_000;
const PRICE_DASHBOARD_FILTER_DEBOUNCE_MS = 350;
const ACTIVE_LISTINGS_JOB_STATES = new Set(["pending", "running", "retrying"]);
const TERMINAL_LISTINGS_JOB_STATES = new Set(["completed", "failed", "cancelled", "cancelled_partial"]);

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

function calculatePercentDelta(currentValue: number | null | undefined, baseValue: number | null | undefined) {
  if (typeof currentValue !== "number" || !Number.isFinite(currentValue)) {
    return null;
  }
  if (typeof baseValue !== "number" || !Number.isFinite(baseValue) || baseValue <= 0) {
    return null;
  }
  return ((currentValue - baseValue) / baseValue) * 100;
}

function arePriceDashboardFiltersEqual(left: ListingsPanelFilters, right: ListingsPanelFilters) {
  return left.minPrice === right.minPrice
    && left.maxPrice === right.maxPrice
    && left.usageType === right.usageType
    && left.spatialScope === right.spatialScope
    && left.minSize === right.minSize
    && left.maxSize === right.maxSize;
}

function buildPriceDashboardAnalyticsOptions(
  filters: ListingsPanelFilters,
  cityName: string | null = null,
  addressScope: "all_addresses" | "selected_address" = "all_addresses",
) {
  return {
    cityName,
    minPrice: filters.minPrice || null,
    maxPrice: filters.maxPrice || null,
    usageType: filters.usageType,
    spatialScope: filters.spatialScope,
    addressScope,
    minSize: filters.minSize || null,
    maxSize: filters.maxSize || null,
  };
}

export function Step6Analysis() {
  const queryClient = useQueryClient();
  const { authStatus, isLoading: isAuthLoading, openAuthModal } = useAuth();
  const journeyId = useJourneyStore((state) => state.journeyId);
  const zoneFingerprint = useJourneyStore((state) => state.selectedZoneFingerprint);
  const listingsJobId = useJourneyStore((state) => state.listingsJobId);
  const listingsFilters = useJourneyStore((state) => state.listingsFilters);
  const listingsAddressScope = useJourneyStore((state) => state.listingsAddressScope);
  const selectedListingKey = useJourneyStore((state) => state.selectedListingKey);
  const selectedAddress = useJourneyStore((state) => state.selectedAddress);
  const setListingsFilters = useJourneyStore((state) => state.setListingsFilters);
  const setListingsAddressScope = useJourneyStore((state) => state.setListingsAddressScope);
  const setSelectedListingKey = useJourneyStore((state) => state.setSelectedListingKey);
  const config = useJourneyStore((state) => state.config);
  const activeTab = useUIStore((state) => state.activeTab);
  const setActiveTab = useUIStore((state) => state.setActiveTab);
  const setJobIds = useJourneyStore((state) => state.setJobIds);
  const toggleFavorite = useFavoritesStore((state) => state.toggleFavorite);
  const favoriteListings = useFavoritesStore((state) => state.favorites);
  const isFavoritesHydrating = useFavoritesStore((state) => state.isHydrating);
  const listingCardRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const listingsPanelScrollRef = useRef<HTMLDivElement | null>(null);
  const lastScrolledListingKeyRef = useRef<string | null>(null);
  const lastProgressRunKeyRef = useRef<string | null>(null);
  const autoCollapsedProgressRunKeyRef = useRef<string | null>(null);
  const lastListingsAvailabilityRef = useRef<{ runKey: string; freshnessStatus: string | null } | null>(null);
  const [isProgressCollapsed, setIsProgressCollapsed] = useState(false);
  const [isFiltersCollapsed, setIsFiltersCollapsed] = useState(false);
  const [isPreparingDashboard, setIsPreparingDashboard] = useState(false);
  const [openAvailabilityPopoverKey, setOpenAvailabilityPopoverKey] = useState<string | null>(null);
  const [openPriceDeltaTooltipKey, setOpenPriceDeltaTooltipKey] = useState<string | null>(null);
  const [debouncedPriceComparisonFilters, setDebouncedPriceComparisonFilters] = useState<ListingsPanelFilters>(listingsFilters);
  const [failedListingImageKeys, setFailedListingImageKeys] = useState<Record<string, true>>({});

  const persistedListingsJobId = listingsJobId;

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      setDebouncedPriceComparisonFilters((current) => (
        arePriceDashboardFiltersEqual(current, listingsFilters) ? current : listingsFilters
      ));
    }, PRICE_DASHBOARD_FILTER_DEBOUNCE_MS);

    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [listingsFilters]);

  const listingsQuery = useQuery({
    queryKey: ["zone-listings", journeyId, zoneFingerprint, config.type, "all", listingsAddressScope],
    queryFn: async () => getZoneListings(journeyId as string, zoneFingerprint as string, config.type, "all", "all", listingsAddressScope),
    enabled: Boolean(journeyId && zoneFingerprint),
    placeholderData: keepPreviousData,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) {
        return 5000;
      }
      const jobId = persistedListingsJobId || data.job_id || null;
      const cachedJob = jobId
        ? queryClient.getQueryData<{ state?: string | null }>(["listings-job", jobId])
        : null;
      const cachedJobState = cachedJob?.state || null;
      if (cachedJobState && TERMINAL_LISTINGS_JOB_STATES.has(cachedJobState) && data.freshness_status === "no_cache") {
        return false;
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
      return state === "completed" || state === "failed" || state === "cancelled" || state === "cancelled_partial" ? false : 5000;
    }
  });

  const rawListings = listingsQuery.data?.listings || [];
  const listingsInZone = rawListings.filter((listing) => listing.inside_zone);
  const listingsOutsideZone = rawListings.filter((listing) => listing.has_coordinates && !listing.inside_zone);
  const listingsWithoutCoordinates = rawListings.filter((listing) => !listing.has_coordinates);

  const scrapeDiagnostics = extractListingsScrapeDiagnostics((listingsJobQuery.data?.result_ref as Record<string, unknown> | null | undefined) || undefined);
  const listingsJobState = listingsJobQuery.data?.state || null;
  const hasActiveListingsJob = listingsJobState ? ACTIVE_LISTINGS_JOB_STATES.has(listingsJobState) : false;
  const hasInterruptedListingsJob = listingsJobState === "failed" || listingsJobState === "cancelled" || listingsJobState === "cancelled_partial";
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

  const isScraping = listingsQuery.isLoading
    || hasActiveListingsJob
    || (Boolean(effectiveListingsJobId) && !listingsJobQuery.data)
    || (listingsQuery.data?.freshness_status === "no_cache" && !hasInterruptedListingsJob && !listingsJobState);
  const diagnosticsSummary = scrapeDiagnostics?.summary;
  const overallDuration = formatDuration(scrapeDiagnostics?.total_duration_ms);
  const freshnessStatusLabel = hasInterruptedListingsJob
    ? (listingsJobState === "cancelled_partial" ? "Scraping interrompido" : "Scraping falhou")
    : freshnessLabel(listingsQuery.data?.freshness_status);
  const interruptedScrapeMessage = hasInterruptedListingsJob && listingsQuery.data?.freshness_status === "no_cache"
    ? (listingsJobQuery.data?.error_message === "missing_heartbeat"
      ? "O job de scraping foi interrompido antes de consolidar resultados. No ambiente local isso costuma indicar que a fila Dramatiq ficou sem worker ativo."
      : "O job de scraping terminou sem consolidar resultados. Refaça a busca para disparar uma nova tentativa.")
    : null;
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
  const showDeferredAddressInventoryNotice = Boolean(
    selectedAddress
    && !effectiveListingsJobId
    && listingsQuery.data?.freshness_status === "no_cache"
  );
  const deferredAddressInventoryNotice = selectedAddress
    ? `Os imóveis ligados a "${selectedAddress.label}" serão adicionados em até 24 horas. Enquanto isso, exibimos os imóveis já persistidos no banco para ${listingsAddressScope === "selected_address" ? "esse endereço pesquisado" : "todos os endereços pesquisados nesta jornada"}.`
    : null;

  const displayedListings = applyListingsPanelFilters(rawListings, listingsFilters);
  const favoriteListingKeySet = useMemo(() => new Set(favoriteListings.map((favorite) => favorite.listingKey)), [favoriteListings]);

  const priceComparisonDashboardQuery = useQuery({
    queryKey: buildPriceDashboardQueryKey(debouncedPriceComparisonFilters),
    queryFn: async () => getZoneDashboardAnalytics(
      journeyId as string,
      zoneFingerprint as string,
      config.type,
      {
        ...buildPriceDashboardAnalyticsOptions(debouncedPriceComparisonFilters, null, listingsAddressScope),
        page: "preco",
      },
    ),
    enabled: Boolean(journeyId && zoneFingerprint),
    staleTime: DASHBOARD_ANALYTICS_STALE_TIME,
    gcTime: DASHBOARD_ANALYTICS_GC_TIME,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
    placeholderData: keepPreviousData,
  });

  function buildPriceDashboardQueryKey(filters: ListingsPanelFilters, cityName: string | null = null) {
    return [
      "zone-dashboard-analytics",
      journeyId,
      zoneFingerprint,
      config.type,
      "price-panel",
      listingsAddressScope,
      cityName || "default",
      filters.spatialScope,
      filters.usageType,
      filters.minPrice || "",
      filters.maxPrice || "",
      filters.minSize || "",
      filters.maxSize || "",
    ] as const;
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

  function hasDashboardBaseCache() {
    if (!journeyId || !zoneFingerprint) {
      return false;
    }

    return queryClient.getQueryData(buildPriceDashboardQueryKey(listingsFilters)) !== undefined;
  }

  async function primeDashboardAnalytics() {
    if (!journeyId || !zoneFingerprint) {
      return;
    }

    await fetchDashboardQueryIfMissing(
      buildPriceDashboardQueryKey(listingsFilters),
      async () => getZoneDashboardAnalytics(
        journeyId,
        zoneFingerprint,
        config.type,
        {
          ...buildPriceDashboardAnalyticsOptions(listingsFilters, null, listingsAddressScope),
          page: "preco",
        },
      ),
    );
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
    if (!hasInterruptedListingsJob) {
      return;
    }
    if (persistedListingsJobId) {
      setJobIds({ listingsJobId: null });
    }
  }, [hasInterruptedListingsJob, persistedListingsJobId, setJobIds]);

  useEffect(() => {
    const currentRunKey = [
      journeyId || "no-journey",
      zoneFingerprint || "no-zone",
      effectiveListingsJobId || "no-job",
    ].join(":");
    const currentFreshnessStatus = listingsQuery.data?.freshness_status || null;
    const previousAvailability = lastListingsAvailabilityRef.current;
    const shouldRecalculateDashboard = Boolean(
      journeyId
      && zoneFingerprint
      && previousAvailability
      && previousAvailability.runKey === currentRunKey
      && previousAvailability.freshnessStatus === "no_cache"
      && currentFreshnessStatus
      && currentFreshnessStatus !== "no_cache"
      && !isScraping
    );

    lastListingsAvailabilityRef.current = {
      runKey: currentRunKey,
      freshnessStatus: currentFreshnessStatus,
    };

    if (!shouldRecalculateDashboard) {
      return;
    }

    void queryClient.invalidateQueries({
      queryKey: ["zone-dashboard-analytics", journeyId, zoneFingerprint, config.type],
    });
  }, [
    config.type,
    effectiveListingsJobId,
    isScraping,
    journeyId,
    listingsQuery.data?.freshness_status,
    queryClient,
    zoneFingerprint,
  ]);

  useEffect(() => {
    setFailedListingImageKeys({});
  }, [journeyId, zoneFingerprint]);

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
  }, [config.type, journeyId, listingsAddressScope, queryClient, zoneFingerprint]);

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

  function handlePriceDeltaTooltipBlur(cardKey: string, event: React.FocusEvent<HTMLDivElement>) {
    const nextFocused = event.relatedTarget;
    if (nextFocused instanceof Node && event.currentTarget.contains(nextFocused)) {
      return;
    }
    setOpenPriceDeltaTooltipKey((current) => (current === cardKey ? null : current));
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
                {freshnessStatusLabel}
              </p>
              {listingsJobQuery.data ? (
                <p className="mt-1 text-xs font-medium text-slate-500">
                  Busca de imóveis: {listingsJobQuery.data.progress_percent}%
                  {scrapeDiagnostics?.active_platform ? ` · ativo em ${platformLabel(scrapeDiagnostics.active_platform)}` : ""}
                  {overallDuration ? ` · ${overallDuration}` : ""}
                </p>
              ) : null}
            </div>
          </div>

          {interruptedScrapeMessage ? (
            <div className="mb-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
              <div className="flex items-start gap-2">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <p>{interruptedScrapeMessage}</p>
              </div>
            </div>
          ) : null}

          {platformEntries.length > 0 ? (
            <div className="mb-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm" data-testid="listings-platform-progress">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Progresso por plataforma</p>
                  <p className="mt-1 text-sm text-slate-600">
                    {diagnosticsSummary?.total_scraped ? `${diagnosticsSummary.total_scraped} anúncios processados até agora` : "Acompanhando o scraping em tempo real."}
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
                          {isActivePlatform ? <p className="font-medium text-pastel-violet-700">Buscando anúncios nesta plataforma agora.</p> : null}
                          {duration ? <p>Duração: {duration}</p> : null}
                          {details.scrape_duration_ms ? <p>Coleta: {formatDuration(details.scrape_duration_ms)}</p> : null}
                          {details.persist_duration_ms ? <p>Gravação: {formatDuration(details.persist_duration_ms)}</p> : null}
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
              {isPreparingDashboard ? "Preparando dashboard..." : "Dashboard analítico"}
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
                      <label className="text-xs text-slate-500">Origem da coleta dos imóveis</label>
                      <select
                        aria-label="Origem da coleta dos imóveis"
                        value={listingsAddressScope}
                        onChange={(e) => setListingsAddressScope(e.target.value as "all_addresses" | "selected_address")}
                        className="rounded-md border border-slate-200 px-2 py-1.5 text-sm text-slate-700 outline-none focus:border-pastel-violet-400 focus:ring-1 focus:ring-pastel-violet-200"
                      >
                        <option value="all_addresses">Todos os imóveis</option>
                        <option value="selected_address" disabled={!selectedAddress}>Somente imóveis do endereço selecionado</option>
                      </select>
                      <p className="text-xs text-slate-500">
                        {selectedAddress
                          ? `Endereço pesquisado atual: ${selectedAddress.label}. Este filtro usa a origem da busca do passo 5, não o endereço do imóvel.`
                          : "Selecione um endereço no passo 5 para restringir os imóveis à origem dessa busca."}
                      </p>
                    </div>
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
            {showDeferredAddressInventoryNotice && deferredAddressInventoryNotice ? (
              <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 shadow-sm">
                <div className="flex items-start gap-2">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                  <p>{deferredAddressInventoryNotice}</p>
                </div>
              </div>
            ) : null}
            {listingsQuery.isLoading ? <p className="rounded-xl bg-white p-4 text-sm text-slate-500">Carregando imóveis...</p> : null}
            {listingsQuery.error ? <p className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">{apiActionHint(listingsQuery.error)}</p> : null}
            {!listingsQuery.isLoading && rawListings.length === 0 ? (
              <div className="rounded-2xl border border-slate-200 bg-white p-5 text-sm text-slate-600 shadow-sm">
                {showDeferredAddressInventoryNotice && deferredAddressInventoryNotice
                  ? deferredAddressInventoryNotice
                  : listingsQuery.data?.freshness_status === "no_cache"
                    ? "A busca foi iniciada. Esta tela é atualizada automaticamente assim que os primeiros imóveis estiverem prontos."
                  : scrapedButNoCards
                    ? `A busca terminou e encontrou ${diagnosticsSummary?.total_scraped || 0} anúncios, mas nenhum permaneceu elegível após os filtros da busca. Tente outra rua ou outra zona.`
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
              const regionAveragePrice = priceComparisonDashboardQuery.data?.price.zone_average_price ?? null;
              const priceDeltaVsRegion = calculatePercentDelta(price, regionAveragePrice);
              const unitPriceLabel = typeof listing.current_unit_price === "number" && Number.isFinite(listing.current_unit_price)
                ? `${formatCurrencyBr(listing.current_unit_price)}/m²`
                : "m² indisponível";
              const priceDeltaTone = typeof priceDeltaVsRegion !== "number"
                ? "text-slate-500"
                : priceDeltaVsRegion > 0
                  ? "text-rose-600"
                  : priceDeltaVsRegion < 0
                    ? "text-emerald-600"
                    : "text-slate-600";
              const priceDeltaDetail = typeof regionAveragePrice === "number"
                ? `${debouncedPriceComparisonFilters.spatialScope === "inside_zone" ? "Média da zona" : "Média do recorte"}: ${formatCurrencyBr(regionAveragePrice)}`
                : "Média da região indisponível";
              const adUrl = resolvePlatformUrl(listing.url, listing.platform);
              const imageCandidates = resolveListingCardImageUrls(listing);
              const imageUrl = imageCandidates.find((candidateUrl) => !failedListingImageKeys[`${cardInstanceKey}:${candidateUrl}`]) || null;
              const imageStateKey = imageUrl ? `${cardInstanceKey}:${imageUrl}` : null;
              const shouldRenderImage = Boolean(imageUrl && imageStateKey);
              const platformVariants = listing.platform_variants || [];
              const hasAvailabilityPopover = Boolean(listing.duplication_badge && platformVariants.length > 1);
              const isSelected = listingKey !== "" && listingKey === selectedListingKey;
              const isSavedFavorite = listingKey ? favoriteListingKeySet.has(listingKey) : false;
              const favoriteButtonLabel = isAuthLoading
                ? "Verificando sua conta"
                : !authStatus.is_authenticated
                ? "Entre para salvar na sua conta"
                : isSavedFavorite
                  ? "Remover da lista de interesse"
                  : "Adicionar a lista de interesse";
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
                    {shouldRenderImage && imageUrl ? (
                      <img
                        key={imageStateKey}
                        src={imageUrl}
                        alt={listing.address_normalized || "Imagem do imóvel"}
                        className="absolute inset-0 h-full w-full object-cover"
                        loading="lazy"
                        onError={() => {
                          if (!imageStateKey) {
                            return;
                          }
                          setFailedListingImageKeys((current) => {
                            if (current[imageStateKey]) {
                              return current;
                            }
                            return {
                              ...current,
                              [imageStateKey]: true,
                            };
                          });
                        }}
                      />
                    ) : null}
                    {!shouldRenderImage ? (
                      <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-400">
                        <Building2 className="h-9 w-9" />
                        <span className="mt-2 text-xs font-semibold uppercase tracking-[0.16em]">{availablePlatformsLabel(listing.platforms_available, listing.platform)}</span>
                      </div>
                    ) : null}
                    <div className="absolute left-2 top-2 rounded bg-white/90 px-2 py-1 text-xs font-bold text-slate-700 shadow-sm backdrop-blur-sm">
                      {availablePlatformsLabel(listing.platforms_available, listing.platform)}
                    </div>
                  </div>
                  <div className="flex flex-1 flex-col p-4">
                      <div className="mb-3 flex flex-col gap-2">
                      <div className="min-w-0">
                        <p className="text-sm text-slate-500">{config.type === "rent" ? "Locação" : "Compra"}</p>
                        {(listing.platforms_available || []).length > 1 ? (
                          <p className="text-xs text-slate-400">Menor preço em {platformLabel(listing.platform)}</p>
                        ) : null}
                      </div>
                      <div className="rounded-xl border border-slate-200 bg-slate-50/80 px-4 py-3 shadow-sm">
                        <div className="grid grid-cols-[minmax(0,1fr)_auto] grid-rows-[auto_auto] gap-x-5 gap-y-1">
                          <p className="self-start text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">Preço atual</p>
                          <div
                            className={`relative flex items-start justify-end self-start ${openPriceDeltaTooltipKey === cardInstanceKey ? "z-10" : ""}`}
                            onMouseEnter={() => setOpenPriceDeltaTooltipKey(cardInstanceKey)}
                            onMouseLeave={() => setOpenPriceDeltaTooltipKey((current) => (current === cardInstanceKey ? null : current))}
                            onFocusCapture={() => setOpenPriceDeltaTooltipKey(cardInstanceKey)}
                            onBlurCapture={(event) => handlePriceDeltaTooltipBlur(cardInstanceKey, event)}
                          >
                            <button
                              type="button"
                              data-testid={`listing-price-delta-trigger-${cardInstanceKey}`}
                              aria-describedby={openPriceDeltaTooltipKey === cardInstanceKey ? `listing-price-delta-tooltip-${cardInstanceKey}` : undefined}
                              aria-label={priceDeltaDetail}
                              onClick={(event) => event.stopPropagation()}
                              onKeyDown={(event) => event.stopPropagation()}
                              className={`inline-flex items-center gap-1 rounded-md px-1 py-0.5 text-[0.9rem] font-semibold leading-none ${priceDeltaTone}`}
                            >
                              {typeof priceDeltaVsRegion === "number" ? (
                                priceDeltaVsRegion > 0 ? <ArrowUpRight className="h-4 w-4" /> : <ArrowDownRight className="h-4 w-4" />
                              ) : null}
                              <span>{formatPercentDelta(priceDeltaVsRegion)}</span>
                            </button>
                            {openPriceDeltaTooltipKey === cardInstanceKey && typeof regionAveragePrice === "number" ? (
                              <div
                                id={`listing-price-delta-tooltip-${cardInstanceKey}`}
                                role="tooltip"
                                data-testid={`listing-price-delta-tooltip-${cardInstanceKey}`}
                                className="absolute right-0 top-[calc(100%+0.4rem)] max-w-[220px] rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-left text-[11px] text-slate-600 shadow-lg"
                              >
                                {priceDeltaDetail}
                              </div>
                            ) : null}
                          </div>
                          <h3 className="self-end text-xl font-bold leading-tight text-slate-800">{formatCurrencyBr(price)}</h3>
                          <div className="flex items-end justify-end self-end text-right">
                            <span className="text-[0.8rem] font-semibold leading-none text-slate-700">{unitPriceLabel}</span>
                          </div>
                        </div>
                      </div>
                    </div>
                    <h4 className="mb-2 text-sm font-medium text-slate-700">{listing.address_normalized || "Endereço não informado"}</h4>
                    <div className="mb-4 flex flex-wrap items-center gap-4 text-sm text-slate-600">
                      <span className="inline-flex items-center gap-1"><MapIcon className="h-3.5 w-3.5" /> {listing.area_m2 ? `${Math.round(listing.area_m2)}m²` : "Área indisponível"}</span>
                      <span className="inline-flex items-center gap-1"><Home className="h-3.5 w-3.5" /> {listing.bedrooms ?? "--"} quartos</span>
                    </div>
                    <div className={`mb-3 flex w-full items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-medium ${spatialBadge.className}`}>
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
                                      <span className="rounded-lg bg-slate-200 px-2 py-1 text-[10px] font-medium text-slate-500">Link indisponível</span>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                    <div className="mt-auto border-t border-slate-100 pt-3">
                      <div className="flex items-center gap-2">
                        {adUrl ? (
                          <a
                            href={adUrl}
                            target="_blank"
                            rel="noreferrer"
                            aria-label="Abrir página do anúncio"
                            onClick={(event) => event.stopPropagation()}
                            className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-pastel-violet-50 px-3 py-2.5 text-sm font-medium text-pastel-violet-600 transition-colors hover:bg-pastel-violet-100"
                          >
                            <span>Abrir página do anúncio</span>
                            <ExternalLink className="h-4 w-4" />
                          </a>
                        ) : (
                          <button
                            type="button"
                            disabled
                            aria-label="Anúncio indisponível"
                            onClick={(event) => event.stopPropagation()}
                            className="flex flex-1 cursor-not-allowed items-center justify-center gap-2 rounded-lg bg-slate-100 px-3 py-2.5 text-sm font-medium text-slate-400"
                          >
                            <span>Anúncio indisponível</span>
                            <ExternalLink className="h-4 w-4" />
                          </button>
                        )}
                        <button
                          type="button"
                          aria-label={favoriteButtonLabel}
                          aria-pressed={isSavedFavorite}
                          title={favoriteButtonLabel}
                          disabled={!listingKey || !journeyId || !zoneFingerprint || isFavoritesHydrating || isAuthLoading}
                          onClick={async (event) => {
                            event.stopPropagation();
                            if (!listingKey || !journeyId || !zoneFingerprint || isFavoritesHydrating || isAuthLoading) {
                              return;
                            }
                            if (!authStatus.is_authenticated) {
                              openAuthModal("login");
                              return;
                            }
                            const nextWillBeSaved = !isSavedFavorite;
                            const changed = await toggleFavorite({
                              listing,
                              journeyId,
                              zoneFingerprint,
                              searchType: config.type,
                              usageType: listingsFilters.usageType,
                            });
                            if (!nextWillBeSaved || !changed) {
                              return;
                            }
                            void queryClient.prefetchQuery({
                              queryKey: buildZoneFavoriteAnalyticsQueryKey(
                                journeyId,
                                zoneFingerprint,
                                config.type,
                                listingsFilters.usageType,
                              ),
                              queryFn: async () => getZoneFavoriteAnalytics(
                                journeyId,
                                zoneFingerprint,
                                config.type,
                                listingsFilters.usageType,
                              ),
                              staleTime: FAVORITES_ANALYTICS_STALE_TIME,
                              gcTime: FAVORITES_ANALYTICS_GC_TIME,
                            });
                          }}
                          className={`inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border transition ${isSavedFavorite ? "border-rose-200 bg-rose-50 text-rose-600 hover:border-rose-300 hover:bg-rose-100" : "border-slate-200 bg-white text-slate-500 hover:border-pastel-violet-300 hover:bg-pastel-violet-50 hover:text-pastel-violet-700"}`}
                        >
                          <Heart className={`h-4.5 w-4.5 ${isSavedFavorite ? "fill-current" : ""}`} />
                        </button>
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
              listingsAddressScope={listingsAddressScope}
            />
          ) : null
        )}
      </div>
    </div>
  );
}