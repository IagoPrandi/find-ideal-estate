import { useEffect, useMemo, useRef, useState } from "react";
import { Loader2, LogIn, LogOut, CreditCard, User } from "lucide-react";
import { useAuth } from "./AuthContext";
import { PlanosPage } from "../billing/PlanosPage";
import { ContaPage } from "../billing/ContaPage";

const GOOGLE_CLIENT_ID = String(import.meta.env.VITE_GOOGLE_CLIENT_ID || "").trim();
const GOOGLE_SCRIPT_ID = "google-identity-services";

type GoogleCredentialResponse = {
  credential?: string;
};

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (options: {
            client_id: string;
            callback: (response: GoogleCredentialResponse) => void;
            auto_select?: boolean;
            cancel_on_tap_outside?: boolean;
          }) => void;
          renderButton: (
            parent: HTMLElement,
            options: {
              type?: "standard" | "icon";
              theme?: "outline" | "filled_blue" | "filled_black";
              size?: "large" | "medium" | "small";
              text?: "signin_with" | "signup_with" | "continue_with" | "signin";
              shape?: "rectangular" | "pill" | "circle" | "square";
              width?: number;
              locale?: string;
            }
          ) => void;
        };
      };
    };
  }
}

let googleScriptPromise: Promise<void> | null = null;

function loadGoogleIdentityScript(): Promise<void> {
  if (window.google?.accounts?.id) {
    return Promise.resolve();
  }
  if (googleScriptPromise) {
    return googleScriptPromise;
  }

  googleScriptPromise = new Promise((resolve, reject) => {
    const existing = document.getElementById(GOOGLE_SCRIPT_ID) as HTMLScriptElement | null;
    if (existing) {
      existing.addEventListener("load", () => resolve(), { once: true });
      existing.addEventListener("error", () => reject(new Error("google-script-error")), { once: true });
      return;
    }

    const script = document.createElement("script");
    script.id = GOOGLE_SCRIPT_ID;
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.defer = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("google-script-error"));
    document.head.appendChild(script);
  });

  return googleScriptPromise;
}

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
    authStatus,
    closeAuthModal,
    errorMessage,
    isAuthModalOpen,
    isLoading,
    isSubmitting,
    clearError,
    loginWithGoogle,
    logout,
    openAuthModal,
  } = useAuth();
  const [googleNotice, setGoogleNotice] = useState<string | null>(null);
  const [showPlanos, setShowPlanos] = useState(false);
  const [showConta, setShowConta] = useState(false);
  const googleButtonRef = useRef<HTMLDivElement | null>(null);

  const expiryLabel = useMemo(() => formatExpiry(authStatus.session_expires_at), [authStatus.session_expires_at]);
  const userName = authStatus.user?.display_name?.trim() || authStatus.user?.email?.split("@")[0] || "Conta";

  const closeModal = () => {
    if (isSubmitting) {
      return;
    }
    clearError();
    setGoogleNotice(null);
    closeAuthModal();
  };

  useEffect(() => {
    if (!isAuthModalOpen || authStatus.is_authenticated || !GOOGLE_CLIENT_ID || !googleButtonRef.current) {
      return;
    }

    let isMounted = true;
    void loadGoogleIdentityScript()
      .then(() => {
        if (!isMounted || !googleButtonRef.current || !window.google?.accounts?.id) {
          return;
        }
        const buttonWidth = Math.min(360, Math.max(280, googleButtonRef.current.clientWidth || 320));
        googleButtonRef.current.replaceChildren();
        window.google.accounts.id.initialize({
          client_id: GOOGLE_CLIENT_ID,
          callback: (response) => {
            void (async () => {
              clearError();
              setGoogleNotice(null);
              if (!response.credential) {
                setGoogleNotice("O Google não retornou uma credencial válida.");
                return;
              }
              const success = await loginWithGoogle({ credential: response.credential });
              if (success) {
                closeAuthModal();
              }
            })();
          },
          auto_select: false,
          cancel_on_tap_outside: true,
        });
        window.google.accounts.id.renderButton(googleButtonRef.current, {
          type: "standard",
          theme: "outline",
          size: "large",
          text: "continue_with",
          shape: "rectangular",
          width: buttonWidth,
          locale: "pt-BR",
        });
      })
      .catch(() => {
        if (isMounted) {
          setGoogleNotice("Não foi possível carregar o login do Google agora.");
        }
      });

    return () => {
      isMounted = false;
    };
  }, [authStatus.is_authenticated, clearError, closeAuthModal, isAuthModalOpen, loginWithGoogle]);

  const handleGoogleLogin = () => {
    clearError();
    if (!GOOGLE_CLIENT_ID) {
      setGoogleNotice("Login com Google ainda depende da configuração OAuth deste ambiente.");
      return;
    }
    setGoogleNotice("Aguarde o botão do Google carregar para continuar.");
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
                  openAuthModal();
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
          <div className="w-full max-w-sm overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl">
            <div className="flex items-start justify-between gap-4 border-b border-slate-200 px-6 py-5">
              <div className="min-w-0">
                <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">Conta</p>
                <h2 className="mt-2 text-lg font-semibold tracking-tight text-slate-900">Entrar para salvar a jornada</h2>
                <p className="mt-1 text-sm leading-relaxed text-slate-500">
                  Acesse sua conta para continuar de onde parou.
                </p>
              </div>
              <button type="button" className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-500 transition hover:border-slate-300 hover:text-slate-700" onClick={closeModal}>
                Fechar
              </button>
            </div>

            <div className="grid gap-4 px-6 py-6">
              {GOOGLE_CLIENT_ID ? (
                <div className="flex min-h-11 justify-center" ref={googleButtonRef} />
              ) : (
                <button
                  type="button"
                  className="inline-flex items-center justify-center gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-700 transition hover:border-pastel-violet-200 hover:text-slate-900"
                  onClick={handleGoogleLogin}
                >
                  <GoogleIcon />
                  <span>Continuar com Google</span>
                </button>
              )}

              {googleNotice ? (
                <p className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-medium text-amber-700" role="alert">
                  {googleNotice}
                </p>
              ) : null}

              {errorMessage ? (
                <p className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700" role="alert">
                  {errorMessage}
                </p>
              ) : null}
            </div>

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
