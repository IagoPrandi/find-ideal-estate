import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useJourneyStore, useUIStore } from "../../state";
import { WizardPanel } from "./WizardPanel";

vi.mock("./Step1Config", () => ({ Step1Config: () => <div>Conteúdo da etapa 1</div> }));
vi.mock("./Step2Transport", () => ({ Step2Transport: () => <div>Conteúdo da etapa 2</div> }));
vi.mock("./Step3Zones", () => ({ Step3Zones: () => <div>Conteúdo da etapa 3</div> }));
vi.mock("./Step4Compare", () => ({ Step4Compare: () => <div>Conteúdo da etapa 4</div> }));
vi.mock("./Step5Address", () => ({ Step5Address: () => <div>Conteúdo da etapa 5</div> }));
vi.mock("./Step6Analysis", () => ({ Step6Analysis: () => <div>Conteúdo da etapa 6</div> }));

describe("WizardPanel", () => {
  beforeEach(() => {
    useJourneyStore.getState().resetJourney();
    useUIStore.getState().resetUI();
  });

  it("keeps the tracker visible and hides step content when collapsed", () => {
    useUIStore.setState((state) => ({ ...state, isCollapsed: true }));

    render(<WizardPanel />);

    expect(screen.getByRole("button", { name: "Expandir painel" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Ir para etapa Configuração/i })).toBeInTheDocument();
    expect(screen.queryByText("Conteúdo da etapa 1")).not.toBeInTheDocument();
    expect(screen.getByTestId("wizard-step-panel")).toHaveAttribute("aria-hidden", "true");
  });

  it("restores the active step content when the tracker expands the panel", () => {
    useUIStore.setState((state) => ({ ...state, isCollapsed: true }));

    render(<WizardPanel />);
    fireEvent.click(screen.getByRole("button", { name: "Expandir painel" }));

    expect(screen.getByText("Conteúdo da etapa 1")).toBeInTheDocument();
    expect(screen.getByTestId("wizard-step-panel")).toHaveAttribute("aria-hidden", "false");
  });
});
