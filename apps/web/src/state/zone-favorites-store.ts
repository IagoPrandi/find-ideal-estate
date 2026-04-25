import { create } from "zustand";
import type { AuthStatusRead, FavoriteZoneEntry } from "../api/client";

export type ZoneFavoritesPanelTab = "saved" | "compare";

type ZoneFavoritesState = {
  zoneFavorites: FavoriteZoneEntry[];
  isPanelOpen: boolean;
  activeTab: ZoneFavoritesPanelTab;
  selectedZoneKey: string | null;
  isAuthenticated: boolean;
  isHydrating: boolean;
  accountUserId: string | null;
  isZoneFavorite: (journeyId: string, zoneFingerprint: string) => boolean;
  syncWithAuthStatus: (authStatus: AuthStatusRead) => Promise<void>;
  addZoneFavorite: (payload: {
    journeyId: string;
    zoneFingerprint: string;
    searchType: string;
    usageType: string;
  }) => Promise<boolean>;
  removeZoneFavorite: (zoneKey: string) => Promise<boolean>;
  toggleZoneFavorite: (payload: {
    journeyId: string;
    zoneFingerprint: string;
    searchType: string;
    usageType: string;
  }) => Promise<boolean>;
  setPanelOpen: (value: boolean) => void;
  togglePanel: () => void;
  setActiveTab: (value: ZoneFavoritesPanelTab) => void;
  setSelectedZoneKey: (value: string | null) => void;
  resetZoneFavoritesState: () => void;
};

let latestZoneSyncRequestId = 0;

function buildZoneKey(journeyId: string, zoneFingerprint: string) {
  return `zone:${journeyId}:${zoneFingerprint}`;
}

async function getAccountZoneFavoritesApi() {
  const client = await import("../api/client");
  return client.getAccountZoneFavorites();
}

async function saveAccountZoneFavoriteApi(payload: {
  journeyId: string;
  zoneFingerprint: string;
  searchType: string;
  usageType: string;
}) {
  const client = await import("../api/client");
  return client.saveAccountZoneFavorite(payload);
}

async function deleteAccountZoneFavoriteApi(zoneKey: string) {
  const client = await import("../api/client");
  await client.deleteAccountZoneFavorite(zoneKey);
}

export const useZoneFavoritesStore = create<ZoneFavoritesState>((set, get) => ({
  zoneFavorites: [],
  isPanelOpen: false,
  activeTab: "saved",
  selectedZoneKey: null,
  isAuthenticated: false,
  isHydrating: false,
  accountUserId: null,
  isZoneFavorite: (journeyId, zoneFingerprint) => {
    const key = buildZoneKey(journeyId, zoneFingerprint);
    return get().zoneFavorites.some((entry) => entry.zoneKey === key);
  },
  syncWithAuthStatus: async (authStatus) => {
    const nextUserId = authStatus.is_authenticated ? authStatus.user?.id || null : null;

    if (!authStatus.is_authenticated || !nextUserId) {
      latestZoneSyncRequestId += 1;
      set({
        zoneFavorites: [],
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

    const syncRequestId = ++latestZoneSyncRequestId;
    set({
      isAuthenticated: true,
      isHydrating: true,
      accountUserId: nextUserId,
    });

    try {
      const zoneFavorites = await getAccountZoneFavoritesApi();
      if (syncRequestId !== latestZoneSyncRequestId) {
        return;
      }
      set({
        zoneFavorites,
        isAuthenticated: true,
        isHydrating: false,
        accountUserId: nextUserId,
      });
    } catch {
      if (syncRequestId !== latestZoneSyncRequestId) {
        return;
      }
      set({
        zoneFavorites: [],
        isAuthenticated: true,
        isHydrating: false,
        accountUserId: nextUserId,
      });
    }
  },
  addZoneFavorite: async ({ journeyId, zoneFingerprint, searchType, usageType }) => {
    if (!get().isAuthenticated) {
      return false;
    }
    try {
      const saved = await saveAccountZoneFavoriteApi({ journeyId, zoneFingerprint, searchType, usageType });
      set((state) => ({
        zoneFavorites: [saved, ...state.zoneFavorites.filter((entry) => entry.zoneKey !== saved.zoneKey)],
      }));
      return true;
    } catch {
      return false;
    }
  },
  removeZoneFavorite: async (zoneKey) => {
    if (!get().isAuthenticated) {
      return false;
    }
    try {
      await deleteAccountZoneFavoriteApi(zoneKey);
      set((state) => ({
        zoneFavorites: state.zoneFavorites.filter((entry) => entry.zoneKey !== zoneKey),
      }));
      return true;
    } catch {
      return false;
    }
  },
  toggleZoneFavorite: async (payload) => {
    const key = buildZoneKey(payload.journeyId, payload.zoneFingerprint);
    if (get().zoneFavorites.some((entry) => entry.zoneKey === key)) {
      return await get().removeZoneFavorite(key);
    }
    return await get().addZoneFavorite(payload);
  },
  setPanelOpen: (value) => set({ isPanelOpen: value }),
  togglePanel: () => set((state) => ({ isPanelOpen: !state.isPanelOpen })),
  setActiveTab: (value) => set({ activeTab: value }),
  setSelectedZoneKey: (value) => set({ selectedZoneKey: value }),
  resetZoneFavoritesState: () => {
    set({
      zoneFavorites: [],
      isPanelOpen: false,
      activeTab: "saved",
      selectedZoneKey: null,
      isAuthenticated: false,
      isHydrating: false,
      accountUserId: null,
    });
  },
}));
