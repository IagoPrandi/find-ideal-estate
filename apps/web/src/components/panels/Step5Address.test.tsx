import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Step5Address } from "./Step5Address";
import { useJourneyStore, useUIStore } from "../../state";
import { getZoneAddressSuggestions } from "../../api/client";

vi.mock("../../api/client", () => ({
  apiActionHint: (error: unknown) => (error instanceof Error ? error.message : "erro"),
  getZoneAddressSuggestions: vi.fn(),
  searchZoneListings: vi.fn()
}));

describe("Step5Address", () => {
  beforeEach(() => {
    useJourneyStore.getState().resetJourney();
    useUIStore.getState().resetUI();
    useJourneyStore.setState((state) => ({
      ...state,
      journeyId: "journey-1",
      selectedZoneId: "zone-1",
      selectedZoneFingerprint: "zone-fp-1"
    }));
  });

  afterEach(() => {
    vi.clearAllMocks();
    useJourneyStore.getState().resetJourney();
    useUIStore.getState().resetUI();
  });

  it("loads the selected zone streets when the input receives focus", async () => {
    vi.mocked(getZoneAddressSuggestions).mockResolvedValue([
      {
        label: "Rua Schilling, Vila Leopoldina, Sao Paulo-SP",
        normalized: "rua schilling, vila leopoldina, sao paulo-sp",
        location_type: "street",
        lat: -23.520908,
        lon: -46.727037
      },
      {
        label: "Rua Carlos Weber, Vila Leopoldina, Sao Paulo-SP",
        normalized: "rua carlos weber, vila leopoldina, sao paulo-sp",
        location_type: "street",
        lat: -23.521,
        lon: -46.728
      }
    ]);

    const user = userEvent.setup();
    render(<Step5Address />);

    const input = screen.getByLabelText("Endereço alvo na zona");

    await user.click(input);

    await waitFor(() => {
      expect(getZoneAddressSuggestions).toHaveBeenCalledWith("journey-1", "zone-fp-1", "");
    });

    expect(screen.getByTestId("zone-street-suggestions")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Rua Schilling/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Rua Carlos Weber/i })).toBeInTheDocument();
  });
});