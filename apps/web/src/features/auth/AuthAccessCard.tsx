import { useEffect, useMemo, useRef, useState } from "react";
import {
  BarChart3,
  Building2,
  CheckCircle2,
  CreditCard,
  Loader2,
  LogIn,
  LogOut,
  Map,
  Navigation,
  Shield,
  ShieldCheck,
  Sparkles,
  User,
  X,
} from "lucide-react";
import { useAuth } from "./AuthContext";
import { PlanosPage } from "../billing/PlanosPage";
import { ContaPage } from "../billing/ContaPage";

const GOOGLE_CLIENT_ID = String(import.meta.env.VITE_GOOGLE_CLIENT_ID || "").trim();
const GOOGLE_SCRIPT_ID = "google-identity-services";
const AUTH_ONBOARDING_DELAY_MS = 650;

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

const onboardingHighlights = [
  {
    title: "Jornada guiada no mapa",
    description: "Escolha um ponto de referência e veja zonas por tempo de transporte público, a pé ou de carro.",
    icon: Navigation,
    accent: "bg-pastel-violet-50 text-pastel-violet-700",
  },
  {
    title: "Imóveis reais, sem ruído",
    description: "Anúncios do QuintoAndar, ZapImóveis e VivaReal agregados e sem duplicatas.",
    icon: Building2,
    accent: "bg-sky-50 text-sky-700",
  },
  {
    title: "Zonas enriquecidas",
    description: "Segurança, áreas verdes, risco de alagamento e pontos de interesse em cada região.",
    icon: Shield,
    accent: "bg-emerald-50 text-emerald-700",
  },
  {
    title: "Dashboard de preços",
    description: "Histórico, distribuição por faixa e heatmap de segurança pública da zona.",
    icon: BarChart3,
    accent: "bg-amber-50 text-amber-700",
  },
];

const loginBenefits = [
  "Salvar imóveis e zonas favoritas",
  "Personalizar tempo e raio de busca",
  "Gerar zonas com raio acima de 500 m",
  "Retomar e compartilhar sua jornada",
];

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
  const autoOpenedGuestModalRef = useRef(false);
  const latestAuthStatusRef = useRef(authStatus);

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
    latestAuthStatusRef.current = authStatus;
  }, [authStatus]);

  useEffect(() => {
    if (isLoading || authStatus.is_authenticated || autoOpenedGuestModalRef.current) {
      return;
    }
    autoOpenedGuestModalRef.current = true;
    const timerId = window.setTimeout(() => {
      if (!latestAuthStatusRef.current.is_authenticated) {
        openAuthModal();
      }
    }, AUTH_ONBOARDING_DELAY_MS);

    return () => window.clearTimeout(timerId);
  }, [authStatus.is_authenticated, isLoading, openAuthModal]);

  useEffect(() => {
    if (authStatus.is_authenticated && isAuthModalOpen) {
      closeAuthModal();
    }
  }, [authStatus.is_authenticated, closeAuthModal, isAuthModalOpen]);

  useEffect(() => {
    if (!isAuthModalOpen) {
      return;
    }

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        if (isSubmitting) {
          return;
        }
        clearError();
        setGoogleNotice(null);
        closeAuthModal();
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [clearError, closeAuthModal, isAuthModalOpen, isSubmitting]);

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
              {authStatus.user?.is_superuser ? (
                <button
                  type="button"
                  aria-label="Painel admin"
                  title="Painel admin"
                  className="pointer-events-auto inline-flex h-11 w-11 items-center justify-center rounded-full border border-white/80 bg-white/95 text-slate-600 shadow-md backdrop-blur-md transition hover:-translate-y-0.5 hover:text-pastel-violet-700"
                  onClick={() => { window.location.hash = "#/admin"; }}
                >
                  <ShieldCheck className="h-4 w-4" />
                </button>
              ) : null}
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

      {isAuthModalOpen && !authStatus.is_authenticated ? (
        <div className="fixed inset-0 z-[80] flex items-stretch justify-end bg-slate-950/20 backdrop-blur-[2px]" role="dialog" aria-modal="true" aria-labelledby="auth-onboarding-title">
          <button
            type="button"
            aria-label="Fechar janela e explorar sem login"
            className="hidden flex-1 cursor-default bg-white/10 backdrop-blur-md lg:block"
            onClick={closeModal}
          />
          <div className="relative flex h-full w-full max-w-[44rem] flex-col overflow-y-auto border-l border-white/80 bg-white px-5 py-4 shadow-2xl sm:px-8 lg:px-10">
            <button
              type="button"
              aria-label="Fechar janela de entrada"
              className="absolute right-5 top-4 inline-flex h-10 w-10 items-center justify-center rounded-full border border-slate-200 bg-white/95 text-slate-500 shadow-sm transition hover:border-slate-300 hover:text-slate-800"
              onClick={closeModal}
            >
              <X className="h-4 w-4" />
            </button>

            <div className="flex min-h-full flex-col justify-between gap-5">
              <div>
                <div className="flex items-center gap-3 pr-12">
                  <span className="inline-flex h-10 w-10 items-center justify-center rounded-2xl bg-pastel-violet-50 text-pastel-violet-700">
                    <Map className="h-5 w-5" />
                  </span>
                  <div className="min-w-0">
                    <p className="text-lg font-extrabold leading-tight tracking-tight text-slate-950">BetterPlace</p>
                    <p className="text-xs font-semibold text-slate-400">Tenha certeza onde morar</p>
                  </div>
                </div>

                <div className="mt-6 max-w-[36rem]">
                  <p className="text-[11px] font-extrabold uppercase tracking-[0.28em] text-slate-400">Bem-vindo</p>
                  <h2 id="auth-onboarding-title" className="mt-2 text-3xl font-extrabold leading-tight tracking-tight text-slate-950">
                    Escolha pela vizinhança, não só pelo anúncio.
                  </h2>
                  <p className="mt-3 text-base leading-relaxed text-slate-500">
                    Uma jornada guiada que cruza transporte, segurança, área verde e preço para revelar onde vale a pena morar.
                  </p>
                </div>

                <div className="mt-6 grid gap-4 sm:grid-cols-2">
                  {onboardingHighlights.map((item) => {
                    const Icon = item.icon;
                    return (
                      <div key={item.title} className="flex min-w-0 gap-3">
                        <span className={`inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl ${item.accent}`}>
                          <Icon className="h-5 w-5" />
                        </span>
                        <div className="min-w-0">
                          <h3 className="text-sm font-extrabold leading-snug text-slate-900">{item.title}</h3>
                          <p className="mt-1 text-xs leading-relaxed text-slate-500">{item.description}</p>
                        </div>
                      </div>
                    );
                  })}
                </div>

                <div className="mt-5 rounded-[1.35rem] border border-pastel-violet-200 bg-pastel-violet-50/80 p-4 shadow-inner shadow-white/60">
                  <div className="flex items-center gap-2 text-pastel-violet-700">
                    <Sparkles className="h-4 w-4" />
                    <p className="text-xs font-extrabold uppercase tracking-[0.16em]">Entre para aproveitar mais</p>
                  </div>
                  <div className="mt-3 grid gap-2.5 sm:grid-cols-2">
                    {loginBenefits.map((benefit) => (
                      <div key={benefit} className="flex min-w-0 items-start gap-2.5">
                        <span className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-white text-pastel-violet-600 shadow-sm">
                          <CheckCircle2 className="h-3.5 w-3.5" />
                        </span>
                        <span className="min-w-0 text-sm font-semibold leading-snug text-slate-600">{benefit}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              <div className="sticky bottom-0 -mx-5 grid gap-3 border-t border-slate-100 bg-white/95 px-5 pb-4 pt-4 backdrop-blur sm:-mx-8 sm:grid-cols-[minmax(0,1fr)_auto] sm:px-8 lg:-mx-10 lg:px-10">
                <div className="min-w-0">
                  {GOOGLE_CLIENT_ID ? (
                    <div className="flex min-h-12 w-full items-center justify-center rounded-2xl border border-pastel-violet-200 bg-white px-3 py-1 shadow-sm" ref={googleButtonRef} />
                  ) : (
                    <button
                      type="button"
                      className="inline-flex min-h-12 w-full items-center justify-center gap-3 rounded-2xl border border-pastel-violet-500 bg-pastel-violet-500 px-5 py-3 text-sm font-extrabold text-white shadow-lg shadow-pastel-violet-200 transition hover:bg-pastel-violet-600"
                      onClick={handleGoogleLogin}
                    >
                      <GoogleIcon />
                      <span>Continuar com Google</span>
                    </button>
                  )}
                </div>

                <button
                  type="button"
                  className="inline-flex min-h-12 items-center justify-center rounded-2xl border border-slate-200 bg-white px-5 py-3 text-sm font-extrabold text-slate-700 shadow-sm transition hover:border-pastel-violet-200 hover:bg-pastel-violet-50 hover:text-pastel-violet-700"
                  onClick={closeModal}
                >
                  Explorar sem login
                </button>

                {googleNotice ? (
                  <p className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-medium text-amber-700 sm:col-span-2" role="alert">
                    {googleNotice}
                  </p>
                ) : null}

                {errorMessage ? (
                  <p className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700 sm:col-span-2" role="alert">
                    {errorMessage}
                  </p>
                ) : null}

                {authStatus.is_authenticated ? (
                  <p className="text-xs text-slate-500 sm:col-span-2">
                    Sessão atual de {userName}
                    {expiryLabel ? ` · expira em ${expiryLabel}` : ""}.
                  </p>
                ) : null}
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
