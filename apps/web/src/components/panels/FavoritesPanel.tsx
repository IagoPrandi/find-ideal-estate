import { useEffect, useMemo, useRef, useState } from "react";
import { useQueries } from "@tanstack/react-query";
import { ArrowRight, ChevronsLeft, ChevronsRight, ExternalLink, Eye, EyeOff, Heart, Link2, Loader2, MapPin, MessageSquare, Trash2 } from "lucide-react";
import type { FavoriteZoneEntry } from "../../api/client";
import { getZoneFavoriteAnalytics } from "../../api/client";
import { getPoiCategoryMeta, POI_CATEGORY_ORDER } from "../../domain/poi";
import {
  buildFavoriteRanking,
  buildFavoriteMetricWinCounts,
  getFavoriteMetricTooltip,
  buildZoneFavoriteAnalyticsQueryKey,
  buildZoneFavoriteAnalyticsRequestKey,
  FAVORITE_METRIC_DEFINITIONS,
  formatFavoriteMetricValue,
  getFavoriteMetricDefinition,
} from "../../lib/favorites";
import {
  buildZoneRanking,
  buildZoneMetricWinCounts,
  formatZoneMetricValue,
  ZONE_METRIC_DEFINITIONS,
} from "../../lib/zone-favorites";
import { formatCurrencyBr, getListingDisplayPrice, resolveListingCardImageUrls, resolvePlatformUrl } from "../../lib/listingFormat";
import { useFavoritesStore, useJourneyStore, useUIStore, useZoneFavoritesStore } from "../../state";

const FAVORITES_ANALYTICS_STALE_TIME = 30 * 60_000;
const FAVORITES_ANALYTICS_GC_TIME = 60 * 60_000;
const ZONE_COLOR_OPTIONS = ["#0ea5e9", "#8b5cf6", "#10b981", "#f97316", "#ef4444", "#14b8a6", "#eab308", "#ec4899"] as const;

function MetricChip({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-2 rounded-lg bg-white px-2.5 py-1.5">
      <span className="font-semibold text-slate-500">{label}</span>
      <span className="text-slate-800">{value}</span>
    </div>
  );
}

export function FavoritesPanel() {
  const favorites = useFavoritesStore((state) => state.favorites);
  const selectedMetricIds = useFavoritesStore((state) => state.selectedMetricIds);
  const isPanelOpen = useFavoritesStore((state) => state.isPanelOpen);
  const activeTab = useFavoritesStore((state) => state.activeTab);
  const activeScope = useFavoritesStore((state) => state.activeScope);
  const isAuthenticated = useFavoritesStore((state) => state.isAuthenticated);
  const togglePanel = useFavoritesStore((state) => state.togglePanel);
  const setActiveTab = useFavoritesStore((state) => state.setActiveTab);
  const setActiveScope = useFavoritesStore((state) => state.setActiveScope);
  const removeFavorite = useFavoritesStore((state) => state.removeFavorite);
  const toggleMetric = useFavoritesStore((state) => state.toggleMetric);
  const updateListingNote = useFavoritesStore((state) => state.updateListingNote);
  const zoneFavorites = useZoneFavoritesStore((state) => state.zoneFavorites);
  const removeZoneFavorite = useZoneFavoritesStore((state) => state.removeZoneFavorite);
  const selectedZoneKey = useZoneFavoritesStore((state) => state.selectedZoneKey);
  const hiddenZoneKeys = useZoneFavoritesStore((state) => state.hiddenZoneKeys);
  const setSelectedZoneKey = useZoneFavoritesStore((state) => state.setSelectedZoneKey);
  const selectedZoneMetricIds = useZoneFavoritesStore((state) => state.selectedZoneMetricIds);
  const toggleZoneMetric = useZoneFavoritesStore((state) => state.toggleZoneMetric);
  const toggleZoneMapVisibility = useZoneFavoritesStore((state) => state.toggleZoneMapVisibility);
  const updateZoneNote = useZoneFavoritesStore((state) => state.updateZoneNote);
  const updateZoneColor = useZoneFavoritesStore((state) => state.updateZoneColor);
  const shareZone = useZoneFavoritesStore((state) => state.shareZone);
  const selectedSavedListingKey = useFavoritesStore((state) => state.selectedSavedListingKey);
  const setSelectedSavedListingKey = useFavoritesStore((state) => state.setSelectedSavedListingKey);
  const setJourneyId = useJourneyStore((state) => state.setJourneyId);
  const setSelectedZone = useJourneyStore((state) => state.setSelectedZone);
  const setJourneyConfig = useJourneyStore((state) => state.setConfig);
  const setPanelOpen = useFavoritesStore((state) => state.setPanelOpen);
  const goToStep = useUIStore((state) => state.goToStep);
  const setMaxStep = useUIStore((state) => state.setMaxStep);
  const [expandedZoneKey, setExpandedZoneKey] = useState<string | null>(null);
  const [poiCategoryFilter, setPoiCategoryFilter] = useState<Record<string, string | "all">>({});
  const zoneCardRefs = useRef<Record<string, HTMLElement | null>>({});
  const addManualFavorite = useFavoritesStore((state) => state.addManualFavorite);
  const [manualUrl, setManualUrl] = useState("");
  const [manualSubmitting, setManualSubmitting] = useState(false);
  const [manualError, setManualError] = useState<string | null>(null);
  const [editingNoteKey, setEditingNoteKey] = useState<string | null>(null);
  const [noteText, setNoteText] = useState("");
  const [zoneShareStatus, setZoneShareStatus] = useState<Record<string, string>>({});

  async function handleSubmitManualUrl(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (manualSubmitting) return;
    setManualSubmitting(true);
    setManualError(null);
    const result = await addManualFavorite({ url: manualUrl });
    setManualSubmitting(false);
    if (result.ok) {
      setManualUrl("");
    } else {
      setManualError(result.error || "Não foi possível adicionar pelo link.");
    }
  }

  useEffect(() => {
    if (!selectedZoneKey) return;
    const node = zoneCardRefs.current[selectedZoneKey];
    if (node) {
      node.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [selectedZoneKey]);

  const orderedZones = useMemo(
    () => buildZoneRanking(zoneFavorites, selectedZoneMetricIds),
    [zoneFavorites, selectedZoneMetricIds],
  );

  const zoneRankingWinCounts = useMemo(
    () => buildZoneMetricWinCounts(zoneFavorites, selectedZoneMetricIds),
    [zoneFavorites, selectedZoneMetricIds],
  );

  const zoneRankPositionByKey = useMemo(
    () => new Map(orderedZones.map((entry, idx) => [entry.zoneKey, idx + 1])),
    [orderedZones],
  );

  function handleSelectZone(zoneKey: string) {
    setSelectedZoneKey(selectedZoneKey === zoneKey ? null : zoneKey);
  }

  function startEditingNote(key: string, currentNote: string | null) {
    setEditingNoteKey(key);
    setNoteText(currentNote || "");
  }

  async function saveListingNote(listingKey: string) {
    await updateListingNote(listingKey, noteText);
    setEditingNoteKey(null);
  }

  async function saveZoneNote(zoneKey: string) {
    await updateZoneNote(zoneKey, noteText);
    setEditingNoteKey(null);
  }

  async function handleShareZone(zoneKey: string) {
    const token = await shareZone(zoneKey);
    if (!token) {
      setZoneShareStatus((current) => ({ ...current, [zoneKey]: "Não foi possível criar o link." }));
      return;
    }
    const url = new URL(window.location.href);
    url.hash = `#/zona/compartilhada/${encodeURIComponent(token)}`;
    const shareUrl = url.toString();
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(shareUrl);
      setZoneShareStatus((current) => ({ ...current, [zoneKey]: "Link da zona copiado." }));
    } else {
      setZoneShareStatus((current) => ({ ...current, [zoneKey]: shareUrl }));
    }
  }

  function handleContinueFromZone(entry: FavoriteZoneEntry) {
    const searchType = (entry.searchType === "sale" ? "sale" : "rent") as "rent" | "sale";
    const usageType = (entry.usageType === "commercial" ? "commercial" : entry.usageType === "all" ? "all" : "residential") as "residential" | "commercial" | "all";
    setJourneyId(entry.journeyId);
    setJourneyConfig({ type: searchType, propertyUsageType: usageType });
    setSelectedZone(null, entry.zoneFingerprint);
    setSelectedZoneKey(entry.zoneKey);
    setMaxStep(5);
    goToStep(5);
    setPanelOpen(false);
  }
  const [failedImageKeys, setFailedImageKeys] = useState<Record<string, true>>({});

  const analyticsTargets = useMemo(() => {
    const targets = new Map<string, { requestKey: string; journeyId: string; zoneFingerprint: string; searchType: string; usageType: string }>();
    for (const favorite of favorites) {
      const requestKey = buildZoneFavoriteAnalyticsRequestKey(
        favorite.journeyId,
        favorite.zoneFingerprint,
        favorite.searchType,
        favorite.usageType,
      );
      if (!targets.has(requestKey)) {
        targets.set(requestKey, {
          requestKey,
          journeyId: favorite.journeyId,
          zoneFingerprint: favorite.zoneFingerprint,
          searchType: favorite.searchType,
          usageType: favorite.usageType,
        });
      }
    }
    return Array.from(targets.values());
  }, [favorites]);

  const analyticsQueries = useQueries({
    queries: analyticsTargets.map((target) => ({
      queryKey: buildZoneFavoriteAnalyticsQueryKey(
        target.journeyId,
        target.zoneFingerprint,
        target.searchType,
        target.usageType,
      ),
      queryFn: async () => getZoneFavoriteAnalytics(
        target.journeyId,
        target.zoneFingerprint,
        target.searchType,
        target.usageType,
      ),
      enabled: isPanelOpen,
      staleTime: FAVORITES_ANALYTICS_STALE_TIME,
      gcTime: FAVORITES_ANALYTICS_GC_TIME,
      retry: false,
      refetchOnWindowFocus: false,
    })),
  });

  const analyticsByRequestKey = useMemo(() => {
    const requestMap = new Map<string, (typeof analyticsQueries)[number]["data"]>();
    analyticsTargets.forEach((target, index) => {
      requestMap.set(target.requestKey, analyticsQueries[index]?.data);
    });
    return requestMap;
  }, [analyticsQueries, analyticsTargets]);

  const comparisonItems = useMemo(
    () => favorites.map((favorite) => ({
      ...favorite,
      analytics: analyticsByRequestKey.get(
        buildZoneFavoriteAnalyticsRequestKey(
          favorite.journeyId,
          favorite.zoneFingerprint,
          favorite.searchType,
          favorite.usageType,
        ),
      ) || null,
    })),
    [analyticsByRequestKey, favorites],
  );

  const selectedMetrics = useMemo(
    () => selectedMetricIds.map((metricId) => getFavoriteMetricDefinition(metricId)),
    [selectedMetricIds],
  );

  const ranking = useMemo(
    () => buildFavoriteRanking(comparisonItems, selectedMetricIds),
    [comparisonItems, selectedMetricIds],
  );

  const rankingPositionByListingKey = useMemo(() => {
    return new Map(ranking.map((item, index) => [item.listingKey, index + 1]));
  }, [ranking]);

  const metricWinCounts = useMemo(
    () => buildFavoriteMetricWinCounts(comparisonItems, selectedMetricIds),
    [comparisonItems, selectedMetricIds],
  );

  const isAnalyticsLoading = analyticsQueries.some((query) => query.isPending || query.isLoading);
  const hasAnalyticsError = analyticsQueries.some((query) => query.isError);

  function renderFavoritePreviewImage(cardKey: string, urls: string[], altText: string) {
    const imageUrl = urls.find((candidateUrl) => !failedImageKeys[`${cardKey}:${candidateUrl}`]) || null;
    const imageStateKey = imageUrl ? `${cardKey}:${imageUrl}` : null;
    if (!imageUrl || !imageStateKey) {
      return (
        <div className="flex h-full items-center justify-center bg-gradient-to-br from-pastel-violet-100 via-white to-slate-100 text-slate-400">
          <Heart className="h-6 w-6" />
        </div>
      );
    }
    return (
      <img
        src={imageUrl}
        alt={altText}
        className="h-full w-full object-cover"
        loading="lazy"
        onError={() => {
          setFailedImageKeys((current) => {
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
    );
  }

  return (
    <div className={`favorites-shell ${isPanelOpen ? "favorites-shell--open" : "favorites-shell--closed"}`}>
      <button
        type="button"
        aria-label={isPanelOpen ? "Ocultar painel de favoritos" : "Mostrar painel de favoritos"}
        aria-expanded={isPanelOpen}
        onClick={togglePanel}
        data-testid="favorites-panel-toggle"
        className={`favorites-toggle ${isPanelOpen ? "favorites-toggle--active" : ""}`}
        title={isPanelOpen ? "Ocultar painel de favoritos" : "Mostrar painel de favoritos"}
      >
        <Heart className={`h-4 w-4 ${favorites.length > 0 ? "fill-current" : ""}`} />
        <span className="text-[11px] font-bold uppercase tracking-[0.14em]">{favorites.length}</span>
        {isPanelOpen ? <ChevronsRight className="h-4 w-4" /> : <ChevronsLeft className="h-4 w-4" />}
      </button>

      <aside className={`favorites-panel ${isPanelOpen ? "favorites-panel--open" : "favorites-panel--closed"}`} aria-hidden={!isPanelOpen} data-testid="favorites-panel">
        <div className="border-b border-slate-200 bg-white px-5 pt-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <h2 className="text-sm font-semibold text-slate-900">Painel de interesse</h2>
              <p className="mt-1 text-xs text-slate-500">
                {activeScope === "listings"
                  ? favorites.length === 0
                    ? isAuthenticated
                      ? "Salve imóveis na etapa 6 para montar ranking e matriz comparativa na sua conta."
                      : "Entre na sua conta para salvar imóveis e comparar favoritos em qualquer navegador."
                    : `${favorites.length} ${favorites.length === 1 ? "imóvel salvo" : "imóveis salvos"} na sua conta.`
                  : orderedZones.length === 0
                    ? isAuthenticated
                      ? "Salve zonas na etapa 4 para comparar pontos de interesse e métricas em qualquer navegador."
                      : "Entre na sua conta para salvar zonas da análise."
                    : `${orderedZones.length} ${orderedZones.length === 1 ? "zona salva" : "zonas salvas"} na sua conta.`}
              </p>
            </div>
            <div className="inline-flex rounded-2xl border border-slate-200 bg-slate-50 p-1 text-xs font-semibold text-slate-600">
              <button
                type="button"
                onClick={() => setActiveTab("saved")}
                className={`rounded-xl px-3 py-2 transition ${activeTab === "saved" ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
              >
                Lista salva
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("compare")}
                className={`rounded-xl px-3 py-2 transition ${activeTab === "compare" ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
              >
                Comparação
              </button>
            </div>
          </div>
          <div className="mt-3 overflow-x-auto" data-testid="favorites-scope-tabs">
            <div className="flex min-w-max gap-6">
              <button
                type="button"
                onClick={() => setActiveScope("listings")}
                className={`pb-3 text-sm font-medium border-b-2 transition-colors ${activeScope === "listings" ? "border-pastel-violet-500 text-pastel-violet-600" : "border-transparent text-slate-500 hover:text-slate-700"}`}
                data-testid="favorites-scope-tab-listings"
              >
                {`Imóveis${favorites.length ? ` (${favorites.length})` : ""}`}
              </button>
              <button
                type="button"
                onClick={() => setActiveScope("zones")}
                className={`pb-3 text-sm font-medium border-b-2 transition-colors ${activeScope === "zones" ? "border-pastel-violet-500 text-pastel-violet-600" : "border-transparent text-slate-500 hover:text-slate-700"}`}
                data-testid="favorites-scope-tab-zones"
              >
                {`Zonas${orderedZones.length ? ` (${orderedZones.length})` : ""}`}
              </button>
            </div>
          </div>
        </div>

        {activeScope === "listings" ? (
          activeTab === "saved" ? (
          <div className="panel-scroll flex-1 space-y-3 overflow-y-auto px-5 py-4">
            <form
              onSubmit={handleSubmitManualUrl}
              className="rounded-[20px] border border-slate-200 bg-white p-3 shadow-sm"
              data-testid="manual-favorite-form"
            >
              <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                <Link2 className="h-3.5 w-3.5" />
                Adicionar por link
              </div>
              <div className="mt-2 flex flex-col gap-2 sm:flex-row">
                <input
                  type="url"
                  inputMode="url"
                  placeholder="https://www.quintoandar.com.br/imovel/..."
                  value={manualUrl}
                  onChange={(event) => setManualUrl(event.target.value)}
                  disabled={manualSubmitting || !isAuthenticated}
                  className="flex-1 rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-800 outline-none transition focus:border-pastel-violet-400 focus:ring-1 focus:ring-pastel-violet-200 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-400"
                />
                <button
                  type="submit"
                  disabled={manualSubmitting || !isAuthenticated || !manualUrl.trim()}
                  className="inline-flex items-center justify-center gap-1.5 rounded-xl bg-pastel-violet-500 px-4 py-2 text-xs font-semibold text-white transition hover:bg-pastel-violet-600 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500"
                >
                  {manualSubmitting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                  Adicionar
                </button>
              </div>
              {!isAuthenticated ? (
                <p className="mt-2 text-[11px] text-slate-500">Entre na sua conta para salvar imóveis por link.</p>
              ) : null}
              {manualError ? (
                <p className="mt-2 text-[11px] text-rose-600">{manualError}</p>
              ) : null}
            </form>
            {favorites.length === 0 ? (
              <div className="rounded-[24px] border border-dashed border-slate-300 bg-slate-50/80 px-5 py-8 text-center">
                <p className="text-sm font-semibold text-slate-700">{isAuthenticated ? "Nenhum imóvel salvo ainda" : "Entre para usar favoritos"}</p>
                <p className="mt-2 text-xs leading-relaxed text-slate-500">
                  {isAuthenticated
                    ? "Use o coração ao lado do link do anúncio para adicionar itens à lista de interesse da sua conta."
                    : "Os favoritos agora são associados à sua conta, não mais ao navegador atual."}
                </p>
              </div>
            ) : (
              ranking.map((favorite) => {
                const adUrl = resolvePlatformUrl(favorite.listing.url, favorite.listing.platform);
                const imageCandidates = resolveListingCardImageUrls(favorite.listing);
                const price = getListingDisplayPrice(favorite.listing);
                const rankingPosition = rankingPositionByListingKey.get(favorite.listingKey) || null;
                const unitPriceLabel = typeof favorite.listing.current_unit_price === "number"
                  ? `${formatCurrencyBr(favorite.listing.current_unit_price)}/m²`
                  : "m² indisponível";
                const isCardSelected = selectedSavedListingKey === favorite.listingKey;
                return (
                  <article
                    key={favorite.listingKey}
                    onClick={() => setSelectedSavedListingKey(isCardSelected ? null : favorite.listingKey)}
                    className={`cursor-pointer overflow-hidden rounded-[24px] border bg-white shadow-sm transition-colors ${isCardSelected ? "border-pastel-violet-400 ring-1 ring-pastel-violet-300" : "border-slate-200 hover:border-slate-300"}`}
                    data-testid={`saved-listing-card-${favorite.listingKey}`}
                  >
                    <div className="grid min-h-[10rem] grid-cols-[7.5rem_minmax(0,1fr)]">
                      <div className="h-full w-full bg-slate-100">
                        {renderFavoritePreviewImage(
                          favorite.listingKey,
                          imageCandidates,
                          favorite.listing.address_normalized || "Imagem do imóvel salvo",
                        )}
                      </div>
                      <div className="flex min-w-0 flex-col gap-3 p-4">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-400">{favorite.listing.platform || "Plataforma"}</p>
                              {rankingPosition ? (
                                <span
                                  data-testid={`favorite-saved-rank-${favorite.listingKey}`}
                                  className={`inline-flex items-center rounded-full px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.12em] ${rankingPosition === 1 ? "border border-emerald-200 bg-emerald-50 text-emerald-700" : "border border-slate-200 bg-slate-50 text-slate-600"}`}
                                >
                                  {`${rankingPosition}º no ranking`}
                                </span>
                              ) : null}
                            </div>
                            <h3 className="mt-1 line-clamp-2 text-sm font-bold leading-snug text-slate-900">{favorite.listing.address_normalized || "Endereço não informado"}</h3>
                          </div>
                          <button
                            type="button"
                            aria-label="Remover da lista de interesse"
                            onClick={(event) => {
                              event.stopPropagation();
                              void removeFavorite(favorite.listingKey);
                            }}
                            className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-rose-200 bg-rose-50 text-rose-600 transition hover:border-rose-300 hover:bg-rose-100"
                            title="Remover da lista de interesse"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                        <div className="flex flex-wrap gap-2 text-[11px] font-semibold text-slate-600">
                          <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1">{formatCurrencyBr(price)}</span>
                          <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1">{unitPriceLabel}</span>
                          <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1">{favorite.listing.area_m2 ? `${Math.round(favorite.listing.area_m2)} m²` : "Área indisponível"}</span>
                          <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1">{favorite.listing.bedrooms ?? "--"} quartos</span>
                        </div>
                        <div className="mt-auto flex items-center justify-between gap-3">
                          <p className="text-[11px] text-slate-500">Salvo em {new Date(favorite.savedAt).toLocaleDateString("pt-BR")}</p>
                          <div className="flex items-center gap-1.5">
                            <button
                              type="button"
                              onClick={(event) => { event.stopPropagation(); startEditingNote(favorite.listingKey, favorite.note); }}
                              title={favorite.note ? "Editar comentário" : "Adicionar comentário"}
                              className={`inline-flex h-8 w-8 items-center justify-center rounded-xl border transition ${favorite.note ? "border-amber-200 bg-amber-50 text-amber-600 hover:bg-amber-100" : "border-slate-200 bg-slate-50 text-slate-400 hover:border-slate-300 hover:text-slate-600"}`}
                            >
                              <MessageSquare className="h-3.5 w-3.5" />
                            </button>
                            {adUrl ? (
                              <a
                                href={adUrl}
                                target="_blank"
                                rel="noreferrer"
                                onClick={(event) => event.stopPropagation()}
                                className="inline-flex items-center gap-1.5 rounded-xl border border-pastel-violet-200 bg-pastel-violet-50 px-3 py-2 text-xs font-semibold text-pastel-violet-700 transition hover:bg-pastel-violet-100"
                              >
                                Abrir anúncio
                                <ExternalLink className="h-3.5 w-3.5" />
                              </a>
                            ) : null}
                          </div>
                        </div>
                        {editingNoteKey === favorite.listingKey ? (
                          <div className="mt-2 flex flex-col gap-1.5" onClick={(event) => event.stopPropagation()}>
                            <textarea
                              value={noteText}
                              onChange={(e) => setNoteText(e.target.value)}
                              placeholder="Escreva um comentário sobre este imóvel..."
                              rows={2}
                              className="w-full rounded-xl border border-slate-200 px-3 py-2 text-xs text-slate-800 outline-none focus:border-pastel-violet-400 focus:ring-1 focus:ring-pastel-violet-200"
                            />
                            <div className="flex gap-2">
                              <button type="button" onClick={() => void saveListingNote(favorite.listingKey)} className="rounded-lg bg-pastel-violet-500 px-3 py-1.5 text-xs font-semibold text-white hover:bg-pastel-violet-600">Salvar</button>
                              <button type="button" onClick={(event) => { event.stopPropagation(); setEditingNoteKey(null); }} className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-50">Cancelar</button>
                            </div>
                          </div>
                        ) : favorite.note ? (
                          <p className="mt-2 rounded-xl border border-amber-100 bg-amber-50/70 px-3 py-2 text-[11px] text-amber-800">{favorite.note}</p>
                        ) : null}
                      </div>
                    </div>
                  </article>
                );
              })
            )}
          </div>
        ) : (
          <div className="panel-scroll flex-1 overflow-y-auto px-5 py-4">
            <section className="rounded-[24px] border border-slate-200 bg-white p-4 shadow-sm" data-testid="favorites-metric-selector">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Métricas ativas</p>
                  <h3 className="mt-1 text-sm font-bold text-slate-800">Seleção usada no ranking e na matriz</h3>
                </div>
                <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[11px] font-semibold text-slate-600">{selectedMetricIds.length} selecionada{selectedMetricIds.length === 1 ? "" : "s"}</span>
              </div>
              <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                {FAVORITE_METRIC_DEFINITIONS.map((metric) => {
                  const isSelected = selectedMetricIds.includes(metric.id);
                  return (
                    <button
                      key={metric.id}
                      type="button"
                      aria-pressed={isSelected}
                      onClick={() => toggleMetric(metric.id)}
                      title={getFavoriteMetricTooltip(metric.id)}
                      className={`rounded-2xl border px-3 py-2 text-left text-xs transition ${isSelected ? "border-pastel-violet-300 bg-pastel-violet-50 text-pastel-violet-800 shadow-sm" : "border-slate-200 bg-slate-50/80 text-slate-600 hover:border-slate-300 hover:bg-white"}`}
                    >
                      <span className="block font-semibold">{metric.label}</span>
                    </button>
                  );
                })}
              </div>
            </section>

            <section className="mt-4 rounded-[24px] border border-slate-200 bg-white p-4 shadow-sm" data-testid="favorites-ranking">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Ranking</p>
                  <h3 className="mt-1 text-sm font-bold text-slate-800">Ordem pelo desempenho das métricas selecionadas</h3>
                </div>
                {isAnalyticsLoading ? <Loader2 className="h-4 w-4 animate-spin text-pastel-violet-600" /> : null}
              </div>
              {favorites.length === 0 ? (
                <p className="mt-3 text-xs leading-relaxed text-slate-500">Salve imóveis para montar o ranking.</p>
              ) : (
                <div className="mt-4 space-y-2.5">
                  {ranking.map((item, index) => {
                    const adUrl = resolvePlatformUrl(item.listing.url, item.listing.platform);
                    const metricWins = metricWinCounts.get(item.listingKey) || 0;
                    const isRankingSelected = selectedSavedListingKey === item.listingKey;
                    return (
                      <div
                        key={item.listingKey}
                        onClick={() => setSelectedSavedListingKey(isRankingSelected ? null : item.listingKey)}
                        className={`grid cursor-pointer grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 rounded-2xl border px-3 py-3 transition-colors ${isRankingSelected ? "border-pastel-violet-400 bg-pastel-violet-50 ring-1 ring-pastel-violet-200" : index === 0 ? "border-emerald-200 bg-emerald-50/70 hover:border-emerald-300" : "border-slate-200 bg-slate-50/70 hover:border-slate-300"}`}
                      >
                        <div className={`flex h-8 w-8 items-center justify-center rounded-xl text-xs font-extrabold ${index === 0 ? "bg-emerald-600 text-white" : "bg-slate-200 text-slate-700"}`}>#{index + 1}</div>
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold text-slate-900">{item.listing.address_normalized || "Endereço não informado"}</p>
                          <p className="mt-1 truncate text-[11px] text-slate-500">
                            {`Venceu ${metricWins} de ${selectedMetricIds.length} ${selectedMetricIds.length === 1 ? "métrica selecionada" : "métricas selecionadas"}`}
                          </p>
                        </div>
                        {adUrl ? (
                          <a
                            href={adUrl}
                            target="_blank"
                            rel="noreferrer"
                            onClick={(event) => event.stopPropagation()}
                            className="inline-flex h-8 w-8 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-500 transition hover:border-pastel-violet-300 hover:text-pastel-violet-700"
                            aria-label="Abrir anúncio salvo"
                          >
                            <ExternalLink className="h-3.5 w-3.5" />
                          </a>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              )}
              {hasAnalyticsError ? <p className="mt-3 text-[11px] text-amber-700">Alguns imóveis salvos não têm analytics disponíveis neste momento. A comparação continua com os dados válidos.</p> : null}
            </section>

            <section className="mt-4 rounded-[24px] border border-slate-200 bg-white p-4 shadow-sm" data-testid="favorites-matrix-section">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Matriz</p>
                  <h3 className="mt-1 text-sm font-bold text-slate-800">Linhas fixas pelos favoritos salvos</h3>
                </div>
                <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[11px] font-semibold text-slate-600">{ranking.length} linha{ranking.length === 1 ? "" : "s"}</span>
              </div>
              {favorites.length === 0 ? (
                <p className="mt-3 text-xs leading-relaxed text-slate-500">A matriz aparece automaticamente quando houver imóveis na lista de interesse.</p>
              ) : (
                <div className="mt-4 overflow-x-auto rounded-2xl border border-slate-200">
                  <table className="w-max min-w-full border-collapse text-[11px] text-slate-700" data-testid="favorites-matrix">
                    <thead className="bg-slate-50 text-left text-[10px] font-bold uppercase tracking-[0.12em] text-slate-500">
                      <tr>
                        <th className="sticky left-0 z-10 w-[8.4rem] min-w-[8.4rem] max-w-[8.4rem] border-b border-r border-slate-200 bg-slate-50 px-2.5 py-2">Imóvel</th>
                        {selectedMetrics.map((metric) => (
                          <th key={metric.id} title={getFavoriteMetricTooltip(metric.id)} className="whitespace-nowrap border-b border-slate-200 px-3 py-2">{metric.shortLabel}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {ranking.map((item, index) => {
                        const adUrl = resolvePlatformUrl(item.listing.url, item.listing.platform);
                        const isRowSelected = selectedSavedListingKey === item.listingKey;
                        return (
                          <tr
                            key={item.listingKey}
                            onClick={() => setSelectedSavedListingKey(isRowSelected ? null : item.listingKey)}
                            className={`cursor-pointer ${isRowSelected ? "bg-pastel-violet-50" : index % 2 === 0 ? "bg-white hover:bg-slate-50" : "bg-slate-50/60 hover:bg-slate-100"}`}
                          >
                            <td className="sticky left-0 z-[1] w-[8.4rem] min-w-[8.4rem] max-w-[8.4rem] border-r border-slate-200 bg-inherit px-2.5 py-2.5 align-top">
                              <div className="w-[8.4rem] min-w-[8.4rem] max-w-[8.4rem]">
                                <div className="flex items-start justify-between gap-2">
                                  <div className="min-w-0">
                                    <p className="break-words whitespace-normal font-semibold leading-snug text-slate-900">{item.listing.address_normalized || "Endereço não informado"}</p>
                                  </div>
                                  {adUrl ? (
                                    <a
                                      href={adUrl}
                                      target="_blank"
                                      rel="noreferrer"
                                      onClick={(event) => event.stopPropagation()}
                                      className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 transition hover:border-pastel-violet-300 hover:text-pastel-violet-700"
                                      aria-label="Abrir anúncio na matriz"
                                    >
                                      <ExternalLink className="h-3.5 w-3.5" />
                                    </a>
                                  ) : null}
                                </div>
                              </div>
                            </td>
                            {selectedMetrics.map((metric) => (
                              <td key={`${item.listingKey}:${metric.id}`} className="whitespace-nowrap border-l border-slate-100 px-3 py-2.5 align-top text-slate-700">
                                {formatFavoriteMetricValue(item, metric.id)}
                              </td>
                            ))}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </div>
          )
        ) : activeTab === "saved" ? (
          <div className="panel-scroll flex-1 space-y-3 overflow-y-auto px-5 py-4">
            {orderedZones.length === 0 ? (
              <div className="rounded-[24px] border border-dashed border-slate-300 bg-slate-50/80 px-5 py-8 text-center">
                <p className="text-sm font-semibold text-slate-700">
                  {isAuthenticated ? "Nenhuma zona salva ainda" : "Entre para usar zonas salvas"}
                </p>
                <p className="mt-2 text-xs leading-relaxed text-slate-500">
                  {isAuthenticated
                    ? "Use o coração ao lado do título da zona, na Etapa 4, para incluir aqui com pontos de interesse e métricas."
                    : "As zonas salvas ficam na sua conta, não no navegador atual."}
                </p>
              </div>
            ) : (
              orderedZones.map((entry) => {
                const isExpanded = expandedZoneKey === entry.zoneKey;
                const isSelected = selectedZoneKey === entry.zoneKey;
                const isHiddenOnMap = hiddenZoneKeys.includes(entry.zoneKey);
                const poiPoints = entry.payload.poi_points || [];
                const activeFilter = poiCategoryFilter[entry.zoneKey] || "all";
                const categoryCounts = new Map<string, number>();
                for (const poi of poiPoints) {
                  const categoryKey = poi.category || "other";
                  categoryCounts.set(categoryKey, (categoryCounts.get(categoryKey) || 0) + 1);
                }
                const orderedCategoryKeys = [
                  ...POI_CATEGORY_ORDER.filter((key) => categoryCounts.has(key)),
                  ...Array.from(categoryCounts.keys()).filter((key) => !POI_CATEGORY_ORDER.includes(key as typeof POI_CATEGORY_ORDER[number])),
                ];
                const filteredPois = activeFilter === "all"
                  ? poiPoints
                  : poiPoints.filter((poi) => (poi.category || "other") === activeFilter);
                const transport = entry.payload.transport_point;
                const metrics = entry.payload.metrics;
                const zoneColor = entry.color || entry.payload.color || "#0ea5e9";
                const transportSummary = entry.payload.transport_summary;
                const propertyTypeEntries = Object.entries(entry.payload.property_type_counts || {}).filter(([, count]) => Number(count) > 0);
                return (
                  <article
                    key={entry.zoneKey}
                    ref={(node) => {
                      zoneCardRefs.current[entry.zoneKey] = node;
                    }}
                    className={`overflow-hidden rounded-[24px] border bg-white shadow-sm transition-colors ${isSelected ? "border-pastel-violet-400 ring-1 ring-pastel-violet-300" : "border-slate-200"}`}
                    data-testid={`saved-zone-card-${entry.zoneKey}`}
                  >
                    <div className="flex w-full items-start justify-between gap-3 px-4 py-4 hover:bg-slate-50/60">
                      <button
                        type="button"
                        onClick={() => handleSelectZone(entry.zoneKey)}
                        className="min-w-0 flex-1 text-left"
                        aria-pressed={isSelected}
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-400">Zona salva</p>
                          {(() => {
                            const pos = zoneRankPositionByKey.get(entry.zoneKey);
                            if (!pos || zoneFavorites.length < 2) return null;
                            return (
                              <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.12em] ${pos === 1 ? "border border-emerald-200 bg-emerald-50 text-emerald-700" : "border border-slate-200 bg-slate-50 text-slate-600"}`}>
                                {`${pos}º no ranking`}
                              </span>
                            );
                          })()}
                        </div>
                        <h3 className="mt-1 line-clamp-2 text-sm font-bold text-slate-900">
                          {entry.payload.neighborhood_name
                            ? `${entry.payload.neighborhood_name}${entry.payload.city_name ? ` · ${entry.payload.city_name}` : ""}`
                            : `Zona ${entry.zoneFingerprint.slice(0, 8)}`}
                        </h3>
                        <p className="mt-1 text-[11px] text-slate-500">
                          Salvo em {new Date(entry.savedAt).toLocaleDateString("pt-BR")}
                          {transport?.name ? ` · Seed: ${transport.name}` : transport?.lat && transport?.lon ? ` · Seed: ${transport.lat.toFixed(4)}, ${transport.lon.toFixed(4)}` : ""}
                        </p>
                      </button>
                      <div className="flex shrink-0 items-center gap-1.5">
                        <button
                          type="button"
                          aria-label={isHiddenOnMap ? "Mostrar zona salva no mapa" : "Ocultar zona salva no mapa"}
                          title={isHiddenOnMap ? "Mostrar zona salva no mapa" : "Ocultar zona salva no mapa"}
                          onClick={(event) => {
                            event.stopPropagation();
                            toggleZoneMapVisibility(entry.zoneKey);
                          }}
                          className={`inline-flex h-9 w-9 items-center justify-center rounded-xl border transition ${isHiddenOnMap ? "border-slate-200 bg-slate-100 text-slate-500 hover:border-slate-300 hover:text-slate-700" : "border-pastel-violet-200 bg-pastel-violet-50 text-pastel-violet-700 hover:border-pastel-violet-300 hover:bg-pastel-violet-100"}`}
                          data-testid={`saved-zone-visibility-${entry.zoneKey}`}
                        >
                          {isHiddenOnMap ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                        </button>
                        <button
                          type="button"
                          aria-label="Compartilhar zona salva"
                          onClick={(event) => {
                            event.stopPropagation();
                            void handleShareZone(entry.zoneKey);
                          }}
                          className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-600 transition hover:border-pastel-violet-300 hover:bg-pastel-violet-50 hover:text-pastel-violet-700"
                          title="Compartilhar zona salva"
                        >
                          <Link2 className="h-4 w-4" />
                        </button>
                        <button
                          type="button"
                          aria-label="Remover zona salva"
                          onClick={(event) => {
                            event.stopPropagation();
                            void removeZoneFavorite(entry.zoneKey);
                          }}
                          className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-rose-200 bg-rose-50 text-rose-600 transition hover:border-rose-300 hover:bg-rose-100"
                          title="Remover zona salva"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                    <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 px-4 py-3">
                      <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">Cor da zona</span>
                      {ZONE_COLOR_OPTIONS.map((color) => (
                        <button
                          key={`${entry.zoneKey}:${color}`}
                          type="button"
                          aria-label={`Usar cor ${color}`}
                          onClick={(event) => {
                            event.stopPropagation();
                            void updateZoneColor(entry.zoneKey, color);
                          }}
                          className={`h-7 w-7 rounded-full border-2 transition ${zoneColor.toLowerCase() === color ? "border-slate-900" : "border-white ring-1 ring-slate-200"}`}
                          style={{ backgroundColor: color }}
                        />
                      ))}
                      <input
                        type="color"
                        value={zoneColor}
                        onChange={(event) => void updateZoneColor(entry.zoneKey, event.target.value)}
                        className="h-7 w-9 cursor-pointer rounded border border-slate-200 bg-white p-0.5"
                        aria-label="Escolher cor personalizada da zona"
                      />
                      {zoneShareStatus[entry.zoneKey] ? (
                        <span className="ml-auto max-w-full truncate text-[11px] font-medium text-slate-500">{zoneShareStatus[entry.zoneKey]}</span>
                      ) : entry.share ? (
                        <span className="ml-auto text-[11px] font-medium text-slate-500">Compartilhamento ativo</span>
                      ) : null}
                    </div>
                    <div className="grid grid-cols-2 gap-2 border-t border-slate-100 bg-slate-50/60 px-4 py-3 text-[11px] text-slate-600 sm:grid-cols-3">
                      <MetricChip label="Tempo" value={metrics.travel_time_minutes != null ? `${metrics.travel_time_minutes} min` : "--"} />
                      <MetricChip label="Área" value={metrics.zone_area_m2 != null ? `${(metrics.zone_area_m2 / 1_000_000).toFixed(2)} km²` : "--"} />
                      <MetricChip label="Verde" value={metrics.green_percentage != null ? `${metrics.green_percentage.toFixed(1)}%` : "--"} />
                      <MetricChip label="Alagamento" value={metrics.flood_percentage != null ? `${metrics.flood_percentage.toFixed(1)}%` : "--"} />
                      <MetricChip label="Preço m²" value={metrics.zone_average_unit_price != null ? `${formatCurrencyBr(metrics.zone_average_unit_price)}/m²` : "--"} />
                      <MetricChip label="Preço médio" value={metrics.zone_average_price != null ? formatCurrencyBr(metrics.zone_average_price) : "--"} />
                      <MetricChip label="Homicídios/km²" value={metrics.homicide_density_per_km2 != null ? metrics.homicide_density_per_km2.toFixed(2) : "--"} />
                      <MetricChip label="Roubos/km²" value={metrics.robbery_density_per_km2 != null ? metrics.robbery_density_per_km2.toFixed(2) : "--"} />
                      <MetricChip label="Crimes/km²" value={metrics.crime_density_per_km2 != null ? metrics.crime_density_per_km2.toFixed(2) : "--"} />
                      {transportSummary ? (
                        <>
                          <MetricChip label="Pontos de ônibus" value={String(transportSummary.bus_stop_count ?? 0)} />
                          <MetricChip label="Linhas de ônibus" value={String(transportSummary.bus_line_count ?? 0)} />
                          <MetricChip label="Terminais" value={String(transportSummary.bus_terminal_count ?? 0)} />
                          <MetricChip label="Estações trem/metrô" value={String(transportSummary.train_metro_platform_count ?? 0)} />
                          <MetricChip label="Linhas trem/metrô" value={String(transportSummary.train_metro_line_count ?? 0)} />
                        </>
                      ) : null}
                      {propertyTypeEntries.map(([type, count]) => (
                        <MetricChip
                          key={`${entry.zoneKey}:property:${type}`}
                          label={type === "residential" ? "Residenciais" : type === "commercial" ? "Comerciais" : type}
                          value={String(count)}
                        />
                      ))}
                    </div>
                    {orderedCategoryKeys.length > 0 ? (
                      <div className="flex flex-wrap gap-1.5 border-t border-slate-100 px-4 py-3">
                        <button
                          type="button"
                          onClick={() => setPoiCategoryFilter((current) => ({ ...current, [entry.zoneKey]: "all" }))}
                          className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold transition ${activeFilter === "all" ? "border-pastel-violet-300 bg-pastel-violet-50 text-pastel-violet-700" : "border-slate-200 bg-slate-50 text-slate-600 hover:border-slate-300"}`}
                        >
                          Todos <span className="text-[10px] text-slate-500">{poiPoints.length}</span>
                        </button>
                        {orderedCategoryKeys.map((categoryKey) => {
                          const meta = getPoiCategoryMeta(categoryKey);
                          const count = categoryCounts.get(categoryKey) || 0;
                          const isActive = activeFilter === categoryKey;
                          return (
                            <button
                              key={categoryKey}
                              type="button"
                              onClick={() => setPoiCategoryFilter((current) => ({ ...current, [entry.zoneKey]: categoryKey }))}
                              className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold transition ${isActive ? "text-white" : "bg-slate-50 text-slate-700 hover:bg-slate-100"}`}
                              style={{
                                borderColor: meta.color,
                                backgroundColor: isActive ? meta.color : undefined,
                              }}
                            >
                              <span
                                className="inline-block h-2 w-2 rounded-full"
                                style={{ backgroundColor: isActive ? "#ffffff" : meta.color }}
                              />
                              {meta.label}
                              <span className={`text-[10px] ${isActive ? "text-white/80" : "text-slate-500"}`}>{count}</span>
                            </button>
                          );
                        })}
                      </div>
                    ) : null}
                    <div className="border-t border-slate-100 px-4 py-3">
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => setExpandedZoneKey(isExpanded ? null : entry.zoneKey)}
                            className="text-xs font-semibold text-pastel-violet-700 transition hover:text-pastel-violet-900"
                          >
                            {isExpanded ? `Ocultar ${filteredPois.length} pontos de interesse` : `Ver ${filteredPois.length} pontos de interesse`}
                          </button>
                          <button
                            type="button"
                            onClick={() => startEditingNote(entry.zoneKey, entry.note ?? null)}
                            title={entry.note ? "Editar comentário" : "Adicionar comentário"}
                            className={`inline-flex h-7 w-7 items-center justify-center rounded-lg border transition ${entry.note ? "border-amber-200 bg-amber-50 text-amber-600 hover:bg-amber-100" : "border-slate-200 bg-slate-50 text-slate-400 hover:border-slate-300 hover:text-slate-600"}`}
                          >
                            <MessageSquare className="h-3.5 w-3.5" />
                          </button>
                        </div>
                        <button
                          type="button"
                          onClick={() => handleContinueFromZone(entry)}
                          className="inline-flex items-center gap-1.5 rounded-xl bg-pastel-violet-500 px-3 py-2 text-xs font-semibold text-white transition hover:bg-pastel-violet-600"
                          data-testid={`saved-zone-continue-${entry.zoneKey}`}
                        >
                          Continuar para endereços
                          <ArrowRight className="h-3.5 w-3.5" />
                        </button>
                      </div>
                      {editingNoteKey === entry.zoneKey ? (
                        <div className="mt-2 flex flex-col gap-1.5">
                          <textarea
                            value={noteText}
                            onChange={(e) => setNoteText(e.target.value)}
                            placeholder="Escreva um comentário sobre esta zona..."
                            rows={2}
                            className="w-full rounded-xl border border-slate-200 px-3 py-2 text-xs text-slate-800 outline-none focus:border-pastel-violet-400 focus:ring-1 focus:ring-pastel-violet-200"
                          />
                          <div className="flex gap-2">
                            <button type="button" onClick={() => void saveZoneNote(entry.zoneKey)} className="rounded-lg bg-pastel-violet-500 px-3 py-1.5 text-xs font-semibold text-white hover:bg-pastel-violet-600">Salvar</button>
                            <button type="button" onClick={() => setEditingNoteKey(null)} className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-50">Cancelar</button>
                          </div>
                        </div>
                      ) : entry.note ? (
                        <p className="mt-2 rounded-xl border border-amber-100 bg-amber-50/70 px-3 py-2 text-[11px] text-amber-800">{entry.note}</p>
                      ) : null}
                      {isExpanded ? (
                        <ul className="mt-3 space-y-2 text-[11px] text-slate-600">
                          {filteredPois.length === 0 ? (
                            <li className="text-slate-400">Nenhum ponto de interesse nesta categoria.</li>
                          ) : (
                            filteredPois.map((poi, index) => {
                              const meta = getPoiCategoryMeta(poi.category || "other");
                              return (
                                <li key={`${entry.zoneKey}:poi:${poi.id || index}`} className="flex items-start gap-2 rounded-lg border border-slate-100 bg-slate-50/80 px-2.5 py-1.5">
                                  <MapPin className="mt-0.5 h-3.5 w-3.5" style={{ color: meta.color }} />
                                  <div className="min-w-0 flex-1">
                                    <div className="flex flex-wrap items-center gap-1.5">
                                      <p className="truncate font-semibold text-slate-800">{poi.name || meta.singularLabel || "Ponto de interesse sem nome"}</p>
                                      <span
                                        className="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold text-white"
                                        style={{ backgroundColor: meta.color }}
                                      >
                                        {meta.label}
                                      </span>
                                    </div>
                                    <p className="truncate text-slate-500">
                                      {poi.address || `${poi.lat.toFixed(5)}, ${poi.lon.toFixed(5)}`}
                                    </p>
                                  </div>
                                </li>
                              );
                            })
                          )}
                        </ul>
                      ) : null}
                    </div>
                  </article>
                );
              })
            )}
          </div>
        ) : (
          <div className="panel-scroll flex-1 overflow-y-auto px-5 py-4">
            <section className="rounded-[24px] border border-slate-200 bg-white p-4 shadow-sm" data-testid="zone-metric-selector">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Métricas ativas</p>
                  <h3 className="mt-1 text-sm font-bold text-slate-800">Seleção usada no ranking e na matriz</h3>
                </div>
                <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[11px] font-semibold text-slate-600">
                  {selectedZoneMetricIds.length} selecionada{selectedZoneMetricIds.length === 1 ? "" : "s"}
                </span>
              </div>
              <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                {ZONE_METRIC_DEFINITIONS.map((metric) => {
                  const isSelected = selectedZoneMetricIds.includes(metric.id);
                  return (
                    <button
                      key={metric.id}
                      type="button"
                      aria-pressed={isSelected}
                      onClick={() => toggleZoneMetric(metric.id)}
                      className={`rounded-2xl border px-3 py-2 text-left text-xs transition ${isSelected ? "border-pastel-violet-300 bg-pastel-violet-50 text-pastel-violet-800 shadow-sm" : "border-slate-200 bg-slate-50/80 text-slate-600 hover:border-slate-300 hover:bg-white"}`}
                    >
                      <span className="block font-semibold">{metric.label}</span>
                    </button>
                  );
                })}
              </div>
            </section>

            <section className="mt-4 rounded-[24px] border border-slate-200 bg-white p-4 shadow-sm" data-testid="zone-ranking">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Ranking</p>
                  <h3 className="mt-1 text-sm font-bold text-slate-800">Ordem pelo desempenho das métricas selecionadas</h3>
                </div>
              </div>
              {orderedZones.length === 0 ? (
                <p className="mt-3 text-xs leading-relaxed text-slate-500">Salve zonas para montar o ranking.</p>
              ) : (
                <div className="mt-4 space-y-2.5">
                  {orderedZones.map((entry, index) => {
                    const wins = zoneRankingWinCounts.get(entry.zoneKey) || 0;
                    const zoneName = entry.payload.neighborhood_name
                      ? `${entry.payload.neighborhood_name}${entry.payload.city_name ? ` · ${entry.payload.city_name}` : ""}`
                      : `Zona ${entry.zoneFingerprint.slice(0, 8)}`;
                    const isRankSelected = selectedZoneKey === entry.zoneKey;
                    return (
                      <div
                        key={entry.zoneKey}
                        onClick={() => setSelectedZoneKey(isRankSelected ? null : entry.zoneKey)}
                        className={`grid cursor-pointer grid-cols-[auto_minmax(0,1fr)] items-center gap-3 rounded-2xl border px-3 py-3 transition-colors ${isRankSelected ? "border-pastel-violet-400 bg-pastel-violet-50 ring-1 ring-pastel-violet-200" : index === 0 ? "border-emerald-200 bg-emerald-50/70 hover:border-emerald-300" : "border-slate-200 bg-slate-50/70 hover:border-slate-300"}`}
                      >
                        <div className={`flex h-8 w-8 items-center justify-center rounded-xl text-xs font-extrabold ${index === 0 ? "bg-emerald-600 text-white" : "bg-slate-200 text-slate-700"}`}>#{index + 1}</div>
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold text-slate-900">{zoneName}</p>
                          <p className="mt-1 truncate text-[11px] text-slate-500">
                            {`Venceu ${wins} de ${selectedZoneMetricIds.length} ${selectedZoneMetricIds.length === 1 ? "métrica selecionada" : "métricas selecionadas"}`}
                          </p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </section>

            <section className="mt-4 rounded-[24px] border border-slate-200 bg-white p-4 shadow-sm" data-testid="zone-matrix">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Matriz</p>
                  <h3 className="mt-1 text-sm font-bold text-slate-800">Métricas comparativas das zonas salvas</h3>
                </div>
                <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[11px] font-semibold text-slate-600">
                  {orderedZones.length} linha{orderedZones.length === 1 ? "" : "s"}
                </span>
              </div>
              {orderedZones.length === 0 ? (
                <p className="mt-3 text-xs leading-relaxed text-slate-500">
                  Salve zonas para comparar métricas lado a lado.
                </p>
              ) : (
                <div className="mt-4 overflow-x-auto rounded-2xl border border-slate-200">
                  <table className="w-max min-w-full border-collapse text-[11px] text-slate-700">
                    <thead className="bg-slate-50 text-left text-[10px] font-bold uppercase tracking-[0.12em] text-slate-500">
                      <tr>
                        <th className="sticky left-0 z-10 w-[8.4rem] min-w-[8.4rem] max-w-[8.4rem] border-b border-r border-slate-200 bg-slate-50 px-2.5 py-2">Zona</th>
                        {ZONE_METRIC_DEFINITIONS.filter((m) => selectedZoneMetricIds.includes(m.id)).map((metric) => (
                          <th key={metric.id} className="whitespace-nowrap border-b border-slate-200 px-3 py-2">
                            {metric.shortLabel}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {orderedZones.map((entry, index) => {
                        const zoneName = entry.payload.neighborhood_name
                          ? `${entry.payload.neighborhood_name}${entry.payload.city_name ? ` · ${entry.payload.city_name}` : ""}`
                          : `Zona ${entry.zoneFingerprint.slice(0, 8)}`;
                        const isRowSelected = selectedZoneKey === entry.zoneKey;
                        return (
                          <tr
                            key={entry.zoneKey}
                            onClick={() => setSelectedZoneKey(isRowSelected ? null : entry.zoneKey)}
                            className={`cursor-pointer ${isRowSelected ? "bg-pastel-violet-50" : index % 2 === 0 ? "bg-white hover:bg-slate-50" : "bg-slate-50/60 hover:bg-slate-100"}`}
                          >
                            <td className="sticky left-0 z-[1] w-[8.4rem] min-w-[8.4rem] max-w-[8.4rem] border-r border-slate-200 bg-inherit px-2.5 py-2.5 align-top">
                              <p className="break-words whitespace-normal font-semibold leading-snug text-slate-900">{zoneName}</p>
                              <p className="mt-0.5 text-[10px] text-slate-500">{`${entry.payload.poi_points?.length ?? 0} pontos de interesse`}</p>
                            </td>
                            {ZONE_METRIC_DEFINITIONS.filter((m) => selectedZoneMetricIds.includes(m.id)).map((metric) => (
                              <td key={`${entry.zoneKey}:${metric.id}`} className="whitespace-nowrap border-l border-slate-100 px-3 py-2.5 align-top text-slate-700">
                                {formatZoneMetricValue(entry, metric.id)}
                              </td>
                            ))}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </div>
        )}
      </aside>
    </div>
  );
}
