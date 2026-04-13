import { create } from "zustand";
import type { ListingCardRead } from "../api/client";
import { ALL_FAVORITE_METRIC_IDS, DEFAULT_FAVORITE_METRIC_IDS, type FavoriteMetricId, isFavoriteMetricId } from "../lib/favorites";
import { getListingSelectionKey } from "../lib/listingFormat";

export type FavoritesPanelTab = "saved" | "compare";

export type FavoriteListingEntry = {
  listingKey: string;
  journeyId: string;
  zoneFingerprint: string;
  searchType: string;
  usageType: string;
  savedAt: string;
  listing: ListingCardRead;
};

type FavoritesPersistedState = {
  favorites: FavoriteListingEntry[];
  selectedMetricIds: FavoriteMetricId[];
};

type FavoritesState = FavoritesPersistedState & {
  isPanelOpen: boolean;
  activeTab: FavoritesPanelTab;
  isFavorite: (listingKey: string) => boolean;
  addFavorite: (payload: {
    listing: ListingCardRead;
    journeyId: string;
    zoneFingerprint: string;
    searchType: string;
    usageType: string;
  }) => void;
  removeFavorite: (listingKey: string) => void;
  toggleFavorite: (payload: {
    listing: ListingCardRead;
    journeyId: string;
    zoneFingerprint: string;
    searchType: string;
    usageType: string;
  }) => void;
  setPanelOpen: (value: boolean) => void;
  togglePanel: () => void;
  setActiveTab: (value: FavoritesPanelTab) => void;
  toggleMetric: (metricId: FavoriteMetricId) => void;
  setSelectedMetricIds: (metricIds: FavoriteMetricId[]) => void;
  resetFavoritesState: () => void;
};

const FAVORITES_STORAGE_KEY = "find-ideal-estate:favorites:v1";

function normalizeMetricIds(metricIds: string[] | undefined) {
  const normalized = (metricIds || []).filter(isFavoriteMetricId);
  return normalized.length > 0 ? normalized : DEFAULT_FAVORITE_METRIC_IDS;
}

function loadPersistedState(): FavoritesPersistedState {
  if (typeof window === "undefined") {
    return {
      favorites: [],
      selectedMetricIds: DEFAULT_FAVORITE_METRIC_IDS,
    };
  }

  try {
    const raw = window.localStorage.getItem(FAVORITES_STORAGE_KEY);
    if (!raw) {
      return {
        favorites: [],
        selectedMetricIds: DEFAULT_FAVORITE_METRIC_IDS,
      };
    }

    const parsed = JSON.parse(raw) as Partial<FavoritesPersistedState>;
    return {
      favorites: Array.isArray(parsed.favorites) ? parsed.favorites : [],
      selectedMetricIds: normalizeMetricIds(parsed.selectedMetricIds as string[] | undefined),
    };
  } catch {
    return {
      favorites: [],
      selectedMetricIds: DEFAULT_FAVORITE_METRIC_IDS,
    };
  }
}

function persistState(state: FavoritesPersistedState) {
  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.setItem(
    FAVORITES_STORAGE_KEY,
    JSON.stringify({
      favorites: state.favorites,
      selectedMetricIds: state.selectedMetricIds.filter((metricId) => ALL_FAVORITE_METRIC_IDS.includes(metricId)),
    }),
  );
}

const initialPersistedState = loadPersistedState();

export const useFavoritesStore = create<FavoritesState>((set, get) => ({
  favorites: initialPersistedState.favorites,
  selectedMetricIds: initialPersistedState.selectedMetricIds,
  isPanelOpen: false,
  activeTab: "saved",
  isFavorite: (listingKey) => get().favorites.some((favorite) => favorite.listingKey === listingKey),
  addFavorite: ({ listing, journeyId, zoneFingerprint, searchType, usageType }) => {
    const listingKey = getListingSelectionKey(listing);
    if (!listingKey) {
      return;
    }

    set((state) => {
      const nextFavorites = [
        {
          listingKey,
          journeyId,
          zoneFingerprint,
          searchType,
          usageType,
          savedAt: new Date().toISOString(),
          listing,
        },
        ...state.favorites.filter((favorite) => favorite.listingKey !== listingKey),
      ];
      persistState({ favorites: nextFavorites, selectedMetricIds: state.selectedMetricIds });
      return { favorites: nextFavorites };
    });
  },
  removeFavorite: (listingKey) => {
    set((state) => {
      const nextFavorites = state.favorites.filter((favorite) => favorite.listingKey !== listingKey);
      persistState({ favorites: nextFavorites, selectedMetricIds: state.selectedMetricIds });
      return { favorites: nextFavorites };
    });
  },
  toggleFavorite: (payload) => {
    const listingKey = getListingSelectionKey(payload.listing);
    if (!listingKey) {
      return;
    }
    if (get().isFavorite(listingKey)) {
      get().removeFavorite(listingKey);
      return;
    }
    get().addFavorite(payload);
  },
  setPanelOpen: (value) => set({ isPanelOpen: value }),
  togglePanel: () => set((state) => ({ isPanelOpen: !state.isPanelOpen })),
  setActiveTab: (value) => set({ activeTab: value }),
  toggleMetric: (metricId) => {
    set((state) => {
      const hasMetric = state.selectedMetricIds.includes(metricId);
      const nextMetricIds = hasMetric
        ? state.selectedMetricIds.filter((currentMetricId) => currentMetricId !== metricId)
        : [...state.selectedMetricIds, metricId];
      if (nextMetricIds.length === 0) {
        return state;
      }
      persistState({ favorites: state.favorites, selectedMetricIds: nextMetricIds });
      return { selectedMetricIds: nextMetricIds };
    });
  },
  setSelectedMetricIds: (metricIds) => {
    const nextMetricIds = normalizeMetricIds(metricIds);
    set((state) => {
      persistState({ favorites: state.favorites, selectedMetricIds: nextMetricIds });
      return { selectedMetricIds: nextMetricIds };
    });
  },
  resetFavoritesState: () => {
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(FAVORITES_STORAGE_KEY);
    }
    set({
      favorites: [],
      selectedMetricIds: DEFAULT_FAVORITE_METRIC_IDS,
      isPanelOpen: false,
      activeTab: "saved",
    });
  },
}));