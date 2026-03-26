import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

type MapClickEvent = {
  lngLat: {
    lat: number;
    lng: number;
  };
  point: {
    x: number;
    y: number;
  };
};

let clickHandler: ((event: MapClickEvent) => void) | null = null;

vi.mock("maplibre-gl", () => {
  class MockPopup {
    setLngLat() {
      return this;
    }
    setHTML() {
      return this;
    }
    addTo() {
      return this;
    }
  }

  class MockMarker {
    setLngLat() {
      return this;
    }
    setPopup() {
      return this;
    }
    addTo() {
      return this;
    }
    remove() {
      return this;
    }
  }

  class MockMap {
    private sources: Record<string, { setData: (data: unknown) => void }> = {};
    private layers = new Set<string>();

    on(
      event: string,
      layerOrCallback: string | ((event: MapClickEvent) => void) | (() => void),
      maybeCallback?: (event: MapClickEvent) => void
    ) {
      if (event === "load") {
        const callback =
          typeof layerOrCallback === "function" ? layerOrCallback : (maybeCallback as (() => void) | undefined);
        if (callback) {
          (callback as () => void)();
        }
      }
      if (event === "click" && typeof layerOrCallback === "function") {
        clickHandler = layerOrCallback as (event: MapClickEvent) => void;
      }
      return this;
    }
    addSource(name: string) {
      this.sources[name] = {
        setData: () => {
          return;
        }
      };
      return this;
    }
    getSource(name: string) {
      return this.sources[name];
    }
    addLayer(layer: { id: string }) {
      this.layers.add(layer.id);
      return this;
    }
    moveLayer() {
      return this;
    }
    getLayer(id: string) {
      return this.layers.has(id) ? { id } : undefined;
    }
    setLayoutProperty() {
      return this;
    }
    setPaintProperty() {
      return this;
    }
    queryRenderedFeatures() {
      return [];
    }
    flyTo() {
      return this;
    }
    getCanvas() {
      return { style: { cursor: "" } };
    }
    getCenter() {
      return { lat: -23.55052, lng: -46.633308 };
    }
    getBounds() {
      return {
        getWest: () => -46.8,
        getSouth: () => -23.7,
        getEast: () => -46.4,
        getNorth: () => -23.4
      };
    }
    getZoom() {
      return 10.7;
    }
    zoomIn() {
      return this;
    }
    zoomOut() {
      return this;
    }
    resize() {
      return this;
    }
    remove() {
      return this;
    }
  }

  return {
    default: {
      Map: MockMap,
      Marker: MockMarker,
      Popup: MockPopup
    }
  };
});

async function triggerMapClick(lat: number, lon: number) {
  if (!clickHandler) {
    throw new Error("Map click handler not initialized.");
  }
  await act(async () => {
    clickHandler?.({
      lngLat: {
        lat,
        lng: lon
      },
      point: { x: 0, y: 0 }
    });
  });
}

function jsonResponse(payload: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(payload), {
      status,
      headers: {
        "Content-Type": "application/json"
      }
    })
  );
}

describe("App frontend FE smoke", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    clickHandler = null;
    vi.stubGlobal("fetch", vi.fn());
  });

  it("renders base UI with create run disabled initially", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: /Configurar busca/i })).toBeInTheDocument();

    const createRunButton = screen.getByRole("button", {
      name: "Achar pontos de transporte"
    });

    expect(createRunButton).toBeDisabled();
    expect(screen.getByText(/Defina o ponto principal/i)).toBeInTheDocument();
  });

  it("opens and closes help modal", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Ajuda" }));
    expect(screen.getByRole("heading", { name: /^Ajuda$/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Fechar" }));
    expect(screen.queryByRole("heading", { name: /^Ajuda$/i })).not.toBeInTheDocument();
  });

  it("toggles panel minimize and restore", async () => {
    const user = userEvent.setup();
    render(<App />);

    const toggleButton = screen.getByRole("button", { name: "Minimizar painel" });
    await user.click(toggleButton);

    expect(screen.getByRole("button", { name: "Expandir painel" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Expandir painel" }));
    expect(screen.getByRole("button", { name: "Minimizar painel" })).toBeInTheDocument();
  });

  it("switches property mode between rent and buy", async () => {
    const user = userEvent.setup();
    render(<App />);

    const rentButton = screen.getByRole("button", { name: "Aluguel" });
    const buyButton = screen.getByRole("button", { name: "Compra" });

    expect(rentButton).toHaveClass("bg-white");
    await user.click(buyButton);
    expect(buyButton).toHaveClass("bg-white");
  });

  it("covers FE6 happy path: reference -> generate zones -> step 2", async () => {
    const user = userEvent.setup();
    let createJourneyPayload: Record<string, unknown> | null = null;
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url.endsWith("/journeys") && init?.method === "POST") {
        createJourneyPayload = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : null;
        return jsonResponse({
          id: "journey_fe6_ok",
          state: "running",
          input_snapshot: createJourneyPayload?.input_snapshot || {},
          created_at: "2026-03-24T10:00:00Z",
          updated_at: "2026-03-24T10:00:00Z"
        });
      }

      if (url.endsWith("/jobs") && init?.method === "POST") {
        const payload = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : {};
        const type = String(payload.job_type || "");
        if (type === "transport_search") {
          return jsonResponse({ id: "job_transport_fe6", job_type: type, state: "queued", progress_percent: 0, created_at: "2026-03-24T10:00:00Z" });
        }
        if (type === "zone_generation") {
          return jsonResponse({ id: "job_zone_fe6", job_type: type, state: "queued", progress_percent: 0, created_at: "2026-03-24T10:00:00Z" });
        }
        if (type === "zone_enrichment") {
          return jsonResponse({ id: "job_enrich_fe6", job_type: type, state: "queued", progress_percent: 0, created_at: "2026-03-24T10:00:00Z" });
        }
      }

      if (url.endsWith("/jobs/job_transport_fe6")) {
        return jsonResponse({
          id: "job_transport_fe6",
          job_type: "transport_search",
          state: "completed",
          progress_percent: 100,
          current_stage: "transport_search",
          created_at: "2026-03-24T10:00:00Z"
        });
      }

      if (url.endsWith("/jobs/job_zone_fe6")) {
        return jsonResponse({
          id: "job_zone_fe6",
          job_type: "zone_generation",
          state: "completed",
          progress_percent: 100,
          current_stage: "zone_generation",
          created_at: "2026-03-24T10:00:00Z"
        });
      }

      if (url.endsWith("/jobs/job_enrich_fe6")) {
        return jsonResponse({
          id: "job_enrich_fe6",
          job_type: "zone_enrichment",
          state: "completed",
          progress_percent: 100,
          current_stage: "zone_enrichment",
          created_at: "2026-03-24T10:00:00Z"
        });
      }

      if (url.endsWith("/journeys/journey_fe6_ok/transport-points")) {
        return jsonResponse([
          {
            id: "tp_1",
            journey_id: "journey_fe6_ok",
            source: "gtfs",
            name: "Parada A",
            lat: -23.55052,
            lon: -46.633308,
            walk_time_sec: 360,
            walk_distance_m: 420,
            route_ids: ["r1", "r2", "r3"],
            modal_types: ["bus", "rail", "bus"],
            route_count: 7,
            created_at: "2026-03-24T10:00:00Z"
          }
        ]);
      }

      if (url.endsWith("/journeys/journey_fe6_ok/zones")) {
        return jsonResponse({
          zones: [
            {
              id: "zone_id_1",
              journey_id: "journey_fe6_ok",
              transport_point_id: "tp_1",
              fingerprint: "zone_1",
              state: "complete",
              travel_time_minutes: 41,
              walk_distance_meters: 420,
              isochrone_geom: {
                type: "Polygon",
                coordinates: [[[-46.67, -23.57], [-46.64, -23.57], [-46.64, -23.54], [-46.67, -23.54], [-46.67, -23.57]]]
              },
              poi_counts: {},
              badges_provisional: false,
              created_at: "2026-03-24T10:00:00Z",
              updated_at: "2026-03-24T10:00:00Z"
            }
          ],
          total_count: 1,
          completed_count: 1
        });
      }

      return jsonResponse({ detail: "not found" }, 404);
    });

    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    await triggerMapClick(-23.55052, -46.633308);

    const createRunButton = screen.getByRole("button", {
      name: "Achar pontos de transporte"
    });

    await waitFor(() => {
      expect(createRunButton).toBeEnabled();
    });

    await user.click(createRunButton);
    await screen.findByRole("heading", { name: /Ponto de transporte/i });
    await user.click(screen.getByRole("button", { name: /Gerar zonas/i }));

    expect(createJourneyPayload).not.toBeNull();
    if (!createJourneyPayload) {
      throw new Error("createJourney payload was not captured");
    }
    const snapshot = (createJourneyPayload["input_snapshot"] as Record<string, unknown>) || {};
    expect(snapshot.zone_detail_include_pois).toBe(true);
    expect(snapshot.zone_detail_include_transport).toBe(true);
    expect(snapshot.zone_detail_include_green).toBe(true);
    expect(snapshot.zone_detail_include_flood).toBe(true);
    expect(snapshot.zone_detail_include_public_safety).toBe(true);

    expect(await screen.findByText(/Payload válido: 1 zonas consolidadas\./i)).toBeInTheDocument();
    expect(screen.getByText(/Seleção:/i)).toBeInTheDocument();
  });

  it("covers FE6 extreme empty state when zones payload has zero features", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url.endsWith("/journeys") && init?.method === "POST") {
        return jsonResponse({
          id: "journey_fe6_empty",
          state: "running",
          input_snapshot: {},
          created_at: "2026-03-24T10:00:00Z",
          updated_at: "2026-03-24T10:00:00Z"
        });
      }

      if (url.endsWith("/jobs") && init?.method === "POST") {
        const payload = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : {};
        const type = String(payload.job_type || "");
        const id = type === "transport_search" ? "job_transport_fe6_empty" : type === "zone_generation" ? "job_zone_fe6_empty" : "job_enrich_fe6_empty";
        return jsonResponse({ id, job_type: type, state: "queued", progress_percent: 0, created_at: "2026-03-24T10:00:00Z" });
      }

      if (url.endsWith("/jobs/job_transport_fe6_empty") || url.endsWith("/jobs/job_zone_fe6_empty") || url.endsWith("/jobs/job_enrich_fe6_empty")) {
        return jsonResponse({
          id: "job_done",
          job_type: "transport_search",
          state: "completed",
          progress_percent: 100,
          current_stage: "completed",
          created_at: "2026-03-24T10:00:00Z"
        });
      }

      if (url.endsWith("/journeys/journey_fe6_empty/transport-points")) {
        return jsonResponse([
          {
            id: "tp_1",
            journey_id: "journey_fe6_empty",
            source: "gtfs",
            name: "Parada A",
            lat: -23.551111,
            lon: -46.631111,
            walk_time_sec: 320,
            walk_distance_m: 380,
            route_ids: ["r1"],
            modal_types: ["bus"],
            route_count: 1,
            created_at: "2026-03-24T10:00:00Z"
          }
        ]);
      }

      if (url.endsWith("/journeys/journey_fe6_empty/zones")) {
        return jsonResponse({
          zones: [],
          total_count: 0,
          completed_count: 0
        });
      }

      return jsonResponse({ detail: "not found" }, 404);
    });

    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    await triggerMapClick(-23.551111, -46.631111);
    await user.click(screen.getByRole("button", { name: "Achar pontos de transporte" }));
    await screen.findByRole("heading", { name: /Ponto de transporte/i });
    await user.click(screen.getByRole("button", { name: /Gerar zonas/i }));

    expect(
      await screen.findByText(/Nenhuma zona consolidada retornada\. Revise os dados de referência\./i)
    ).toBeInTheDocument();
    expect(screen.getByText(/zonas:\s*empty/i)).toBeInTheDocument();
  });

  it(
    "covers FE6 long-text scenario for interests and keeps panel functional",
    async () => {
    const user = userEvent.setup();
    render(<App />);

    const optionalInterestsHeading = screen.getByRole("heading", { name: "Interesses opcionais" });
    const optionalInterestsSection = optionalInterestsHeading.closest("section");
    if (!optionalInterestsSection) {
      throw new Error("Optional interests section not found.");
    }
    await user.click(within(optionalInterestsSection).getByRole("button", { name: "Adicionar interesse" }));

    const longLabel =
      "Academia com nome extremamente longo para validar renderização sem overflow e com responsividade no painel lateral";
    await user.type(screen.getByPlaceholderText("Ex.: Academia XYZ"), longLabel);

    await user.click(within(optionalInterestsSection).getByRole("button", { name: "Selecionar no mapa" }));
    await triggerMapClick(-23.612345, -46.598765);

    expect(await screen.findByText(longLabel)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Configurar busca/i })).toBeInTheDocument();
    },
    15_000
  );

  it("sends unchecked zone info options as false in run params", async () => {
    const user = userEvent.setup();
    let createJourneyPayload: Record<string, unknown> | null = null;

    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url.endsWith("/journeys") && init?.method === "POST") {
        createJourneyPayload = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : null;
        return jsonResponse({
          id: "journey_checklist_flags",
          state: "running",
          input_snapshot: createJourneyPayload?.input_snapshot || {},
          created_at: "2026-03-24T10:00:00Z",
          updated_at: "2026-03-24T10:00:00Z"
        });
      }

      if (url.endsWith("/jobs") && init?.method === "POST") {
        const payload = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : {};
        const type = String(payload.job_type || "");
        return jsonResponse({ id: `job_${type}`, job_type: type, state: "completed", progress_percent: 100, created_at: "2026-03-24T10:00:00Z" });
      }

      if (url.includes("/jobs/job_transport_search") || url.includes("/jobs/job_zone_generation") || url.includes("/jobs/job_zone_enrichment")) {
        return jsonResponse({ id: "job_done", job_type: "transport_search", state: "completed", progress_percent: 100, current_stage: "completed", created_at: "2026-03-24T10:00:00Z" });
      }

      if (url.endsWith("/journeys/journey_checklist_flags/transport-points")) {
        return jsonResponse([
          {
            id: "tp_check",
            journey_id: "journey_checklist_flags",
            source: "gtfs",
            name: "Parada",
            lat: -23.55052,
            lon: -46.633308,
            walk_time_sec: 200,
            walk_distance_m: 260,
            route_ids: ["r1"],
            modal_types: ["bus"],
            route_count: 1,
            created_at: "2026-03-24T10:00:00Z"
          }
        ]);
      }

      return jsonResponse({ detail: "not found" }, 404);
    });

    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    await triggerMapClick(-23.55052, -46.633308);

    const camadasSection = screen
      .getByText("Analisar nas zonas (Enriquecimento)")
      .closest("section");
    if (!camadasSection) {
      throw new Error("Seção de enriquecimento da zona não encontrada.");
    }
    await user.click(within(camadasSection).getByLabelText("POIs da zona"));
    await user.click(within(camadasSection).getByLabelText("Transporte da zona"));
    await user.click(within(camadasSection).getByLabelText("Área verde da zona"));
    await user.click(within(camadasSection).getByLabelText("Alagamento da zona"));
    await user.click(within(camadasSection).getByLabelText("Segurança pública"));

    await user.click(screen.getByRole("button", { name: "Achar pontos de transporte" }));

    expect(createJourneyPayload).not.toBeNull();
    if (!createJourneyPayload) {
      throw new Error("createJourney payload was not captured");
    }

    const snapshot = (createJourneyPayload["input_snapshot"] as Record<string, unknown>) || {};
    expect(snapshot.zone_detail_include_pois).toBe(false);
    expect(snapshot.zone_detail_include_transport).toBe(false);
    expect(snapshot.zone_detail_include_green).toBe(false);
    expect(snapshot.zone_detail_include_flood).toBe(false);
    expect(snapshot.zone_detail_include_public_safety).toBe(false);
  });

  it("verifies M5.7: cache hit under 500ms and incremental diff without list flicker", async () => {
    const user = userEvent.setup();
    let listingsFetchRound = 0;

    const baseFeature = {
      type: "Feature",
      geometry: {
        type: "Point",
        coordinates: [-46.6333, -23.5505]
      }
    } as const;

    const finalListingsRound1 = {
      type: "FeatureCollection",
      features: [
        {
          ...baseFeature,
          properties: {
            property_id: "prop_shared",
            platform_listing_id: "qa_1",
            current_best_price: 3200,
            area_m2: 54,
            bedrooms: 2,
            platform: "quintoandar",
            address: "Rua A, 100",
            url: "https://example.com/a",
            observed_at: "2026-03-22T14:00:00Z",
            duplication_badge: "Disponível em 2 plataformas"
          }
        },
        {
          ...baseFeature,
          geometry: { type: "Point", coordinates: [-46.631, -23.552] },
          properties: {
            property_id: "prop_old",
            platform_listing_id: "qa_2",
            current_best_price: 4100,
            area_m2: 62,
            bedrooms: 3,
            platform: "zapimoveis",
            address: "Rua B, 200",
            url: "https://example.com/b",
            observed_at: "2026-03-22T14:00:00Z"
          }
        }
      ]
    };

    const finalListingsRound2 = {
      type: "FeatureCollection",
      features: [
        {
          ...baseFeature,
          properties: {
            property_id: "prop_shared",
            platform_listing_id: "qa_1",
            current_best_price: 3190,
            area_m2: 54,
            bedrooms: 2,
            platform: "quintoandar",
            address: "Rua A, 100",
            url: "https://example.com/a",
            observed_at: "2026-03-22T14:05:00Z",
            duplication_badge: "Disponível em 2 plataformas"
          }
        },
        {
          ...baseFeature,
          geometry: { type: "Point", coordinates: [-46.6295, -23.5531] },
          properties: {
            property_id: "prop_new",
            platform_listing_id: "qa_3",
            current_best_price: 3600,
            area_m2: 58,
            bedrooms: 2,
            platform: "vivareal",
            address: "Rua C, 300",
            url: "https://example.com/c",
            observed_at: "2026-03-22T14:05:00Z"
          }
        }
      ]
    };

    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url.endsWith("/journeys") && init?.method === "POST") {
        return jsonResponse({
          id: "journey_m57",
          state: "running",
          input_snapshot: {},
          created_at: "2026-03-24T10:00:00Z",
          updated_at: "2026-03-24T10:00:00Z"
        });
      }

      if (url.endsWith("/jobs") && init?.method === "POST") {
        const payload = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : {};
        const type = String(payload.job_type || "");
        if (type === "transport_search") {
          return jsonResponse({ id: "job_transport_m57", job_type: type, state: "queued", progress_percent: 0, created_at: "2026-03-24T10:00:00Z" });
        }
        if (type === "zone_generation") {
          return jsonResponse({ id: "job_zone_m57", job_type: type, state: "queued", progress_percent: 0, created_at: "2026-03-24T10:00:00Z" });
        }
        if (type === "zone_enrichment") {
          return jsonResponse({ id: "job_enrich_m57", job_type: type, state: "queued", progress_percent: 0, created_at: "2026-03-24T10:00:00Z" });
        }
      }

      if (url.endsWith("/jobs/job_transport_m57") || url.endsWith("/jobs/job_zone_m57") || url.endsWith("/jobs/job_enrich_m57")) {
        return jsonResponse({
          id: "job_m57_done",
          job_type: "zone_generation",
          state: "completed",
          progress_percent: 100,
          current_stage: "completed",
          created_at: "2026-03-24T10:00:00Z"
        });
      }

      if (url.endsWith("/journeys/journey_m57/transport-points")) {
        return jsonResponse([
          {
            id: "tp_m57",
            journey_id: "journey_m57",
            source: "gtfs",
            name: "Parada Principal",
            lat: -23.55052,
            lon: -46.633308,
            walk_time_sec: 320,
            walk_distance_m: 380,
            route_ids: ["r1", "r2", "r3"],
            modal_types: ["bus", "rail", "bus"],
            route_count: 7,
            created_at: "2026-03-24T10:00:00Z"
          }
        ]);
      }

      if (url.endsWith("/journeys/journey_m57/zones")) {
        return jsonResponse({
          zones: [
            {
              id: "zone_id_1",
              journey_id: "journey_m57",
              transport_point_id: "tp_m57",
              fingerprint: "zone_1",
              state: "complete",
              travel_time_minutes: 41,
              walk_distance_meters: 380,
              isochrone_geom: {
                type: "Polygon",
                coordinates: [[[-46.67, -23.57], [-46.64, -23.57], [-46.64, -23.54], [-46.67, -23.54], [-46.67, -23.57]]]
              },
              poi_counts: { parque: 2, farmacia: 1 },
              badges_provisional: false,
              created_at: "2026-03-24T10:00:00Z",
              updated_at: "2026-03-24T10:00:00Z"
            }
          ],
          total_count: 1,
          completed_count: 1
        });
      }

      if (url.includes("/journeys/journey_m57/listings/address-suggest")) {
        return jsonResponse([
          {
            label: "Zona 1",
            normalized: "zona 1",
            location_type: "neighborhood",
            lat: -23.55,
            lon: -46.63
          }
        ]);
      }

      if (url.endsWith("/journeys/journey_m57/listings/search") && init?.method === "POST") {
        return jsonResponse({ source: "cache", freshness_status: "fresh", listings: [], total_count: 2, cache_age_hours: 1 });
      }

      if (url.includes("/journeys/journey_m57/zones/zone_1/listings")) {
        listingsFetchRound += 1;
        const features = listingsFetchRound === 1 ? finalListingsRound1.features : finalListingsRound2.features;
        const listings = features.map((feature) => {
          const props = feature.properties as Record<string, unknown>;
          const coords = (feature.geometry.coordinates || []) as number[];
          return {
            ...props,
            current_best_price:
              props.current_best_price !== undefined && props.current_best_price !== null
                ? String(props.current_best_price)
                : null,
            second_best_price:
              props.second_best_price !== undefined && props.second_best_price !== null
                ? String(props.second_best_price)
                : null,
            lat: coords[1],
            lon: coords[0]
          };
        });

        return jsonResponse({
          source: "cache",
          freshness_status: "fresh",
          listings,
          total_count: listings.length,
          cache_age_hours: 1
        });
      }

      return jsonResponse({ detail: "not found" }, 404);
    });

    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    await triggerMapClick(-23.55052, -46.633308);
    await user.click(screen.getByRole("button", { name: "Achar pontos de transporte" }));
    await screen.findByRole("heading", { name: /Ponto de transporte/i });
    await user.click(screen.getByRole("button", { name: /Gerar zonas/i }));

    await screen.findByText(/Payload válido: 1 zonas consolidadas\./i);
    await user.click(screen.getByRole("button", { name: "Comparação" }));
    await user.click(screen.getByRole("button", { name: "Carregar detalhamento" }));
    await screen.findAllByText(/Detalhamento concluído\. Escolha como buscar imóveis\./i);

    await waitFor(() => {
      const endereco = screen.getByRole("button", { name: "Endereço" });
      expect(endereco.className).toMatch(/bg-pastel-violet-500/);
    });

    const searchInput = screen.getByPlaceholderText("Digite bairro, rua ou referência");
    await user.type(searchInput, "zona");
    const suggestions = screen.getByTestId("street-suggestions-ul");
    fireEvent.click(within(suggestions).getByRole("button", { name: /Zona .*zone_1/i }));

    if (!screen.queryByRole("button", { name: "Buscar imóveis" })) {
      await user.click(screen.getByRole("button", { name: "Endereço" }));
      await waitFor(() => {
        expect(screen.getByRole("button", { name: "Endereço" }).className).toMatch(/bg-pastel-violet-500/);
      });
    }

    const firstClickStart = performance.now();
    await user.click(screen.getByRole("button", { name: "Buscar imóveis" }));
    await screen.findByText(/Resultado final pronto:/i);
    const firstClickElapsed = performance.now() - firstClickStart;

    expect(firstClickElapsed).toBeLessThan(500);
    expect(screen.getAllByText(/Dados de \d+h atrás/i).length).toBeGreaterThan(0);

    // Após a 1.ª busca o fluxo avança para a etapa Análise (6); o botão de busca só existe na etapa Endereço (5).
    await user.click(screen.getByRole("button", { name: "Endereço" }));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Endereço" }).className).toMatch(/bg-pastel-violet-500/);
    });

    await user.click(screen.getByRole("button", { name: "Buscar imóveis" }));
    await screen.findByText(/Resultado final pronto:/i);

    expect(screen.getByText(/Revalidação concluída: \+1 novos \/ -1 removidos\./i)).toBeInTheDocument();
    expect(screen.getByText(/Resultado final pronto:/i)).toBeInTheDocument();
  });

  it(
    "verifies M6.2: dashboard tab loads with 30-day line chart data for FREE",
    async () => {
    const user = userEvent.setup();

    const rollups = Array.from({ length: 35 }, (_, idx) => {
      const day = String(35 - idx).padStart(2, "0");
      return {
        id: `rollup_${idx}`,
        date: `2026-03-${day}`,
        zone_fingerprint: "zone_1",
        search_type: "rent",
        median_price: String(3000 + idx * 10),
        p25_price: String(2600 + idx * 8),
        p75_price: String(3600 + idx * 12),
        sample_count: 20 + idx,
        computed_at: "2026-03-22T10:00:00Z"
      };
    });

    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url.endsWith("/journeys") && init?.method === "POST") {
        return jsonResponse({
          id: "journey_m62",
          state: "running",
          input_snapshot: {},
          created_at: "2026-03-24T10:00:00Z",
          updated_at: "2026-03-24T10:00:00Z"
        });
      }

      if (url.endsWith("/jobs") && init?.method === "POST") {
        const payload = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : {};
        const type = String(payload.job_type || "");
        if (type === "transport_search") {
          return jsonResponse({ id: "job_transport_m62", job_type: type, state: "queued", progress_percent: 0, created_at: "2026-03-24T10:00:00Z" });
        }
        if (type === "zone_generation") {
          return jsonResponse({ id: "job_zone_m62", job_type: type, state: "queued", progress_percent: 0, created_at: "2026-03-24T10:00:00Z" });
        }
        if (type === "zone_enrichment") {
          return jsonResponse({ id: "job_enrich_m62", job_type: type, state: "queued", progress_percent: 0, created_at: "2026-03-24T10:00:00Z" });
        }
      }

      if (url.endsWith("/jobs/job_transport_m62") || url.endsWith("/jobs/job_zone_m62") || url.endsWith("/jobs/job_enrich_m62")) {
        return jsonResponse({
          id: "job_m62_done",
          job_type: "zone_generation",
          state: "completed",
          progress_percent: 100,
          current_stage: "completed",
          created_at: "2026-03-24T10:00:00Z"
        });
      }

      if (url.endsWith("/journeys/journey_m62/transport-points")) {
        return jsonResponse([
          {
            id: "tp_m62",
            journey_id: "journey_m62",
            source: "gtfs",
            name: "Parada Principal",
            lat: -23.55052,
            lon: -46.633308,
            walk_time_sec: 300,
            walk_distance_m: 350,
            route_ids: ["b1", "r1", "b3"],
            modal_types: ["bus", "rail", "bus"],
            route_count: 7,
            created_at: "2026-03-24T10:00:00Z"
          }
        ]);
      }

      if (url.endsWith("/journeys/journey_m62/zones")) {
        return jsonResponse({
          zones: [
            {
              id: "zone_id_1",
              journey_id: "journey_m62",
              transport_point_id: "tp_m62",
              fingerprint: "zone_1",
              state: "complete",
              travel_time_minutes: 41,
              walk_distance_meters: 350,
              isochrone_geom: {
                type: "Polygon",
                coordinates: [[[-46.67, -23.57], [-46.64, -23.57], [-46.64, -23.54], [-46.67, -23.54], [-46.67, -23.57]]]
              },
              poi_counts: {
                parque: 12,
                farmacia: 11,
                mercado: 10,
                escola: 9,
                academia: 8,
                restaurante: 7,
                hospital: 6
              },
              badges_provisional: false,
              created_at: "2026-03-24T10:00:00Z",
              updated_at: "2026-03-24T10:00:00Z"
            }
          ],
          total_count: 1,
          completed_count: 1
        });
      }

      if (url.includes("/journeys/") && url.includes("/zones/zone_1/price-rollups")) {
        const parsed = new URL(url);
        expect(parsed.searchParams.get("days")).toBe("30");
        return jsonResponse(rollups);
      }

      return jsonResponse({ detail: "not found" }, 404);
    });

    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    await triggerMapClick(-23.55052, -46.633308);
    await user.click(screen.getByRole("button", { name: "Achar pontos de transporte" }));
    await screen.findByRole("heading", { name: /Ponto de transporte/i });
    await user.click(screen.getByRole("button", { name: /Gerar zonas/i }));
    await screen.findByText(/Payload válido: 1 zonas consolidadas\./i);

    await user.click(screen.getByRole("button", { name: "Comparação" }));
    await user.click(screen.getByRole("button", { name: "Carregar detalhamento" }));
    await screen.findAllByText(/Detalhamento concluído\./i);

    await user.click(screen.getByRole("button", { name: "Análise" }));
    await user.click(screen.getByRole("button", { name: "Dashboard" }));

    expect(await screen.findByTestId("m6-dashboard-panel")).toBeInTheDocument();
    expect(screen.getByText(/Histórico mediano \(30 dias\)/i)).toBeInTheDocument();
    expect(screen.getByTestId("m6-linechart-points")).toHaveTextContent("Pontos exibidos: 30");
    expect(screen.getByTestId("m6-monthly-variation")).toHaveTextContent("n/d");
    expect(screen.getByTestId("m6-seed-travel")).toHaveTextContent("41 min");
    expect(screen.getByText(/Distribuição por faixas \(10 buckets\)/i)).toBeInTheDocument();
    expect(screen.getByText(/7 linhas \(3 usadas\)/i)).toBeInTheDocument();

    const poisPanel = screen.getByTestId("m6-top-pois");
    expect(within(poisPanel).getAllByRole("listitem")).toHaveLength(6);
    expect(within(poisPanel).getByText(/parque/i)).toBeInTheDocument();
    expect(within(poisPanel).queryByText(/hospital/i)).not.toBeInTheDocument();

    const rollupsCalls = fetchMock.mock.calls.filter((call) =>
      String(call[0]).includes("/price-rollups")
    );
    expect(rollupsCalls.length).toBeGreaterThan(0);
    },
    15_000
  );
});
