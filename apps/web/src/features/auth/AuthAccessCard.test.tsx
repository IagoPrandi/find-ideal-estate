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

  it("abre o modal de login ao clicar em Entrar na conta", async () => {
    const user = userEvent.setup();

    render(
      <AuthProvider>
        <AuthAccessCard />
      </AuthProvider>
    );

    await user.click(await screen.findByRole("button", { name: "Entrar na conta" }));

    expect(screen.getByText("Entrar para salvar a jornada")).toBeInTheDocument();
  });

  it("mostra aviso explicito quando Google nao esta configurado", async () => {
    const user = userEvent.setup();

    render(
      <AuthProvider>
        <AuthAccessCard />
      </AuthProvider>
    );

    await user.click(await screen.findByRole("button", { name: "Entrar na conta" }));
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

    await user.click(await screen.findByRole("button", { name: "Entrar na conta" }));
    expect(screen.getByText("Entrar para salvar a jornada")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Fechar" }));

    await waitFor(() => {
      expect(screen.queryByText("Entrar para salvar a jornada")).not.toBeInTheDocument();
    });
  });
});
