import { ChevronDown, ChevronUp } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { WizardStepId } from "../../features/app/wizardSteps";

export type TrackerStep = {
  id: WizardStepId;
  title: string;
  desc: string;
  Icon: LucideIcon;
};

type Props = {
  steps: TrackerStep[];
  activeStep: WizardStepId;
  isStepLocked: (id: WizardStepId) => boolean;
  onNavigateToStep: (id: WizardStepId) => void;
  isPanelMinimized: boolean;
  onTogglePanelMinimized: () => void;
};

/** Tracker horizontal com passos do fluxo (estilo GEMINI). */
export function ProgressTracker({
  steps,
  activeStep,
  isStepLocked,
  onNavigateToStep,
  isPanelMinimized,
  onTogglePanelMinimized
}: Props) {
  return (
    <div className="pointer-events-auto flex shrink-0 items-center justify-between rounded-2xl border border-slate-200 bg-white/95 p-2.5 shadow-md backdrop-blur-md">
      <div className="no-scrollbar flex flex-1 items-center gap-1 overflow-x-auto px-1">
        {steps.map((step, i) => {
          const StepIcon = step.Icon;
          const locked = isStepLocked(step.id);
          const isCurrent = activeStep === step.id;
          const isPast = activeStep > step.id;
          return (
            <div key={step.id} className="flex items-center">
              <button
                type="button"
                disabled={locked}
                onClick={() => onNavigateToStep(step.id)}
                aria-label={step.title}
                title={step.title}
                className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-colors ${
                  isCurrent
                    ? "bg-pastel-violet-500 text-white shadow-md"
                    : isPast
                      ? "bg-pastel-violet-100 text-pastel-violet-600 hover:bg-pastel-violet-200"
                      : locked
                        ? "cursor-not-allowed bg-slate-100 text-slate-400"
                        : "bg-slate-100 text-slate-500"
                }`}
              >
                <StepIcon className="h-4 w-4" aria-hidden />
              </button>
              {i < steps.length - 1 ? (
                <div
                  className={`mx-1 h-0.5 w-3 rounded-full sm:w-4 ${isPast ? "bg-pastel-violet-300" : "bg-slate-200"}`}
                />
              ) : null}
            </div>
          );
        })}
      </div>
      <button
        type="button"
        onClick={onTogglePanelMinimized}
        className="ml-3 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-slate-100 text-slate-500 transition-colors hover:bg-pastel-violet-50 hover:text-pastel-violet-600"
        title={isPanelMinimized ? "Expandir painel" : "Minimizar painel"}
      >
        {isPanelMinimized ? <ChevronDown size={22} /> : <ChevronUp size={22} />}
      </button>
    </div>
  );
}
