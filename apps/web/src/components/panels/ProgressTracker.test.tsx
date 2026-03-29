import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useJourneyStore } from "../../state";
import { ProgressTracker } from "./ProgressTracker";

describe("ProgressTracker", () => {
  beforeEach(() => {
    useJourneyStore.getState().resetJourney();
  });

  it("hides step 2 when the journey modal is walk", () => {
    useJourneyStore.setState((state) => ({
      ...state,
      config: {
        ...state.config,
        modal: "walk"
      }
    }));

    render(
      <ProgressTracker
        currentStep={3}
        maxStep={3}
        isCollapsed={false}
        onStepClick={vi.fn()}
        onToggleCollapse={vi.fn()}
      />
    );

    expect(screen.queryByRole("button", { name: /Ir para etapa Origem/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Ir para etapa Configuração/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Ir para etapa Zonas/i })).toBeInTheDocument();
  });

  it("keeps step 2 visible when the journey modal is transit", () => {
    useJourneyStore.setState((state) => ({
      ...state,
      config: {
        ...state.config,
        modal: "transit"
      }
    }));

    render(
      <ProgressTracker
        currentStep={2}
        maxStep={2}
        isCollapsed={false}
        onStepClick={vi.fn()}
        onToggleCollapse={vi.fn()}
      />
    );

    expect(screen.getByRole("button", { name: /Ir para etapa Origem/i })).toBeInTheDocument();
  });

  it("hides step 2 when the journey modal is car", () => {
    useJourneyStore.setState((state) => ({
      ...state,
      config: {
        ...state.config,
        modal: "car"
      }
    }));

    render(
      <ProgressTracker
        currentStep={3}
        maxStep={3}
        isCollapsed={false}
        onStepClick={vi.fn()}
        onToggleCollapse={vi.fn()}
      />
    );

    expect(screen.queryByRole("button", { name: /Ir para etapa Origem/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Ir para etapa Configuração/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Ir para etapa Zonas/i })).toBeInTheDocument();
  });
});