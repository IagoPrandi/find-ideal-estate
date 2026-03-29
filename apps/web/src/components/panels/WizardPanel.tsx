import { useUIStore } from "../../state";
import { ProgressTracker } from "./ProgressTracker";
import { Step1Config } from "./Step1Config";
import { Step2Transport } from "./Step2Transport";
import { Step3Zones } from "./Step3Zones";
import { Step4Compare } from "./Step4Compare";
import { Step5Address } from "./Step5Address";
import { Step6Analysis } from "./Step6Analysis";

export function WizardPanel() {
  const step = useUIStore((state) => state.step);
  const maxStep = useUIStore((state) => state.maxStep);
  const isCollapsed = useUIStore((state) => state.isCollapsed);
  const panelWidth = useUIStore((state) => state.panelWidth);
  const goToStep = useUIStore((state) => state.goToStep);
  const toggleCollapse = useUIStore((state) => state.toggleCollapse);

  return (
    <>
      <div
        className="wizard-shell pointer-events-none absolute bottom-4 left-4 top-4 z-10 flex flex-col gap-3 transition-all duration-500 ease-[cubic-bezier(0.25,1,0.5,1)]"
        style={{ width: `${panelWidth}px` }}
      >
        <div className="pointer-events-auto">
          <ProgressTracker currentStep={step} maxStep={maxStep} isCollapsed={isCollapsed} onStepClick={goToStep} onToggleCollapse={toggleCollapse} />
        </div>

        <div className={`pointer-events-auto overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl transition-all duration-500 ease-in-out ${isCollapsed ? "pointer-events-none flex-none scale-95 opacity-0" : "flex-1 opacity-100"}`} style={{ height: isCollapsed ? "0px" : "auto" }}>
          <div className="h-full w-full min-w-0">
            {step === 1 ? <Step1Config /> : null}
            {step === 2 ? <Step2Transport /> : null}
            {step === 3 ? <Step3Zones /> : null}
            {step === 4 ? <Step4Compare /> : null}
            {step === 5 ? <Step5Address /> : null}
            {step === 6 ? <Step6Analysis /> : null}
          </div>
        </div>
      </div>
    </>
  );
}