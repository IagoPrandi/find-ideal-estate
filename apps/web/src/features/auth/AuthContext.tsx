import { createContext, ReactNode, startTransition, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { ApiError, AuthStatusRead, getAuthStatus, loginGoogleAuth, logoutAuth } from "../../api/client";
import { useFavoritesStore, useZoneFavoritesStore } from "../../state";

type AuthContextValue = {
  authStatus: AuthStatusRead;
  isLoading: boolean;
  isSubmitting: boolean;
  errorMessage: string | null;
  isAuthModalOpen: boolean;
  refresh: () => Promise<void>;
  loginWithGoogle: (payload: { credential: string }) => Promise<boolean>;
  logout: () => Promise<void>;
  clearError: () => void;
  openAuthModal: () => void;
  closeAuthModal: () => void;
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
  const syncFavoritesWithAuthStatus = useFavoritesStore((state) => state.syncWithAuthStatus);
  const syncZoneFavoritesWithAuthStatus = useZoneFavoritesStore((state) => state.syncWithAuthStatus);
  const [authStatus, setAuthStatus] = useState<AuthStatusRead>(GUEST_STATUS);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);

  const clearError = useCallback(() => setErrorMessage(null), []);

  const refresh = useCallback(async () => {
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
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    void syncFavoritesWithAuthStatus(authStatus);
    void syncZoneFavoritesWithAuthStatus(authStatus);
  }, [authStatus, syncFavoritesWithAuthStatus, syncZoneFavoritesWithAuthStatus]);

  const loginWithGoogle = useCallback(async (payload: { credential: string }) => {
    setIsSubmitting(true);
    try {
      const next = await loginGoogleAuth(payload);
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
  }, []);

  const logout = useCallback(async () => {
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
  }, []);

  const openAuthModal = useCallback(() => {
    clearError();
    setIsAuthModalOpen(true);
  }, [clearError]);

  const closeAuthModal = useCallback(() => {
    setIsAuthModalOpen(false);
  }, []);

  const value = useMemo<AuthContextValue>(() => ({
    authStatus,
    isLoading,
    isSubmitting,
    errorMessage,
    isAuthModalOpen,
    refresh,
    loginWithGoogle,
    logout,
    clearError,
    openAuthModal,
    closeAuthModal,
  }), [authStatus, clearError, closeAuthModal, errorMessage, isAuthModalOpen, isLoading, isSubmitting, loginWithGoogle, logout, openAuthModal, refresh]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth deve ser usado dentro de AuthProvider.");
  }
  return context;
}
