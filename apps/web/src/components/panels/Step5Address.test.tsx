import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Step5Address } from "./Step5Address";
import { useJourneyStore, useUIStore } from "../../state";
import { getListingsScrapePlan, getZoneAddressSuggestions, searchZoneListings } from "../../api/client";

vi.mock("../../api/client", () => ({
  apiActionHint: (error: unknown) => (error instanceof Error ? error.message : "erro"),
  getListingsScrapePlan: vi.fn(),
  getZoneAddressSuggestions: vi.fn(),
  searchZoneListings: vi.fn()
}));

describe("Step5Address", () => {
  beforeEach(() => {
    vi.mocked(getListingsScrapePlan).mockResolvedValue({
      search_type: "rent",
      usage_type: "residential",
      total_pages: 12,
      platforms: [
        { platform: "quintoandar", max_pages: 4 },
        { platform: "vivareal", max_pages: 4 },
        { platform: "zapimoveis", max_pages: 4 }
      ]
    } as never);
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

    const input = screen.getByLabelText("Endereço de busca na zona");

    await user.click(input);

    await waitFor(() => {
      expect(getZoneAddressSuggestions).toHaveBeenCalledWith("journey-1", "zone-fp-1", "");
    });

    expect(getListingsScrapePlan).toHaveBeenCalledWith("journey-1", "rent", "residential");

    expect(screen.getByTestId("zone-street-suggestions")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Rua Schilling/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Rua Carlos Weber/i })).toBeInTheDocument();
  });

  it("triggers listings search when a suggestion is selected", async () => {
    useJourneyStore.getState().setConfig({ propertyUsageType: "commercial" });
    vi.mocked(getZoneAddressSuggestions).mockResolvedValue([
      {
        label: "Rua Guaipa, Vila Leopoldina, Sao Paulo-SP",
        normalized: "rua guaipa vila leopoldina sao paulo-sp",
        location_type: "street",
        lat: -23.520908,
        lon: -46.727037
      }
    ]);
    vi.mocked(searchZoneListings).mockResolvedValue({
      source: "none",
      job_id: "listings-job-1",
      freshness_status: "queued_for_next_prewarm",
      listings: [],
      total_count: 0
    } as never);

    const user = userEvent.setup();
    render(<Step5Address />);

    const input = screen.getByLabelText("Endereço de busca na zona");
    await user.click(input);

    const option = await screen.findByRole("option", { name: /Rua Guaipa/i });
    await user.click(option);

    await waitFor(() => {
      expect(getListingsScrapePlan).toHaveBeenCalledWith("journey-1", "rent", "commercial");
      expect(searchZoneListings).toHaveBeenCalledWith(
        "journey-1",
        "zone-fp-1",
        expect.objectContaining({
          search_location_label: "Rua Guaipa, Vila Leopoldina, Sao Paulo-SP",
          search_location_type: "street",
          usage_type: "commercial",
          start_scraping: true,
        })
      );
    });

    await waitFor(() => {
      expect(useUIStore.getState().step).toBe(6);
      expect(useJourneyStore.getState().listingsJobId).toBe("listings-job-1");
    });
  });

  it("waits for the listings search response before opening results", async () => {
    let resolveSearch: (value: unknown) => void;
    const pendingSearch = new Promise((resolve) => {
      resolveSearch = resolve;
    });
    vi.mocked(getZoneAddressSuggestions).mockResolvedValue([
      {
        label: "Rua Guaipa, Vila Leopoldina, Sao Paulo-SP",
        normalized: "rua guaipa vila leopoldina sao paulo-sp",
        location_type: "street",
        lat: -23.520908,
        lon: -46.727037
      }
    ]);
    vi.mocked(searchZoneListings).mockReturnValue(pendingSearch as never);

    const user = userEvent.setup();
    render(<Step5Address />);

    const input = screen.getByLabelText("Endereço de busca na zona");
    await user.click(input);

    const option = await screen.findByRole("option", { name: /Rua Guaipa/i });
    await user.click(option);

    await waitFor(() => {
      expect(searchZoneListings).toHaveBeenCalled();
    });

    expect(useUIStore.getState().step).not.toBe(6);
    expect(screen.getByText("Iniciando busca...")).toBeInTheDocument();

    resolveSearch!({
      source: "none",
      job_id: "listings-job-1",
      freshness_status: "no_cache",
      listings: [],
      total_count: 0,
    });

    await waitFor(() => {
      expect(useUIStore.getState().step).toBe(6);
      expect(useJourneyStore.getState().listingsJobId).toBe("listings-job-1");
    });
  });

  it("allows proceeding to step 6 when the address is only scheduled for later prewarm", async () => {
    vi.mocked(getZoneAddressSuggestions).mockResolvedValue([
      {
        label: "Rua Guaipa, Vila Leopoldina, Sao Paulo-SP",
        normalized: "rua guaipa vila leopoldina sao paulo-sp",
        location_type: "street",
        lat: -23.520908,
        lon: -46.727037
      }
    ]);
    vi.mocked(searchZoneListings).mockResolvedValue({
      source: "none",
      job_id: null,
      freshness_status: "queued_for_next_prewarm",
      upgrade_reason: "address_search_registered",
      next_refresh_window: "até 24 horas",
      listings: [],
      total_count: 0,
    } as never);

    const user = userEvent.setup();
    render(<Step5Address />);

    const input = screen.getByLabelText("Endereço de busca na zona");
    await user.click(input);

    const option = await screen.findByRole("option", { name: /Rua Guaipa/i });
    await user.click(option);

    await waitFor(() => {
      expect(useJourneyStore.getState().listingsJobId).toBeNull();
      expect(useUIStore.getState().step).toBe(6);
    });
  });
});
