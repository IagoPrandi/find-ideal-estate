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
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url.endsWith("/auth/me")) {
        return jsonResponse({
          is_authenticated: false,
          user: null,
          session_expires_at: null
        });
      }

      if (url.endsWith("/auth/register") && init?.method === "POST") {
        return jsonResponse({
          is_authenticated: true,
          user: {
            id: "c2b9d4aa-869d-4d91-97e4-c05f6676a4f0",
            email: "maria@example.com",
            display_name: "Maria",
            is_active: true,
            created_at: "2026-04-12T20:00:00Z"
          },
          session_expires_at: "2026-05-12T20:00:00Z"
        });
      }

      return jsonResponse({ detail: "not-found" }, 404);
    }));
  });

  it("permite criar conta e mostra sessao autenticada", async () => {
    const user = userEvent.setup();

    render(
      <AuthProvider>
        <AuthAccessCard />
      </AuthProvider>
    );

    await user.click(await screen.findByRole("button", { name: "Entrar na conta" }));
    await user.click(screen.getByRole("button", { name: "Quero criar conta" }));
    await user.type(screen.getByLabelText("Nome exibido"), "Maria");
    await user.type(screen.getByLabelText("E-mail"), "maria@example.com");
    await user.type(screen.getByLabelText("Senha"), "senha-segura-123");
    await user.type(screen.getByLabelText("Repita a senha"), "senha-segura-123");
    await user.click(screen.getByRole("button", { name: /^Criar conta$/ }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Sair da conta" })).toBeInTheDocument();
    });

    expect(screen.getByText("maria@example.com")).toBeInTheDocument();
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

  it("bloqueia cadastro quando a confirmacao de senha diverge", async () => {
    const user = userEvent.setup();

    render(
      <AuthProvider>
        <AuthAccessCard />
      </AuthProvider>
    );

    await user.click(await screen.findByRole("button", { name: "Entrar na conta" }));
    await user.click(screen.getByRole("button", { name: "Quero criar conta" }));
    await user.type(screen.getByLabelText("E-mail"), "maria@example.com");
    await user.type(screen.getByLabelText("Senha"), "senha-segura-123");
    await user.type(screen.getByLabelText("Repita a senha"), "senha-diferente-123");
    await user.click(screen.getByRole("button", { name: /^Criar conta$/ }));

    expect(screen.getByText(/As senhas informadas não coincidem/i)).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});