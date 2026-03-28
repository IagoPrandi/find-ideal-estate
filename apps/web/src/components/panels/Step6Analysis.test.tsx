import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
    useJourneyStore.getState().resetJourney();
    useUIStore.getState().resetUI();
  });

  it("shows per-platform scrape progress while listings job is running", async () => {
    renderWithQueryClient();

    const progressPanel = await screen.findByTestId("listings-platform-progress");

    expect(progressPanel).toBeInTheDocument();
    expect(within(progressPanel).getByText(/Progresso por plataforma/i)).toBeInTheDocument();
    expect(screen.getByText(/Job de listings: 67%/i)).toBeInTheDocument();
    expect(within(progressPanel).getByText(/^QuintoAndar$/i)).toBeInTheDocument();
    expect(within(progressPanel).getByText(/^VivaReal$/i)).toBeInTheDocument();
    expect(within(progressPanel).getByText(/^ZapImóveis$/i)).toBeInTheDocument();
    expect(within(progressPanel).getByText(/^Concluída$/i)).toBeInTheDocument();
    expect(within(progressPanel).getByText(/Raspando agora nesta plataforma/i)).toBeInTheDocument();
    expect(within(progressPanel).getByText(/96 anúncios raspados no worker/i)).toBeInTheDocument();

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

    expect(await screen.findByTestId("listings-platform-progress")).toBeInTheDocument();
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
          current_best_price: "4200",
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
    expect(screen.getByText(/Rua Fora, 20/i)).toBeInTheDocument();
    expect(screen.getByText(/Endereço sem coordenadas/i)).toBeInTheDocument();
    expect(screen.getByText(/1 dentro da zona · 1 fora da zona · 1 sem coordenadas/i)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Escopo espacial/i), {
      target: { value: "inside_zone" }
    });

    expect(screen.getByText(/Rua Dentro, 10/i)).toBeInTheDocument();
    expect(screen.queryByText(/Rua Fora, 20/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Endereço sem coordenadas/i)).not.toBeInTheDocument();
  });
});