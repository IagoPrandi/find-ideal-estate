import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Step4Compare } from "./Step4Compare";
import { useJourneyStore, useUIStore } from "../../state";
import { createZoneEnrichmentJob, getJob, getJourneyZonesList, updateJourney } from "../../api/client";

vi.mock("../../api/client", () => ({
  apiActionHint: (error: unknown) => (error instanceof Error ? error.message : "erro"),
  createZoneEnrichmentJob: vi.fn(),
  getJob: vi.fn(),
  getJourneyZonesList: vi.fn(),
  updateJourney: vi.fn()
}));

const scrollIntoViewMock = vi.fn();

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
      <Step4Compare />
    </QueryClientProvider>
  );
}

describe("Step4Compare", () => {
  beforeEach(() => {
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: scrollIntoViewMock
    });

    vi.clearAllMocks();
    scrollIntoViewMock.mockReset();
    useJourneyStore.getState().resetJourney();
    useUIStore.getState().resetUI();
    useJourneyStore.setState((state) => ({
      ...state,
      journeyId: "journey-1",
      selectedZoneId: "zone-1",
      selectedZoneFingerprint: "zone-fp-1"
    }));

    vi.mocked(updateJourney).mockResolvedValue({} as never);
    vi.mocked(createZoneEnrichmentJob).mockResolvedValue({ id: "job-poi-backfill" } as never);
    vi.mocked(getJob).mockResolvedValue({ id: "job-poi-backfill", state: "completed", error_message: null } as never);
    vi.mocked(getJourneyZonesList).mockResolvedValue({
      zones: [
        {
          id: "zone-1",
          journey_id: "journey-1",
          transport_point_id: "tp-1",
          fingerprint: "zone-fp-1",
          state: "complete",
          is_circle_fallback: false,
          travel_time_minutes: 8,
          walk_distance_meters: 320,
          isochrone_geom: null,
          green_area_m2: 1800,
          green_vegetation_label: "Media vegetacao",
          flood_area_m2: 0,
          safety_incidents_count: 2,
          poi_counts: { school: 1, supermarket: 1, pharmacy: 2, restaurant: 1, gym: 1, park: 0 },
          poi_points: [
            {
              kind: "poi",
              id: "poi-1",
              name: "Colegio Centro",
              category: "school",
              address: "Rua A, 10",
              lat: -23.55,
              lon: -46.63
            },
            {
              kind: "poi",
              id: "poi-2",
              name: "Mercado Azul",
              category: "supermarket",
              address: "Rua B, 20",
              lat: -23.551,
              lon: -46.631
            },
            {
              kind: "poi",
              id: "poi-3",
              name: "Farmacia Vida",
              category: "pharmacy",
              address: "Rua C, 30",
              lat: -23.552,
              lon: -46.632
            },
            {
              kind: "poi",
              id: "poi-4",
              name: "Farmacia Centro",
              category: "pharmacy",
              address: "Rua D, 40",
              lat: -23.553,
              lon: -46.633
            },
            {
              kind: "poi",
              id: "poi-5",
              name: "Restaurante Central",
              category: "restaurant",
              address: "Rua E, 50",
              lat: -23.554,
              lon: -46.634
            },
            {
              kind: "poi",
              id: "poi-6",
              name: "Academia Movimento",
              category: "gym",
              address: "Rua F, 60",
              lat: -23.555,
              lon: -46.635
            }
          ],
          badges: {},
          badges_provisional: false,
          created_at: "2026-03-29T10:00:00Z",
          updated_at: "2026-03-29T10:00:00Z"
        }
      ],
      total_count: 1,
      completed_count: 1
    } as never);
  });

  it("filters the zone POI list by category", async () => {
    renderWithQueryClient();

    const poiList = await screen.findByTestId("zone-poi-list");
    expect(createZoneEnrichmentJob).not.toHaveBeenCalled();
    expect(within(poiList).getAllByRole("listitem")).toHaveLength(6);
    expect(within(poiList).getByText("Colegio Centro")).toBeInTheDocument();
    expect(within(poiList).getByText("Mercado Azul")).toBeInTheDocument();
    expect(within(poiList).getByText("Restaurante Central")).toBeInTheDocument();
    expect(within(poiList).getByText("Academia Movimento")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Farmacias \(2\)/i }));

    await waitFor(() => {
      expect(within(poiList).getAllByRole("listitem")).toHaveLength(2);
    });

    expect(useJourneyStore.getState().activePoiCategory).toBe("pharmacy");

    expect(within(poiList).getByText("Farmacia Vida")).toBeInTheDocument();
    expect(within(poiList).getByText("Farmacia Centro")).toBeInTheDocument();
    expect(within(poiList).queryByText("Colegio Centro")).not.toBeInTheDocument();
    expect(within(poiList).queryByText("Mercado Azul")).not.toBeInTheDocument();
  });

  it("scrolls to a POI selected from the map and keeps it highlighted in the panel", async () => {
    renderWithQueryClient();

    await screen.findByTestId("zone-poi-list");

    await act(async () => {
      useJourneyStore.getState().setActivePoiCategory("restaurant");
      useJourneyStore.getState().setSelectedPoiKey("zone-fp-1:restaurant:poi-5");
    });

    await waitFor(() => {
      expect(scrollIntoViewMock).toHaveBeenCalled();
      expect(screen.getByRole("button", { name: /Restaurante Central/i })).toBeInTheDocument();
    });

    expect(screen.queryByText("Colegio Centro")).not.toBeInTheDocument();
  });

  it("starts an enrichment backfill for zones enriched with the old POI category set", async () => {
    vi.mocked(getJourneyZonesList)
      .mockResolvedValueOnce({
        zones: [
          {
            id: "zone-legacy",
            journey_id: "journey-1",
            transport_point_id: "tp-1",
            fingerprint: "zone-fp-1",
            state: "complete",
            is_circle_fallback: false,
            travel_time_minutes: 8,
            walk_distance_meters: 320,
            isochrone_geom: null,
            green_area_m2: 1800,
            green_vegetation_label: "Media vegetacao",
            flood_area_m2: 0,
            safety_incidents_count: 2,
            poi_counts: { school: 1, supermarket: 1, pharmacy: 0, park: 0 },
            poi_points: [
              {
                kind: "poi",
                id: "poi-1",
                name: "Colegio Centro",
                category: "school",
                address: "Rua A, 10",
                lat: -23.55,
                lon: -46.63
              }
            ],
            badges: {},
            badges_provisional: false,
            created_at: "2026-03-29T10:00:00Z",
            updated_at: "2026-03-29T10:00:00Z"
          }
        ],
        total_count: 1,
        completed_count: 1
      } as never)
      .mockResolvedValueOnce({
        zones: [
          {
            id: "zone-legacy",
            journey_id: "journey-1",
            transport_point_id: "tp-1",
            fingerprint: "zone-fp-1",
            state: "complete",
            is_circle_fallback: false,
            travel_time_minutes: 8,
            walk_distance_meters: 320,
            isochrone_geom: null,
            green_area_m2: 1800,
            green_vegetation_label: "Media vegetacao",
            flood_area_m2: 0,
            safety_incidents_count: 2,
            poi_counts: { school: 1, supermarket: 1, pharmacy: 0, park: 0, restaurant: 1, gym: 1 },
            poi_points: [
              {
                kind: "poi",
                id: "poi-1",
                name: "Colegio Centro",
                category: "school",
                address: "Rua A, 10",
                lat: -23.55,
                lon: -46.63
              },
              {
                kind: "poi",
                id: "poi-2",
                name: "Restaurante Central",
                category: "restaurant",
                address: "Rua B, 20",
                lat: -23.551,
                lon: -46.631
              }
            ],
            badges: {},
            badges_provisional: false,
            created_at: "2026-03-29T10:00:00Z",
            updated_at: "2026-03-29T10:00:00Z"
          }
        ],
        total_count: 1,
        completed_count: 1
      } as never);

    renderWithQueryClient();

    await waitFor(() => {
      expect(createZoneEnrichmentJob).toHaveBeenCalledWith("journey-1");
      expect(getJob).toHaveBeenCalledWith("job-poi-backfill");
    });

    await waitFor(() => {
      expect(screen.getByText("Colegio Centro")).toBeInTheDocument();
      expect(screen.getByText("Restaurante Central")).toBeInTheDocument();
    });
  });
});