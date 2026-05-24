import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  getAdminScrapingBatches,
  getAdminScrapingOverview,
  getAdminScrapingQueue,
  getAdminUsageRestrictions,
  getAdminUsers,
  runAdminScrapingNow,
  updateAdminGlobalUsageRestrictions,
  updateAdminUserScrapingPermission,
  updateAdminUserUsageRestrictions,
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
    getAdminUsageRestrictions: vi.fn(),
    getAdminUsers: vi.fn(),
    removeAdminScrapingQueueAddress: vi.fn(),
    runAdminScrapingNow: vi.fn(),
    updateAdminGlobalUsageRestrictions: vi.fn(),
    updateAdminUserRole: vi.fn(),
    updateAdminUserScrapingPermission: vi.fn(),
    updateAdminUserUsageRestrictions: vi.fn(),
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
        can_start_immediate_scraping: true,
        usage_restrictions_disabled: false,
        role: "user",
        created_at: "2026-05-18T12:00:00Z",
      },
      session_expires_at: "2026-06-18T12:00:00Z",
      usage_restrictions_disabled_globally: false,
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
    vi.mocked(getAdminUsageRestrictions).mockResolvedValue({
      usage_restrictions_disabled_globally: false,
    });
    vi.mocked(getAdminUsers).mockResolvedValue({
      items: [
        {
          id: "user-2",
          email: "morador@example.com",
          display_name: "Morador",
          is_active: true,
          is_superuser: false,
          can_start_immediate_scraping: false,
          usage_restrictions_disabled: false,
          role: "user",
          created_at: "2026-05-18T12:00:00Z",
        },
      ],
      total_count: 1,
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
          can_start_immediate_scraping: false,
          usage_restrictions_disabled: false,
          role: "proprietario",
          created_at: "2026-05-18T12:00:00Z",
        },
        session_expires_at: "2026-06-18T12:00:00Z",
        usage_restrictions_disabled_globally: false,
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
    expect(await screen.findByText(/Batelada criada com 1/)).toBeInTheDocument();
  });

  it("mostra status e quantidade de imÃƒÂ³veis por plataforma em cada endereÃƒÂ§o da batelada", async () => {
    vi.mocked(getAdminScrapingBatches).mockResolvedValue({
      items: [
        {
          job: {
            id: "job-batch-1",
            journey_id: null,
            job_type: "listings_prewarm",
            state: "completed",
            progress_percent: 100,
            current_stage: "listings_prewarm",
            cancel_requested_at: null,
            started_at: "2026-05-18T12:00:00Z",
            finished_at: "2026-05-18T12:03:00Z",
            worker_id: "worker-1",
            result_ref: null,
            error_code: null,
            error_message: null,
            created_at: "2026-05-18T12:00:00Z",
          },
          trigger: "admin_run_now",
          status: "partial",
          target_count: 1,
          processed_count: 1,
          skipped_count: 0,
          failed_count: 0,
          duration_ms: 180000,
          target_statuses: {
            "rent:residential:rua teste": {
              status: "partial",
              search_location_label: "Rua Teste",
              search_location_normalized: "rua teste",
              search_type: "rent",
              usage_type: "residential",
              total_count: 2,
              duration_ms: 120000,
              platforms: ["quintoandar", "zapimoveis"],
              platform_statuses: {
                quintoandar: { status: "completed", listing_count: 2 },
                zapimoveis: { status: "failed", listing_count: 0, error_message: "Timeout" },
              },
            },
          },
        },
      ],
      total_count: 1,
      limit: 20,
      offset: 0,
    });

    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: /Bateladas/i }));
    await user.click(await screen.findByRole("button", { name: /job-batch-1/i }));

    expect(await screen.findByText("Rua Teste")).toBeInTheDocument();
    expect(screen.getByText("QuintoAndar")).toBeInTheDocument();
    expect(screen.getByText(/ZAP/)).toBeInTheDocument();
    expect(screen.getByText(/2 im/)).toBeInTheDocument();
    expect(screen.getByText(/0 im/)).toBeInTheDocument();
    expect(screen.getByText("Timeout")).toBeInTheDocument();
  });

  it("permite liberar scraping imediato para um usuario", async () => {
    vi.mocked(updateAdminUserScrapingPermission).mockResolvedValue({
      id: "user-2",
      email: "morador@example.com",
      display_name: "Morador",
      is_active: true,
      is_superuser: false,
      can_start_immediate_scraping: true,
      usage_restrictions_disabled: false,
      role: "user",
      created_at: "2026-05-18T12:00:00Z",
    });

    const user = userEvent.setup();
    renderPage();

    const usersTab = await screen.findByRole("button", { name: /Usu/i });
    await user.click(usersTab);

    const toggle = await screen.findByRole("checkbox", { name: /Liberado/i });
    await user.click(toggle);

    await waitFor(() => {
      expect(updateAdminUserScrapingPermission).toHaveBeenCalledWith("user-2", true);
    });
    expect(await screen.findByText(/scraping imediato atualizada/i)).toBeInTheDocument();
  });

  it("permite alternar todas as restriÃƒÂ§ÃƒÂµes de uso para um usuÃƒÂ¡rio", async () => {
    vi.mocked(updateAdminUserUsageRestrictions).mockResolvedValue({
      id: "user-2",
      email: "morador@example.com",
      display_name: "Morador",
      is_active: true,
      is_superuser: false,
      can_start_immediate_scraping: false,
      usage_restrictions_disabled: true,
      role: "user",
      created_at: "2026-05-18T12:00:00Z",
    });

    const user = userEvent.setup();
    renderPage();

    const usersTab = await screen.findByRole("button", { name: /Usu/i });
    await user.click(usersTab);

    const restrictionButtons = await screen.findAllByRole("button", { name: /Restri/i });
    await user.click(restrictionButtons[1]);

    await waitFor(() => {
      expect(updateAdminUserUsageRestrictions).toHaveBeenCalledWith("user-2", true);
    });
    expect(await screen.findByText(/uso atualizadas/i)).toBeInTheDocument();
  });

  it("permite alternar restricoes de uso para todos os usuarios", async () => {
    vi.mocked(updateAdminGlobalUsageRestrictions).mockResolvedValue({
      usage_restrictions_disabled_globally: true,
    });

    const user = userEvent.setup();
    renderPage();

    const usersTab = await screen.findByRole("button", { name: /Usu/i });
    await user.click(usersTab);

    await user.click(await screen.findByRole("button", { name: /Ativar sem restr/i }));

    await waitFor(() => {
      expect(updateAdminGlobalUsageRestrictions).toHaveBeenCalledWith(true);
    });
    expect(await screen.findByText(/globais atualizadas/i)).toBeInTheDocument();
  });
});
