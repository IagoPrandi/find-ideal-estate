import { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, Search } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { apiActionHint, createZoneEnrichmentJob, getJob, getJourneyZonesList, updateJourney } from "../../api/client";
import { getPoiCategoryMeta, getZonePoiSelectionKey, POI_CATEGORY_ORDER, sortPoiPoints, ZonePoiPointLike, zoneNeedsPoiBackfill } from "../../domain/poi";
import { formatCurrencyBr } from "../../lib/listingFormat";
import { useJourneyStore, useUIStore } from "../../state";

type JourneyRank = {
  position?: number | null;
  total?: number;
  percentile?: number | null;
};

type ZoneSortKey = "travel_time" | "safety" | "green" | "flood" | "price";

const SORT_OPTIONS: Array<{ key: ZoneSortKey; label: string }> = [
  { key: "travel_time", label: "Mais rápidas" },
  { key: "safety", label: "Mais seguras" },
  { key: "green", label: "Mais arborizadas" },
  { key: "flood", label: "Menor risco de alagamento" },
  { key: "price", label: "Mais baratas" },
];

function formatRank(rank: JourneyRank | null | undefined) {
  if (!rank?.position || !rank?.total) {
    return "Sem base";
  }
  return `${rank.position}º/${rank.total}`;
}

function getRankValue(rank: JourneyRank | null | undefined) {
  if (!rank?.position || !rank?.total) {
    return Number.POSITIVE_INFINITY;
  }
  return rank.position;
}

function getZoneSortValue(
  zone: Awaited<ReturnType<typeof getJourneyZonesList>>["zones"][number],
  sortKey: ZoneSortKey
) {
  if (sortKey === "travel_time") {
    return zone.travel_time_minutes ?? Number.POSITIVE_INFINITY;
  }
  if (sortKey === "price") {
    return zone.price_summary?.p50_price ?? Number.POSITIVE_INFINITY;
  }
  if (sortKey === "safety") {
    return getRankValue(zone.journey_rankings?.safety);
  }
  if (sortKey === "green") {
    return getRankValue(zone.journey_rankings?.green);
  }
  return getRankValue(zone.journey_rankings?.flood);
}

function ZoneMetricChip({
  label,
  value,
  tone,
  title,
}: {
  label: string;
  value: string;
  tone: "violet" | "emerald" | "amber" | "rose" | "slate";
  title?: string;
}) {
  const className = {
    violet: "border-pastel-violet-200 bg-pastel-violet-50 text-pastel-violet-700",
    emerald: "border-emerald-200 bg-emerald-50 text-emerald-700",
    amber: "border-amber-200 bg-amber-50 text-amber-700",
    rose: "border-rose-200 bg-rose-50 text-rose-700",
    slate: "border-slate-200 bg-slate-100 text-slate-700",
  }[tone];

  return (
    <span title={title} className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${className}`}>
      <span className="font-semibold">{label}</span>
      <span>{value}</span>
    </span>
  );
}

function ZonePoiList({
  poiPoints,
  zoneFingerprint,
  isZoneSelected,
  onInteract,
}: {
  poiPoints: ZonePoiPointLike[];
  zoneFingerprint: string;
  isZoneSelected: boolean;
  onInteract: () => void;
}) {
  const activePoiCategory = useJourneyStore((state) => state.activePoiCategory);
  const selectedPoiKey = useJourneyStore((state) => state.selectedPoiKey);
  const setActivePoiCategory = useJourneyStore((state) => state.setActivePoiCategory);
  const setSelectedPoiKey = useJourneyStore((state) => state.setSelectedPoiKey);
  const poiItemRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const lastScrolledPoiKeyRef = useRef<string | null>(null);

  const countsByCategory = useMemo(() => {
    const counts = new Map<string, number>();
    for (const point of poiPoints) {
      const category = point.category || "other";
      counts.set(category, (counts.get(category) || 0) + 1);
    }
    return counts;
  }, [poiPoints]);

  const orderedPoints = useMemo(() => sortPoiPoints(poiPoints), [poiPoints]);

  const visiblePoints = useMemo(() => {
    if (activePoiCategory === "all") {
      return orderedPoints;
    }
    return orderedPoints.filter((point) => point.category === activePoiCategory);
  }, [activePoiCategory, orderedPoints]);

  const availableCategories = POI_CATEGORY_ORDER.filter((category) => (countsByCategory.get(category) || 0) > 0);

  useEffect(() => {
    if (!isZoneSelected) {
      return;
    }
    if (!selectedPoiKey) {
      lastScrolledPoiKeyRef.current = null;
      return;
    }

    const hasSelectedPoiVisible = visiblePoints.some(
      (point, index) => getZonePoiSelectionKey(point, zoneFingerprint, index) === selectedPoiKey
    );
    if (!hasSelectedPoiVisible) {
      setSelectedPoiKey(null);
    }
  }, [isZoneSelected, selectedPoiKey, setSelectedPoiKey, visiblePoints, zoneFingerprint]);

  useEffect(() => {
    if (!isZoneSelected) {
      return;
    }
    if (!selectedPoiKey) {
      lastScrolledPoiKeyRef.current = null;
      return;
    }
    if (lastScrolledPoiKeyRef.current === selectedPoiKey) {
      return;
    }
    const selectedItem = poiItemRefs.current[selectedPoiKey];
    if (!selectedItem) {
      return;
    }
    selectedItem.scrollIntoView({ block: "nearest", behavior: "smooth" });
    lastScrolledPoiKeyRef.current = selectedPoiKey;
  }, [isZoneSelected, selectedPoiKey, visiblePoints]);

  if (poiPoints.length === 0) {
    return <p className="text-xs text-slate-500">POIs detalhados ainda nao foram carregados para esta zona.</p>;
  }

  return (
    <div className="space-y-3" onClick={(event) => event.stopPropagation()}>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => {
            onInteract();
            setActivePoiCategory("all");
          }}
          className={`rounded-full border px-3 py-1 text-xs font-semibold transition-colors ${activePoiCategory === "all" ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:text-slate-900"}`}
        >
          Todos ({poiPoints.length})
        </button>
        {availableCategories.map((category) => {
          const meta = getPoiCategoryMeta(category);
          const count = countsByCategory.get(category) || 0;
          const isActive = activePoiCategory === category;
          return (
            <button
              key={category}
              type="button"
              onClick={() => {
                onInteract();
                setActivePoiCategory(category);
              }}
              className={`rounded-full border px-3 py-1 text-xs font-semibold transition-colors ${isActive ? "text-white" : "bg-white text-slate-700 hover:text-slate-900"}`}
              style={{
                borderColor: isActive ? meta.color : "#e2e8f0",
                backgroundColor: isActive ? meta.color : "#ffffff"
              }}
            >
              {meta.label} ({count})
            </button>
          );
        })}
      </div>

      <ul className="max-h-44 space-y-2 overflow-y-auto pr-1" data-testid="zone-poi-list">
        {visiblePoints.map((point, index) => {
          const meta = getPoiCategoryMeta(point.category);
          const itemKey = getZonePoiSelectionKey(point, zoneFingerprint, index);
          const isSelected = itemKey === selectedPoiKey;
          return (
            <li key={itemKey} className="rounded-xl border border-slate-100 bg-slate-50/80 px-3 py-2">
              <button
                ref={(element) => {
                  poiItemRefs.current[itemKey] = element;
                }}
                type="button"
                data-poi-key={itemKey}
                onClick={() => {
                  onInteract();
                  setSelectedPoiKey(itemKey);
                }}
                className={`w-full rounded-lg px-1 py-1 text-left transition-colors ${isSelected ? "bg-white ring-2 ring-pastel-violet-300" : "hover:bg-white/80"}`}
              >
                <div className="mb-1 flex items-center gap-2">
                  <span className="inline-flex h-2.5 w-2.5 rounded-full" style={{ backgroundColor: meta.color }} aria-hidden="true" />
                  <span className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">{meta.singularLabel}</span>
                </div>
                <p className="text-sm font-semibold text-slate-800">{point.name || "POI sem nome"}</p>
                {point.address ? <p className="text-xs text-slate-500">{point.address}</p> : null}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function ZoneCard({
  zone,
  isSelected,
  onSelect,
  onContinue,
}: {
  zone: Awaited<ReturnType<typeof getJourneyZonesList>>["zones"][number];
  isSelected: boolean;
  onSelect: () => void;
  onContinue: () => void;
}) {
  const showGreen = zone.green_vegetation_label !== null && zone.green_vegetation_label !== undefined;
  const poiPoints = zone.poi_points || [];
  const priceP50 = zone.price_summary?.p50_price ?? null;
  const priceChipValue = priceP50 != null ? formatCurrencyBr(priceP50) : "Sem base";
  const priceTooltip = priceP50 != null
    ? "Metade dos imóveis está abaixo desse valor e metade está acima, considerando o recorte padrão de imóveis para venda dentro da zona."
    : undefined;

  return (
    <div
      className={`cursor-pointer rounded-xl border bg-white p-4 shadow-sm transition-all hover:shadow-md ${isSelected ? "border-pastel-violet-400 ring-1 ring-pastel-violet-400" : "border-slate-200"}`}
      onClick={onSelect}
    >
      <div className="mb-3 flex items-start justify-between gap-3">
        <h3 className="text-sm font-semibold text-slate-800">{`Zona ${zone.fingerprint.slice(0, 8)}`}</h3>
        <div className="flex items-center gap-1.5">
          {zone.is_circle_fallback ? (
            <span className="rounded bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-700" title="Zona circular (Valhalla indisponivel)">~circulo</span>
          ) : null}
          <span className="rounded bg-slate-100 px-2 py-1 text-xs font-bold text-slate-600">Ate {zone.travel_time_minutes ?? "--"}m</span>
        </div>
      </div>

      <div className="mb-3 flex flex-wrap gap-2">
        <ZoneMetricChip label="Segurança" value={formatRank(zone.journey_rankings?.safety)} tone="emerald" />
        {showGreen ? <ZoneMetricChip label="Verde" value={formatRank(zone.journey_rankings?.green)} tone="violet" /> : null}
        <ZoneMetricChip label="Alagamento" value={formatRank(zone.journey_rankings?.flood)} tone="amber" />
        <ZoneMetricChip label="Valor mediano" value={priceChipValue} tone="rose" title={priceTooltip} />
        <ZoneMetricChip label="POIs" value={String(poiPoints.length)} tone="slate" />
      </div>

      <div className="mb-4 flex flex-wrap gap-3 text-xs text-slate-500">
        <span>{zone.walk_distance_meters ? `${Math.round(zone.walk_distance_meters)} m ate o seed` : "Sem distancia consolidada"}</span>
        <span>{poiPoints.length > 0 ? `${poiPoints.length} POIs mapeados` : zone.poi_counts ? `${Object.keys(zone.poi_counts).length} grupos de POIs` : "POIs pendentes"}</span>
        <span>{zone.price_summary?.active_listing_count ? `${zone.price_summary.active_listing_count} anúncios ativos no recorte padrão` : "Sem base de valor consolidada"}</span>
        {showGreen ? <span>{zone.green_vegetation_label}</span> : null}
      </div>

      <div className="rounded-2xl border border-slate-100 bg-slate-50/70 p-3">
        <p className="mb-3 text-xs font-bold uppercase tracking-[0.14em] text-slate-500">POIs da zona</p>
        <ZonePoiList poiPoints={poiPoints} zoneFingerprint={zone.fingerprint} isZoneSelected={isSelected} onInteract={onSelect} />
      </div>

      {isSelected ? (
        <div className="mt-4 border-t border-slate-100 pt-3 animate-[fadeIn_0.2s_ease-out]">
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onContinue();
            }}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-pastel-violet-500 px-4 py-2 text-sm font-medium text-white transition-all hover:bg-pastel-violet-600"
          >
            Procurar Imoveis nesta Zona
            <Search className="h-4 w-4" />
          </button>
        </div>
      ) : null}
    </div>
  );
}

export function Step4Compare() {
  const journeyId = useJourneyStore((state) => state.journeyId);
  const selectedZoneFingerprint = useJourneyStore((state) => state.selectedZoneFingerprint);
  const setSelectedZone = useJourneyStore((state) => state.setSelectedZone);
  const goToStep = useUIStore((state) => state.goToStep);
  const setMaxStep = useUIStore((state) => state.setMaxStep);
  const [poiBackfillJobId, setPoiBackfillJobId] = useState<string | null>(null);
  const [poiBackfillError, setPoiBackfillError] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<ZoneSortKey>("travel_time");
  const poiBackfillRequestedRef = useRef<string | null>(null);
  const query = useQuery({
    queryKey: ["journey-zones", journeyId],
    queryFn: async () => getJourneyZonesList(journeyId as string),
    enabled: Boolean(journeyId),
    refetchInterval: poiBackfillJobId ? 3000 : false
  });

  const hasLegacyPoiZones = useMemo(
    () =>
      Boolean(query.data?.zones.some((zone) => zoneNeedsPoiBackfill(zone))),
    [query.data?.zones]
  );

  const poiBackfillJobQuery = useQuery({
    queryKey: ["journey-zones-poi-backfill-job", poiBackfillJobId],
    queryFn: async () => getJob(poiBackfillJobId as string),
    enabled: Boolean(poiBackfillJobId),
    refetchInterval: (jobQuery) => {
      const state = jobQuery.state.data?.state;
      return state === "completed" || state === "failed" || state === "cancelled" ? false : 3000;
    }
  });

  useEffect(() => {
    poiBackfillRequestedRef.current = null;
    setPoiBackfillJobId(null);
    setPoiBackfillError(null);
  }, [journeyId]);

  useEffect(() => {
    if (!journeyId || !query.data || !hasLegacyPoiZones || poiBackfillJobId) {
      return;
    }
    if (poiBackfillRequestedRef.current === journeyId) {
      return;
    }

    poiBackfillRequestedRef.current = journeyId;
    setPoiBackfillError(null);

    void createZoneEnrichmentJob(journeyId)
      .then((job) => {
        setPoiBackfillJobId(job.id);
      })
      .catch((caughtError) => {
        setPoiBackfillError(apiActionHint(caughtError));
      });
  }, [hasLegacyPoiZones, journeyId, poiBackfillJobId, query.data]);

  useEffect(() => {
    if (!poiBackfillJobId) {
      return;
    }

    const state = poiBackfillJobQuery.data?.state;
    if (state === "completed") {
      setPoiBackfillJobId(null);
      setPoiBackfillError(null);
      void query.refetch();
      return;
    }

    if (state === "failed" || state === "cancelled") {
      setPoiBackfillJobId(null);
      setPoiBackfillError(poiBackfillJobQuery.data?.error_message || "A atualizacao automatica dos POIs falhou.");
    }
  }, [poiBackfillJobId, poiBackfillJobQuery.data?.error_message, poiBackfillJobQuery.data?.state, query]);

  async function handleSelect(zoneId: string, fingerprint: string) {
    setSelectedZone(zoneId, fingerprint);
    if (!journeyId) {
      return;
    }
    try {
      await updateJourney(journeyId, {
        selected_zone_id: zoneId,
        last_completed_step: 4
      });
    } catch {
      // Step remains usable even if the patch fails.
    }
  }

  const sortedZones = useMemo(() => {
    const zones = [...(query.data?.zones || [])];
    zones.sort((left, right) => {
      const leftValue = getZoneSortValue(left, sortKey);
      const rightValue = getZoneSortValue(right, sortKey);
      if (leftValue !== rightValue) {
        return leftValue - rightValue;
      }
      const leftTime = left.travel_time_minutes ?? Number.POSITIVE_INFINITY;
      const rightTime = right.travel_time_minutes ?? Number.POSITIVE_INFINITY;
      if (leftTime !== rightTime) {
        return leftTime - rightTime;
      }
      return left.fingerprint.localeCompare(right.fingerprint, "pt-BR");
    });
    return zones;
  }, [query.data?.zones, sortKey]);

  return (
    <div className="flex h-full flex-col animate-[fadeInRight_0.3s_ease-out]">
      <div className="border-b border-slate-100 p-5">
        <div className="mb-1 flex items-center justify-between">
          <h2 className="text-xl font-semibold tracking-tight text-slate-800">Zonas Encontradas</h2>
          <span className="rounded-md bg-emerald-100 px-2 py-1 text-xs font-bold text-emerald-700">Concluído</span>
        </div>
        <p className="text-sm text-slate-500">Compare as zonas pela viagem e pelos indicadores enriquecidos.</p>
      </div>

      <div className="panel-scroll flex-1 overflow-y-auto bg-slate-50/50 p-4">
        {query.isLoading ? <p className="rounded-xl bg-white p-4 text-sm text-slate-500 shadow-sm">Carregando zonas...</p> : null}
        {query.error ? <p className="mb-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">{apiActionHint(query.error)}</p> : null}
        {poiBackfillJobId ? (
          <p className="mb-3 rounded-xl border border-sky-200 bg-sky-50 p-4 text-sm text-sky-800">
            Atualizando os POIs detalhados desta jornada para preencher o mapa e os cards.
          </p>
        ) : null}
        {poiBackfillError ? <p className="mb-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">{poiBackfillError}</p> : null}
        {query.data?.zones.some((z) => z.is_circle_fallback) ? (
          <div className="mb-3 flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 animate-[fadeIn_0.3s_ease-out]">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
            <span>
              <strong>Roteamento indisponível.</strong> As zonas foram calculadas como círculos aproximados (Valhalla offline). Os limites podem diferir da isócrona real de deslocamento.
            </span>
          </div>
        ) : null}
        <div className="mb-3 flex flex-wrap gap-2 rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">
          {SORT_OPTIONS.map((option) => {
            const isActive = option.key === sortKey;
            return (
              <button
                key={option.key}
                type="button"
                onClick={() => setSortKey(option.key)}
                className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors ${isActive ? "border-pastel-violet-300 bg-pastel-violet-50 text-pastel-violet-700" : "border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:text-slate-800"}`}
              >
                {option.label}
              </button>
            );
          })}
        </div>
        <div className="space-y-3">
          {sortedZones.map((zone) => {
            const isSelected = selectedZoneFingerprint === zone.fingerprint;
            return (
              <ZoneCard
                key={zone.id}
                zone={zone}
                isSelected={isSelected}
                onSelect={() => void handleSelect(zone.id, zone.fingerprint)}
                onContinue={() => {
                  setMaxStep(5);
                  goToStep(5);
                }}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}