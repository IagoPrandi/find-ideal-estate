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