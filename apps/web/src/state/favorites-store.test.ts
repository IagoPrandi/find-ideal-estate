import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  deleteAccountFavorite,
  deleteAccountZoneFavorite,
  getAccountFavorites,
  saveAccountFavorite,
  saveAccountZoneFavorite,
  type ListingCardRead,
} from "../api/client";
import { useFavoritesStore } from "./favorites-store";
import { useZoneFavoritesStore } from "./zone-favorites-store";

vi.mock("../api/client", () => ({
  addManualListingFavorite: vi.fn(),
  deleteAccountFavorite: vi.fn(),
  deleteAccountZoneFavorite: vi.fn(),
  getAccountFavorites: vi.fn(),
  getAccountZoneFavorites: vi.fn(),
  saveAccountFavorite: vi.fn(),
  saveAccountZoneFavorite: vi.fn(),
  updateListingFavoriteNote: vi.fn(),
  updateZoneFavoriteNote: vi.fn(),
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, resolve, reject };
}

const listing: ListingCardRead = {
  property_id: "prop-1",
  platform: "quintoandar",
  platform_listing_id: "qa-1",
  address_normalized: "Rua Dentro, 10",
  current_best_price: "3500",
  has_coordinates: false,
  inside_zone: true,
  platforms_available: ["quintoandar"],
  platform_variants: [],
};

const sampleFavorite = {
  listingKey: "property:prop-1",
  journeyId: "journey-1",
  zoneFingerprint: "zone-fp-1",
  searchType: "rent",
  usageType: "residential",
  savedAt: "2026-04-13T15:00:00Z",
  listing: {
    ...listing,
    address_normalized: "Rua Teste, 1",
    url: "/imovel/1",
    current_best_price: "3200",
    current_unit_price: 64,
    area_m2: 50,
    bedrooms: 2,
    has_coordinates: true,
    lat: -23.5,
    lon: -46.7,
  },
  note: null,
};

describe("favorites stores", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useFavoritesStore.getState().resetFavoritesState();
    useZoneFavoritesStore.getState().resetZoneFavoritesState();
    useFavoritesStore.setState({ isAuthenticated: true });
    useZoneFavoritesStore.setState({ isAuthenticated: true });
  });

  it("loads account favorites on authenticated sync and clears them on logout", async () => {
    vi.mocked(getAccountFavorites).mockResolvedValue([sampleFavorite] as never);

    await useFavoritesStore.getState().syncWithAuthStatus({
      is_authenticated: true,
      user: {
        id: "user-1",
        email: "ana@example.com",
        display_name: "Ana",
        is_active: true,
        is_superuser: false,
        can_start_immediate_scraping: false,
        usage_restrictions_disabled: false,
        created_at: "2026-04-12T10:00:00Z",
        role: "user",
      },
      session_expires_at: "2026-05-12T10:00:00Z",
      usage_restrictions_disabled_globally: false,
    });

    expect(useFavoritesStore.getState().isAuthenticated).toBe(true);
    expect(useFavoritesStore.getState().favorites).toEqual([sampleFavorite]);

    await useFavoritesStore.getState().syncWithAuthStatus({
      is_authenticated: false,
      user: null,
      session_expires_at: null,
      usage_restrictions_disabled_globally: false,
    });

    expect(useFavoritesStore.getState().isAuthenticated).toBe(false);
    expect(useFavoritesStore.getState().favorites).toEqual([]);
    expect(useFavoritesStore.getState().pendingFavoriteKeys).toEqual([]);
  });

  it("persists add and remove through the account API", async () => {
    vi.mocked(saveAccountFavorite).mockResolvedValue(sampleFavorite as never);
    vi.mocked(deleteAccountFavorite).mockResolvedValue(undefined as never);

    const saved = await useFavoritesStore.getState().addFavorite({
      listing: sampleFavorite.listing,
      journeyId: sampleFavorite.journeyId,
      zoneFingerprint: sampleFavorite.zoneFingerprint,
      searchType: sampleFavorite.searchType,
      usageType: sampleFavorite.usageType,
    });

    expect(saved).toBe(true);
    expect(useFavoritesStore.getState().favorites).toEqual([sampleFavorite]);

    const removed = await useFavoritesStore.getState().removeFavorite(sampleFavorite.listingKey);

    expect(removed).toBe(true);
    expect(useFavoritesStore.getState().favorites).toEqual([]);
    expect(useFavoritesStore.getState().pendingFavoriteKeys).toEqual([]);
  });

  it("shows listing favorite optimistically and replaces it with the server response", async () => {
    const saveRequest = deferred<Awaited<ReturnType<typeof saveAccountFavorite>>>();
    vi.mocked(saveAccountFavorite).mockReturnValue(saveRequest.promise);

    const resultPromise = useFavoritesStore.getState().addFavorite({
      listing,
      journeyId: "journey-1",
      zoneFingerprint: "zone-fp-1",
      searchType: "rent",
      usageType: "residential",
    });

    expect(useFavoritesStore.getState().favorites).toHaveLength(1);
    expect(useFavoritesStore.getState().favorites[0].listingKey).toBe("property:prop-1");
    expect(useFavoritesStore.getState().pendingFavoriteKeys).toEqual(["property:prop-1"]);

    saveRequest.resolve({
      listingKey: "property:prop-1",
      journeyId: "journey-1",
      zoneFingerprint: "zone-fp-1",
      searchType: "rent",
      usageType: "residential",
      savedAt: "2026-05-21T10:00:00Z",
      listing,
      note: "confirmado",
    });

    await expect(resultPromise).resolves.toBe(true);
    expect(useFavoritesStore.getState().favorites[0].savedAt).toBe("2026-05-21T10:00:00Z");
    expect(useFavoritesStore.getState().favorites[0].note).toBe("confirmado");
    expect(useFavoritesStore.getState().pendingFavoriteKeys).toEqual([]);
  });

  it("rolls back optimistic listing favorite when the save fails", async () => {
    vi.mocked(saveAccountFavorite).mockRejectedValue(new Error("limite atingido"));

    await expect(useFavoritesStore.getState().addFavorite({
      listing,
      journeyId: "journey-1",
      zoneFingerprint: "zone-fp-1",
      searchType: "rent",
      usageType: "residential",
    })).resolves.toBe(false);

    expect(useFavoritesStore.getState().favorites).toEqual([]);
    expect(useFavoritesStore.getState().pendingFavoriteKeys).toEqual([]);
  });

  it("removes listing favorite optimistically and restores it when delete fails", async () => {
    useFavoritesStore.setState({
      favorites: [{
        listingKey: "property:prop-1",
        journeyId: "journey-1",
        zoneFingerprint: "zone-fp-1",
        searchType: "rent",
        usageType: "residential",
        savedAt: "2026-05-21T10:00:00Z",
        listing,
        note: null,
      }],
    });
    vi.mocked(deleteAccountFavorite).mockRejectedValue(new Error("falha"));

    await expect(useFavoritesStore.getState().removeFavorite("property:prop-1")).resolves.toBe(false);

    expect(useFavoritesStore.getState().favorites).toHaveLength(1);
    expect(useFavoritesStore.getState().pendingFavoriteKeys).toEqual([]);
  });

  it("shows zone favorite optimistically and replaces it with the server response", async () => {
    const saveRequest = deferred<Awaited<ReturnType<typeof saveAccountZoneFavorite>>>();
    vi.mocked(saveAccountZoneFavorite).mockReturnValue(saveRequest.promise);

    const resultPromise = useZoneFavoritesStore.getState().addZoneFavorite({
      journeyId: "journey-1",
      zoneFingerprint: "zone-fp-1",
      searchType: "rent",
      usageType: "residential",
    });

    const zoneKey = "zone:journey-1:zone-fp-1";
    expect(useZoneFavoritesStore.getState().zoneFavorites).toHaveLength(1);
    expect(useZoneFavoritesStore.getState().zoneFavorites[0].zoneKey).toBe(zoneKey);
    expect(useZoneFavoritesStore.getState().pendingZoneKeys).toEqual([zoneKey]);

    saveRequest.resolve({
      zoneKey,
      journeyId: "journey-1",
      zoneFingerprint: "zone-fp-1",
      searchType: "rent",
      usageType: "residential",
      savedAt: "2026-05-21T10:00:00Z",
      payload: {
        fingerprint: "zone-fp-1",
        journey_id: "journey-1",
        transport_point_id: null,
        transport_point: null,
        neighborhood_name: "Vila Mariana",
        city_name: "Sao Paulo",
        state_code: "SP",
        isochrone_geom: null,
        poi_counts: null,
        poi_points: [],
        metrics: { zone_average_price: 4200 },
        listings: [],
      },
      note: null,
    });

    await expect(resultPromise).resolves.toBe(true);
    expect(useZoneFavoritesStore.getState().zoneFavorites[0].payload.city_name).toBe("Sao Paulo");
    expect(useZoneFavoritesStore.getState().pendingZoneKeys).toEqual([]);
  });

  it("rolls back optimistic zone favorite when the save fails", async () => {
    vi.mocked(saveAccountZoneFavorite).mockRejectedValue(new Error("limite atingido"));

    await expect(useZoneFavoritesStore.getState().addZoneFavorite({
      journeyId: "journey-1",
      zoneFingerprint: "zone-fp-1",
      searchType: "rent",
      usageType: "residential",
    })).resolves.toBe(false);

    expect(useZoneFavoritesStore.getState().zoneFavorites).toEqual([]);
    expect(useZoneFavoritesStore.getState().pendingZoneKeys).toEqual([]);
  });

  it("removes zone favorite optimistically and restores it when delete fails", async () => {
    const zoneKey = "zone:journey-1:zone-fp-1";
    useZoneFavoritesStore.setState({
      zoneFavorites: [{
        zoneKey,
        journeyId: "journey-1",
        zoneFingerprint: "zone-fp-1",
        searchType: "rent",
        usageType: "residential",
        savedAt: "2026-05-21T10:00:00Z",
        payload: {
          fingerprint: "zone-fp-1",
          journey_id: "journey-1",
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
      }],
    });
    vi.mocked(deleteAccountZoneFavorite).mockRejectedValue(new Error("falha"));

    await expect(useZoneFavoritesStore.getState().removeZoneFavorite(zoneKey)).resolves.toBe(false);

    expect(useZoneFavoritesStore.getState().zoneFavorites).toHaveLength(1);
    expect(useZoneFavoritesStore.getState().pendingZoneKeys).toEqual([]);
  });
});
