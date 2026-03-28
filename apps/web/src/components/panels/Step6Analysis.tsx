import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  CircleDot,
  ExternalLink,
  Home,
  Loader2,
  MapIcon,
  ShieldX,
  ShieldAlert,
  SlidersHorizontal,
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
import { apiActionHint, getJob, getJourneyZonesList, getPriceRollups, getZoneListings } from "../../api/client";
import { ListingsScrapeDiagnosticsSchema, type ListingsScrapeDiagnostics, type ListingsScrapePlatformDiagnostics } from "../../api/schemas";
import { applyListingsPanelFilters, parseFiniteNumber, formatCurrencyBr, resolvePlatformUrl } from "../../lib/listingFormat";
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

export function Step6Analysis() {
  const journeyId = useJourneyStore((state) => state.journeyId);
  const zoneFingerprint = useJourneyStore((state) => state.selectedZoneFingerprint);
  const listingsJobId = useJourneyStore((state) => state.listingsJobId);
  const listingsFilters = useJourneyStore((state) => state.listingsFilters);
  const setListingsFilters = useJourneyStore((state) => state.setListingsFilters);
  const config = useJourneyStore((state) => state.config);
  const activeTab = useUIStore((state) => state.activeTab);
  const setActiveTab = useUIStore((state) => state.setActiveTab);

  const persistedListingsJobId = listingsJobId;

  const listingsQuery = useQuery({
    queryKey: ["zone-listings", journeyId, zoneFingerprint, config.type, "all"],
    queryFn: async () => getZoneListings(journeyId as string, zoneFingerprint as string, config.type, "residential", "all"),
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
  const rawListings = listingsQuery.data?.listings || [];
  const listingsInZone = rawListings.filter((listing) => listing.inside_zone);
  const listingsOutsideZone = rawListings.filter((listing) => listing.has_coordinates && !listing.inside_zone);
  const listingsWithoutCoordinates = rawListings.filter((listing) => !listing.has_coordinates);
  const listingPrices = rawListings
    .map((listing) => parseFiniteNumber(listing.current_best_price))
    .filter((value): value is number => value !== null);
  const listingUnitPrices = rawListings
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
  const scrapedButNoCards = (listingsQuery.data?.source === "cache")
    && rawListings.length === 0
    && (diagnosticsSummary?.total_scraped || 0) > 0
    && listingsJobQuery.data?.state === "completed";

  const listingsForScope = listingsFilters.spatialScope === "inside_zone" ? listingsInZone : rawListings;
  const noMatchesInZoneForScope = listingsFilters.spatialScope === "inside_zone"
    && rawListings.length > 0
    && listingsForScope.length === 0;

  const displayedListings = applyListingsPanelFilters(rawListings, listingsFilters);

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
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Progresso por plataforma</p>
                  <p className="mt-1 text-sm text-slate-600">
                    {diagnosticsSummary?.total_scraped ? `${diagnosticsSummary.total_scraped} anúncios raspados no worker` : "Acompanhando o scrape em tempo real."}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                  <span className="rounded-full bg-slate-100 px-2.5 py-1 font-medium text-slate-600">
                    {diagnosticsSummary?.platforms_completed?.length || 0} concluídas
                  </span>
                  <span className="rounded-full bg-slate-100 px-2.5 py-1 font-medium text-slate-600">
                    {diagnosticsSummary?.platforms_failed?.length || 0} falhas
                  </span>
                </div>
              </div>

              <div className="mt-4 grid gap-3 md:grid-cols-3">
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
            </div>
          ) : null}

          <div className="flex gap-6 border-b border-transparent">
            <button type="button" onClick={() => setActiveTab("imoveis")} className={`pb-3 text-sm font-medium border-b-2 transition-colors ${activeTab === "imoveis" ? "border-pastel-violet-500 text-pastel-violet-600" : "border-transparent text-slate-500 hover:text-slate-700"}`}>
              Imóveis ({displayedListings.length}{displayedListings.length !== (listingsQuery.data?.total_count || 0) ? ` de ${listingsQuery.data?.total_count || 0}` : ""})
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
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <div className="mb-3 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-500">
                <SlidersHorizontal className="h-3.5 w-3.5" />
                Filtros
              </div>
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
              const price = parseFiniteNumber(listing.current_best_price);
              const adUrl = resolvePlatformUrl(listing.url, listing.platform);
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
                <div key={`${listing.platform_listing_id || index}-${listing.platform || "platform"}`} className="group flex flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white transition-shadow hover:shadow-lg sm:flex-row">
                  <div className="relative h-40 shrink-0 bg-gradient-to-br from-pastel-violet-100 via-white to-slate-100 sm:h-auto sm:w-48">
                    {listing.image_url ? (
                      <img
                        src={listing.image_url}
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
                      <div className="mb-3 inline-flex items-center gap-1.5 rounded-md border border-amber-100 bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-700">
                        <AlertTriangle className="h-3 w-3" />
                        {listing.duplication_badge}
                      </div>
                    ) : null}
                    <div className="mt-auto flex gap-2 border-t border-slate-100 pt-3">
                      <button type="button" className="flex-1 rounded-lg bg-slate-50 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-100">
                        Ver Acessibilidade
                      </button>
                      {adUrl ? (
                        <a href={adUrl} target="_blank" rel="noreferrer" aria-label="Ver anúncio" className="flex w-10 items-center justify-center rounded-lg bg-pastel-violet-50 text-pastel-violet-500 transition-colors hover:bg-pastel-violet-100">
                          <ExternalLink className="h-4 w-4" />
                        </a>
                      ) : (
                        <button type="button" disabled aria-label="Anúncio indisponível" className="flex w-10 cursor-not-allowed items-center justify-center rounded-lg bg-slate-100 text-slate-300">
                          <ExternalLink className="h-4 w-4" />
                        </button>
                      )}
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