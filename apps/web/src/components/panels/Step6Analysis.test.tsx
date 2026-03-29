import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Step6Analysis } from "./Step6Analysis";
import { useJourneyStore, useUIStore } from "../../state";
import { getJob, getJourneyZonesList, getPriceRollups, getZoneListings } from "../../api/client";

vi.mock("../../api/client", () => ({
  apiActionHint: (error: unknown) => (error instanceof Error ? error.message : "erro"),
  getJob: vi.fn(),
  getJourneyZonesList: vi.fn(),
  getPriceRollups: vi.fn(),
  getZoneListings: vi.fn()
}));

const scrollIntoViewMock = vi.fn();

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
      <Step6Analysis />
    </QueryClientProvider>
  );
}

describe("Step6Analysis", () => {
  beforeEach(() => {
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: scrollIntoViewMock
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
    vi.mocked(getPriceRollups).mockResolvedValue([] as never);
    vi.mocked(getJourneyZonesList).mockResolvedValue({
      zones: [],
      total_count: 0,
      completed_count: 0
    } as never);
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
    useJourneyStore.getState().resetJourney();
    useUIStore.getState().resetUI();
  });

  it("shows per-platform scrape progress while listings job is running", async () => {
    renderWithQueryClient();

    const progressPanel = await screen.findByTestId("listings-platform-progress");
    const progressGrid = within(progressPanel).getByTestId("listings-platform-progress-grid");

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

    renderWithQueryClient();

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

    renderWithQueryClient();

    expect(await screen.findByText(/Rua Dentro, 10/i)).toBeInTheDocument();
    expect(screen.getByText(/R\$\s*4\.100/i)).toBeInTheDocument();
    expect(screen.getByText(/Rua Fora, 20/i)).toBeInTheDocument();
    expect(screen.getByText(/Endereço sem coordenadas/i)).toBeInTheDocument();
    expect(screen.getByText(/1 dentro da zona · 1 fora da zona · 1 sem coordenadas/i)).toBeInTheDocument();
    expect(screen.getByAltText(/Rua Fora, 20/i)).toHaveAttribute("src", "https://www.vivareal.com.br/listing-images/vr-1.webp");

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

    renderWithQueryClient();

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

    renderWithQueryClient();

    await screen.findByText(/Rua Dentro, 10/i);

    useJourneyStore.getState().setSelectedListingKey("property:prop-1");

    await waitFor(() => {
      expect(scrollIntoViewMock).toHaveBeenCalled();
    });

    scrollIntoViewMock.mockClear();

    await act(async () => {
      useJourneyStore.getState().setListingsFilters({ minPrice: "0" });
    });

    await waitFor(() => {
      expect(screen.getByDisplayValue("0")).toBeInTheDocument();
    });

    expect(scrollIntoViewMock).not.toHaveBeenCalled();
  });
});