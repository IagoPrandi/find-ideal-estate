import { create } from "zustand";
import { WIZARD_STEP_IDS, type WizardStepId } from "../features/app/wizardSteps";

export type AnalysisTab = "imoveis" | "dashboard";

type UIState = {
  step: WizardStepId;
  maxStep: WizardStepId;
  isCollapsed: boolean;
  activeTab: AnalysisTab;
  panelWidth: number;
  goToStep: (step: WizardStepId) => void;
  setMaxStep: (step: WizardStepId) => void;
  toggleCollapse: () => void;
  setCollapsed: (value: boolean) => void;
  setActiveTab: (tab: AnalysisTab) => void;
  resetUI: () => void;
};

const panelWidthForStep = (step: WizardStepId) => (step === 6 ? 600 : 420);

export const useUIStore = create<UIState>((set) => ({
  step: 1,
  maxStep: 1,
  isCollapsed: false,
  activeTab: "imoveis",
  panelWidth: panelWidthForStep(1),
  goToStep: (step) =>
    set((state) => ({
      step,
      maxStep: WIZARD_STEP_IDS.includes(step) && step > state.maxStep ? step : state.maxStep,
      isCollapsed: false,
      panelWidth: panelWidthForStep(step)
    })),
  setMaxStep: (step) =>
    set((state) => ({
      maxStep: step > state.maxStep ? step : state.maxStep
    })),
  toggleCollapse: () => set((state) => ({ isCollapsed: !state.isCollapsed })),
  setCollapsed: (value) => set({ isCollapsed: value }),
  setActiveTab: (tab) => set({ activeTab: tab }),
  resetUI: () =>
    set({
      step: 1,
      maxStep: 1,
      isCollapsed: false,
      activeTab: "imoveis",
      panelWidth: panelWidthForStep(1)
    })
}));