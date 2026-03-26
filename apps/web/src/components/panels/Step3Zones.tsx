import { LoaderCircle, MapIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { apiActionHint, createZoneEnrichmentJob, createZoneGenerationJob, getJob, updateJourney } from "../../api/client";
import { useJourneyStore, useUIStore } from "../../state";

type StageMode = "idle" | "generation" | "enrichment" | "finalizing";

export function Step3Zones() {
  const journeyId = useJourneyStore((state) => state.journeyId);
  const config = useJourneyStore((state) => state.config);
  const pickedCoord = useJourneyStore((state) => state.pickedCoord);
  const primaryReferenceLabel = useJourneyStore((state) => state.primaryReferenceLabel);
  const selectedTransportId = useJourneyStore((state) => state.selectedTransportId);
  const zoneGenerationJobId = useJourneyStore((state) => state.zoneGenerationJobId);
  const zoneEnrichmentJobId = useJourneyStore((state) => state.zoneEnrichmentJobId);
  const setConfig = useJourneyStore((state) => state.setConfig);
  const setJobIds = useJourneyStore((state) => state.setJobIds);
  const goToStep = useUIStore((state) => state.goToStep);
  const setMaxStep = useUIStore((state) => state.setMaxStep);
  const [progress, setProgress] = useState(0);
  const [stageMode, setStageMode] = useState<StageMode>("idle");
  const [error, setError] = useState<string | null>(null);
  const generationIntervalRef = useRef<number | undefined>(undefined);
  const enrichmentIntervalRef = useRef<number | undefined>(undefined);
  const cancelledRef = useRef(false);

  useEffect(() => {
    cancelledRef.current = false;

    return () => {
      cancelledRef.current = true;
      if (generationIntervalRef.current) {
        window.clearInterval(generationIntervalRef.current);
      }
      if (enrichmentIntervalRef.current) {
        window.clearInterval(enrichmentIntervalRef.current);
      }
    };
  }, []);

  function clearPolling() {
    if (generationIntervalRef.current) {
      window.clearInterval(generationIntervalRef.current);
      generationIntervalRef.current = undefined;
    }
    if (enrichmentIntervalRef.current) {
      window.clearInterval(enrichmentIntervalRef.current);
      enrichmentIntervalRef.current = undefined;
    }
  }

  function buildInputSnapshot() {
    if (!pickedCoord) {
      return null;
    }

    return {
      reference_point: {
        lat: pickedCoord.lat,
        lon: pickedCoord.lon,
        label: primaryReferenceLabel || pickedCoord.label || "Ponto selecionado no mapa"
      },
      search_type: config.type,
      transport_mode: config.modal,
      public_transport_mode: config.modal === "transit" ? config.publicTransportMode : null,
      max_travel_minutes: config.time,
      max_travel_time_min: config.time,
      zone_radius_meters: config.zoneRadiusMeters,
      zone_radius_m: config.zoneRadiusMeters,
      transport_search_radius_m: config.transportSearchRadiusMeters,
      enrichments: { ...config.enrichments }
    };
  }

  function pollJobUntilTerminal(
    jobId: string,
    intervalRef: React.MutableRefObject<number | undefined>,
    onProgress: (progressValue: number) => void,
    fallbackError: string
  ): Promise<void> {
    return new Promise((resolve, reject) => {
      const tick = async () => {
        if (cancelledRef.current) {
          if (intervalRef.current) {
            window.clearInterval(intervalRef.current);
            intervalRef.current = undefined;
          }
          resolve();
          return;
        }

        try {
          const job = await getJob(jobId);
          if (job.state === "completed") {
            if (intervalRef.current) {
              window.clearInterval(intervalRef.current);
              intervalRef.current = undefined;
            }
            resolve();
            return;
          }

          if (job.state === "failed" || job.state === "cancelled") {
            if (intervalRef.current) {
              window.clearInterval(intervalRef.current);
              intervalRef.current = undefined;
            }
            reject(new Error(job.error_message || fallbackError));
            return;
          }

          onProgress(job.progress_percent || 0);
        } catch (caughtError) {
          if (intervalRef.current) {
            window.clearInterval(intervalRef.current);
            intervalRef.current = undefined;
          }
          reject(caughtError);
        }
      };

      void tick();
      intervalRef.current = window.setInterval(() => {
        void tick();
      }, 3000);
    });
  }

  async function runGenerationPipeline() {
    if (!journeyId) {
      setError("Jornada ausente. Volte para a etapa anterior.");
      return;
    }

    const inputSnapshot = buildInputSnapshot();
    if (!inputSnapshot || !selectedTransportId) {
      setError("Selecione um ponto seed na etapa anterior antes de gerar as zonas.");
      return;
    }

    clearPolling();
    setError(null);

    try {
      await updateJourney(journeyId, {
        input_snapshot: inputSnapshot,
        selected_transport_point_id: selectedTransportId,
        last_completed_step: 2
      });

      setStageMode("generation");
      setProgress(4);

      let generationJobId = zoneGenerationJobId;
      if (!generationJobId) {
        const job = await createZoneGenerationJob(journeyId);
        generationJobId = job.id;
        if (!cancelledRef.current) {
          setJobIds({ zoneGenerationJobId: job.id, zoneEnrichmentJobId: null });
        }
      }

      await pollJobUntilTerminal(
        generationJobId,
        generationIntervalRef,
        (progressValue) => {
          setStageMode("generation");
          setProgress(Math.max(8, Math.round(progressValue / 2)));
        },
        "A geração das zonas falhou."
      );

      if (cancelledRef.current) {
        return;
      }

      setStageMode("enrichment");
      setProgress(52);

      let enrichmentJobId = zoneEnrichmentJobId;
      if (!enrichmentJobId) {
        const job = await createZoneEnrichmentJob(journeyId);
        enrichmentJobId = job.id;
        if (!cancelledRef.current) {
          setJobIds({ zoneEnrichmentJobId: job.id });
        }
      }

      await pollJobUntilTerminal(
        enrichmentJobId,
        enrichmentIntervalRef,
        (progressValue) => {
          setStageMode("enrichment");
          setProgress(Math.max(52, 50 + Math.round(progressValue / 2)));
        },
        "O enriquecimento das zonas falhou."
      );

      if (cancelledRef.current) {
        return;
      }

      setStageMode("finalizing");
      setProgress(100);
      await updateJourney(journeyId, { last_completed_step: 3 });
      setMaxStep(4);
      setJobIds({ zoneGenerationJobId: null, zoneEnrichmentJobId: null });
      window.setTimeout(() => {
        if (!cancelledRef.current) {
          goToStep(4);
        }
      }, 400);
    } catch (caughtError) {
      clearPolling();
      setStageMode("idle");
      setProgress(0);
      setJobIds({ zoneGenerationJobId: null, zoneEnrichmentJobId: null });
      setError(caughtError instanceof Error ? caughtError.message : apiActionHint(caughtError));
    }
  }

  const isBusy = stageMode !== "idle";
  const stageLabel = stageMode === "generation" ? "Gerando zonas" : stageMode === "enrichment" ? "Enriquecendo camadas" : "Finalizando";

  return (
    <div className="flex h-full flex-col animate-[fadeInRight_0.3s_ease-out]">
      <div className="border-b border-slate-100 p-5">
        <h2 className="text-xl font-semibold tracking-tight text-slate-800">Gerar zonas</h2>
        <p className="text-sm text-slate-500">Ajuste os parâmetros da busca e gere as zonas a partir do ponto seed escolhido.</p>
      </div>

      <div className="panel-scroll flex-1 overflow-y-auto bg-slate-50/50 p-4">
        {isBusy ? (
          <div className="flex h-full flex-col items-center justify-center rounded-3xl border border-slate-200 bg-white px-6 py-10 text-center shadow-sm">
            <div className="relative mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-pastel-violet-50 text-pastel-violet-500">
              <MapIcon className="h-8 w-8" />
              <div className="absolute inset-0 rounded-2xl border-4 border-pastel-violet-200 opacity-20 animate-ping" />
            </div>
            <h3 className="mb-2 text-xl font-semibold text-slate-800">{stageMode === "finalizing" ? "Concluindo preparação" : "Processando zonas"}</h3>
            <p className="mb-8 max-w-xs text-sm text-slate-500">{stageMode === "generation" ? "Executando a geração das zonas candidatas a partir do seed selecionado." : stageMode === "enrichment" ? "Calculando camadas urbanas e consolidando comparações da etapa seguinte." : "Salvando o estado final da jornada para abrir a comparação."}</p>

            <div className="w-full max-w-xs space-y-2">
              <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
                <div className="h-full bg-pastel-violet-500 transition-all duration-300 ease-out" style={{ width: `${progress}%` }} />
              </div>
              <div className="flex justify-between text-xs font-medium text-slate-400">
                <span>{stageLabel}</span>
                <span>{Math.round(progress)}%</span>
              </div>
            </div>

            <button type="button" onClick={() => goToStep(2)} className="mt-8 text-sm font-medium text-slate-400 transition-colors hover:text-rose-600">
              Voltar para o seed
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            {!selectedTransportId ? <p className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">Escolha um ponto seed na etapa de transporte antes de gerar as zonas.</p> : null}
            {error ? <p className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p> : null}

            <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="mb-5 flex items-start gap-3">
                <div className="rounded-2xl bg-pastel-violet-50 p-3 text-pastel-violet-500">
                  <MapIcon className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-slate-800">Parâmetros da geração</h3>
                  <p className="text-sm text-slate-500">Esses valores alimentam a geração de zonas e o processamento comparativo da próxima etapa.</p>
                </div>
              </div>

              <div className="grid gap-5 md:grid-cols-2">
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <label className="text-sm font-medium text-slate-700">Tempo máximo de viagem</label>
                    <span className="text-sm font-bold text-pastel-violet-600">{config.time} min</span>
                  </div>
                  <input
                    type="range"
                    min="10"
                    max="90"
                    step="5"
                    value={config.time}
                    onChange={(event) => setConfig({ time: Number(event.target.value) })}
                    className="w-full accent-pastel-violet-500"
                  />
                  <p className="text-xs text-slate-400">Limita o alcance temporal usado para montar as zonas candidatas.</p>
                </div>

                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <label className="text-sm font-medium text-slate-700">Raio das zonas</label>
                    <span className="text-sm font-bold text-pastel-violet-600">{config.zoneRadiusMeters} m</span>
                  </div>
                  <input
                    type="range"
                    min="400"
                    max="2500"
                    step="100"
                    value={config.zoneRadiusMeters}
                    onChange={(event) => setConfig({ zoneRadiusMeters: Number(event.target.value) })}
                    className="w-full accent-pastel-violet-500"
                  />
                  <p className="text-xs text-slate-400">Define o raio-base usado para consolidar a zona ao redor do seed selecionado.</p>
                </div>
              </div>
            </section>
          </div>
        )}
      </div>

      <div className="border-t border-slate-100 bg-white p-5">
        <button
          type="button"
          onClick={() => {
            void runGenerationPipeline();
          }}
          disabled={!selectedTransportId || isBusy}
          className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-slate-900 px-4 py-3 text-sm font-medium text-white transition-all hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
        >
          {isBusy ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <MapIcon className="h-4 w-4" />}
          {zoneGenerationJobId || zoneEnrichmentJobId ? "Retomar geração" : "Gerar zonas"}
        </button>
      </div>
    </div>
  );
}