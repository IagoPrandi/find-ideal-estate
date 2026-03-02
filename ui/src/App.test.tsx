import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

type MapClickEvent = {
  lngLat: {
    lat: number;
    lng: number;
  };
};

let clickHandler: ((event: MapClickEvent) => void) | null = null;

vi.mock("mapbox-gl", () => {
  class MockPopup {
    setHTML() {
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

    on(event: string, callback: ((event: MapClickEvent) => void) | (() => void)) {
      if (event === "load") {
        (callback as () => void)();
      }
      if (event === "click") {
        clickHandler = callback as (event: MapClickEvent) => void;
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
    addLayer() {
      return this;
    }
    setLayoutProperty() {
      return this;
    }
    getCenter() {
      return { lat: -23.55052, lng: -46.633308 };
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
      }
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

    expect(screen.getByRole("heading", { name: "Imóvel Ideal" })).toBeInTheDocument();

    const createRunButton = screen.getByRole("button", {
      name: "Gerar Zonas Candidatas"
    });

    expect(createRunButton).toBeDisabled();
    expect(screen.getByText(/Defina o ponto principal/i)).toBeInTheDocument();
  });

  it("opens and closes help modal", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Abrir ajuda" }));
    expect(screen.getByRole("heading", { name: /Ajuda — FE1/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Fechar" }));
    expect(screen.queryByRole("heading", { name: /Ajuda — FE1/i })).not.toBeInTheDocument();
  });

  it("toggles panel minimize and restore", async () => {
    const user = userEvent.setup();
    render(<App />);

    const toggleButton = screen.getByRole("button", { name: "Minimizar" });
    await user.click(toggleButton);

    expect(screen.getByRole("button", { name: "Abrir" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Abrir" }));
    expect(screen.getByRole("button", { name: "Minimizar" })).toBeInTheDocument();
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

    expect(await screen.findByText(/Payload válido: 1 zonas consolidadas\./i)).toBeInTheDocument();
    expect(await screen.findAllByText(/Zonas candidatas prontas\./i)).not.toHaveLength(0);
    expect(screen.getByRole("button", { name: "Ir para passo 2" })).toHaveClass("bg-primary");
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

    await user.click(screen.getByRole("button", { name: "Adicionar interesse" }));

    const longLabel =
      "Academia com nome extremamente longo para validar renderização sem overflow e com responsividade no painel lateral";
    await user.type(screen.getByPlaceholderText("Ex.: Academia XYZ"), longLabel);

    await triggerMapClick(-23.612345, -46.598765);

    expect(await screen.findByText(longLabel)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Imóvel Ideal" })).toBeInTheDocument();
  });
});
