import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createJourney } from "../../api/client";
import { useJourneyStore, useUIStore } from "../../state";
import { Step1Config } from "./Step1Config";

vi.mock("../../api/client", () => ({
  apiActionHint: (error: unknown) => (error instanceof Error ? error.message : "erro"),
  createJourney: vi.fn()
}));

vi.mock("../../features/auth/useEntitlements", () => ({
  useEntitlements: () => ({
    can_customize_distance: true,
    can_customize_max_time: true,
    max_walk_minutes_cap: null,
    max_car_minutes_cap: null,
  }),
}));

describe("Step1Config", () => {
  beforeEach(() => {
    useJourneyStore.getState().resetJourney();
    useUIStore.getState().resetUI();
    vi.mocked(createJourney).mockResolvedValue({ id: "journey-1" } as never);
  });

  it("shows the reference point placement button and toggles picking mode", () => {
    render(<Step1Config />);

    const button = screen.getByRole("button", { name: /Colocar ponto no mapa/i });
    expect(button).toHaveAttribute("aria-pressed", "false");
    expect(useJourneyStore.getState().isPickingReferencePoint).toBe(false);

    fireEvent.click(button);

    expect(useJourneyStore.getState().isPickingReferencePoint).toBe(true);
    expect(screen.getByRole("button", { name: /Clique no mapa para posicionar/i })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText(/Clique no mapa para posicionar\./i)).toBeInTheDocument();
  });

  it("shows the floating vegetation selector on hover and enables green when a level is chosen", () => {
    render(<Step1Config />);

    const greenCheckbox = screen.getByRole("checkbox", { name: /Áreas verdes/i });
    expect(greenCheckbox).not.toBeChecked();
    expect(screen.queryByRole("button", { name: /Pouca vegetação/i })).not.toBeInTheDocument();

    fireEvent.mouseEnter(screen.getByText(/Áreas verdes/i).closest("div") as HTMLElement);

    expect(screen.getByRole("button", { name: /Pouca vegetação/i })).toBeVisible();
    expect(screen.getByRole("button", { name: /Média vegetação/i })).toBeVisible();
    expect(screen.getByRole("button", { name: /Muita vegetação/i })).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: /Muita vegetação/i }));
    expect(useJourneyStore.getState().config.enrichments.green).toBe(true);
  });

  it("sends the selected vegetation level in the journey payload", async () => {
    useJourneyStore.getState().setPickedCoord({ lat: -23.55, lon: -46.63, label: "Trabalho" });
    render(<Step1Config />);

    fireEvent.mouseEnter(screen.getByText(/Áreas verdes/i).closest("div") as HTMLElement);
    fireEvent.click(screen.getByRole("button", { name: /Muita vegetação/i }));
    fireEvent.click(screen.getByRole("button", { name: /Comercial/i }));
    fireEvent.click(screen.getByRole("button", { name: /Encontrar pontos de transporte próximos/i }));

    await waitFor(() => {
      expect(createJourney).toHaveBeenCalledWith(
        expect.objectContaining({
          input_snapshot: expect.objectContaining({
            property_usage_type: "commercial",
            enrichments: expect.objectContaining({
              green: true,
              green_vegetation_level: "high"
            })
          })
        })
      );
    });
  });

  it("sends walk mode directly to the isochrone generation step", async () => {
    useJourneyStore.getState().setPickedCoord({ lat: -23.55, lon: -46.63, label: "Trabalho" });
    render(<Step1Config />);

    fireEvent.click(screen.getByRole("button", { name: /A pé/i }));
    fireEvent.change(screen.getByRole("slider", { name: /Tempo de caminhada/i }), { target: { value: "25" } });
    fireEvent.click(screen.getByRole("button", { name: /Gerar área acessível a pé/i }));

    await waitFor(() => {
      expect(createJourney).toHaveBeenCalledWith(
        expect.objectContaining({
          input_snapshot: expect.objectContaining({
            transport_mode: "walk",
            max_travel_minutes: 25,
            zone_radius_meters: null,
            transport_search_radius_meters: null,
          })
        })
      );
    });

    expect(useUIStore.getState().step).toBe(3);
    expect(useUIStore.getState().maxStep).toBe(3);
  });

  it("sends car mode directly to the isochrone generation step", async () => {
    useJourneyStore.getState().setPickedCoord({ lat: -23.55, lon: -46.63, label: "Trabalho" });
    render(<Step1Config />);

    fireEvent.click(screen.getByRole("button", { name: /Carro/i }));
    fireEvent.change(screen.getByRole("slider", { name: /Tempo de carro/i }), { target: { value: "30" } });
    fireEvent.click(screen.getByRole("button", { name: /Gerar área acessível de carro/i }));

    await waitFor(() => {
      expect(createJourney).toHaveBeenCalledWith(
        expect.objectContaining({
          input_snapshot: expect.objectContaining({
            transport_mode: "car",
            max_travel_minutes: 30,
            zone_radius_meters: null,
            transport_search_radius_meters: null,
          })
        })
      );
    });

    expect(useUIStore.getState().step).toBe(3);
    expect(useUIStore.getState().maxStep).toBe(3);
  });

  it("hides transport controls and stores a transport-free snapshot in area mode", async () => {
    render(<Step1Config />);

    fireEvent.click(screen.getByRole("button", { name: /Desenhar área/i }));

    expect(screen.getByText(/Tipo de imóvel para analisar/i)).toBeInTheDocument();
    expect(screen.getByText(/Análises nas zonas/i)).toBeInTheDocument();
    expect(screen.queryByText(/Como pretende se deslocar/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Público/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/Raio de busca do transporte/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Tempo de caminhada/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Tempo de carro/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Residencial/i }));
    fireEvent.click(screen.getByRole("button", { name: /Desenhar área no mapa/i }));

    await waitFor(() => {
      expect(createJourney).toHaveBeenCalledWith(
        expect.objectContaining({
          input_snapshot: expect.objectContaining({
            journey_input_mode: "area",
            property_usage_type: "residential",
            transport_mode: null,
            public_transport_mode: null,
            max_travel_minutes: null,
            zone_radius_meters: null,
            transport_search_radius_meters: null,
          })
        })
      );
    });

    expect(useJourneyStore.getState().pendingManualAreaDrawing).toBe(true);
    expect(useUIStore.getState().step).toBe(1);
  });
});
