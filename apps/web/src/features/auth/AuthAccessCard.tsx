import { FormEvent, useMemo, useState } from "react";
import { Loader2, LogIn, LogOut, CreditCard, User } from "lucide-react";
import { useAuth } from "./AuthContext";
import { PlanosPage } from "../billing/PlanosPage";
import { ContaPage } from "../billing/ContaPage";

const GOOGLE_AUTH_URL = String(import.meta.env.VITE_GOOGLE_AUTH_URL || "").trim();

function formatExpiry(value: string | null | undefined) {
  if (!value) {
    return null;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short"
  }).format(date);
}

function GoogleIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4" role="img">
      <path fill="#EA4335" d="M12 10.2v3.9h5.4c-.2 1.3-.8 2.3-1.7 3.1l2.8 2.2c1.7-1.5 2.6-3.8 2.6-6.6 0-.6-.1-1.2-.2-1.8H12z" />
      <path fill="#4285F4" d="M12 21c2.4 0 4.5-.8 6-2.1l-2.8-2.2c-.8.5-1.9.9-3.2.9-2.4 0-4.4-1.6-5.1-3.8l-2.9 2.2C5.4 18.9 8.5 21 12 21z" />
      <path fill="#FBBC05" d="M6.9 13.8c-.2-.5-.3-1.2-.3-1.8s.1-1.2.3-1.8L4 8c-.6 1.1-1 2.5-1 4s.4 2.9 1 4l2.9-2.2z" />
      <path fill="#34A853" d="M12 6.4c1.3 0 2.4.4 3.3 1.3l2.5-2.5C16.5 3.9 14.4 3 12 3 8.5 3 5.4 5.1 4 8l2.9 2.2C7.6 8 9.6 6.4 12 6.4z" />
    </svg>
  );
}

export function AuthAccessCard() {
  const {
    authModalMode,
    authStatus,
    closeAuthModal,
    errorMessage,
    isAuthModalOpen,
    isLoading,
    isSubmitting,
    clearError,
    login,
    logout,
    modeLabel,
    openAuthModal,
    register,
  } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirmation, setPasswordConfirmation] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [googleNotice, setGoogleNotice] = useState<string | null>(null);
  const [formNotice, setFormNotice] = useState<string | null>(null);
  const [showPlanos, setShowPlanos] = useState(false);
  const [showConta, setShowConta] = useState(false);

  const expiryLabel = useMemo(() => formatExpiry(authStatus.session_expires_at), [authStatus.session_expires_at]);
  const userName = authStatus.user?.display_name?.trim() || authStatus.user?.email?.split("@")[0] || "Conta";

  const closeModal = () => {
    if (isSubmitting) {
      return;
    }
    clearError();
    setGoogleNotice(null);
    setFormNotice(null);
    closeAuthModal();
  };

  const resetForm = () => {
    setEmail("");
    setPassword("");
    setPasswordConfirmation("");
    setDisplayName("");
    setFormNotice(null);
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const normalizedEmail = email.trim();
    const normalizedPassword = password.trim();
    if (!normalizedEmail || !normalizedPassword) {
      return;
    }
    setFormNotice(null);

    if (authModalMode === "register") {
      const normalizedConfirmation = passwordConfirmation.trim();
      if (!normalizedConfirmation) {
        setFormNotice("Repita a senha para concluir o cadastro.");
        return;
      }
      if (normalizedPassword !== normalizedConfirmation) {
        setFormNotice("As senhas informadas não coincidem.");
        return;
      }
    }

    const success = authModalMode === "login"
      ? await login({ email: normalizedEmail, password: normalizedPassword })
      : await register({ email: normalizedEmail, password: normalizedPassword, displayName });

    if (success) {
      resetForm();
      closeAuthModal();
    }
  };

  const handleGoogleLogin = () => {
    clearError();
    setFormNotice(null);
    if (!GOOGLE_AUTH_URL) {
      setGoogleNotice("Login com Google ainda depende da configuração OAuth deste ambiente.");
      return;
    }
    window.location.assign(GOOGLE_AUTH_URL);
  };

  return (
    <>
      <div className="auth-shell">
        <div className="auth-shell__content">
          {authStatus.is_authenticated ? (
            <>
              <div className="hidden rounded-full border border-white/80 bg-white/95 px-3 py-2 text-xs font-semibold text-slate-600 shadow-md backdrop-blur-md sm:flex sm:items-center sm:gap-2">
                <span className={`inline-flex h-6 min-w-6 items-center justify-center rounded-full px-2 text-[11px] font-bold uppercase ${authStatus.user?.role === "proprietario" ? "bg-amber-100 text-amber-700" : "bg-pastel-violet-100 text-pastel-violet-700"}`}>
                  {authStatus.user?.role === "proprietario" ? "★" : userName.slice(0, 1)}
                </span>
                <span className="max-w-[10rem] truncate">{authStatus.user?.email}</span>
              </div>
              <button
                type="button"
                aria-label="Planos"
                title="Planos"
                className="pointer-events-auto inline-flex h-11 w-11 items-center justify-center rounded-full border border-white/80 bg-white/95 text-slate-600 shadow-md backdrop-blur-md transition hover:-translate-y-0.5 hover:text-pastel-violet-700"
                onClick={() => setShowPlanos(true)}
              >
                <CreditCard className="h-4 w-4" />
              </button>
              <button
                type="button"
                aria-label="Minha conta"
                title="Conta"
                className="pointer-events-auto inline-flex h-11 w-11 items-center justify-center rounded-full border border-white/80 bg-white/95 text-slate-600 shadow-md backdrop-blur-md transition hover:-translate-y-0.5 hover:text-pastel-violet-700"
                onClick={() => setShowConta(true)}
              >
                <User className="h-4 w-4" />
              </button>
              <button
                type="button"
                aria-label="Sair da conta"
                title="Sair"
                className="pointer-events-auto inline-flex h-11 w-11 items-center justify-center rounded-full border border-white/80 bg-white/95 text-slate-600 shadow-md backdrop-blur-md transition hover:-translate-y-0.5 hover:text-pastel-violet-700 disabled:cursor-not-allowed disabled:opacity-60"
                onClick={() => void logout()}
                disabled={isSubmitting}
              >
                {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <LogOut className="h-4 w-4" />}
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                aria-label="Ver planos"
                title="Planos"
                className="pointer-events-auto inline-flex h-11 items-center justify-center gap-1.5 rounded-full border border-white/80 bg-white/95 px-4 text-xs font-semibold text-slate-600 shadow-md backdrop-blur-md transition hover:-translate-y-0.5 hover:text-pastel-violet-700"
                onClick={() => setShowPlanos(true)}
                disabled={isLoading}
              >
                <CreditCard className="h-3.5 w-3.5" />
                Planos
              </button>
              <button
                type="button"
                aria-label="Entrar na conta"
                title="Entrar"
                className="pointer-events-auto inline-flex h-11 w-11 items-center justify-center rounded-full border border-white/80 bg-white/95 text-slate-600 shadow-md backdrop-blur-md transition hover:-translate-y-0.5 hover:text-pastel-violet-700 disabled:cursor-not-allowed disabled:opacity-60"
                onClick={() => {
                  setGoogleNotice(null);
                  setFormNotice(null);
                  openAuthModal("login");
                }}
                disabled={isLoading}
              >
                {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <LogIn className="h-4 w-4" />}
              </button>
            </>
          )}
        </div>
      </div>

      {showPlanos && <PlanosPage onClose={() => setShowPlanos(false)} />}
      {showConta && <ContaPage onClose={() => setShowConta(false)} />}

      {isAuthModalOpen ? (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-slate-950/35 px-4 py-8 backdrop-blur-sm">
          <div className="w-full max-w-md overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl">
            <div className="flex items-start justify-between gap-4 border-b border-slate-200 px-6 py-5">
              <div className="min-w-0">
                <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">Conta</p>
                <h2 className="mt-2 text-lg font-semibold tracking-tight text-slate-900">{authModalMode === "login" ? "Entrar para salvar a jornada" : "Criar conta"}</h2>
                <p className="mt-1 text-sm leading-relaxed text-slate-500">
                  {authModalMode === "login"
                    ? "Acesse sua conta para continuar de onde parou."
                    : "Crie sua conta sem perder a jornada iniciada nesta sessão."}
                </p>
              </div>
              <button type="button" className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-500 transition hover:border-slate-300 hover:text-slate-700" onClick={closeModal}>
                Fechar
              </button>
            </div>

            <form className="grid gap-4 px-6 py-5" onSubmit={(event) => void handleSubmit(event)}>
              <button
                type="button"
                className="inline-flex items-center justify-center gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-700 transition hover:border-pastel-violet-200 hover:text-slate-900"
                onClick={handleGoogleLogin}
              >
                <GoogleIcon />
                <span>Continuar com Google</span>
              </button>

              <div className="gem-divider" />

              {authModalMode === "register" ? (
                <label className="grid gap-2 text-sm font-semibold text-slate-700">
                  Nome exibido
                  <input
                    className="gem-input"
                    value={displayName}
                    onChange={(event) => setDisplayName(event.target.value)}
                    placeholder="Como quer aparecer"
                  />
                </label>
              ) : null}

              <label className="grid gap-2 text-sm font-semibold text-slate-700">
                E-mail
                <input
                  className="gem-input"
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="voce@exemplo.com"
                  required
                />
              </label>

              <label className="grid gap-2 text-sm font-semibold text-slate-700">
                Senha
                <input
                  className="gem-input"
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="Use pelo menos 8 caracteres"
                  minLength={8}
                  required
                />
              </label>

              {authModalMode === "register" ? (
                <label className="grid gap-2 text-sm font-semibold text-slate-700">
                  Repita a senha
                  <input
                    className="gem-input"
                    type="password"
                    value={passwordConfirmation}
                    onChange={(event) => setPasswordConfirmation(event.target.value)}
                    placeholder="Digite a senha novamente"
                    minLength={8}
                    required
                  />
                </label>
              ) : null}

              {googleNotice ? (
                <p className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-medium text-amber-700" role="alert">
                  {googleNotice}
                </p>
              ) : null}

              {formNotice ? (
                <p className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-medium text-amber-700" role="alert">
                  {formNotice}
                </p>
              ) : null}

              {errorMessage ? (
                <p className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700" role="alert">
                  {errorMessage}
                </p>
              ) : null}

              <div className="grid gap-3 pt-1 sm:grid-cols-2">
                <button
                  type="submit"
                  className="gem-primary-button disabled:cursor-not-allowed disabled:opacity-60"
                  disabled={isSubmitting}
                >
                  {isSubmitting ? "Processando..." : modeLabel(authModalMode)}
                </button>
                <button
                  type="button"
                  className="gem-secondary-button disabled:cursor-not-allowed disabled:opacity-60"
                  onClick={() => {
                    clearError();
                    setGoogleNotice(null);
                    setFormNotice(null);
                    openAuthModal(authModalMode === "login" ? "register" : "login");
                  }}
                  disabled={isSubmitting}
                >
                  {authModalMode === "login" ? "Quero criar conta" : "Já tenho conta"}
                </button>
              </div>
            </form>

            {authStatus.is_authenticated ? (
              <div className="border-t border-slate-200 bg-slate-50 px-6 py-4 text-xs text-slate-500">
                Sessão atual de {userName}{expiryLabel ? ` · expira em ${expiryLabel}` : ""}.
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </>
  );
}