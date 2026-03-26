import { AlertTriangle, Search } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { apiActionHint, getJourneyZonesList, updateJourney } from "../../api/client";
import { Badge } from "../shared";
import { useJourneyStore, useUIStore } from "../../state";

type BackendBadge = {
  value?: number;
  percentile?: number;
  tier?: string;
};

function tierToLevel(tier: string | undefined): "best" | "above" | "neutral" | "below" {
  if (tier === "excellent") {
    return "best";
  }
  if (tier === "good") {
    return "above";
  }
  if (tier === "poor") {
    return "below";
  }
  return "neutral";
}

function getBadgeValue(value: BackendBadge | undefined) {
  return tierToLevel(value?.tier);
}

export function Step4Compare() {
  const journeyId = useJourneyStore((state) => state.journeyId);
  const selectedZoneFingerprint = useJourneyStore((state) => state.selectedZoneFingerprint);
  const setSelectedZone = useJourneyStore((state) => state.setSelectedZone);
  const goToStep = useUIStore((state) => state.goToStep);
  const setMaxStep = useUIStore((state) => state.setMaxStep);
  const query = useQuery({
    queryKey: ["journey-zones", journeyId],
    queryFn: async () => getJourneyZonesList(journeyId as string),
    enabled: Boolean(journeyId)
  });

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
        {query.data?.zones.some((z) => z.is_circle_fallback) ? (
          <div className="mb-3 flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 animate-[fadeIn_0.3s_ease-out]">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
            <span>
              <strong>Roteamento indisponível.</strong> As zonas foram calculadas como círculos aproximados (Valhalla offline). Os limites podem diferir da isócrona real de deslocamento.
            </span>
          </div>
        ) : null}
        <div className="space-y-3">
          {query.data?.zones.map((zone) => {
            const isSelected = selectedZoneFingerprint === zone.fingerprint;
            const badges = (zone.badges || {}) as Record<string, BackendBadge>;
            return (
              <div
                key={zone.id}
                className={`cursor-pointer rounded-xl border bg-white p-4 shadow-sm transition-all hover:shadow-md ${isSelected ? "border-pastel-violet-400 ring-1 ring-pastel-violet-400" : "border-slate-200"}`}
                onClick={() => void handleSelect(zone.id, zone.fingerprint)}
              >
                <div className="mb-3 flex items-start justify-between gap-3">
                  <h3 className="text-sm font-semibold text-slate-800">{`Zona ${zone.fingerprint.slice(0, 8)}`}</h3>
                  <div className="flex items-center gap-1.5">
                    {zone.is_circle_fallback ? (
                      <span className="rounded bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-700" title="Zona circular (Valhalla indisponível)">~círculo</span>
                    ) : null}
                    <span className="rounded bg-slate-100 px-2 py-1 text-xs font-bold text-slate-600">Até {zone.travel_time_minutes ?? "--"}m</span>
                  </div>
                </div>

                <div className="mb-3 flex flex-wrap gap-2">
                  <Badge type="safety" value={getBadgeValue(badges.safety_badge)} />
                  <Badge type="green" value={getBadgeValue(badges.green_badge)} />
                  <Badge type="flood" value={getBadgeValue(badges.flood_badge)} />
                  <Badge type="pois" value={getBadgeValue(badges.poi_badge)} />
                </div>

                <div className="flex flex-wrap gap-3 text-xs text-slate-500">
                  <span>{zone.walk_distance_meters ? `${Math.round(zone.walk_distance_meters)} m até o seed` : "Sem distância consolidada"}</span>
                  <span>{zone.poi_counts ? `${Object.keys(zone.poi_counts).length} grupos de POIs` : "POIs pendentes"}</span>
                </div>

                {isSelected ? (
                  <div className="mt-4 border-t border-slate-100 pt-3 animate-[fadeIn_0.2s_ease-out]">
                    <button
                      type="button"
                      onClick={() => {
                        setMaxStep(5);
                        goToStep(5);
                      }}
                      className="flex w-full items-center justify-center gap-2 rounded-lg bg-pastel-violet-500 px-4 py-2 text-sm font-medium text-white transition-all hover:bg-pastel-violet-600"
                    >
                      Procurar Imóveis nesta Zona
                      <Search className="h-4 w-4" />
                    </button>
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}