import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FavoritesPanel } from "./FavoritesPanel";
import { useFavoritesStore } from "../../state";
import { getZoneFavoriteAnalytics } from "../../api/client";

vi.mock("../../api/client", () => ({
  getZoneFavoriteAnalytics: vi.fn(),
  getAccountFavorites: vi.fn(),
  saveAccountFavorite: vi.fn(),
  deleteAccountFavorite: vi.fn(),
}));

function renderPanel() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <FavoritesPanel />
    </QueryClientProvider>,
  );
}

describe("FavoritesPanel", () => {
  beforeEach(() => {
    useFavoritesStore.getState().resetFavoritesState();
    useFavoritesStore.setState({
      isAuthenticated: true,
      isPanelOpen: true,
      activeTab: "compare",
      selectedMetricIds: ["listing_total_price"],
      favorites: [
        {
          listingKey: "property:cheap",
          journeyId: "journey-1",
          zoneFingerprint: "zone-cheap",
          searchType: "rent",
          usageType: "all",
          savedAt: "2026-03-27T10:00:00Z",
          listing: {
            property_id: "cheap",
            platform: "quintoandar",
            platform_listing_id: "qa-1",
            address_normalized: "Rua Mais Barata, 10",
            url: "/imovel/cheap",
            current_best_price: "3000",
            current_unit_price: 50,
            area_m2: 60,
            bedrooms: 2,
            inside_zone: true,
            has_coordinates: true,
            lat: -23.5,
            lon: -46.7,
            platforms_available: ["quintoandar"],
            platform_variants: [],
          },
        },
        {
          listingKey: "property:green",
          journeyId: "journey-2",
          zoneFingerprint: "zone-green",
          searchType: "rent",
          usageType: "all",
          savedAt: "2026-03-27T11:00:00Z",
          listing: {
            property_id: "green",
            platform: "vivareal",
            platform_listing_id: "vr-1",
            address_normalized: "Rua Mais Verde, 20",
            url: "/imovel/green",
            current_best_price: "5000",
            current_unit_price: 70,
            area_m2: 72,
            bedrooms: 3,
            inside_zone: true,
            has_coordinates: true,
            lat: -23.49,
            lon: -46.69,
            platforms_available: ["vivareal"],
            platform_variants: [],
          },
        },
      ],
    });

    vi.mocked(getZoneFavoriteAnalytics).mockImplementation(async (_journeyId, zoneFingerprint) => {
      if (zoneFingerprint === "zone-green") {
        return {
          context: {
            zone_fingerprint: zoneFingerprint,
            neighborhood_name: "Zona Verde",
            city_name: "São Paulo",
            state_code: "SP",
            zone_area_m2: 120000,
          },
          metrics: {
            zone_average_price: 9000,
            zone_average_unit_price: 80,
            homicide_density_per_km2: 0.01,
            robbery_density_per_km2: 1.2,
            theft_density_per_km2: 2.8,
            crime_density_per_km2: 4.01,
            green_percentage: 35,
            flood_percentage: 0.5,
            flood_risk_label: "Baixo",
          },
        } as never;
      }

      return {
        context: {
          zone_fingerprint: zoneFingerprint,
          neighborhood_name: "Zona Econômica",
          city_name: "São Paulo",
          state_code: "SP",
          zone_area_m2: 110000,
        },
        metrics: {
          zone_average_price: 8500,
          zone_average_unit_price: 65,
          homicide_density_per_km2: 0.02,
          robbery_density_per_km2: 3.1,
          theft_density_per_km2: 5.4,
          crime_density_per_km2: 8.52,
          green_percentage: 12,
          flood_percentage: 1.8,
          flood_risk_label: "Moderado",
        },
      } as never;
    });
  });

  it("uses the selected metrics as the single source of truth for ranking and matrix columns", async () => {
    renderPanel();

    expect(screen.getByText("2 imóveis salvos na sua conta.")).toBeInTheDocument();

    await waitFor(() => {
      expect(getZoneFavoriteAnalytics).toHaveBeenCalledTimes(2);
    });

    const ranking = await screen.findByTestId("favorites-ranking");
    const matrix = screen.getByTestId("favorites-matrix");

    expect(within(matrix).getByText("Valor total")).toBeInTheDocument();
    expect(within(matrix).queryByText("Arborização")).not.toBeInTheDocument();
    expect(within(ranking).getAllByText(/Rua Mais/i)[0]).toHaveTextContent("Rua Mais Barata, 10");
    expect(within(ranking).getByText("Venceu 1 de 1 métrica selecionada")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Mais arborização/i }));

    await waitFor(() => {
      expect(within(matrix).getByText("Arborização")).toBeInTheDocument();
    });

    expect(within(ranking).getAllByText("Venceu 1 de 2 métricas selecionadas")).toHaveLength(2);

    fireEvent.click(screen.getByRole("button", { name: /Menos roubo/i }));

    await waitFor(() => {
      expect(within(ranking).getAllByText(/Rua Mais/i)[0]).toHaveTextContent("Rua Mais Verde, 20");
    });

    expect(within(ranking).getByText("Venceu 2 de 3 métricas selecionadas")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Menor valor total/i }));

    await waitFor(() => {
      expect(within(matrix).queryByText("Valor total")).not.toBeInTheDocument();
    });

    expect(within(ranking).getAllByText(/Rua Mais/i)[0]).toHaveTextContent("Rua Mais Verde, 20");
    expect(within(ranking).getByText("Venceu 2 de 2 métricas selecionadas")).toBeInTheDocument();
  });

  it("shows the current ranking position inside each saved favorite card", async () => {
    useFavoritesStore.setState((state) => ({
      ...state,
      activeTab: "saved",
      selectedMetricIds: ["listing_total_price", "zone_green_percentage"],
    }));

    renderPanel();

    await waitFor(() => {
      expect(getZoneFavoriteAnalytics).toHaveBeenCalled();
    });

    expect(await screen.findByTestId("favorite-saved-rank-property:cheap")).toHaveTextContent("2º no ranking");
    expect(screen.getByTestId("favorite-saved-rank-property:green")).toHaveTextContent("1º no ranking");
  });
});