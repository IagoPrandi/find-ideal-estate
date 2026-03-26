import type { RunStatusResponse } from "../../api/schemas";

export type WizardSharedStatusProps = {
  statusMessage: string;
  zonesState: string;
  zonesStateMessage: string;
  zoneSelectionMessage: string;
  runId: string | null;
  runStatus: RunStatusResponse["status"] | null;
  executionProgress: {
    elapsedSec: number;
    label: string;
    percent: number;
  };
};

export function WizardSharedStatus(props: WizardSharedStatusProps) {
  const {
    statusMessage,
    zonesState,
    zonesStateMessage,
    zoneSelectionMessage,
    runId,
    runStatus,
    executionProgress
  } = props;

  return (
    <>
      <section className="gem-panel-section text-sm">
        <div className="gem-panel-header">
          <p className="gem-eyebrow">Progresso real</p>
          <h3 className="gem-title mt-1">Estado do fluxo</h3>
          <p className="gem-subtitle mt-1">Sem spinner cego: cada transição de backend aparece em texto e barra de execução.</p>
        </div>
        <div className="gem-panel-body space-y-2.5">
          <p className="text-sm text-slate-600">{statusMessage}</p>
          <div className="flex flex-wrap gap-2 text-[11px]">
            <span className="gem-chip">Zonas: {zonesState}</span>
            <span className="gem-chip">Seleção: {zoneSelectionMessage}</span>
            {runStatus ? <span className="gem-chip">Backend: {runStatus.stage}</span> : null}
          </div>
          <p className="text-xs text-slate-500">{zonesStateMessage}</p>
          {runId ? <p className="font-mono text-[11px] text-slate-500">run_id: {runId}</p> : null}
        </div>
      </section>

      <section className="gem-panel-section text-sm">
        <div className="gem-panel-body">
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-sm font-semibold text-slate-800">Execução</h3>
            <span className="text-[11px] text-slate-500">{executionProgress.elapsedSec}s</span>
          </div>
          <p className="mt-1 text-xs text-slate-500">{executionProgress.label}</p>
          <div className="mt-2 h-2 w-full rounded-full bg-slate-100 overflow-hidden">
            <div
              className="h-2 rounded-full bg-pastel-violet-500 transition-all duration-300"
              style={{ width: `${Math.max(4, Math.min(100, executionProgress.percent || 0))}%` }}
            />
          </div>
          <p className="mt-2 text-[11px] text-slate-500">Etapa atual (API): {runStatus?.stage || "—"}</p>
        </div>
      </section>
    </>
  );
}
