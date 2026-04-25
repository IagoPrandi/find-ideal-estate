import { create } from "zustand";
import type { AuthStatusRead, FavoriteListingEntry, ListingCardRead } from "../api/client";
import { ALL_FAVORITE_METRIC_IDS, DEFAULT_FAVORITE_METRIC_IDS, type FavoriteMetricId, isFavoriteMetricId } from "../lib/favorites";
import { getListingSelectionKey } from "../lib/listingFormat";

export type FavoritesPanelTab = "saved" | "compare";
export type FavoritesPanelScope = "listings" | "zones";

type FavoritesPreferenceState = {
  selectedMetricIds: FavoriteMetricId[];
};

type FavoritesLegacyState = {
  favorites?: FavoriteListingEntry[];
  selectedMetricIds?: string[];
};

type FavoritesState = {
  favorites: FavoriteListingEntry[];
  selectedMetricIds: FavoriteMetricId[];
  isPanelOpen: boolean;
  activeTab: FavoritesPanelTab;
  activeScope: FavoritesPanelScope;
  selectedSavedListingKey: string | null;
  isAuthenticated: boolean;
  isHydrating: boolean;
  accountUserId: string | null;
  isFavorite: (listingKey: string) => boolean;
  syncWithAuthStatus: (authStatus: AuthStatusRead) => Promise<void>;
  addFavorite: (payload: {
    listing: ListingCardRead;
    journeyId: string;
    zoneFingerprint: string;
    searchType: string;
    usageType: string;
  }) => Promise<boolean>;
  addManualFavorite: (payload: {
    url: string;
    searchType?: string;
    usageType?: string;
    journeyId?: string | null;
    zoneFingerprint?: string | null;
  }) => Promise<{ ok: boolean; error?: string }>;
  removeFavorite: (listingKey: string) => Promise<boolean>;
  toggleFavorite: (payload: {
    listing: ListingCardRead;
    journeyId: string;
    zoneFingerprint: string;
    searchType: string;
    usageType: string;
  }) => Promise<boolean>;
  setPanelOpen: (value: boolean) => void;
  togglePanel: () => void;
  setActiveTab: (value: FavoritesPanelTab) => void;
  setActiveScope: (value: FavoritesPanelScope) => void;
  setSelectedSavedListingKey: (value: string | null) => void;
  toggleMetric: (metricId: FavoriteMetricId) => void;
  setSelectedMetricIds: (metricIds: FavoriteMetricId[]) => void;
  resetFavoritesState: () => void;
};

const FAVORITES_PREFERENCES_STORAGE_KEY = "find-ideal-estate:favorite-preferences:v1";
const LEGACY_FAVORITES_STORAGE_KEY = "find-ideal-estate:favorites:v1";
let latestFavoritesSyncRequestId = 0;

function normalizeMetricIds(metricIds: string[] | undefined) {
  const normalized = (metricIds || []).filter(isFavoriteMetricId);
  return normalized.length > 0 ? normalized : DEFAULT_FAVORITE_METRIC_IDS;
}

function loadLegacyState(): FavoritesLegacyState {
  if (typeof window === "undefined") {
    return {};
  }

  try {
    const raw = window.localStorage.getItem(LEGACY_FAVORITES_STORAGE_KEY);
    if (!raw) {
      return {};
    }

    return JSON.parse(raw) as FavoritesLegacyState;
  } catch {
    return {};
  }
}

function loadPreferenceState(): FavoritesPreferenceState {
  const legacyState = loadLegacyState();
  if (typeof window === "undefined") {
    return {
      selectedMetricIds: normalizeMetricIds(legacyState.selectedMetricIds),
    };
  }

  try {
    const raw = window.localStorage.getItem(FAVORITES_PREFERENCES_STORAGE_KEY);
    if (!raw) {
      return {
        selectedMetricIds: normalizeMetricIds(legacyState.selectedMetricIds),
      };
    }

    const parsed = JSON.parse(raw) as Partial<FavoritesPreferenceState>;
    return {
      selectedMetricIds: normalizeMetricIds(parsed.selectedMetricIds as string[] | undefined),
    };
  } catch {
    return {
      selectedMetricIds: normalizeMetricIds(legacyState.selectedMetricIds),
    };
  }
}

function persistPreferenceState(state: FavoritesPreferenceState) {
  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.setItem(
    FAVORITES_PREFERENCES_STORAGE_KEY,
    JSON.stringify({
      selectedMetricIds: state.selectedMetricIds.filter((metricId) => ALL_FAVORITE_METRIC_IDS.includes(metricId)),
    }),
  );
}

function clearLegacyFavoritesState() {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.removeItem(LEGACY_FAVORITES_STORAGE_KEY);
}

async function getAccountFavoritesApi() {
  const client = await import("../api/client");
  return client.getAccountFavorites();
}

async function saveAccountFavoriteApi(payload: {
  listing: ListingCardRead;
  journeyId: string;
  zoneFingerprint: string;
  searchType: string;
  usageType: string;
}) {
  const client = await import("../api/client");
  return client.saveAccountFavorite(payload);
}

async function deleteAccountFavoriteApi(listingKey: string) {
  const client = await import("../api/client");
  await client.deleteAccountFavorite(listingKey);
}

async function addManualListingFavoriteApi(payload: {
  url: string;
  searchType?: string;
  usageType?: string;
  journeyId?: string | null;
  zoneFingerprint?: string | null;
}) {
  const client = await import("../api/client");
  return client.addManualListingFavorite(payload);
}

const initialPreferenceState = loadPreferenceState();

export const useFavoritesStore = create<FavoritesState>((set, get) => ({
  favorites: [],
  selectedMetricIds: initialPreferenceState.selectedMetricIds,
  isPanelOpen: false,
  activeTab: "saved",
  activeScope: "listings",
  selectedSavedListingKey: null,
  isAuthenticated: false,
  isHydrating: false,
  accountUserId: null,
  isFavorite: (listingKey) => get().favorites.some((favorite) => favorite.listingKey === listingKey),
  syncWithAuthStatus: async (authStatus) => {
    const nextUserId = authStatus.is_authenticated ? authStatus.user?.id || null : null;

    if (!authStatus.is_authenticated || !nextUserId) {
      latestFavoritesSyncRequestId += 1;
      set({
        favorites: [],
        isAuthenticated: false,
        isHydrating: false,
        accountUserId: null,
      });
      return;
    }

    const currentState = get();
    if (currentState.isAuthenticated && currentState.accountUserId === nextUserId && !currentState.isHydrating) {
      return;
    }

    const syncRequestId = ++latestFavoritesSyncRequestId;
    set({
      isAuthenticated: true,
      isHydrating: true,
      accountUserId: nextUserId,
    });

    try {
      let favorites = await getAccountFavoritesApi();
      const legacyFavorites = Array.isArray(loadLegacyState().favorites) ? loadLegacyState().favorites || [] : [];

      if (legacyFavorites.length > 0) {
        for (const favorite of legacyFavorites) {
          await saveAccountFavoriteApi({
            listing: favorite.listing,
            journeyId: favorite.journeyId,
            zoneFingerprint: favorite.zoneFingerprint,
            searchType: favorite.searchType,
            usageType: favorite.usageType,
          });
        }
        clearLegacyFavoritesState();
        favorites = await getAccountFavoritesApi();
      }

      if (syncRequestId !== latestFavoritesSyncRequestId) {
        return;
      }

      set({
        favorites,
        isAuthenticated: true,
        isHydrating: false,
        accountUserId: nextUserId,
      });
    } catch {
      if (syncRequestId !== latestFavoritesSyncRequestId) {
        return;
      }

      set({
        favorites: [],
        isAuthenticated: true,
        isHydrating: false,
        accountUserId: nextUserId,
      });
    }
  },
  addFavorite: async ({ listing, journeyId, zoneFingerprint, searchType, usageType }) => {
    if (!get().isAuthenticated) {
      return false;
    }

    const listingKey = getListingSelectionKey(listing);
    if (!listingKey) {
      return false;
    }

    try {
      const savedFavorite = await saveAccountFavoriteApi({ listing, journeyId, zoneFingerprint, searchType, usageType });
      set((state) => ({
        favorites: [savedFavorite, ...state.favorites.filter((favorite) => favorite.listingKey !== savedFavorite.listingKey)],
      }));
      return true;
    } catch {
      return false;
    }
  },
  addManualFavorite: async ({ url, searchType, usageType, journeyId, zoneFingerprint }) => {
    if (!get().isAuthenticated) {
      return { ok: false, error: "Entre na sua conta para adicionar imóveis por link." };
    }
    const trimmed = (url || "").trim();
    if (!trimmed) {
      return { ok: false, error: "Informe a URL do anúncio." };
    }
    try {
      const saved = await addManualListingFavoriteApi({
        url: trimmed,
        searchType,
        usageType,
        journeyId,
        zoneFingerprint,
      });
      set((state) => ({
        favorites: [saved, ...state.favorites.filter((favorite) => favorite.listingKey !== saved.listingKey)],
      }));
      return { ok: true };
    } catch (error) {
      const message = error instanceof Error ? error.message : "Falha ao adicionar imóvel pelo link.";
      return { ok: false, error: message };
    }
  },
  removeFavorite: async (listingKey) => {
    if (!get().isAuthenticated) {
      return false;
    }

    try {
      await deleteAccountFavoriteApi(listingKey);
      set((state) => ({
        favorites: state.favorites.filter((favorite) => favorite.listingKey !== listingKey),
      }));
      return true;
    } catch {
      return false;
    }
  },
  toggleFavorite: async (payload) => {
    const listingKey = getListingSelectionKey(payload.listing);
    if (!listingKey) {
      return false;
    }
    if (get().isFavorite(listingKey)) {
      return await get().removeFavorite(listingKey);
    }
    return await get().addFavorite(payload);
  },
  setPanelOpen: (value) => set({ isPanelOpen: value }),
  togglePanel: () => set((state) => ({ isPanelOpen: !state.isPanelOpen })),
  setActiveTab: (value) => set({ activeTab: value }),
  setActiveScope: (value) => set({ activeScope: value }),
  setSelectedSavedListingKey: (value) => set({ selectedSavedListingKey: value }),
  toggleMetric: (metricId) => {
    set((state) => {
      const hasMetric = state.selectedMetricIds.includes(metricId);
      const nextMetricIds = hasMetric
        ? state.selectedMetricIds.filter((currentMetricId) => currentMetricId !== metricId)
        : [...state.selectedMetricIds, metricId];
      if (nextMetricIds.length === 0) {
        return state;
      }
      persistPreferenceState({ selectedMetricIds: nextMetricIds });
      return { selectedMetricIds: nextMetricIds };
    });
  },
  setSelectedMetricIds: (metricIds) => {
    const nextMetricIds = normalizeMetricIds(metricIds);
    set(() => {
      persistPreferenceState({ selectedMetricIds: nextMetricIds });
      return { selectedMetricIds: nextMetricIds };
    });
  },
  resetFavoritesState: () => {
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(FAVORITES_PREFERENCES_STORAGE_KEY);
      window.localStorage.removeItem(LEGACY_FAVORITES_STORAGE_KEY);
    }
    set({
      favorites: [],
      selectedMetricIds: DEFAULT_FAVORITE_METRIC_IDS,
      isPanelOpen: false,
      activeTab: "saved",
      activeScope: "listings",
      selectedSavedListingKey: null,
      isAuthenticated: false,
      isHydrating: false,
      accountUserId: null,
    });
  },
}));