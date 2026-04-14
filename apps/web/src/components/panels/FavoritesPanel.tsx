import { useMemo, useState } from "react";
import { useQueries } from "@tanstack/react-query";
import { ChevronsLeft, ChevronsRight, ExternalLink, Heart, Loader2, Trash2 } from "lucide-react";
import { getZoneFavoriteAnalytics } from "../../api/client";
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
import { formatCurrencyBr, getListingDisplayPrice, resolveListingCardImageUrls, resolvePlatformUrl } from "../../lib/listingFormat";
import { useFavoritesStore } from "../../state";

const FAVORITES_ANALYTICS_STALE_TIME = 30 * 60_000;
const FAVORITES_ANALYTICS_GC_TIME = 60 * 60_000;

export function FavoritesPanel() {
  const favorites = useFavoritesStore((state) => state.favorites);
  const selectedMetricIds = useFavoritesStore((state) => state.selectedMetricIds);
  const isPanelOpen = useFavoritesStore((state) => state.isPanelOpen);
  const activeTab = useFavoritesStore((state) => state.activeTab);
  const isAuthenticated = useFavoritesStore((state) => state.isAuthenticated);
  const togglePanel = useFavoritesStore((state) => state.togglePanel);
  const setActiveTab = useFavoritesStore((state) => state.setActiveTab);
  const removeFavorite = useFavoritesStore((state) => state.removeFavorite);
  const toggleMetric = useFavoritesStore((state) => state.toggleMetric);
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
      enabled: isPanelOpen && activeTab === "compare",
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
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-white px-5 py-4">
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-slate-900">Painel de interesse</h2>
            <p className="mt-1 text-xs text-slate-500">
              {favorites.length === 0
                ? (isAuthenticated
                    ? "Salve imóveis na etapa 6 para montar ranking e matriz comparativa na sua conta."
                    : "Entre na sua conta para salvar imóveis e comparar favoritos em qualquer navegador.")
                : `${favorites.length} ${favorites.length === 1 ? "imóvel salvo" : "imóveis salvos"} na sua conta.`}
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

        {activeTab === "saved" ? (
          <div className="panel-scroll flex-1 space-y-3 overflow-y-auto px-5 py-4">
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
              favorites.map((favorite) => {
                const adUrl = resolvePlatformUrl(favorite.listing.url, favorite.listing.platform);
                const imageCandidates = resolveListingCardImageUrls(favorite.listing);
                const price = getListingDisplayPrice(favorite.listing);
                const unitPriceLabel = typeof favorite.listing.current_unit_price === "number"
                  ? `${formatCurrencyBr(favorite.listing.current_unit_price)}/m²`
                  : "m² indisponível";
                return (
                  <article key={favorite.listingKey} className="overflow-hidden rounded-[24px] border border-slate-200 bg-white shadow-sm">
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
                            <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-400">{favorite.listing.platform || "Plataforma"}</p>
                            <h3 className="mt-1 line-clamp-2 text-sm font-bold leading-snug text-slate-900">{favorite.listing.address_normalized || "Endereço não informado"}</h3>
                          </div>
                          <button
                            type="button"
                            aria-label="Remover da lista de interesse"
                            onClick={() => {
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
                          {adUrl ? (
                            <a
                              href={adUrl}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1.5 rounded-xl border border-pastel-violet-200 bg-pastel-violet-50 px-3 py-2 text-xs font-semibold text-pastel-violet-700 transition hover:bg-pastel-violet-100"
                            >
                              Abrir anúncio
                              <ExternalLink className="h-3.5 w-3.5" />
                            </a>
                          ) : null}
                        </div>
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
                    return (
                      <div key={item.listingKey} className={`grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 rounded-2xl border px-3 py-3 ${index === 0 ? "border-emerald-200 bg-emerald-50/70" : "border-slate-200 bg-slate-50/70"}`}>
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
                        return (
                          <tr key={item.listingKey} className={index % 2 === 0 ? "bg-white" : "bg-slate-50/60"}>
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
        )}
      </aside>
    </div>
  );
}