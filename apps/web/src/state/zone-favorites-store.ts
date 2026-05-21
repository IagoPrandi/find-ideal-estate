import { create } from "zustand";
import type { AuthStatusRead, FavoriteZoneEntry } from "../api/client";
import { ALL_ZONE_METRIC_IDS, DEFAULT_ZONE_METRIC_IDS, type ZoneMetricId, isZoneMetricId } from "../lib/zone-favorites";

export type ZoneFavoritesPanelTab = "saved" | "compare";

const ZONE_FAVORITES_PREFS_KEY = "find-ideal-estate:zone-favorite-preferences:v1";

function normalizeZoneMetricIds(ids: string[] | undefined): ZoneMetricId[] {
  const normalized = (ids || []).filter(isZoneMetricId);
  return normalized.length > 0 ? normalized : DEFAULT_ZONE_METRIC_IDS;
}

function loadZonePrefs(): { selectedZoneMetricIds: ZoneMetricId[] } {
  if (typeof window === "undefined") return { selectedZoneMetricIds: DEFAULT_ZONE_METRIC_IDS };
  try {
    const raw = window.localStorage.getItem(ZONE_FAVORITES_PREFS_KEY);
    if (!raw) return { selectedZoneMetricIds: DEFAULT_ZONE_METRIC_IDS };
    const parsed = JSON.parse(raw) as { selectedZoneMetricIds?: string[] };
    return { selectedZoneMetricIds: normalizeZoneMetricIds(parsed.selectedZoneMetricIds) };
  } catch {
    return { selectedZoneMetricIds: DEFAULT_ZONE_METRIC_IDS };
  }
}

function persistZonePrefs(state: { selectedZoneMetricIds: ZoneMetricId[] }) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(
    ZONE_FAVORITES_PREFS_KEY,
    JSON.stringify({ selectedZoneMetricIds: state.selectedZoneMetricIds.filter((id) => ALL_ZONE_METRIC_IDS.includes(id)) }),
  );
}

type ZoneFavoritesState = {
  zoneFavorites: FavoriteZoneEntry[];
  selectedZoneMetricIds: ZoneMetricId[];
  isPanelOpen: boolean;
  activeTab: ZoneFavoritesPanelTab;
  selectedZoneKey: string | null;
  isAuthenticated: boolean;
  isHydrating: boolean;
  accountUserId: string | null;
  pendingZoneKeys: string[];
  isZoneFavorite: (journeyId: string, zoneFingerprint: string) => boolean;
  isZoneFavoritePending: (journeyId: string, zoneFingerprint: string) => boolean;
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
  toggleZoneMetric: (metricId: ZoneMetricId) => void;
  updateZoneNote: (zoneKey: string, note: string) => Promise<boolean>;
  setPanelOpen: (value: boolean) => void;
  togglePanel: () => void;
  setActiveTab: (value: ZoneFavoritesPanelTab) => void;
  setSelectedZoneKey: (value: string | null) => void;
  resetZoneFavoritesState: () => void;
};

const initialZonePrefs = loadZonePrefs();

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

async function updateZoneNoteApi(zoneKey: string, note: string) {
  const client = await import("../api/client");
  return client.updateZoneFavoriteNote(zoneKey, note);
}

export const useZoneFavoritesStore = create<ZoneFavoritesState>((set, get) => ({
  zoneFavorites: [],
  selectedZoneMetricIds: initialZonePrefs.selectedZoneMetricIds,
  isPanelOpen: false,
  activeTab: "saved",
  selectedZoneKey: null,
  isAuthenticated: false,
  isHydrating: false,
  accountUserId: null,
  pendingZoneKeys: [],
  isZoneFavorite: (journeyId, zoneFingerprint) => {
    const key = buildZoneKey(journeyId, zoneFingerprint);
    return get().zoneFavorites.some((entry) => entry.zoneKey === key);
  },
  isZoneFavoritePending: (journeyId, zoneFingerprint) => {
    const key = buildZoneKey(journeyId, zoneFingerprint);
    return get().pendingZoneKeys.includes(key);
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
        pendingZoneKeys: [],
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
        pendingZoneKeys: [],
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
        pendingZoneKeys: [],
      });
    }
  },
  addZoneFavorite: async ({ journeyId, zoneFingerprint, searchType, usageType }) => {
    if (!get().isAuthenticated) {
      return false;
    }
    const zoneKey = buildZoneKey(journeyId, zoneFingerprint);
    if (get().pendingZoneKeys.includes(zoneKey)) {
      return false;
    }
    const optimisticSavedAt = new Date().toISOString();
    const optimisticZoneFavorite: FavoriteZoneEntry = {
      zoneKey,
      journeyId,
      zoneFingerprint,
      searchType,
      usageType,
      savedAt: optimisticSavedAt,
      payload: {
        fingerprint: zoneFingerprint,
        journey_id: journeyId,
        transport_point_id: null,
        transport_point: null,
        neighborhood_name: null,
        city_name: null,
        state_code: null,
        isochrone_geom: null,
        poi_counts: null,
        poi_points: [],
        metrics: {},
        listings: [],
      },
      note: null,
    };

    set((state) => ({
      pendingZoneKeys: [...state.pendingZoneKeys.filter((key) => key !== zoneKey), zoneKey],
      zoneFavorites: [optimisticZoneFavorite, ...state.zoneFavorites.filter((entry) => entry.zoneKey !== zoneKey)],
    }));

    try {
      const saved = await saveAccountZoneFavoriteApi({ journeyId, zoneFingerprint, searchType, usageType });
      set((state) => ({
        pendingZoneKeys: state.pendingZoneKeys.filter((key) => key !== zoneKey),
        zoneFavorites: [saved, ...state.zoneFavorites.filter((entry) => entry.zoneKey !== saved.zoneKey)],
      }));
      return true;
    } catch {
      set((state) => ({
        pendingZoneKeys: state.pendingZoneKeys.filter((key) => key !== zoneKey),
        zoneFavorites: state.zoneFavorites.filter(
          (entry) => entry.zoneKey !== zoneKey || entry.savedAt !== optimisticSavedAt,
        ),
      }));
      return false;
    }
  },
  removeZoneFavorite: async (zoneKey) => {
    if (!get().isAuthenticated) {
      return false;
    }
    if (get().pendingZoneKeys.includes(zoneKey)) {
      return false;
    }
    const removedFavorite = get().zoneFavorites.find((entry) => entry.zoneKey === zoneKey) || null;
    set((state) => ({
      pendingZoneKeys: [...state.pendingZoneKeys.filter((key) => key !== zoneKey), zoneKey],
      zoneFavorites: state.zoneFavorites.filter((entry) => entry.zoneKey !== zoneKey),
    }));

    try {
      await deleteAccountZoneFavoriteApi(zoneKey);
      set((state) => ({
        pendingZoneKeys: state.pendingZoneKeys.filter((key) => key !== zoneKey),
      }));
      return true;
    } catch {
      set((state) => ({
        pendingZoneKeys: state.pendingZoneKeys.filter((key) => key !== zoneKey),
        zoneFavorites: removedFavorite && !state.zoneFavorites.some((entry) => entry.zoneKey === zoneKey)
          ? [removedFavorite, ...state.zoneFavorites]
          : state.zoneFavorites,
      }));
      return false;
    }
  },
  toggleZoneFavorite: async (payload) => {
    const key = buildZoneKey(payload.journeyId, payload.zoneFingerprint);
    if (get().pendingZoneKeys.includes(key)) {
      return false;
    }
    if (get().zoneFavorites.some((entry) => entry.zoneKey === key)) {
      return await get().removeZoneFavorite(key);
    }
    return await get().addZoneFavorite(payload);
  },
  toggleZoneMetric: (metricId) => {
    set((state) => {
      const hasMetric = state.selectedZoneMetricIds.includes(metricId);
      const next = hasMetric
        ? state.selectedZoneMetricIds.filter((id) => id !== metricId)
        : [...state.selectedZoneMetricIds, metricId];
      if (next.length === 0) return state;
      persistZonePrefs({ selectedZoneMetricIds: next });
      return { selectedZoneMetricIds: next };
    });
  },
  updateZoneNote: async (zoneKey, note) => {
    if (!get().isAuthenticated) return false;
    try {
      const updated = await updateZoneNoteApi(zoneKey, note);
      set((state) => ({
        zoneFavorites: state.zoneFavorites.map((entry) =>
          entry.zoneKey === zoneKey ? { ...entry, note: updated.note } : entry,
        ),
      }));
      return true;
    } catch {
      return false;
    }
  },
  setPanelOpen: (value) => set({ isPanelOpen: value }),
  togglePanel: () => set((state) => ({ isPanelOpen: !state.isPanelOpen })),
  setActiveTab: (value) => set({ activeTab: value }),
  setSelectedZoneKey: (value) => set({ selectedZoneKey: value }),
  resetZoneFavoritesState: () => {
    set({
      zoneFavorites: [],
      selectedZoneMetricIds: DEFAULT_ZONE_METRIC_IDS,
      isPanelOpen: false,
      activeTab: "saved",
      selectedZoneKey: null,
      isAuthenticated: false,
      isHydrating: false,
      accountUserId: null,
      pendingZoneKeys: [],
    });
  },
}));
