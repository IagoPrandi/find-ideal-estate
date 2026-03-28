import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FindIdealApp } from "./FindIdealApp";
import { useJourneyStore, useUIStore } from "../../state";
import { getJourneyTransportPoints, getJourneyZonesList, getZoneListings } from "../../api/client";

const mapEaseToMock = vi.fn();
const mapLayerClickHandlers: Record<string, (event: { features?: Array<{ properties?: Record<string, unknown> }> }) => void> = {};

vi.mock("../../components/panels", () => ({
  WizardPanel: () => <div>Wizard panel</div>
}));

vi.mock("../../api/client", () => ({
  API_BASE: "http://localhost:8000",
  getJourneyTransportPoints: vi.fn(),
  getJourneyZonesList: vi.fn(),
  getZoneListings: vi.fn()
}));

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
    setLayoutProperty() {
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
    Object.keys(mapLayerClickHandlers).forEach((key) => delete mapLayerClickHandlers[key]);

    useJourneyStore.getState().resetJourney();
    useUIStore.getState().resetUI();
    useUIStore.setState((state) => ({ ...state, step: 6 }));
    useJourneyStore.setState((state) => ({
      ...state,
      journeyId: "journey-1",
      selectedZoneFingerprint: "zone-fp-1"
    }));

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
});