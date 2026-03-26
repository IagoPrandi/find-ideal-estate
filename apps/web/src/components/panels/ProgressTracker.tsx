import { ChevronDown, ChevronUp } from "lucide-react";
import { WIZARD_STEPS, type WizardStepId } from "../../features/app/wizardSteps";

export type TrackerStep = {
  id: WizardStepId;
  label: string;
};

type Props = {
  currentStep: WizardStepId;
  maxStep: WizardStepId;
  isCollapsed: boolean;
  onStepClick: (step: WizardStepId) => void;
  onToggleCollapse: () => void;
};

export function ProgressTracker({ currentStep, maxStep, isCollapsed, onStepClick, onToggleCollapse }: Props) {
  return (
    <div className="flex items-center justify-between rounded-3xl border border-slate-200 bg-white/95 p-2.5 shadow-md backdrop-blur-md transition-all">
      <div className="no-scrollbar flex flex-1 items-center gap-1 overflow-x-auto px-1">
        {WIZARD_STEPS.map((step, index) => {
          const isPast = step.id < currentStep;
          const isCurrent = step.id === currentStep;
          const isLocked = step.id > maxStep;
          const iconClassName = isCurrent
            ? "bg-pastel-violet-500 text-white shadow-md"
            : isPast
              ? "bg-pastel-violet-100 text-pastel-violet-600 hover:bg-pastel-violet-200"
              : "bg-slate-100 text-slate-400";

          return (
            <div key={step.id} className="flex items-center">
              <button
                type="button"
                disabled={isLocked}
                onClick={() => onStepClick(step.id)}
                className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-colors ${iconClassName}`}
                title={step.title}
                aria-label={`Ir para etapa ${step.title}`}
              >
                <step.Icon className="h-4 w-4" />
              </button>
              {index < WIZARD_STEPS.length - 1 ? (
                <div
                  className={`mx-1 h-[3px] w-3 rounded-full sm:w-4 ${step.id < currentStep ? "bg-pastel-violet-300" : "bg-slate-200"}`}
                  aria-hidden="true"
                />
              ) : null}
            </div>
          );
        })}
      </div>

      <button
        type="button"
        onClick={onToggleCollapse}
        className="ml-3 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-slate-100 text-slate-500 transition-colors hover:bg-pastel-violet-50 hover:text-pastel-violet-600"
        title={isCollapsed ? "Expandir painel" : "Recolher painel"}
        aria-label={isCollapsed ? "Expandir painel" : "Recolher painel"}
      >
        {isCollapsed ? <ChevronDown className="h-5 w-5" /> : <ChevronUp className="h-5 w-5" />}
      </button>
    </div>
  );
}