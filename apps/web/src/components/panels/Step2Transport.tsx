import { Bus, Clock3, Route, Train, MapIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { apiActionHint, createTransportSearchJob, getJob, getJourneyTransportPoints, updateJourney } from "../../api/client";
import type { TransportPointRead } from "../../api/schemas";
import { useJourneyStore, useUIStore } from "../../state";

function isRailTransportPoint(point: TransportPointRead): boolean {
  return point.modal_types.includes("metro") || point.modal_types.includes("train");
}

export function sanitizeTransportPoints(items: TransportPointRead[]): TransportPointRead[] {
  const deduped = new Map<string, TransportPointRead>();

  for (const point of items) {
    if (point.route_count <= 0 && !isRailTransportPoint(point)) {
      continue;
    }

    const normalizedName = (point.name ?? "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .trim()
      .toLowerCase();
    const externalId = point.external_id?.trim().toLowerCase();
    const dedupKey = externalId
      ? `${point.source}:${externalId}`
      : `${point.source}:${normalizedName}:${point.lat.toFixed(5)}:${point.lon.toFixed(5)}`;

    const current = deduped.get(dedupKey);
    if (!current) {
      deduped.set(dedupKey, point);
      continue;
    }

    const shouldReplace =
      point.route_count > current.route_count ||
      (point.route_count === current.route_count && point.walk_time_sec < current.walk_time_sec) ||
      (point.route_count === current.route_count &&
        point.walk_time_sec === current.walk_time_sec &&
        point.walk_distance_m < current.walk_distance_m);

    if (shouldReplace) {
      deduped.set(dedupKey, point);
    }
  }

  return Array.from(deduped.values());
}

export function Step2Transport() {
  const journeyId = useJourneyStore((state) => state.journeyId);
  const config = useJourneyStore((state) => state.config);
  const selectedTransportId = useJourneyStore((state) => state.selectedTransportId);
  const transportJobId = useJourneyStore((state) => state.transportJobId);
  const setSelectedTransportId = useJourneyStore((state) => state.setSelectedTransportId);
  const setJobIds = useJourneyStore((state) => state.setJobIds);
  const goToStep = useUIStore((state) => state.goToStep);
  const setMaxStep = useUIStore((state) => state.setMaxStep);
  const [points, setPoints] = useState<TransportPointRead[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!journeyId) {
      setError("Jornada ausente. Volte para a etapa de configuração.");
      setIsLoading(false);
      return;
    }
    const activeJourneyId = journeyId;

    let cancelled = false;
    let intervalId: number | undefined;

    async function loadPoints() {
      try {
        const items = await getJourneyTransportPoints(activeJourneyId);
        const sanitizedItems = sanitizeTransportPoints(items);
        if (!cancelled) {
          setPoints(sanitizedItems);
          if (selectedTransportId && !sanitizedItems.some((item) => item.id === selectedTransportId)) {
            setSelectedTransportId(null);
          }
          setIsLoading(false);
          if (sanitizedItems.length === 0) {
            setError("Nenhum ponto elegível retornou para a jornada atual.");
          } else {
            setError(null);
          }
        }
      } catch (caughtError) {
        if (!cancelled) {
          setError(apiActionHint(caughtError));
          setIsLoading(false);
        }
      }
    }

    async function startJob() {
      try {
        let jobId = transportJobId;
        if (!jobId) {
          const job = await createTransportSearchJob(activeJourneyId);
          jobId = job.id;
          if (!cancelled) {
            setJobIds({ transportJobId: job.id });
          }
        }

        const poll = async () => {
          if (!jobId || cancelled) {
            return;
          }
          try {
            const job = await getJob(jobId);
            if (job.state === "completed") {
              window.clearInterval(intervalId);
              await loadPoints();
              return;
            }
            if (job.state === "failed" || job.state === "cancelled") {
              window.clearInterval(intervalId);
              if (!cancelled) {
                setError(job.error_message || "A busca de transporte falhou.");
                setIsLoading(false);
              }
            }
          } catch (caughtError) {
            window.clearInterval(intervalId);
            if (!cancelled) {
              setError(apiActionHint(caughtError));
              setIsLoading(false);
            }
          }
        };

        await poll();
        if (!cancelled) {
          intervalId = window.setInterval(poll, 3000);
        }
      } catch (caughtError) {
        if (!cancelled) {
          setError(apiActionHint(caughtError));
          setIsLoading(false);
        }
      }
    }

    void startJob();

    return () => {
      cancelled = true;
      if (intervalId) {
        window.clearInterval(intervalId);
      }
    };
  }, [journeyId, selectedTransportId, setJobIds, setSelectedTransportId, transportJobId]);

  async function handleAdvance() {
    if (!journeyId || !selectedTransportId) {
      return;
    }
    try {
      await updateJourney(journeyId, {
        selected_transport_point_id: selectedTransportId,
        last_completed_step: 2
      });
      setMaxStep(3);
      goToStep(3);
    } catch (caughtError) {
      setError(apiActionHint(caughtError));
    }
  }

  return (
    <div className="flex h-full flex-col animate-[fadeInRight_0.3s_ease-out]">
      <div className="border-b border-slate-100 p-5">
        <h2 className="text-xl font-semibold tracking-tight text-slate-800">Transporte</h2>
        <p className="text-sm text-slate-500">Selecione o ponto de transporte usado como seed da geração de zonas.</p>
        {config.modal === "transit" && config.publicTransportMode === "bus" ? <p className="mt-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">No modo Ônibus, a lista continua mostrando os pontos urbanos do entorno. A geração de zonas ainda depende da cobertura GTFS perto do seed escolhido.</p> : null}
      </div>

      <div className="panel-scroll flex-1 overflow-y-auto bg-slate-50/50 p-4">
        {isLoading ? <p className="rounded-xl bg-white p-4 text-sm text-slate-500 shadow-sm">Buscando pontos elegíveis...</p> : null}
        {error ? <p className="mb-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">{error}</p> : null}
        <div className="space-y-3">
          {points.map((point) => {
            const isSelected = selectedTransportId === point.id;
            const isRail = isRailTransportPoint(point);
            return (
              <button
                key={point.id}
                type="button"
                onClick={() => setSelectedTransportId(point.id)}
                className={`w-full rounded-xl border-2 bg-white p-4 text-left transition-all ${isSelected ? "border-pastel-violet-400 bg-pastel-violet-50" : "border-transparent shadow-sm hover:border-slate-200 hover:shadow-md"}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-start gap-3">
                    <div className={`rounded-lg p-2 ${isRail ? "bg-pastel-violet-100 text-pastel-violet-600" : "bg-slate-100 text-slate-600"}`}>
                      {isRail ? <Train className="h-5 w-5" /> : <Bus className="h-5 w-5" />}
                    </div>
                    <div className="min-w-0">
                      <h3 className="text-sm font-medium text-slate-800">{point.name || "Ponto sem nome"}</h3>
                      <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-slate-500">
                        <span className="inline-flex items-center gap-1"><Route className="h-3.5 w-3.5" /> {Math.round(point.walk_distance_m)} m</span>
                        <span className="inline-flex items-center gap-1"><Clock3 className="h-3.5 w-3.5" /> {Math.max(1, Math.round(point.walk_time_sec / 60))} min a pé</span>
                        <span>{point.route_count} linhas</span>
                      </div>
                    </div>
                  </div>
                  <div className="flex h-5 w-5 items-center justify-center rounded-full border border-slate-300">
                    {isSelected ? <div className="h-3 w-3 rounded-full bg-pastel-violet-500" /> : null}
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      <div className="border-t border-slate-100 bg-white p-5">
        <button type="button" onClick={handleAdvance} disabled={!selectedTransportId} className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-slate-900 px-4 py-3 text-sm font-medium text-white transition-all hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400">
          Confirmar ponto seed
          <MapIcon className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}