import { describe, expect, it } from "vitest";
import { sanitizeTransportPoints } from "./Step2Transport";

describe("sanitizeTransportPoints", () => {
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
});