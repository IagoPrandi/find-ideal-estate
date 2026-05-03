import { beforeEach, describe, expect, it, vi } from "vitest";
import { deleteAccountFavorite, getAccountFavorites, saveAccountFavorite } from "../api/client";
import { useFavoritesStore } from "./favorites-store";

vi.mock("../api/client", () => ({
  deleteAccountFavorite: vi.fn(),
  getAccountFavorites: vi.fn(),
  saveAccountFavorite: vi.fn(),
}));

const sampleFavorite = {
  listingKey: "property:prop-1",
  journeyId: "journey-1",
  zoneFingerprint: "zone-fp-1",
  searchType: "rent",
  usageType: "residential",
  savedAt: "2026-04-13T15:00:00Z",
  listing: {
    property_id: "prop-1",
    platform: "quintoandar",
    platform_listing_id: "qa-1",
    address_normalized: "Rua Teste, 1",
    url: "/imovel/1",
    current_best_price: "3200",
    current_unit_price: 64,
    area_m2: 50,
    bedrooms: 2,
    inside_zone: true,
    has_coordinates: true,
    lat: -23.5,
    lon: -46.7,
    platforms_available: ["quintoandar"],
    platform_variants: [],
  },
};

describe("favorites-store", () => {
  beforeEach(() => {
    useFavoritesStore.getState().resetFavoritesState();
    vi.clearAllMocks();
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
        created_at: "2026-04-12T10:00:00Z",
        role: "user",
      },
      session_expires_at: "2026-05-12T10:00:00Z",
    });

    expect(useFavoritesStore.getState().isAuthenticated).toBe(true);
    expect(useFavoritesStore.getState().favorites).toEqual([sampleFavorite]);

    await useFavoritesStore.getState().syncWithAuthStatus({
      is_authenticated: false,
      user: null,
      session_expires_at: null,
    });

    expect(useFavoritesStore.getState().isAuthenticated).toBe(false);
    expect(useFavoritesStore.getState().favorites).toEqual([]);
  });

  it("persists add and remove through the account API", async () => {
    useFavoritesStore.setState({ isAuthenticated: true, accountUserId: "user-1" });
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
  });
});
