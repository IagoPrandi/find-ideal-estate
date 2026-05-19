import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  getAdminScrapingBatches,
  getAdminScrapingOverview,
  getAdminScrapingQueue,
  getAdminUsers,
  runAdminScrapingNow,
} from "../../api/client";
import { useAuth } from "../auth/AuthContext";
import { ScrapingAdminPage } from "./ScrapingAdminPage";

vi.mock("../auth/AuthContext", () => ({
  useAuth: vi.fn(),
}));

vi.mock("../../api/client", () => {
  class ApiError extends Error {
    status: number;
    recoverable: boolean;
    constructor(message: string, status = 400, recoverable = false) {
      super(message);
      this.status = status;
      this.recoverable = recoverable;
    }
  }
  return {
    ApiError,
    addAdminScrapingQueueAddresses: vi.fn(),
    cancelAdminScrapingBatch: vi.fn(),
    getAdminScrapingBatches: vi.fn(),
    getAdminScrapingOverview: vi.fn(),
    getAdminScrapingQueue: vi.fn(),
    getAdminUsers: vi.fn(),
    removeAdminScrapingQueueAddress: vi.fn(),
    runAdminScrapingNow: vi.fn(),
    updateAdminUserRole: vi.fn(),
  };
});

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ScrapingAdminPage />
    </QueryClientProvider>,
  );
}

function developerAuthContext() {
  return {
    authStatus: {
      is_authenticated: true,
      user: {
        id: "user-1",
        email: "dev@example.com",
        display_name: "Dev",
        is_active: true,
        is_superuser: true,
        role: "user",
        created_at: "2026-05-18T12:00:00Z",
      },
      session_expires_at: "2026-06-18T12:00:00Z",
    },
    isLoading: false,
    isSubmitting: false,
    errorMessage: null,
    isAuthModalOpen: false,
    refresh: vi.fn(),
    loginWithGoogle: vi.fn(),
    logout: vi.fn(),
    clearError: vi.fn(),
    openAuthModal: vi.fn(),
    closeAuthModal: vi.fn(),
  };
}

function mockDeveloperAuth() {
  vi.mocked(useAuth).mockReturnValue(developerAuthContext());
}

describe("ScrapingAdminPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockDeveloperAuth();
    vi.mocked(getAdminScrapingOverview).mockResolvedValue({
      scheduler_enabled: true,
      cron_hour: 3,
      cron_minute: 0,
      timezone: "UTC",
      next_run_at: "2026-05-19T03:00:00Z",
      seconds_until_next_run: 3600,
      lookback_hours: 24,
      limit: 100,
      active_job: null,
      latest_job: null,
      queue_count: 1,
    });
    vi.mocked(getAdminScrapingQueue).mockResolvedValue({
      items: [
        {
          search_location_normalized: "rua teste",
          search_location_label: "Rua Teste",
          search_location_type: "address",
          search_type: "rent",
          usage_type: "residential",
          demand_count: 1,
        },
      ],
      total_count: 1,
      limit: 100,
      lookback_hours: 24,
    });
    vi.mocked(getAdminScrapingBatches).mockResolvedValue({
      items: [],
      total_count: 0,
      limit: 20,
      offset: 0,
    });
    vi.mocked(getAdminUsers).mockResolvedValue({
      items: [],
      total_count: 0,
      limit: 50,
      offset: 0,
    });
    vi.mocked(runAdminScrapingNow).mockResolvedValue({
      job: {
        id: "job-1",
        journey_id: null,
        job_type: "listings_prewarm",
        state: "pending",
        progress_percent: 0,
        current_stage: "listings_prewarm",
        cancel_requested_at: null,
        started_at: null,
        finished_at: null,
        worker_id: null,
        result_ref: null,
        error_code: null,
        error_message: null,
        created_at: "2026-05-18T12:00:00Z",
      },
      target_count: 1,
      status: "queued",
    });
  });

  it("bloqueia a tela para usuario que nao e desenvolvedor", () => {
    vi.mocked(useAuth).mockReturnValue({
      ...developerAuthContext(),
      authStatus: {
        is_authenticated: true,
        user: {
          id: "user-2",
          email: "user@example.com",
          display_name: "User",
          is_active: true,
          is_superuser: false,
          role: "proprietario",
          created_at: "2026-05-18T12:00:00Z",
        },
        session_expires_at: "2026-06-18T12:00:00Z",
      },
      isLoading: false,
    });

    renderPage();

    expect(screen.getByText("Acesso restrito")).toBeInTheDocument();
  });

  it("executa scraping agora e mostra aviso de batelada criada", async () => {
    const user = userEvent.setup();
    renderPage();

    const button = await screen.findByRole("button", { name: /Executar agora/i });
    await user.click(button);

    await waitFor(() => {
      expect(runAdminScrapingNow).toHaveBeenCalledTimes(1);
    });
    expect(await screen.findByText("Batelada criada com 1 endereço(s).")).toBeInTheDocument();
  });
});
