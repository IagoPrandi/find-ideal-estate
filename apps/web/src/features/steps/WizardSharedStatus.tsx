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
      <section className="mt-4 rounded-xl border border-slate-200 bg-slate-50/80 p-4 text-sm shadow-sm">
        <h3 className="text-sm font-semibold text-slate-800">Estado do fluxo</h3>
        <p className="mt-2 text-sm text-slate-600">{statusMessage}</p>
        <p className="mt-2 text-xs text-slate-500">
          Zonas: {zonesState} · {zonesStateMessage}
        </p>
        <p className="mt-1 text-xs text-slate-500">Seleção: {zoneSelectionMessage}</p>
        {runId ? (
          <p className="mt-2 font-mono text-[11px] text-slate-500">run_id: {runId}</p>
        ) : null}
        {runStatus ? (
          <p className="mt-1 text-xs text-slate-500">
            Backend: {runStatus.stage} · {runStatus.state}
          </p>
        ) : null}
      </section>

      <section className="mt-4 rounded-xl border border-slate-200 bg-white p-4 text-sm shadow-sm">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-slate-800">Execução</h3>
          <span className="text-[11px] text-slate-500">{executionProgress.elapsedSec}s</span>
        </div>
        <p className="mt-1 text-xs text-slate-500">{executionProgress.label}</p>
        <div className="mt-2 h-2 w-full rounded bg-slate-100">
          <div
            className="h-2 rounded bg-pastel-violet-500 transition-all duration-300"
            style={{ width: `${Math.max(4, Math.min(100, executionProgress.percent || 0))}%` }}
          />
        </div>
        <p className="mt-2 text-[11px] text-slate-500">Etapa atual (API): {runStatus?.stage || "—"}</p>
      </section>
    </>
  );
}
