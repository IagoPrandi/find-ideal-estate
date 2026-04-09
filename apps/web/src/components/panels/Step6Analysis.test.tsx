import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Step6Analysis } from "./Step6Analysis";
import { useJourneyStore, useUIStore } from "../../state";
import { getJob, getZoneDashboardAnalytics, getZoneListings } from "../../api/client";

vi.mock("../../api/client", () => ({
  apiActionHint: (error: unknown) => (error instanceof Error ? error.message : "erro"),
  getJob: vi.fn(),
  getZoneDashboardAnalytics: vi.fn(),
  getZoneListings: vi.fn()
}));

const scrollIntoViewMock = vi.fn();
const scrollToMock = vi.fn();

async function renderWithQueryClient() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0
      }
    }
  });

  let view!: ReturnType<typeof render>;
  await act(async () => {
    view = render(
      <QueryClientProvider client={queryClient}>
        <Step6Analysis />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(queryClient.isFetching()).toBe(0);
    });
  });

  return view;
}

describe("Step6Analysis", () => {
  beforeEach(() => {
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: scrollIntoViewMock
    });
    Object.defineProperty(HTMLElement.prototype, "scrollTo", {
      configurable: true,
      value: scrollToMock
    });

    useJourneyStore.getState().resetJourney();
    useUIStore.getState().resetUI();
    useJourneyStore.setState((state) => ({
      ...state,
      journeyId: "journey-1",
      selectedZoneFingerprint: "zone-fp-1",
      listingsJobId: "listings-job-1"
    }));

    vi.mocked(getZoneListings).mockResolvedValue({
      source: "none",
      job_id: "listings-job-1",
      freshness_status: "no_cache",
      listings: [],
      total_count: 0,
      cache_age_hours: null
    } as never);
    vi.mocked(getZoneDashboardAnalytics).mockImplementation(async (_journeyId, _zoneFingerprint, _searchType, options) => {
      const selectedPriceCity = typeof options === "object" && options?.cityName
        ? options.cityName
        : null;
      const selectedSafetyCity = typeof options === "object" && options?.cityName
        ? options.cityName
        : null;

      const priceRankingByCity = {
        "São Paulo": [
          { neighborhood_name: "Aclimação", city_name: "São Paulo", value: 87.4, yearly_change_pct: -3.8, listing_count: 2 },
          { neighborhood_name: "Brooklin", city_name: "São Paulo", value: 92.1, yearly_change_pct: -3.1, listing_count: 3 },
          { neighborhood_name: "Campo Belo", city_name: "São Paulo", value: 96.8, yearly_change_pct: -2.7, listing_count: 4 },
          { neighborhood_name: "Itaim Bibi", city_name: "São Paulo", value: 99.5, yearly_change_pct: -2.5, listing_count: 7 },
          { neighborhood_name: "Moema", city_name: "São Paulo", value: 101.2, yearly_change_pct: -1.9, listing_count: 5 },
          { neighborhood_name: "Pinheiros", city_name: "São Paulo", value: 104.9, yearly_change_pct: -1.1, listing_count: 4 },
          { neighborhood_name: "República", city_name: "São Paulo", value: 106.3, yearly_change_pct: 0.4, listing_count: 2 },
          { neighborhood_name: "Saúde", city_name: "São Paulo", value: 109.8, yearly_change_pct: 1.2, listing_count: 3 },
          { neighborhood_name: "Vila Mariana", city_name: "São Paulo", value: 111.4, yearly_change_pct: 2.1, listing_count: 2 },
          { neighborhood_name: "Santana", city_name: "São Paulo", value: 114.2, yearly_change_pct: 3.4, listing_count: 1 },
        ],
        "Barueri": [
          { neighborhood_name: "Alphaville", city_name: "Barueri", value: 75.2, yearly_change_pct: 1.4, listing_count: 8 },
          { neighborhood_name: "Tamboré", city_name: "Barueri", value: 78.6, yearly_change_pct: 1.1, listing_count: 4 },
          { neighborhood_name: "Centro", city_name: "Barueri", value: 81.3, yearly_change_pct: 0.8, listing_count: 2 },
          { neighborhood_name: "Jardim Belval", city_name: "Barueri", value: 83.9, yearly_change_pct: 0.5, listing_count: 1 },
        ],
      } as const;
      const priceRankingSource = selectedPriceCity
        ? priceRankingByCity[selectedPriceCity as keyof typeof priceRankingByCity] || priceRankingByCity["São Paulo"]
        : [...priceRankingByCity["São Paulo"], ...priceRankingByCity["Barueri"]];
      const selectedPriceNeighborhood = selectedPriceCity === "Barueri" ? "Alphaville" : "Itaim Bibi";
      const priceRanking = [...priceRankingSource]
        .sort((left, right) => left.value - right.value || left.neighborhood_name.localeCompare(right.neighborhood_name, "pt-BR"))
        .map((item, index) => ({
          ...item,
          position: index + 1,
          is_selected: item.neighborhood_name === selectedPriceNeighborhood,
        }));
      const selectedRankingItem = priceRanking.find((item) => item.is_selected) || priceRanking[0];
      const safetyRankingByCity = {
        "São Paulo": [
          { neighborhood_name: "Sé", city_name: "São Paulo", value: 1280 },
          { neighborhood_name: "República", city_name: "São Paulo", value: 1174 },
          { neighborhood_name: "Pinheiros", city_name: "São Paulo", value: 1098 },
          { neighborhood_name: "Moema", city_name: "São Paulo", value: 1002 },
          { neighborhood_name: "Jardim Paulista", city_name: "São Paulo", value: 928 },
          { neighborhood_name: "Itaim Bibi", city_name: "São Paulo", value: 841 },
          { neighborhood_name: "Brooklin", city_name: "São Paulo", value: 704 },
          { neighborhood_name: "Campo Belo", city_name: "São Paulo", value: 640 },
          { neighborhood_name: "Saúde", city_name: "São Paulo", value: 522 },
          { neighborhood_name: "Vila Mariana", city_name: "São Paulo", value: 418 },
        ],
        "Barueri": [
          { neighborhood_name: "Alphaville", city_name: "Barueri", value: 212 },
          { neighborhood_name: "Centro", city_name: "Barueri", value: 165 },
          { neighborhood_name: "Tamboré", city_name: "Barueri", value: 121 },
          { neighborhood_name: "Jardim Belval", city_name: "Barueri", value: 96 },
        ],
      } as const;
      const selectedSafetyNeighborhood = selectedSafetyCity === "Barueri" ? "Alphaville" : "Itaim Bibi";
      const safetyRankingSource = selectedSafetyCity
        ? safetyRankingByCity[selectedSafetyCity as keyof typeof safetyRankingByCity] || safetyRankingByCity["São Paulo"]
        : [...safetyRankingByCity["São Paulo"], ...safetyRankingByCity["Barueri"]];
      const safetyRanking = [...safetyRankingSource]
        .sort((left, right) => right.value - left.value || left.neighborhood_name.localeCompare(right.neighborhood_name, "pt-BR"))
        .map((item, index) => ({
          city_name: item.city_name,
          position: index + 1,
          neighborhood_name: item.neighborhood_name,
          value: item.value,
          is_selected: item.neighborhood_name === selectedSafetyNeighborhood,
        }));
      const resolvedSafetyNeighborhood = safetyRanking.find((item) => item.is_selected)?.neighborhood_name || safetyRanking[0]?.neighborhood_name || null;

      return {
        context: {
          zone_fingerprint: "zone-fp-1",
          neighborhood_name: selectedRankingItem.neighborhood_name,
          city_name: selectedPriceCity,
          state_code: null,
          zone_area_m2: 120000,
        },
        price: {
          city_options: ["Barueri", "São Paulo"],
          selected_city: selectedPriceCity,
          ranking_scope_label: "Valor médio do m² por bairro",
          ranking_scope_note: "O ranking abaixo usa o valor médio do m² considerando apenas anúncios ativos com coordenadas dentro da zona analisada.",
          selected_neighborhood_name: selectedRankingItem.neighborhood_name,
          zone_average_price: 10850,
          zone_average_unit_price: selectedPriceCity === "Barueri" ? 79.75 : 99.5,
          zone_yearly_change_pct: selectedPriceCity === "Barueri" ? 1.1 : -2.5,
          zone_active_listing_count: selectedPriceCity === "Barueri" ? 15 : 42,
          neighborhood_average_unit_price: selectedRankingItem.value,
          neighborhood_unit_price_rank: {
            position: selectedRankingItem.position,
            total: priceRanking.length,
            percentile: 77.78,
            scope_label: selectedPriceCity ? `Bairros com anuncios ativos dentro da zona em ${selectedPriceCity}` : "Bairros com anuncios ativos dentro da zona",
            direction: "lower_better",
            note: null,
          },
          neighborhood_unit_price_ranking: priceRanking,
          yearly_change_pct: selectedRankingItem.yearly_change_pct,
          yearly_change_rank: {
            position: selectedRankingItem.position,
            total: priceRanking.length,
            percentile: 66.67,
            scope_label: selectedPriceCity ? `Bairros com anuncios ativos dentro da zona em ${selectedPriceCity}` : "Bairros com anuncios ativos dentro da zona",
            direction: "lower_better",
            note: null,
          },
          history: [
            { date: "2026-03-01", zone_average_price: 11200, neighborhood_average_price: 10900 + selectedRankingItem.position * 20 },
            { date: "2026-03-15", zone_average_price: 11000, neighborhood_average_price: 10800 + selectedRankingItem.position * 20 },
          ],
          price_distribution: [
            { label: "até 3 mil", count: 0 },
            { label: "3-5 mil", count: 1 },
            { label: "5-8 mil", count: 2 },
          ],
          note: null,
        },
        safety: {
          city_options: ["Barueri", "São Paulo"],
          selected_city: selectedSafetyCity,
          ranking_scope_label: "Bairros na zona analisada",
          ranking_scope_note: "O ranking abaixo soma todas as ocorrencias registradas por bairro dentro da zona analisada. Sem filtro de cidade, a lista considera todas as cidades disponiveis; quando preenchido, restringe apenas os bairros exibidos.",
          rate_scale_base: null,
          selected_neighborhood_name: resolvedSafetyNeighborhood,
          homicide_count_365d: 6,
          homicide_density_per_km2: 0.06,
          homicide_rank: { position: 2, total: 6, percentile: 83.33, scope_label: "Zonas da jornada atual", direction: "lower_better", note: null },
          robbery_count_365d: 996,
          robbery_density_per_km2: 9.96,
          robbery_rate_rank: { position: 3, total: 6, percentile: 66.67, scope_label: "Zonas da jornada atual", direction: "lower_better", note: null },
          robbery_rate_ranking: safetyRanking,
          theft_count_365d: 3519,
          robbery_to_theft_ratio: 0.28,
          robbery_to_theft_rank: { position: 3, total: 6, percentile: 66.67, scope_label: "Zonas da jornada atual", direction: "lower_better", note: null },
          peak_hours: [
            { hour: 8, total_count: 2, homicide_count: 0, robbery_count: 0, theft_count: 1 },
            { hour: 18, total_count: 4, homicide_count: 0, robbery_count: 1, theft_count: 1 },
          ],
        },
        environment: {
          ranking_scope_label: "Zonas da jornada atual",
          ranking_scope_note: "A base atual nao inclui malha oficial de bairros para seguranca e ambiente; os rankings desta pagina usam as zonas geradas e persistidas nesta jornada.",
          green_area_m2: 32000,
          green_percentage: 26.6,
          green_rank: { position: 2, total: 6, percentile: 83.33, scope_label: "Zonas da jornada atual", direction: "higher_better", note: null },
          flood_area_m2: 1200,
          flood_percentage: 1.0,
          flood_risk_label: "Moderado",
          flood_rank: { position: 3, total: 6, percentile: 66.67, scope_label: "Zonas da jornada atual", direction: "lower_better", note: null },
        },
      } as never;
    });
    vi.mocked(getJob).mockResolvedValue({
      id: "listings-job-1",
      journey_id: "journey-1",
      job_type: "listings_scrape",
      state: "running",
      progress_percent: 67,
      current_stage: "listings_scrape",
      cancel_requested_at: null,
      started_at: "2026-03-27T10:00:00Z",
      finished_at: null,
      worker_id: "worker-1",
      error_code: null,
      error_message: null,
      created_at: "2026-03-27T10:00:00Z",
      result_ref: {
        scrape_diagnostics: {
          status: "scraping",
          active_platform: "vivareal",
          total_duration_ms: 90000,
          platform_order: ["quintoandar", "vivareal", "zapimoveis"],
          summary: {
            total_scraped: 96,
            platforms_completed: ["quintoandar"],
            platforms_failed: []
          },
          platforms: {
            quintoandar: {
              status: "completed",
              persisted_count: 84,
              total_duration_ms: 45485
            },
            vivareal: {
              status: "scraping",
              scraped_count: 12,
              scrape_duration_ms: 32000
            },
            zapimoveis: {
              status: "pending"
            }
          }
        }
      }
    } as never);
  });

  afterEach(() => {
    vi.clearAllMocks();
    scrollIntoViewMock.mockReset();
    scrollToMock.mockReset();
  });

  it("shows per-platform scrape progress while listings job is running", async () => {
    await renderWithQueryClient();

    const progressPanel = await screen.findByTestId("listings-platform-progress");
    const progressGrid = within(progressPanel).getByTestId("listings-platform-progress-grid");

    await waitFor(() => {
      expect(getZoneListings).toHaveBeenCalledWith("journey-1", "zone-fp-1", "rent", "all", "all");
    });

    expect(progressPanel).toBeInTheDocument();
    expect(progressGrid.className).toContain("grid-cols-1");
    expect(within(progressPanel).getByText(/Progresso por plataforma/i)).toBeInTheDocument();
    expect(screen.getByText(/Job de listings: 67%/i)).toBeInTheDocument();
    expect(within(progressPanel).getByText(/^QuintoAndar$/i)).toBeInTheDocument();
    expect(within(progressPanel).getByText(/^VivaReal$/i)).toBeInTheDocument();
    expect(within(progressPanel).getByText(/^ZapImóveis$/i)).toBeInTheDocument();
    expect(within(progressPanel).getByText(/^Concluída$/i)).toBeInTheDocument();
    expect(within(progressPanel).getByText(/Raspando agora nesta plataforma/i)).toBeInTheDocument();
    expect(within(progressPanel).getByText(/96 anúncios raspados no worker/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /recolher progresso do scraping/i })).toHaveAttribute("aria-expanded", "true");

    await waitFor(() => {
      expect(getJob).toHaveBeenCalledWith("listings-job-1");
    });
  });

  it("explains when scraping completed but no listings fell inside the zone", async () => {
    vi.mocked(getZoneListings).mockResolvedValue({
      source: "cache",
      job_id: null,
      freshness_status: "fresh",
      listings: [],
      total_count: 0,
      cache_age_hours: 0.1
    } as never);
    vi.mocked(getJob).mockResolvedValue({
      id: "listings-job-1",
      journey_id: "journey-1",
      job_type: "listings_scrape",
      state: "completed",
      progress_percent: 100,
      current_stage: "listings_scrape",
      cancel_requested_at: null,
      started_at: "2026-03-27T10:00:00Z",
      finished_at: "2026-03-27T10:03:00Z",
      worker_id: "worker-1",
      error_code: null,
      error_message: null,
      created_at: "2026-03-27T10:00:00Z",
      result_ref: {
        scrape_diagnostics: {
          status: "complete",
          total_duration_ms: 180000,
          platform_order: ["quintoandar", "vivareal", "zapimoveis"],
          summary: {
            total_scraped: 210,
            platforms_completed: ["quintoandar", "vivareal", "zapimoveis"],
            platforms_failed: []
          },
          platforms: {
            quintoandar: { status: "completed", persisted_count: 70 },
            vivareal: { status: "completed", persisted_count: 60 },
            zapimoveis: { status: "completed", persisted_count: 80 }
          }
        }
      }
    } as never);

    await renderWithQueryClient();

    const progressPanel = await screen.findByTestId("listings-platform-progress");
    const progressToggle = screen.getByRole("button", { name: /expandir progresso do scraping/i });

    expect(progressPanel).toBeInTheDocument();
    expect(progressToggle).toHaveAttribute("aria-expanded", "false");
    expect(within(progressPanel).queryByText(/^QuintoAndar$/i)).not.toBeInTheDocument();

    fireEvent.click(progressToggle);

    expect(screen.getByRole("button", { name: /recolher progresso do scraping/i })).toHaveAttribute("aria-expanded", "true");
    expect(within(progressPanel).getByText(/^QuintoAndar$/i)).toBeInTheDocument();
    expect(screen.getByText(/Resultado consolidado/i)).toBeInTheDocument();
    expect(screen.getByText(/raspou 210 anúncios, mas nenhum permaneceu elegível para esta busca após os filtros do backend/i)).toBeInTheDocument();
    expect(screen.getByText(/Job de listings: 100%/i)).toBeInTheDocument();
  });

  it("shows all scraped listings by default and lets the user filter to only inside-zone matches", async () => {
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
          area_m2: 70,
          inside_zone: true,
          has_coordinates: true,
          lat: -23.5,
          lon: -46.7,
          platforms_available: ["quintoandar"]
        },
        {
          property_id: "prop-2",
          platform: "vivareal",
          platform_listing_id: "vr-1",
          address_normalized: "Rua Fora, 20",
          image_url: "/listing-images/vr-1.webp",
          current_best_price: "4200",
          condo_fee: "300",
          iptu: "50",
          area_m2: 90,
          inside_zone: false,
          has_coordinates: true,
          lat: -23.49,
          lon: -46.69,
          platforms_available: ["vivareal"]
        },
        {
          property_id: "prop-3",
          platform: "zapimoveis",
          platform_listing_id: "zap-1",
          address_normalized: "Endereço sem coordenadas",
          current_best_price: "3900",
          condo_fee: "250",
          iptu: "25",
          area_m2: 50,
          inside_zone: false,
          has_coordinates: false,
          lat: null,
          lon: null,
          platforms_available: ["zapimoveis"]
        }
      ],
      total_count: 3,
      cache_age_hours: 0.1
    } as never);
    vi.mocked(getJob).mockResolvedValue({
      id: "listings-job-1",
      journey_id: "journey-1",
      job_type: "listings_scrape",
      state: "completed",
      progress_percent: 100,
      current_stage: "listings_scrape",
      cancel_requested_at: null,
      started_at: "2026-03-27T10:00:00Z",
      finished_at: "2026-03-27T10:03:00Z",
      worker_id: "worker-1",
      error_code: null,
      error_message: null,
      created_at: "2026-03-27T10:00:00Z",
      result_ref: {
        scrape_diagnostics: {
          status: "complete",
          summary: {
            total_scraped: 3,
            platforms_completed: ["quintoandar", "vivareal", "zapimoveis"],
            platforms_failed: []
          },
          platforms: {}
        }
      }
    } as never);

    await renderWithQueryClient();

    expect(await screen.findByText(/Rua Dentro, 10/i)).toBeInTheDocument();
    expect(screen.getByText(/R\$\s*4\.100/i)).toBeInTheDocument();
    expect(screen.getByText(/Rua Fora, 20/i)).toBeInTheDocument();
    expect(screen.getByText(/Endereço sem coordenadas/i)).toBeInTheDocument();
    expect(screen.getByText(/1 dentro da zona · 1 fora da zona · 1 sem coordenadas/i)).toBeInTheDocument();
    expect(screen.getByAltText(/Rua Fora, 20/i)).toHaveAttribute("src", "https://www.vivareal.com.br/listing-images/vr-1.webp");
    expect(screen.getByTestId("listings-sort-price").querySelector("svg")).toHaveClass("lucide-chevron-up");
    expect(screen.getByTestId("listings-sort-size").querySelector("svg")).toHaveClass("lucide-minus");

    expect(
      Array.from(document.querySelectorAll('[data-testid^="listing-card-"]')).map((card) => card.textContent || "")
    ).toEqual([
      expect.stringContaining("Rua Dentro, 10"),
      expect.stringContaining("Endereço sem coordenadas"),
      expect.stringContaining("Rua Fora, 20")
    ]);

    fireEvent.click(screen.getByTestId("listings-sort-price"));

    expect(screen.getByTestId("listings-sort-price").querySelector("svg")).toHaveClass("lucide-chevron-down");
    expect(screen.getByTestId("listings-sort-size").querySelector("svg")).toHaveClass("lucide-minus");
    expect(
      Array.from(document.querySelectorAll('[data-testid^="listing-card-"]')).map((card) => card.textContent || "")
    ).toEqual([
      expect.stringContaining("Rua Fora, 20"),
      expect.stringContaining("Endereço sem coordenadas"),
      expect.stringContaining("Rua Dentro, 10")
    ]);

    fireEvent.click(screen.getByTestId("listings-sort-size"));

    expect(screen.getByTestId("listings-sort-price").querySelector("svg")).toHaveClass("lucide-minus");
    expect(screen.getByTestId("listings-sort-size").querySelector("svg")).toHaveClass("lucide-chevron-up");
    expect(
      Array.from(document.querySelectorAll('[data-testid^="listing-card-"]')).map((card) => card.textContent || "")
    ).toEqual([
      expect.stringContaining("Endereço sem coordenadas"),
      expect.stringContaining("Rua Dentro, 10"),
      expect.stringContaining("Rua Fora, 20")
    ]);

    fireEvent.click(screen.getByRole("button", { name: /recolher filtros de imóveis/i }));
    expect(screen.getByRole("button", { name: /expandir filtros de imóveis/i })).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByLabelText(/Escopo espacial/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /expandir filtros de imóveis/i }));
    expect(screen.getByRole("button", { name: /recolher filtros de imóveis/i })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByLabelText(/Escopo espacial/i)).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("listing-card-property:prop-2"));
    expect(useJourneyStore.getState().selectedListingKey).toBe("property:prop-2");

    fireEvent.change(screen.getByLabelText(/Escopo espacial/i), {
      target: { value: "inside_zone" }
    });

    expect(screen.getByText(/Rua Dentro, 10/i)).toBeInTheDocument();
    expect(screen.queryByText(/Rua Fora, 20/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Endereço sem coordenadas/i)).not.toBeInTheDocument();
  });

  it("shows per-platform prices and ad links when hovering the duplicated availability badge", async () => {
    vi.mocked(getZoneListings).mockResolvedValue({
      source: "cache",
      job_id: null,
      freshness_status: "fresh",
      listings: [
        {
          property_id: "prop-1",
          platform: "zapimoveis",
          platform_listing_id: "zap-1",
          address_normalized: "Avenida Ana Costa, 100",
          current_best_price: "4500",
          condo_fee: null,
          iptu: null,
          duplication_badge: "Disponível em 2 plataformas · menor: R$ 4.500",
          inside_zone: true,
          has_coordinates: true,
          lat: -23.967,
          lon: -46.332,
          platforms_available: ["quintoandar", "zapimoveis"],
          platform_variants: [
            {
              platform: "zapimoveis",
              platform_listing_id: "zap-1",
              url: "/imovel/aluguel-santos-sp-gonzaga/zap-1/",
              current_best_price: "4500",
              condo_fee: null,
              iptu: null,
              observed_at: "2026-03-29T12:00:00Z"
            },
            {
              platform: "quintoandar",
              platform_listing_id: "qa-1",
              url: "https://www.quintoandar.com.br/imovel/qa-1",
              current_best_price: "4700",
              condo_fee: "300",
              iptu: null,
              observed_at: "2026-03-29T12:05:00Z"
            }
          ]
        }
      ],
      total_count: 1,
      cache_age_hours: 0.1
    } as never);
    vi.mocked(getJob).mockResolvedValue({
      id: "listings-job-1",
      journey_id: "journey-1",
      job_type: "listings_scrape",
      state: "completed",
      progress_percent: 100,
      current_stage: "listings_scrape",
      cancel_requested_at: null,
      started_at: "2026-03-27T10:00:00Z",
      finished_at: "2026-03-27T10:03:00Z",
      worker_id: "worker-1",
      error_code: null,
      error_message: null,
      created_at: "2026-03-27T10:00:00Z",
      result_ref: {
        scrape_diagnostics: {
          status: "complete",
          summary: {
            total_scraped: 1,
            platforms_completed: ["quintoandar", "zapimoveis"],
            platforms_failed: []
          },
          platforms: {}
        }
      }
    } as never);

    await renderWithQueryClient();

    const badgeText = await screen.findByText(/Disponível em 2 plataformas/i);
    const badge = badgeText.closest("button") as HTMLButtonElement | null;
    expect(badge).not.toBeNull();
    fireEvent.mouseEnter(badge as HTMLButtonElement);

    const popover = await screen.findByTestId("listing-platform-popover-property:prop-1");
    expect(within(popover).getByText(/Preços por plataforma/i)).toBeInTheDocument();
    expect(within(popover).getByText(/^ZapImóveis$/i)).toBeInTheDocument();
    expect(within(popover).getByText(/^QuintoAndar$/i)).toBeInTheDocument();
    expect(within(popover).getByText(/R\$\s*4\.500/i)).toBeInTheDocument();
    expect(within(popover).getByText(/R\$\s*5\.000/i)).toBeInTheDocument();
    expect(within(popover).getByRole("link", { name: /Abrir anúncio na ZapImóveis/i })).toHaveAttribute("href", "https://www.zapimoveis.com.br/imovel/aluguel-santos-sp-gonzaga/zap-1/");
    expect(within(popover).getByRole("link", { name: /Abrir anúncio na QuintoAndar/i })).toHaveAttribute("href", "https://www.quintoandar.com.br/imovel/qa-1");
  });

  it("renders the price metrics inline in the listing card", async () => {
    vi.mocked(getZoneListings).mockResolvedValue({
      source: "cache",
      job_id: null,
      freshness_status: "fresh",
      listings: [
        {
          property_id: "prop-1",
          platform: "quintoandar",
          platform_listing_id: "qa-1",
          address_normalized: "Rua Itacema, Itaim Bibi, São Paulo, SP",
          neighborhood_name: "Itaim Bibi",
          city_name: "São Paulo",
          current_best_price: "11000",
          current_unit_price: 104.76,
          neighborhood_median_unit_price: 99.5,
          current_vs_neighborhood_pct: 5.29,
          condo_fee: "1500",
          iptu: "400",
          area_m2: 105,
          inside_zone: true,
          has_coordinates: true,
          lat: -23.58,
          lon: -46.68,
          platforms_available: ["quintoandar"],
        },
      ],
      total_count: 1,
      cache_age_hours: 0.1,
    } as never);
    vi.mocked(getJob).mockResolvedValue({
      id: "listings-job-1",
      journey_id: "journey-1",
      job_type: "listings_scrape",
      state: "completed",
      progress_percent: 100,
      current_stage: "listings_scrape",
      cancel_requested_at: null,
      started_at: "2026-03-27T10:00:00Z",
      finished_at: "2026-03-27T10:03:00Z",
      worker_id: "worker-1",
      error_code: null,
      error_message: null,
      created_at: "2026-03-27T10:00:00Z",
      result_ref: { scrape_diagnostics: { status: "complete", summary: { total_scraped: 1, platforms_completed: ["quintoandar"], platforms_failed: [] }, platforms: {} } },
    } as never);

    await renderWithQueryClient();

    const listingCard = await screen.findByTestId("listing-card-property:prop-1");

    await waitFor(() => {
      expect(getZoneDashboardAnalytics).toHaveBeenCalledWith("journey-1", "zone-fp-1", "rent", { page: "preco" });
    });

    expect(vi.mocked(getZoneDashboardAnalytics).mock.calls.some((call) => call[3] === "prop-1")).toBe(false);
    expect(within(listingCard).queryByRole("button", { name: /Ver Acessibilidade/i })).not.toBeInTheDocument();
    expect(within(listingCard).getByText(/R\$\s*105\/m²/i)).toBeInTheDocument();
    expect(within(listingCard).getByText(/\+18\.9%/i)).toBeInTheDocument();
    expect(within(listingCard).queryByText(/Valor por m²/i)).not.toBeInTheDocument();
    expect(within(listingCard).queryByText(/Média do recorte:\s*R\$\s*10\.850/i)).not.toBeInTheDocument();

    fireEvent.mouseEnter(within(listingCard).getByTestId("listing-price-delta-trigger-property:prop-1"));
    expect(await within(listingCard).findByTestId("listing-price-delta-tooltip-property:prop-1")).toHaveTextContent(/Média do recorte:\s*R\$\s*10\.850/i);

    expect(within(listingCard).getByRole("button", { name: /Anúncio indisponível/i })).toBeDisabled();
  });

  it("scrolls the matching card into view when the map selects a listing", async () => {
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
    vi.mocked(getJob).mockResolvedValue({
      id: "listings-job-1",
      journey_id: "journey-1",
      job_type: "listings_scrape",
      state: "completed",
      progress_percent: 100,
      current_stage: "listings_scrape",
      cancel_requested_at: null,
      started_at: "2026-03-27T10:00:00Z",
      finished_at: "2026-03-27T10:03:00Z",
      worker_id: "worker-1",
      error_code: null,
      error_message: null,
      created_at: "2026-03-27T10:00:00Z",
      result_ref: { scrape_diagnostics: { status: "complete", summary: { total_scraped: 1, platforms_completed: ["quintoandar"], platforms_failed: [] }, platforms: {} } }
    } as never);

    await renderWithQueryClient();

    await screen.findByText(/Rua Dentro, 10/i);

    await act(async () => {
      useJourneyStore.getState().setSelectedListingKey("property:prop-1");
    });

    await waitFor(() => {
      expect(scrollToMock).toHaveBeenCalled();
    });

    scrollToMock.mockClear();

    await act(async () => {
      useJourneyStore.getState().setListingsFilters({ minPrice: "0" });
    });

    await waitFor(() => {
      expect(screen.getByDisplayValue("0")).toBeInTheDocument();
    });

    expect(scrollToMock).not.toHaveBeenCalled();
  });

  it("navigates the redesigned analytical dashboard across the three internal pages", async () => {
    vi.mocked(getZoneListings).mockResolvedValue({
      source: "cache",
      job_id: null,
      freshness_status: "fresh",
      listings: [
        {
          property_id: "prop-1",
          platform: "quintoandar",
          platform_listing_id: "qa-1",
          address_normalized: "Rua Itacema, Itaim Bibi, São Paulo, SP",
          current_best_price: "11000",
          condo_fee: "1500",
          iptu: "400",
          area_m2: 105,
          inside_zone: true,
          has_coordinates: true,
          lat: -23.58,
          lon: -46.68,
          platforms_available: ["quintoandar"],
        },
      ],
      total_count: 1,
      cache_age_hours: 0.1,
    } as never);
    vi.mocked(getJob).mockResolvedValue({
      id: "listings-job-1",
      journey_id: "journey-1",
      job_type: "listings_scrape",
      state: "completed",
      progress_percent: 100,
      current_stage: "listings_scrape",
      cancel_requested_at: null,
      started_at: "2026-03-27T10:00:00Z",
      finished_at: "2026-03-27T10:03:00Z",
      worker_id: "worker-1",
      error_code: null,
      error_message: null,
      created_at: "2026-03-27T10:00:00Z",
      result_ref: { scrape_diagnostics: { status: "complete", summary: { total_scraped: 1, platforms_completed: ["quintoandar"], platforms_failed: [] }, platforms: {} } },
    } as never);

    await renderWithQueryClient();

    await screen.findByText(/Rua Itacema, Itaim Bibi, São Paulo, SP/i);

    await waitFor(() => {
      expect(getZoneDashboardAnalytics).toHaveBeenCalledWith("journey-1", "zone-fp-1", "rent", { page: "preco" });
    });

    fireEvent.click(await screen.findByRole("button", { name: /Dashboard Analítico/i }));

    expect(await screen.findByTestId("dashboard-page-preco")).toBeInTheDocument();
    expect(screen.getByTestId("dashboard-price-ranking")).toBeInTheDocument();
    expect(screen.queryByText(/Três leituras da mesma zona/i)).not.toBeInTheDocument();
    expect(screen.getByText(/Preço médio do recorte/i)).toBeInTheDocument();
    expect(screen.getByText(/Preço médio ao longo do tempo/i)).toBeInTheDocument();
    expect(screen.queryByText(/Preço do imóvel vs bairro/i)).not.toBeInTheDocument();
    expect(screen.getByText(/Histograma do bairro destacado/i)).toBeInTheDocument();
    expect(screen.queryByText(/^Diferença vs bairro$/i)).not.toBeInTheDocument();
    expect(screen.getByText(/^Bairro com mais imóveis no recorte$/i)).toBeInTheDocument();
    expect(screen.queryByText(/Carregando métricas analíticas direto da base/i)).not.toBeInTheDocument();
    expect(screen.getAllByText(/R\$\s*99,50\/m²/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/-2\.5% em 365 dias/i)).toBeInTheDocument();

    const pricePage = screen.getByTestId("dashboard-page-preco");
    const priceQueries = within(pricePage);
    const priceCityCombobox = priceQueries.getByRole("combobox", { name: /Filtrar ranking de imóveis por cidade/i });
    expect(priceCityCombobox).toHaveValue("");
    fireEvent.focus(priceCityCombobox);
    expect(await priceQueries.findByRole("option", { name: /^Barueri$/i })).toBeInTheDocument();
    fireEvent.change(priceCityCombobox, { target: { value: "Baru" } });
    fireEvent.click(await priceQueries.findByRole("option", { name: /^Barueri$/i }));

    await waitFor(() => {
      expect(getZoneDashboardAnalytics).toHaveBeenCalledWith("journey-1", "zone-fp-1", "rent", {
        cityName: "Barueri",
        page: "preco",
        minPrice: null,
        maxPrice: null,
        usageType: "all",
        spatialScope: "all",
        minSize: null,
        maxSize: null,
      });
    });

    expect(await screen.findByText(/^Alphaville$/i)).toBeInTheDocument();
    expect(screen.getByText(/4 bairros/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Segurança/i }));
    const safetyPage = await screen.findByTestId("dashboard-page-seguranca");
    const safetyQueries = within(safetyPage);
    await waitFor(() => {
      expect(getZoneDashboardAnalytics).toHaveBeenCalledWith("journey-1", "zone-fp-1", "rent", { page: "seguranca" });
    });
    expect(safetyPage).toBeInTheDocument();
    expect(screen.getByText(/Horários de maior risco/i)).toBeInTheDocument();
    expect(screen.getByTestId("dashboard-safety-ranking")).toBeInTheDocument();
    const safetyCityCombobox = safetyQueries.getByRole("combobox", { name: /Filtrar ranking de segurança por cidade/i });
    expect(safetyCityCombobox).toHaveValue("");
    expect(safetyQueries.getByText(/14 bairros/i)).toBeInTheDocument();
    expect(safetyQueries.getByText(/9,960/i)).toBeInTheDocument();
    expect(screen.getByText(/996 roubos · por km²/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Ranking do bairro|Ranking de densidade de roubos por bairro/i })).toBeInTheDocument();
    expect(safetyQueries.getByText(/^Sé$/i)).toBeInTheDocument();
    expect(safetyQueries.getByText(/^República$/i)).toBeInTheDocument();
    expect(safetyQueries.getByText(/^Jardim Paulista$/i)).toBeInTheDocument();
    expect(safetyQueries.getByText(/^Itaim Bibi$/i)).toBeInTheDocument();
    expect(safetyQueries.getByText(/^Tamboré$/i)).toBeInTheDocument();
    expect(safetyQueries.getByText(/^Jardim Belval$/i)).toBeInTheDocument();
    expect(safetyQueries.queryByText(/^Moema$/i)).not.toBeInTheDocument();
    expect(safetyQueries.queryByText(/^Alphaville$/i)).not.toBeInTheDocument();
    expect(safetyQueries.getAllByText(/^\.\.\.$/)).toHaveLength(2);
    fireEvent.focus(safetyCityCombobox);
    expect(await safetyQueries.findByRole("option", { name: /^Barueri$/i })).toBeInTheDocument();
    fireEvent.change(safetyCityCombobox, { target: { value: "Baru" } });
    fireEvent.click(await safetyQueries.findByRole("option", { name: /^Barueri$/i }));

    await waitFor(() => {
      expect(getZoneDashboardAnalytics).toHaveBeenCalledWith("journey-1", "zone-fp-1", "rent", {
        cityName: "Barueri",
        page: "seguranca",
      });
    });

    expect(await screen.findByText(/^Alphaville$/i)).toBeInTheDocument();
    expect(screen.getByText(/4 bairros/i)).toBeInTheDocument();
    expect(screen.queryByText(/Crimes violentos/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Vegetação e alagamento/i }));
    await waitFor(() => {
      expect(getZoneDashboardAnalytics).toHaveBeenCalledWith("journey-1", "zone-fp-1", "rent", { page: "ambiente" });
    });
    expect(await screen.findByTestId("dashboard-page-ambiente")).toBeInTheDocument();
    expect(screen.getByText(/Percentual de arborização da zona/i)).toBeInTheDocument();
    expect(screen.getByText(/Moderado/i)).toBeInTheDocument();

    const dashboardCallsBeforeReopen = vi.mocked(getZoneDashboardAnalytics).mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: /^Imóveis/i }));
    expect(await screen.findByText(/Rua Itacema, Itaim Bibi, São Paulo, SP/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Dashboard Analítico/i }));

    expect(screen.queryByRole("button", { name: /Preparando dashboard/i })).not.toBeInTheDocument();
    expect(await screen.findByTestId("dashboard-page-preco")).toBeInTheDocument();
    expect(vi.mocked(getZoneDashboardAnalytics).mock.calls.length).toBe(dashboardCallsBeforeReopen);
  });

  it("propagates panel filters to the price dashboard and shows the active filter hero", async () => {
    useJourneyStore.getState().setListingsFilters({
      spatialScope: "inside_zone",
      usageType: "commercial",
      minPrice: "6000",
      maxPrice: "12000",
      minSize: "45",
    });

    vi.mocked(getZoneListings).mockResolvedValue({
      source: "cache",
      job_id: null,
      freshness_status: "fresh",
      listings: [
        {
          property_id: "prop-1",
          platform: "quintoandar",
          platform_listing_id: "qa-1",
          address_normalized: "Rua Itacema, Itaim Bibi, São Paulo, SP",
          current_best_price: "11000",
          condo_fee: "1500",
          iptu: "400",
          area_m2: 105,
          usage_type: "commercial",
          inside_zone: true,
          has_coordinates: true,
          lat: -23.58,
          lon: -46.68,
          platforms_available: ["quintoandar"],
        },
      ],
      total_count: 1,
      cache_age_hours: 0.1,
    } as never);
    vi.mocked(getJob).mockResolvedValue({
      id: "listings-job-1",
      journey_id: "journey-1",
      job_type: "listings_scrape",
      state: "completed",
      progress_percent: 100,
      current_stage: "listings_scrape",
      cancel_requested_at: null,
      started_at: "2026-03-27T10:00:00Z",
      finished_at: "2026-03-27T10:03:00Z",
      worker_id: "worker-1",
      error_code: null,
      error_message: null,
      created_at: "2026-03-27T10:00:00Z",
      result_ref: { scrape_diagnostics: { status: "complete", summary: { total_scraped: 1, platforms_completed: ["quintoandar"], platforms_failed: [] }, platforms: {} } },
    } as never);

    await renderWithQueryClient();

    fireEvent.click(await screen.findByRole("button", { name: /Dashboard Analítico/i }));

    await waitFor(() => {
      expect(vi.mocked(getZoneDashboardAnalytics).mock.calls).toContainEqual([
        "journey-1",
        "zone-fp-1",
        "rent",
        {
          cityName: null,
          page: "preco",
          minPrice: "6000",
          maxPrice: "12000",
          usageType: "commercial",
          spatialScope: "inside_zone",
          minSize: "45",
          maxSize: null,
        },
      ]);
    });

    const hero = await screen.findByTestId("dashboard-price-filters-hero");
    expect(within(hero).getByText(/Filtros aplicados:/i)).toBeInTheDocument();
    expect(within(hero).getByText(/escopo: apenas dentro da zona/i)).toBeInTheDocument();
    expect(within(hero).getByText(/tipo: comercial/i)).toBeInTheDocument();
    expect(within(hero).getByText(/preço: R\$ 6.000 a R\$ 12.000/i)).toBeInTheDocument();
    expect(within(hero).getByText(/área: a partir de 45 m²/i)).toBeInTheDocument();
  });
});