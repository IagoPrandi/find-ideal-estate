import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FindIdealApp } from "./FindIdealApp";
import { useJourneyStore, useUIStore } from "../../state";
import { getBusLineDetails, getBusStopDetails, getJourneyTransportPoints, getJourneyZonesList, getTransportStopDetails, getZoneListings } from "../../api/client";

const mapEaseToMock = vi.fn();
const mapSetLayoutPropertyMock = vi.fn();
const mapSetFilterMock = vi.fn();
let lastPopupHtml = "";
const mapLayerClickHandlers: Record<string, (event: any) => void> = {};
const mapEventHandlers: Record<string, Array<(event?: any) => void>> = {};
const loadedSourceIds = new Set<string>();
const mapAddedLayers: Array<Record<string, any>> = [];
const mapSourceData: Record<string, unknown> = {};

function emitMapEvent(event: string, payload?: any) {
  for (const handler of mapEventHandlers[event] || []) {
    handler(payload);
  }
}

vi.mock("../../components/panels", () => ({
  WizardPanel: () => <div>Wizard panel</div>
}));

vi.mock("../../api/client", () => ({
  API_BASE: "http://localhost:8000",
  getBusLineDetails: vi.fn(),
  getBusStopDetails: vi.fn(),
  getTransportStopDetails: vi.fn(),
  getJourneyTransportPoints: vi.fn(),
  getJourneyZonesList: vi.fn(),
  getZoneListings: vi.fn()
}));

vi.mock("maplibre-gl", () => {
  class MockPopup {
    setLngLat() {
      return this;
    }
    setHTML(html?: string) {
      lastPopupHtml = html || "";
      return this;
    }
    addTo() {
      return this;
    }
    on() {
      return this;
    }
    getElement() {
      return document.body;
    }
    remove() {
      return this;
    }
  }

  class MockMarker {
    setLngLat() {
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
      layerOrCallback: string | (() => void) | ((event: { features?: Array<{ properties?: Record<string, unknown> }> }) => void),
      maybeCallback?: (event: { features?: Array<{ properties?: Record<string, unknown> }> }) => void
    ) {
      if (event === "load") {
        const callback = typeof layerOrCallback === "function" ? layerOrCallback : maybeCallback;
        callback?.();
      }
      if (typeof layerOrCallback === "function" && event !== "load") {
        mapEventHandlers[event] = [...(mapEventHandlers[event] || []), layerOrCallback];
      }
      if (event === "click" && typeof layerOrCallback === "string" && maybeCallback) {
        mapLayerClickHandlers[layerOrCallback] = maybeCallback;
      }
      return this;
    }
    hasImage() {
      return false;
    }
    addImage() {
      return this;
    }
    addSource(name: string) {
      this.sources[name] = {
        setData: (data: unknown) => {
          mapSourceData[name] = data;
        }
      };
      return this;
    }
    getSource(name: string) {
      return this.sources[name];
    }
    addLayer(layer: Record<string, any>) {
      this.layers.add(layer.id);
      mapAddedLayers.push(layer);
      return this;
    }
    getLayer(id: string) {
      return this.layers.has(id) ? { id } : undefined;
    }
    isSourceLoaded(sourceId: string) {
      return loadedSourceIds.has(sourceId);
    }
    setLayoutProperty(layerId: string, property: string, value: string) {
      mapSetLayoutPropertyMock(layerId, property, value);
      return this;
    }
    setFilter(layerId: string, filter: unknown) {
      mapSetFilterMock(layerId, filter);
      return this;
    }
    queryRenderedFeatures() {
      return [];
    }
    getCanvas() {
      return { style: { cursor: "" } };
    }
    getZoom() {
      return 10.7;
    }
    easeTo(payload: unknown) {
      mapEaseToMock(payload);
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
      <FindIdealApp />
    </QueryClientProvider>
  );
}

describe("FindIdealApp", () => {
  beforeEach(() => {
    mapEaseToMock.mockReset();
    mapSetLayoutPropertyMock.mockReset();
    mapSetFilterMock.mockReset();
    lastPopupHtml = "";
    Object.keys(mapLayerClickHandlers).forEach((key) => delete mapLayerClickHandlers[key]);
    Object.keys(mapEventHandlers).forEach((key) => delete mapEventHandlers[key]);
    loadedSourceIds.clear();
    mapAddedLayers.length = 0;
    Object.keys(mapSourceData).forEach((key) => delete mapSourceData[key]);

    useJourneyStore.getState().resetJourney();
    useUIStore.getState().resetUI();
    useUIStore.setState((state) => ({ ...state, step: 6 }));
    useJourneyStore.setState((state) => ({
      ...state,
      journeyId: "journey-1",
      selectedZoneFingerprint: "zone-fp-1"
    }));

    vi.mocked(getBusLineDetails).mockResolvedValue({ count: 0, buses: [], source: "gtfs" } as never);
    vi.mocked(getBusStopDetails).mockResolvedValue({ count: 0, buses: [], source: "gtfs" } as never);
    vi.mocked(getTransportStopDetails).mockResolvedValue({ count: 0, buses: [], source: "gtfs_stop" } as never);
    vi.mocked(getJourneyTransportPoints).mockResolvedValue([] as never);
    vi.mocked(getJourneyZonesList).mockResolvedValue({ zones: [], total_count: 0, completed_count: 0 } as never);
    vi.mocked(getZoneListings).mockResolvedValue({
      source: "cache",
      job_id: null,
      freshness_status: "fresh",
      listings: [
        {
          property_id: "prop-1",
          platform: "quintoandar",
          platform_listing_id: "qa-1",
          address_normalized: "Rua Dentro, 10",
          current_best_price: "3500",
          condo_fee: "500",
          iptu: "100",
          inside_zone: true,
          has_coordinates: true,
          lat: -23.5,
          lon: -46.7,
          platforms_available: ["quintoandar"]
        }
      ],
      total_count: 1,
      cache_age_hours: 0.1
    } as never);
  });

  it("centers the map when a card selection is pushed into shared state", async () => {
    renderWithQueryClient();

    await waitFor(() => {
      expect(getZoneListings).toHaveBeenCalled();
    });

    await act(async () => {
      useJourneyStore.getState().setSelectedListingKey("property:prop-1");
    });

    await waitFor(() => {
      expect(mapEaseToMock).toHaveBeenCalledWith(
        expect.objectContaining({
          center: [-46.7, -23.5]
        })
      );
    });
  });

  it("writes the selected listing key when the user clicks a listing point", async () => {
    renderWithQueryClient();

    await waitFor(() => {
      expect(mapLayerClickHandlers["journey-listings-layer"]).toBeTypeOf("function");
    });

    await act(async () => {
      mapLayerClickHandlers["journey-listings-layer"]({
        features: [{ properties: { listing_key: "property:prop-1" } }]
      });
    });

    expect(useJourneyStore.getState().selectedListingKey).toBe("property:prop-1");
  });

  it("loads transport points first, then lines, then green areas and finally flood areas", async () => {
    useJourneyStore.setState((state) => ({
      ...state,
      config: {
        ...state.config,
        enrichments: {
          ...state.config.enrichments,
          green: true,
        },
      },
    }));

    renderWithQueryClient();

    await waitFor(() => {
      expect(mapSetLayoutPropertyMock).toHaveBeenCalledWith("bus-stop-layer", "visibility", "visible");
      expect(mapSetLayoutPropertyMock).toHaveBeenCalledWith("bus-line-layer", "visibility", "none");
      expect(mapSetLayoutPropertyMock).toHaveBeenCalledWith("green-layer", "visibility", "none");
      expect(mapSetLayoutPropertyMock).toHaveBeenCalledWith("flood-layer", "visibility", "none");
    });

    loadedSourceIds.add("transport-stops-source");
    await act(async () => {
      emitMapEvent("sourcedata", { dataType: "source", sourceId: "transport-stops-source" });
    });

    await waitFor(() => {
      expect(mapSetLayoutPropertyMock).toHaveBeenCalledWith("bus-line-layer", "visibility", "visible");
    });

    loadedSourceIds.add("transport-lines-source");
    await act(async () => {
      emitMapEvent("sourcedata", { dataType: "source", sourceId: "transport-lines-source" });
    });

    await waitFor(() => {
      expect(mapSetLayoutPropertyMock).toHaveBeenCalledWith("green-layer", "visibility", "visible");
      expect(mapSetLayoutPropertyMock).toHaveBeenCalledWith("flood-layer", "visibility", "none");
    });

    loadedSourceIds.add("green-areas-source");
    await act(async () => {
      emitMapEvent("sourcedata", { dataType: "source", sourceId: "green-areas-source" });
    });

    await waitFor(() => {
      expect(mapSetLayoutPropertyMock).toHaveBeenCalledWith("flood-layer", "visibility", "visible");
    });
  });

  it("keeps overlapping zones visually distinguishable on the map", async () => {
    vi.mocked(getJourneyZonesList).mockResolvedValue({
      zones: [
        {
          id: "zone-1",
          journey_id: "journey-1",
          fingerprint: "zone-fp-1",
          state: "complete",
          travel_time_minutes: 6,
          isochrone_geom: {
            type: "Polygon",
            coordinates: [[[-46.633, -23.548], [-46.629, -23.548], [-46.629, -23.544], [-46.633, -23.544], [-46.633, -23.548]]]
          }
        },
        {
          id: "zone-2",
          journey_id: "journey-1",
          fingerprint: "zone-fp-2",
          state: "complete",
          travel_time_minutes: 8,
          isochrone_geom: {
            type: "Polygon",
            coordinates: [[[-46.632, -23.547], [-46.628, -23.547], [-46.628, -23.543], [-46.632, -23.543], [-46.632, -23.547]]]
          }
        }
      ],
      total_count: 2,
      completed_count: 2
    } as never);

    renderWithQueryClient();

    await waitFor(() => {
      const sourceData = mapSourceData["journey-zones-source-runtime"] as { features: Array<{ properties: Record<string, unknown> }> } | undefined;
      expect(sourceData?.features).toHaveLength(2);
      expect(sourceData?.features[0]?.properties.fill_color).toBeDefined();
      expect(sourceData?.features[1]?.properties.fill_color).toBeDefined();
      expect(sourceData?.features[0]?.properties.fill_color).not.toEqual(sourceData?.features[1]?.properties.fill_color);
      expect(sourceData?.features[0]?.properties.label_color).toBeDefined();
    });

    const labelLayer = mapAddedLayers.find((layer) => layer.id === "zones-runtime-label-layer");
    expect(labelLayer?.layout?.["text-allow-overlap"]).toBe(true);
    expect(labelLayer?.layout?.["text-ignore-placement"]).toBe(true);
  });

  it("renders selected zone POIs on the map with category metadata and popup", async () => {
    vi.mocked(getJourneyZonesList).mockResolvedValue({
      zones: [
        {
          id: "zone-1",
          journey_id: "journey-1",
          fingerprint: "zone-fp-1",
          state: "complete",
          travel_time_minutes: 8,
          poi_counts: { school: 1, pharmacy: 1, restaurant: 1, gym: 1, supermarket: 0, park: 0 },
          poi_points: [
            {
              kind: "poi",
              id: "poi-1",
              name: "Colegio Centro",
              category: "school",
              address: "Rua A, 10",
              lat: -23.552,
              lon: -46.632
            },
            {
              kind: "poi",
              id: "poi-2",
              name: "Farmacia Vida",
              category: "pharmacy",
              address: "Rua B, 20",
              lat: -23.551,
              lon: -46.631
            },
            {
              kind: "poi",
              id: "poi-3",
              name: "Restaurante Central",
              category: "restaurant",
              address: "Rua C, 30",
              lat: -23.55,
              lon: -46.63
            },
            {
              kind: "poi",
              id: "poi-4",
              name: "Academia Movimento",
              category: "gym",
              address: "Rua D, 40",
              lat: -23.549,
              lon: -46.629
            }
          ],
          isochrone_geom: {
            type: "Polygon",
            coordinates: [[[-46.633, -23.553], [-46.629, -23.553], [-46.629, -23.549], [-46.633, -23.549], [-46.633, -23.553]]]
          }
        }
      ],
      total_count: 1,
      completed_count: 1
    } as never);

    renderWithQueryClient();

    await waitFor(() => {
      const sourceData = mapSourceData["journey-zone-pois-source-runtime"] as { features: Array<{ properties: Record<string, unknown> }> } | undefined;
      expect(sourceData?.features).toHaveLength(4);
      expect(sourceData?.features.map((feature) => feature.properties.category)).toEqual(["school", "pharmacy", "restaurant", "gym"]);
    });

    await act(async () => {
      useJourneyStore.getState().setActivePoiCategory("restaurant");
      useJourneyStore.getState().setSelectedPoiKey("zone-fp-1:restaurant:poi-3");
    });

    await waitFor(() => {
      const sourceData = mapSourceData["journey-zone-pois-source-runtime"] as { features: Array<{ properties: Record<string, unknown> }> } | undefined;
      expect(sourceData?.features).toHaveLength(1);
      expect(sourceData?.features[0]?.properties.category).toBe("restaurant");
      expect(sourceData?.features[0]?.properties.selected).toBe(true);
    });

    expect(mapAddedLayers.find((layer) => layer.id === "zone-pois-layer")).toBeDefined();
    expect(mapAddedLayers.find((layer) => layer.id === "zone-pois-highlight-layer")).toBeDefined();

    await act(async () => {
      useJourneyStore.getState().setActivePoiCategory("all");
    });

    await act(async () => {
      mapLayerClickHandlers["zone-pois-layer"]({
        lngLat: { lng: -46.632, lat: -23.552 },
        features: [{ properties: { name: "Colegio Centro", category: "school", address: "Rua A, 10", selection_key: "zone-fp-1:school:poi-1" } }]
      });
    });

    expect(useJourneyStore.getState().selectedPoiKey).toBe("zone-fp-1:school:poi-1");
    expect(lastPopupHtml).toContain("Escola");
    expect(lastPopupHtml).toContain("Colegio Centro");
    expect(lastPopupHtml).toContain("Rua A, 10");
  });

  it("opens the layers panel, toggles layer visibility and closes on outside click", async () => {
    renderWithQueryClient();

    const toggleButton = screen.getByRole("button", { name: "Camadas" });
    fireEvent.click(toggleButton);

    const panel = screen.getByText(/Camadas do mapa/i).closest("div");
    if (!panel) {
      throw new Error("Layers panel not rendered.");
    }

    const greenCheckbox = within(panel).getByRole("checkbox", { name: "Área verde" });
    fireEvent.click(greenCheckbox);

    await waitFor(() => {
      expect(mapSetLayoutPropertyMock).toHaveBeenCalledWith("green-layer", "visibility", "none");
    });

    fireEvent.mouseDown(document.body);

    await waitFor(() => {
      expect(screen.queryByText(/Camadas do mapa/i)).not.toBeInTheDocument();
    });
  });

  it("filters the green layer according to the selected vegetation level", async () => {
    useJourneyStore.setState((state) => ({
      ...state,
      config: {
        ...state.config,
        greenVegetationLevel: "high",
        enrichments: {
          ...state.config.enrichments,
          green: true
        }
      }
    }));

    renderWithQueryClient();

    await waitFor(() => {
      expect(mapSetFilterMock).toHaveBeenCalledWith("green-layer", ["in", "vegetation_level", "low", "medium", "high"]);
    });

    await act(async () => {
      useJourneyStore.getState().setConfig({ greenVegetationLevel: "low" });
    });

    await waitFor(() => {
      expect(mapSetFilterMock).toHaveBeenLastCalledWith("green-layer", ["in", "vegetation_level", "low"]);
    });
  });

  it("loads real bus stop details for the popup instead of showing n/d", async () => {
    vi.mocked(getTransportStopDetails).mockResolvedValue({
      count: 7,
      buses: ["875A-10", "175T-10"],
      source: "gtfs"
    } as never);

    renderWithQueryClient();

    await waitFor(() => {
      expect(mapLayerClickHandlers["bus-stop-layer"]).toBeTypeOf("function");
    });

    await act(async () => {
      mapLayerClickHandlers["bus-stop-layer"]({
        lngLat: { lng: -46.65, lat: -23.57 },
        features: [{ properties: { id: "stop-1", name: "R. Tabapuã, 49", source_kind: "gtfs_stop" } }]
      });
    });

    await waitFor(() => {
      expect(getTransportStopDetails).toHaveBeenCalledWith("stop-1", "gtfs_stop");
      expect(lastPopupHtml).toContain("Ônibus identificados: <strong>7</strong>");
      expect(lastPopupHtml).toContain("875A-10");
    });
  });

  it("does not fetch bus stop details when the tile already carries inline bus metadata", async () => {
    renderWithQueryClient();

    await waitFor(() => {
      expect(mapLayerClickHandlers["bus-stop-layer"]).toBeTypeOf("function");
    });

    await act(async () => {
      mapLayerClickHandlers["bus-stop-layer"]({
        lngLat: { lng: -46.65, lat: -23.57 },
        features: [{ properties: { id: "stop-inline", name: "R. Tabapuã, 49", bus_count: 7, bus_list: "175T-10||875A-10" } }]
      });
    });

    expect(getTransportStopDetails).not.toHaveBeenCalledWith("stop-inline", expect.any(String));
    expect(lastPopupHtml).toContain("Ônibus identificados: <strong>7</strong>");
    expect(lastPopupHtml).toContain("175T-10");
    expect(lastPopupHtml).toContain("875A-10");
  });
});