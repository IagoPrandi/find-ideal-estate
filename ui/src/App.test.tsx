import { act, render, screen, waitFor, within } from "@testing-library/react";
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

vi.mock("mapbox-gl", () => {
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
    remove() {
      return this;
    }
  }

  return {
    default: {
      Map: MockMap,
      Marker: MockMarker,
      Popup: MockPopup,
      accessToken: ""
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

    expect(screen.getByRole("heading", { name: "Ponto de Referência" })).toBeInTheDocument();

    const createRunButton = screen.getByRole("button", {
      name: "Gerar Zonas Candidatas"
    });

    expect(createRunButton).toBeDisabled();
    expect(screen.getByText(/Defina o ponto principal/i)).toBeInTheDocument();
  });

  it("opens and closes help modal", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Ajuda" }));
    expect(screen.getByRole("heading", { name: /Ajuda — FE1/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Fechar" }));
    expect(screen.queryByRole("heading", { name: /Ajuda — FE1/i })).not.toBeInTheDocument();
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

    const rentButton = screen.getByRole("button", { name: "Alugar" });
    const buyButton = screen.getByRole("button", { name: "Comprar" });

    expect(rentButton).toHaveClass("bg-primary");
    await user.click(buyButton);
    expect(buyButton).toHaveClass("bg-primary");
  });

  it("covers FE6 happy path: reference -> generate zones -> step 2", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url.endsWith("/runs") && init?.method === "POST") {
        return jsonResponse({
          run_id: "run_fe6_ok",
          status: {
            state: "running",
            stage: "zones_raw"
          }
        });
      }

      if (url.endsWith("/runs/run_fe6_ok/status")) {
        return jsonResponse({
          run_id: "run_fe6_ok",
          status: {
            state: "success",
            stage: "zones_enriched"
          }
        });
      }

      if (url.endsWith("/runs/run_fe6_ok/zones")) {
        return jsonResponse({
          type: "FeatureCollection",
          features: [
            {
              type: "Feature",
              geometry: {
                type: "Polygon",
                coordinates: [
                  [
                    [-46.67, -23.57],
                    [-46.64, -23.57],
                    [-46.64, -23.54],
                    [-46.67, -23.54],
                    [-46.67, -23.57]
                  ]
                ]
              },
              properties: {
                zone_uid: "zone_1",
                score: 0.91,
                time_agg: 41
              }
            }
          ]
        });
      }

      return jsonResponse({ detail: "not found" }, 404);
    });

    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    await triggerMapClick(-23.55052, -46.633308);

    const createRunButton = screen.getByRole("button", {
      name: "Gerar Zonas Candidatas"
    });

    await waitFor(() => {
      expect(createRunButton).toBeEnabled();
    });

    await user.click(createRunButton);

    expect(await screen.findByRole("heading", { name: "Selecionar zona" })).toBeInTheDocument();
    expect(screen.getByText(/Zona 1/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Selecionar zona" })).toBeEnabled();
  });

  it("covers FE6 extreme empty state when zones payload has zero features", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url.endsWith("/runs") && init?.method === "POST") {
        return jsonResponse({
          run_id: "run_fe6_empty",
          status: {
            state: "running",
            stage: "zones_raw"
          }
        });
      }

      if (url.endsWith("/runs/run_fe6_empty/status")) {
        return jsonResponse({
          run_id: "run_fe6_empty",
          status: {
            state: "success",
            stage: "zones_enriched"
          }
        });
      }

      if (url.endsWith("/runs/run_fe6_empty/zones")) {
        return jsonResponse({
          type: "FeatureCollection",
          features: []
        });
      }

      return jsonResponse({ detail: "not found" }, 404);
    });

    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    await triggerMapClick(-23.551111, -46.631111);
    await user.click(screen.getByRole("button", { name: "Gerar Zonas Candidatas" }));

    expect(
      await screen.findByText(/Nenhuma zona consolidada retornada\. Revise os dados de referência\./i)
    ).toBeInTheDocument();
    expect(screen.getByText(/Estado:\s*empty/i)).toBeInTheDocument();
  });

  it("covers FE6 long-text scenario for interests and keeps panel functional", async () => {
    const user = userEvent.setup();
    render(<App />);

    const optionalInterestsHeading = screen.getByRole("heading", { name: /2\) Interesses \(opcional\)/i });
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
    expect(screen.getByRole("heading", { name: "Ponto de Referência" })).toBeInTheDocument();
  });
});
