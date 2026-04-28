import { LoaderCircle, Lock, MapIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { apiActionHint, createZoneEnrichmentJob, createZoneGenerationJob, getJob, updateJourney } from "../../api/client";
import { useEntitlements } from "../../features/auth/useEntitlements";
import { useJourneyStore, useUIStore } from "../../state";

type StageMode = "idle" | "generation" | "enrichment" | "finalizing";

const JOB_POLL_INTERVAL_MS = 1000;
const FINALIZING_TRANSITION_DELAY_MS = 150;

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
  const directAutoStartedRef = useRef(false);
  const isWalkingMode = config.modal === "walk";
  const isDrivingMode = config.modal === "car";
  const isDirectIsochroneMode = isWalkingMode || isDrivingMode;

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
      zone_radius_meters: isDirectIsochroneMode ? null : config.zoneRadiusMeters,
      zone_radius_m: isDirectIsochroneMode ? null : config.zoneRadiusMeters,
      transport_search_radius_m: isDirectIsochroneMode ? null : config.transportSearchRadiusMeters,
      transport_search_radius_meters: isDirectIsochroneMode ? null : config.transportSearchRadiusMeters,
      enrichments: {
        ...config.enrichments,
        green_vegetation_level: config.greenVegetationLevel
      }
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
      }, JOB_POLL_INTERVAL_MS);
    });
  }

  async function runGenerationPipeline() {
    if (!journeyId) {
      setError("Jornada ausente. Volte para a etapa anterior.");
      return;
    }

    const inputSnapshot = buildInputSnapshot();
    if (!inputSnapshot) {
      setError("Selecione um ponto principal no mapa antes de gerar a área acessível.");
      return;
    }

    if (!isDirectIsochroneMode && !selectedTransportId) {
      setError("Selecione um ponto de transporte na etapa anterior antes de gerar as zonas.");
      return;
    }

    clearPolling();
    setError(null);

    try {
      await updateJourney(journeyId, {
        input_snapshot: inputSnapshot,
        selected_transport_point_id: isDirectIsochroneMode ? null : selectedTransportId,
        last_completed_step: isDirectIsochroneMode ? 1 : 2
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
      }, FINALIZING_TRANSITION_DELAY_MS);
    } catch (caughtError) {
      clearPolling();
      setStageMode("idle");
      setProgress(0);
      setJobIds({ zoneGenerationJobId: null, zoneEnrichmentJobId: null });
      setError(apiActionHint(caughtError));
    }
  }

  useEffect(() => {
    directAutoStartedRef.current = false;
  }, [isDirectIsochroneMode, journeyId]);

  useEffect(() => {
    if (!isDirectIsochroneMode || !journeyId || stageMode !== "idle" || directAutoStartedRef.current) {
      return;
    }
    directAutoStartedRef.current = true;
    void runGenerationPipeline();
  }, [isDirectIsochroneMode, journeyId, stageMode]);

  const { can_customize_max_time, can_customize_radius, max_transit_minutes_cap, max_zone_radius_m_cap } = useEntitlements();
  const isBusy = stageMode !== "idle";
  const stageLabel = stageMode === "generation" ? (isDirectIsochroneMode ? "Gerando área acessível" : "Gerando zonas") : stageMode === "enrichment" ? "Enriquecendo camadas" : "Finalizando";

  return (
    <div className="flex h-full flex-col animate-[fadeInRight_0.3s_ease-out]">
      <div className="border-b border-slate-100 p-5">
        <h2 className="text-xl font-semibold tracking-tight text-slate-800">{isDirectIsochroneMode ? "Gerar área acessível" : "Gerar zonas"}</h2>
        <p className="text-sm text-slate-500">{isWalkingMode ? "No modo a pé, a zona é uma única área acessível gerada a partir do ponto principal selecionado." : isDrivingMode ? "No modo carro, a zona é uma única área acessível gerada a partir do ponto principal selecionado." : "Ajuste os parâmetros da busca e gere as zonas a partir do ponto de transporte escolhido."}</p>
      </div>

      <div className="panel-scroll flex-1 overflow-y-auto bg-slate-50/50 p-4">
        {isBusy ? (
          <div className="flex h-full flex-col items-center justify-center rounded-3xl border border-slate-200 bg-white px-6 py-10 text-center shadow-sm">
            <div className="relative mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-pastel-violet-50 text-pastel-violet-500">
              <MapIcon className="h-8 w-8" />
              <div className="absolute inset-0 rounded-2xl border-4 border-pastel-violet-200 opacity-20 animate-ping" />
            </div>
            <h3 className="mb-2 text-xl font-semibold text-slate-800">{stageMode === "finalizing" ? "Concluindo preparação" : "Processando zonas"}</h3>
            <p className="mb-8 max-w-xs text-sm text-slate-500">{stageMode === "generation" ? (isWalkingMode ? "Gerando a área acessível a pé a partir do ponto principal selecionado." : isDrivingMode ? "Gerando a área acessível de carro a partir do ponto principal selecionado." : "Executando a geração das zonas candidatas a partir do ponto de transporte selecionado.") : stageMode === "enrichment" ? "Calculando camadas urbanas e consolidando a comparação da etapa seguinte." : "Salvando o estado final da jornada para abrir a comparação."}</p>

            <div className="w-full max-w-xs space-y-2">
              <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
                <div className="h-full bg-pastel-violet-500 transition-all duration-300 ease-out" style={{ width: `${progress}%` }} />
              </div>
              <div className="flex justify-between text-xs font-medium text-slate-400">
                <span>{stageLabel}</span>
                <span>{Math.round(progress)}%</span>
              </div>
            </div>

            <button type="button" onClick={() => goToStep(isDirectIsochroneMode ? 1 : 2)} className="mt-8 text-sm font-medium text-slate-400 transition-colors hover:text-rose-600">
              {isDirectIsochroneMode ? "Voltar para a configuração" : "Voltar para o ponto de transporte"}
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            {!isDirectIsochroneMode && !selectedTransportId ? <p className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">Escolha um ponto de transporte na etapa anterior antes de gerar as zonas.</p> : null}
            {isWalkingMode ? <p className="rounded-2xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-800">A busca a pé não depende de um ponto de transporte. O sistema vai gerar uma única área acessível usando o tempo de caminhada definido na configuração.</p> : null}
            {isDrivingMode ? <p className="rounded-2xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-800">A busca de carro não depende de um ponto de transporte. O sistema vai gerar uma única área acessível usando o tempo de carro definido na configuração.</p> : null}
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

              {isDirectIsochroneMode ? (
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">{isWalkingMode ? "Tempo de caminhada" : "Tempo de carro"}</p>
                    <p className="mt-2 text-2xl font-semibold text-slate-800">{config.time} min</p>
                    <p className="mt-1 text-xs text-slate-500">Usado para gerar a mancha única da área acessível.</p>
                  </div>
                  <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Ponto de partida</p>
                    <p className="mt-2 text-sm font-semibold text-slate-800">{primaryReferenceLabel || pickedCoord?.label || "Ponto selecionado no mapa"}</p>
                    <p className="mt-1 text-xs text-slate-500">A área acessível sai diretamente da referência principal, sem etapa de transporte.</p>
                  </div>
                </div>
              ) : (
                <div className="grid gap-5 md:grid-cols-2">
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1.5">
                        <label className="text-sm font-medium text-slate-700">Tempo máximo de viagem</label>
                        {!can_customize_max_time && (
                          <span title="Disponível a partir do plano Básico" className="inline-flex cursor-help items-center text-slate-400">
                            <Lock className="h-3.5 w-3.5" />
                          </span>
                        )}
                      </div>
                      <span className="text-sm font-bold text-pastel-violet-600">{config.time} min</span>
                    </div>
                    <input
                      type="range"
                      min="10"
                      max={max_transit_minutes_cap ?? 90}
                      step="5"
                      value={config.time}
                      disabled={!can_customize_max_time}
                      onChange={can_customize_max_time ? (event) => setConfig({ time: Math.min(Number(event.target.value), max_transit_minutes_cap ?? 90) }) : undefined}
                      className={`w-full accent-pastel-violet-500 ${!can_customize_max_time ? "cursor-not-allowed opacity-50" : ""}`}
                    />
                    {!can_customize_max_time
                      ? <p className="text-xs text-slate-400">Disponível a partir do plano Básico.</p>
                      : max_transit_minutes_cap !== null
                        ? <p className="text-xs text-slate-400">Máximo de {max_transit_minutes_cap} min no seu plano.</p>
                        : <p className="text-xs text-slate-400">Limita o alcance temporal usado para montar as zonas candidatas.</p>
                    }
                  </div>

                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1.5">
                        <label className="text-sm font-medium text-slate-700">Raio das zonas</label>
                        {!can_customize_radius && (
                          <span title="Disponível a partir do plano Básico" className="inline-flex cursor-help items-center text-slate-400">
                            <Lock className="h-3.5 w-3.5" />
                          </span>
                        )}
                      </div>
                      <span className="text-sm font-bold text-pastel-violet-600">{config.zoneRadiusMeters} m</span>
                    </div>
                    <input
                      type="range"
                      min={max_zone_radius_m_cap !== null ? Math.min(300, max_zone_radius_m_cap) : 400}
                      max={max_zone_radius_m_cap ?? 2500}
                      step="100"
                      value={config.zoneRadiusMeters}
                      disabled={!can_customize_radius}
                      onChange={can_customize_radius ? (event) => setConfig({ zoneRadiusMeters: Math.min(Number(event.target.value), max_zone_radius_m_cap ?? 2500) }) : undefined}
                      className={`w-full accent-pastel-violet-500 ${!can_customize_radius ? "cursor-not-allowed opacity-50" : ""}`}
                    />
                    {!can_customize_radius
                      ? <p className="text-xs text-slate-400">Disponível a partir do plano Básico.</p>
                      : max_zone_radius_m_cap !== null
                        ? <p className="text-xs text-slate-400">Máximo de {max_zone_radius_m_cap} m no seu plano.</p>
                        : <p className="text-xs text-slate-400">Define o raio-base usado para consolidar a zona ao redor do ponto de transporte selecionado.</p>
                    }
                  </div>
                </div>
              )}
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
          disabled={(!isDirectIsochroneMode && !selectedTransportId) || (isDirectIsochroneMode && !pickedCoord) || isBusy}
          className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-slate-900 px-4 py-3 text-sm font-medium text-white transition-all hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
        >
          {isBusy ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <MapIcon className="h-4 w-4" />}
          {zoneGenerationJobId || zoneEnrichmentJobId ? "Retomar geração" : isWalkingMode ? "Gerar área acessível" : "Gerar zonas"}
        </button>
      </div>
    </div>
  );
}