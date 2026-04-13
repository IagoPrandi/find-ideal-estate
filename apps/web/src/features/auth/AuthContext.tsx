import { createContext, ReactNode, startTransition, useContext, useEffect, useMemo, useState } from "react";
import { ApiError, AuthStatusRead, getAuthStatus, loginAuth, logoutAuth, registerAuth } from "../../api/client";

type AuthMode = "login" | "register";

type AuthContextValue = {
  authStatus: AuthStatusRead;
  isLoading: boolean;
  isSubmitting: boolean;
  errorMessage: string | null;
  refresh: () => Promise<void>;
  login: (payload: { email: string; password: string }) => Promise<boolean>;
  register: (payload: { email: string; password: string; displayName?: string }) => Promise<boolean>;
  logout: () => Promise<void>;
  clearError: () => void;
  modeLabel: (mode: AuthMode) => string;
};

const GUEST_STATUS: AuthStatusRead = {
  is_authenticated: false,
  user: null,
  session_expires_at: null
};

const AuthContext = createContext<AuthContextValue | null>(null);

function toMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  return "Não foi possível concluir a autenticação agora.";
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [authStatus, setAuthStatus] = useState<AuthStatusRead>(GUEST_STATUS);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const refresh = async () => {
    setIsLoading(true);
    try {
      const next = await getAuthStatus();
      startTransition(() => {
        setAuthStatus(next);
        setErrorMessage(null);
      });
    } catch {
      startTransition(() => {
        setAuthStatus(GUEST_STATUS);
      });
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const login = async (payload: { email: string; password: string }) => {
    setIsSubmitting(true);
    try {
      const next = await loginAuth(payload);
      startTransition(() => {
        setAuthStatus(next);
        setErrorMessage(null);
      });
      return true;
    } catch (error) {
      setErrorMessage(toMessage(error));
      return false;
    } finally {
      setIsSubmitting(false);
    }
  };

  const register = async (payload: { email: string; password: string; displayName?: string }) => {
    setIsSubmitting(true);
    try {
      const next = await registerAuth({
        email: payload.email,
        password: payload.password,
        display_name: payload.displayName?.trim() || undefined
      });
      startTransition(() => {
        setAuthStatus(next);
        setErrorMessage(null);
      });
      return true;
    } catch (error) {
      setErrorMessage(toMessage(error));
      return false;
    } finally {
      setIsSubmitting(false);
    }
  };

  const logout = async () => {
    setIsSubmitting(true);
    try {
      const next = await logoutAuth();
      startTransition(() => {
        setAuthStatus(next);
        setErrorMessage(null);
      });
    } catch (error) {
      setErrorMessage(toMessage(error));
    } finally {
      setIsSubmitting(false);
    }
  };

  const value = useMemo<AuthContextValue>(() => ({
    authStatus,
    isLoading,
    isSubmitting,
    errorMessage,
    refresh,
    login,
    register,
    logout,
    clearError: () => setErrorMessage(null),
    modeLabel: (mode) => (mode === "login" ? "Entrar" : "Criar conta")
  }), [authStatus, errorMessage, isLoading, isSubmitting]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth deve ser usado dentro de AuthProvider.");
  }
  return context;
}