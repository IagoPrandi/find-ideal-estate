export type ExecutionStageKey = "zones" | "selectZone" | "detailZone" | "zoneListings" | "finalize";

export type ExecutionStageEntry = {
  status: "idle" | "running" | "done" | "error";
  elapsedSec: number;
  etaSec: number;
  durationSec: number | null;
};

export type ExecutionStagesMap = Record<ExecutionStageKey, ExecutionStageEntry>;

export const EXECUTION_STAGE_META: Record<ExecutionStageKey, { label: string; expectedSec: number }> = {
  zones: { label: "Gerar zonas", expectedSec: 180 },
  selectZone: { label: "Selecionar zona", expectedSec: 8 },
  detailZone: { label: "Detalhar zona", expectedSec: 60 },
  zoneListings: { label: "Buscar imóveis", expectedSec: 180 },
  finalize: { label: "Finalizar", expectedSec: 90 }
};

export const EXECUTION_STAGE_ORDER: ExecutionStageKey[] = [
  "zones",
  "selectZone",
  "detailZone",
  "zoneListings",
  "finalize"
];

export function createInitialExecutionStages(): ExecutionStagesMap {
  return EXECUTION_STAGE_ORDER.reduce((acc, key) => {
    acc[key] = {
      status: "idle",
      elapsedSec: 0,
      etaSec: EXECUTION_STAGE_META[key].expectedSec,
      durationSec: null
    };
    return acc;
  }, {} as ExecutionStagesMap);
}
