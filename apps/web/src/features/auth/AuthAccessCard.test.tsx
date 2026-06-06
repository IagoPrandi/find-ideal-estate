import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AuthAccessCard } from "./AuthAccessCard";
import { AuthProvider } from "./AuthContext";

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

describe("AuthAccessCard", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);

      if (url.endsWith("/auth/me")) {
        return jsonResponse({
          is_authenticated: false,
          user: null,
          session_expires_at: null
        });
      }

      return jsonResponse({ detail: "not-found" }, 404);
    }));
  });

  it("exibe o onboarding automaticamente para visitante", async () => {
    render(
      <AuthProvider>
        <AuthAccessCard />
      </AuthProvider>
    );

    expect(await screen.findByRole("button", { name: "Entrar na conta" })).toBeInTheDocument();
    expect(screen.queryByText("Escolha pela vizinhança, não só pelo anúncio.")).not.toBeInTheDocument();

    expect(await screen.findByText("Escolha pela vizinhança, não só pelo anúncio.")).toBeInTheDocument();
    expect(screen.getByText("Entre para aproveitar mais")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Explorar sem login" })).toBeInTheDocument();
  });

  it("não exibe o onboarding quando há sessão autenticada", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);

      if (url.endsWith("/auth/me")) {
        return jsonResponse({
          is_authenticated: true,
          user: {
            id: "11111111-1111-4111-8111-111111111111",
            email: "usuario@example.com",
            display_name: "Usuário",
            is_active: true,
            is_superuser: false,
            role: "user",
            created_at: "2026-06-05T20:00:00Z",
          },
          session_expires_at: null,
          usage_restrictions_disabled_globally: false,
        });
      }

      return jsonResponse({ detail: "not-found" }, 404);
    }));

    render(
      <AuthProvider>
        <AuthAccessCard />
      </AuthProvider>
    );

    expect(await screen.findByRole("button", { name: "Minha conta" })).toBeInTheDocument();
    expect(screen.queryByText("Escolha pela vizinhança, não só pelo anúncio.")).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("abre o modal de login ao clicar em Entrar na conta", async () => {
    const user = userEvent.setup();

    render(
      <AuthProvider>
        <AuthAccessCard />
      </AuthProvider>
    );

    expect(await screen.findByText("Escolha pela vizinhança, não só pelo anúncio.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Explorar sem login" }));
    await waitFor(() => {
      expect(screen.queryByText("Escolha pela vizinhança, não só pelo anúncio.")).not.toBeInTheDocument();
    });

    await user.click(await screen.findByRole("button", { name: "Entrar na conta" }));

    expect(screen.getByText("Escolha pela vizinhança, não só pelo anúncio.")).toBeInTheDocument();
  });

  it("mostra aviso explicito quando Google nao esta configurado", async () => {
    const user = userEvent.setup();

    render(
      <AuthProvider>
        <AuthAccessCard />
      </AuthProvider>
    );

    expect(await screen.findByText("Escolha pela vizinhança, não só pelo anúncio.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Continuar com Google/i }));

    expect(screen.getByText(/configuração OAuth deste ambiente/i)).toBeInTheDocument();
  });

  it("fecha o modal ao clicar em Fechar", async () => {
    const user = userEvent.setup();

    render(
      <AuthProvider>
        <AuthAccessCard />
      </AuthProvider>
    );

    expect(await screen.findByText("Escolha pela vizinhança, não só pelo anúncio.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Fechar janela de entrada" }));

    await waitFor(() => {
      expect(screen.queryByText("Escolha pela vizinhança, não só pelo anúncio.")).not.toBeInTheDocument();
    });
  });
});
