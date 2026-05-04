import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Step3Zones } from "./Step3Zones";
import {
  createZoneEnrichmentJob,
  createZoneGenerationJob,
  getJob,
  getJourneyZonesList,
  updateJourney
} from "../../api/client";
import { useJourneyStore, useUIStore } from "../../state";
import { useEntitlements } from "../../features/auth/useEntitlements";

vi.mock("../../api/client", () => ({
  apiActionHint: (error: unknown) => (error instanceof Error ? error.message : "erro"),
  createZoneEnrichmentJob: vi.fn(async () => ({ id: "job-enrich-1" })),
  createZoneGenerationJob: vi.fn(async () => ({ id: "job-zone-1" })),
  getJob: vi.fn(async (jobId: string) => ({ id: jobId, state: "completed", progress_percent: 100 })),
  getJourneyZonesList: vi.fn(async () => ({ zones: [], total_count: 0, completed_count: 0 })),
  updateJourney: vi.fn(async () => ({ id: "journey-1" })),
}));

vi.mock("../../features/auth/useEntitlements", () => ({
  useEntitlements: vi.fn(() => ({
    isLoading: false,
    can_customize_radius: true,
    can_customize_max_time: true,
    can_customize_distance: true,
    max_active_metrics: null,
    max_listing_favorites: null,
    max_zone_favorites: null,
    zone_selection_policy: "any",
    planSlug: "pro",
    planName: "Pro",
    max_transit_minutes_cap: null,
    max_walk_minutes_cap: null,
    max_car_minutes_cap: null,
    max_zone_radius_m_cap: 500,
    max_transport_radius_m_cap: null,
  })),
}));

function renderWithQueryClient() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0
      }
    }
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <Step3Zones />
    </QueryClientProvider>
  );
}

describe("Step3Zones", () => {
  beforeEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
    vi.mocked(useEntitlements).mockReturnValue({
      isLoading: false,
      can_customize_radius: true,
      can_customize_max_time: true,
      can_customize_distance: true,
      max_active_metrics: null,
      max_listing_favorites: null,
      max_zone_favorites: null,
      zone_selection_policy: "any",
      planSlug: "pro",
      planName: "Pro",
      max_transit_minutes_cap: null,
      max_walk_minutes_cap: null,
      max_car_minutes_cap: null,
      max_zone_radius_m_cap: 500,
      max_transport_radius_m_cap: null,
    });
    useJourneyStore.getState().resetJourney();
    useUIStore.getState().resetUI();
    useJourneyStore.setState((state) => ({
      ...state,
      journeyId: "journey-1",
      pickedCoord: { lat: -23.55052, lon: -46.63331, label: "Trabalho" },
      primaryReferenceLabel: "Trabalho",
      config: {
        ...state.config,
        modal: "walk",
        time: 25,
      },
    }));
    useUIStore.setState((state) => ({ ...state, step: 3, maxStep: 3 }));
    vi.mocked(getJourneyZonesList).mockResolvedValue({ zones: [], total_count: 0, completed_count: 0 } as never);
  });

  it("auto-starts the single walk isochrone pipeline without a transport seed", async () => {
    renderWithQueryClient();

    await waitFor(() => {
      expect(updateJourney).toHaveBeenCalledWith(
        "journey-1",
        expect.objectContaining({
          selected_transport_point_id: null,
          last_completed_step: 1,
          input_snapshot: expect.objectContaining({
            transport_mode: "walk",
            max_travel_minutes: 25,
            zone_radius_meters: null,
            transport_search_radius_meters: null,
          }),
        })
      );
      expect(createZoneGenerationJob).toHaveBeenCalledWith("journey-1");
      expect(createZoneEnrichmentJob).toHaveBeenCalledWith("journey-1");
      expect(getJob).toHaveBeenCalledWith("job-zone-1");
    });

    await waitFor(() => {
      expect(useUIStore.getState().step).toBe(4);
      expect(useUIStore.getState().maxStep).toBe(4);
      expect(useJourneyStore.getState().zoneEnrichmentJobId).toBe("job-enrich-1");
    }, { timeout: 2000 });
  }, 10000);

  it("auto-starts the single car isochrone pipeline without a transport seed", async () => {
    useJourneyStore.setState((state) => ({
      ...state,
      config: {
        ...state.config,
        modal: "car",
        time: 30,
      },
    }));

    renderWithQueryClient();

    await waitFor(() => {
      expect(updateJourney).toHaveBeenCalledWith(
        "journey-1",
        expect.objectContaining({
          selected_transport_point_id: null,
          last_completed_step: 1,
          input_snapshot: expect.objectContaining({
            transport_mode: "car",
            max_travel_minutes: 30,
            zone_radius_meters: null,
            transport_search_radius_meters: null,
          }),
        })
      );
      expect(createZoneGenerationJob).toHaveBeenCalledWith("journey-1");
      expect(createZoneEnrichmentJob).toHaveBeenCalledWith("journey-1");
    });

    await waitFor(() => {
      expect(useUIStore.getState().step).toBe(4);
      expect(useUIStore.getState().maxStep).toBe(4);
      expect(useJourneyStore.getState().zoneEnrichmentJobId).toBe("job-enrich-1");
    }, { timeout: 2000 });
  }, 10000);

  it("aplica faixa de 50 m a 500 m com passos de 25 m no raio das zonas para planos elegíveis", () => {
    useJourneyStore.setState((state) => ({
      ...state,
      config: {
        ...state.config,
        modal: "transit",
        zoneRadiusMeters: 100,
      },
      selectedTransportId: "transport-1",
    }));

    const { getAllByRole } = renderWithQueryClient();
    const sliders = getAllByRole("slider");
    const radiusSlider = sliders[1] as HTMLInputElement;

    expect(radiusSlider.min).toBe("50");
    expect(radiusSlider.max).toBe("500");
    expect(radiusSlider.step).toBe("25");

    fireEvent.change(radiusSlider, { target: { value: "75" } });
    expect(useJourneyStore.getState().config.zoneRadiusMeters).toBe(75);
  });

  it("mostra no painel as zonas que já apareceram no mapa durante o processamento", async () => {
    useJourneyStore.setState((state) => ({
      ...state,
      config: {
        ...state.config,
        modal: "transit",
        time: 40,
      },
      selectedTransportId: "transport-1",
    }));

    vi.mocked(getJob).mockResolvedValue({
      id: "job-zone-1",
      state: "running",
      progress_percent: 48,
    } as never);
    vi.mocked(getJourneyZonesList).mockResolvedValue({
      zones: [
        {
          id: "zone-1",
          fingerprint: "abcdef1234567890",
          state: "processing",
          travel_time_minutes: 22,
          walk_distance_meters: 180,
        },
      ],
      total_count: 1,
      completed_count: 0,
    } as never);

    renderWithQueryClient();
    fireEvent.click(screen.getByRole("button", { name: "Gerar zonas" }));

    await waitFor(() => {
      expect(screen.getByTestId("step3-zones-preview-panel")).toBeInTheDocument();
    });

    expect(screen.getByText("Zonas já disponíveis")).toBeInTheDocument();
    expect(screen.getByText("Zona abcdef12")).toBeInTheDocument();
    expect(screen.getByText("Até 22 min")).toBeInTheDocument();
    expect(screen.getByText("Gerada, carregando dados")).toBeInTheDocument();
  });
});
