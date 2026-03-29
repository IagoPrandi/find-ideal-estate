import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createJourney } from "../../api/client";
import { useJourneyStore, useUIStore } from "../../state";
import { Step1Config } from "./Step1Config";

vi.mock("../../api/client", () => ({
  apiActionHint: (error: unknown) => (error instanceof Error ? error.message : "erro"),
  createJourney: vi.fn()
}));

describe("Step1Config", () => {
  beforeEach(() => {
    useJourneyStore.getState().resetJourney();
    useUIStore.getState().resetUI();
    vi.mocked(createJourney).mockResolvedValue({ id: "journey-1" } as never);
  });

  it("shows the floating vegetation selector on hover and enables green when a level is chosen", () => {
    render(<Step1Config />);

    const greenCheckbox = screen.getByRole("checkbox", { name: /Áreas verdes/i });
    expect(greenCheckbox).not.toBeChecked();
    expect(screen.queryByRole("button", { name: /Pouca vegetação/i })).not.toBeInTheDocument();

    fireEvent.mouseEnter(greenCheckbox.closest("div") as HTMLElement);

    expect(screen.getByRole("button", { name: /Pouca vegetação/i })).toBeVisible();
    expect(screen.getByRole("button", { name: /Média vegetação/i })).toBeVisible();
    expect(screen.getByRole("button", { name: /Muita vegetação/i })).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: /Muita vegetação/i }));
    expect(useJourneyStore.getState().config.enrichments.green).toBe(true);
  });

  it("sends the selected vegetation level in the journey payload", async () => {
    useJourneyStore.getState().setPickedCoord({ lat: -23.55, lon: -46.63, label: "Trabalho" });
    render(<Step1Config />);

    fireEvent.mouseEnter(screen.getByRole("checkbox", { name: /Áreas verdes/i }).closest("div") as HTMLElement);
    fireEvent.click(screen.getByRole("button", { name: /Muita vegetação/i }));
    fireEvent.click(screen.getByRole("button", { name: /Encontrar pontos seed/i }));

    await waitFor(() => {
      expect(createJourney).toHaveBeenCalledWith(
        expect.objectContaining({
          input_snapshot: expect.objectContaining({
            enrichments: expect.objectContaining({
              green: true,
              green_vegetation_level: "high"
            })
          })
        })
      );
    });
  });
});