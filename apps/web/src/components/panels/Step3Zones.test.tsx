import { render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Step3Zones } from "./Step3Zones";
import { createZoneEnrichmentJob, createZoneGenerationJob, getJob, updateJourney } from "../../api/client";
import { useJourneyStore, useUIStore } from "../../state";

vi.mock("../../api/client", () => ({
  apiActionHint: (error: unknown) => (error instanceof Error ? error.message : "erro"),
  createZoneEnrichmentJob: vi.fn(async () => ({ id: "job-enrich-1" })),
  createZoneGenerationJob: vi.fn(async () => ({ id: "job-zone-1" })),
  getJob: vi.fn(async (jobId: string) => ({ id: jobId, state: "completed", progress_percent: 100 })),
  updateJourney: vi.fn(async () => ({ id: "journey-1" })),
}));

describe("Step3Zones", () => {
  beforeEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
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
  });

  it("auto-starts the single walk isochrone pipeline without a transport seed", async () => {
    render(<Step3Zones />);

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
      expect(getJob).toHaveBeenCalledWith("job-enrich-1");
    });

    await waitFor(() => {
      expect(useUIStore.getState().step).toBe(4);
      expect(useUIStore.getState().maxStep).toBe(4);
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

    render(<Step3Zones />);

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
    }, { timeout: 2000 });
  }, 10000);
});