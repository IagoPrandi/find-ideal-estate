import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Step2Transport, sanitizeTransportPoints } from "./Step2Transport";
import { getBusStopDetails } from "../../api/client";
import { useJourneyStore, useUIStore } from "../../state";

vi.mock("../../api/client", () => ({
  apiActionHint: vi.fn(() => "Erro de API"),
  createTransportSearchJob: vi.fn(async () => ({ id: "job-1" })),
  getBusStopDetails: vi.fn(async () => ({
    count: 2,
    buses: ["875A-10", "175T-10"],
    source: "gtfs"
  })),
  getJob: vi.fn(async () => ({ state: "completed" })),
  getJourneyTransportPoints: vi.fn(async () => ([
    {
      id: "stop-1",
      journey_id: "journey-1",
      source: "gtfs_stop",
      external_id: "gtfs-stop-1",
      name: "R. Tabapuã, 49",
      lat: -23.57,
      lon: -46.65,
      walk_time_sec: 60,
      walk_distance_m: 41,
      route_ids: ["875A-10", "175T-10"],
      modal_types: ["bus"],
      route_count: 2,
      created_at: "2026-03-27T03:14:38.600720Z"
    }
  ])),
  updateJourney: vi.fn(async () => ({ id: "journey-1" }))
}));

describe("sanitizeTransportPoints", () => {
  beforeEach(() => {
    useJourneyStore.getState().resetJourney();
    useUIStore.getState().resetUI();
    useJourneyStore.setState((state) => ({
      ...state,
      journeyId: "journey-1",
      config: {
        ...state.config,
        modal: "transit",
        publicTransportMode: "bus"
      }
    }));
  });

  it("keeps rail stations even when route_count is zero", () => {
    const result = sanitizeTransportPoints([
      {
        id: "train-1",
        journey_id: "journey-1",
        source: "geosampa_trem_station",
        external_id: "train-station-1",
        name: "DOMINGOS DE MORAIS",
        lat: -23.5189,
        lon: -46.7214,
        walk_time_sec: 542,
        walk_distance_m: 678,
        route_ids: [],
        modal_types: ["train"],
        route_count: 0,
        created_at: "2026-03-27T03:14:38.600720Z",
      },
      {
        id: "bus-1",
        journey_id: "journey-1",
        source: "geosampa_bus_stop",
        external_id: "bus-stop-1",
        name: "Ponto sem linhas",
        lat: -23.52,
        lon: -46.72,
        walk_time_sec: 120,
        walk_distance_m: 150,
        route_ids: [],
        modal_types: ["bus"],
        route_count: 0,
        created_at: "2026-03-27T03:14:38.600720Z",
      },
    ]);

    expect(result).toHaveLength(1);
    expect(result[0]?.id).toBe("train-1");
  });

  it("shows the identified bus lines when the card is selected", async () => {
    const user = userEvent.setup();

    render(<Step2Transport />);

    const card = await screen.findByRole("button", { name: /R\. Tabapuã, 49/i });
    await user.click(card);

    await waitFor(() => {
      expect(getBusStopDetails).toHaveBeenCalledWith("gtfs-stop-1");
      expect(screen.getByText(/Linhas identificadas/i)).toBeInTheDocument();
      expect(screen.getByText(/875A-10/i)).toBeInTheDocument();
      expect(screen.getByText(/175T-10/i)).toBeInTheDocument();
    });
  });
});