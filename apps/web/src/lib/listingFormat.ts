import type { ListingCardRead } from "../api/client";
import type { ListingsPanelFilters } from "../state/journey-store";

const PLATFORM_BASE_URLS: Record<string, string> = {
  zapimoveis: "https://www.zapimoveis.com.br",
  vivareal: "https://www.vivareal.com.br",
  quintoandar: "https://www.quintoandar.com.br",
};

function resolvePlatformAbsoluteUrl(url: string | null | undefined, platform: string | null | undefined): string | null {
  if (!url) return null;
  if (url.startsWith("//")) return `https:${url}`;
  if (url.startsWith("https://") || url.startsWith("http://")) return url;
  if (url.startsWith("/")) {
    const base = PLATFORM_BASE_URLS[(platform ?? "").toLowerCase()];
    if (base) return `${base}${url}`;
  }
  return null;
}

/**
 * Ensures a listing URL is absolute. The Glue API (ZapImoveis/VivaReal) sometimes
 * returns relative paths like `/imovel/...`. Resolve them against the platform's
 * known base URL so clicking opens the real external ad page.
 */
export function resolvePlatformUrl(url: string | null | undefined, platform: string | null | undefined): string | null {
  return resolvePlatformAbsoluteUrl(url, platform);
}

export function resolvePlatformImageUrl(url: string | null | undefined, platform: string | null | undefined): string | null {
  return resolvePlatformAbsoluteUrl(url, platform);
}

export function formatCurrencyBr(value: unknown): string {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "Preço não informado";
  }
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
    maximumFractionDigits: 0
  }).format(value);
}

export function parseFiniteNumber(value: unknown): number | null {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }
  if (typeof value === "string") {
    const sanitized = value.replace(/[^\d.,-]/g, "").trim();
    if (!sanitized) {
      return null;
    }

    let normalized = sanitized;
    const hasDot = normalized.includes(".");
    const hasComma = normalized.includes(",");

    if (hasDot && hasComma) {
      normalized = normalized.lastIndexOf(",") > normalized.lastIndexOf(".")
        ? normalized.replace(/\./g, "").replace(",", ".")
        : normalized.replace(/,/g, "");
    } else if (hasComma) {
      normalized = /^-?\d{1,3}(,\d{3})+$/.test(normalized)
        ? normalized.replace(/,/g, "")
        : normalized.replace(",", ".");
    } else if (hasDot) {
      normalized = /^-?\d{1,3}(\.\d{3})+$/.test(normalized)
        ? normalized.replace(/\./g, "")
        : normalized;
    }

    const parsed = Number(normalized);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

export function normalizeCategory(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase();
}

export function getListingDisplayPrice(
  listing: Pick<ListingCardRead, "current_best_price" | "condo_fee" | "iptu">
): number | null {
  const values = [
    parseFiniteNumber(listing.current_best_price),
    parseFiniteNumber(listing.condo_fee),
    parseFiniteNumber(listing.iptu)
  ].filter((value): value is number => value !== null);

  if (values.length === 0) {
    return null;
  }

  return values.reduce((sum, value) => sum + value, 0);
}

export function getListingSelectionKey(
  listing: Pick<ListingCardRead, "property_id" | "platform" | "platform_listing_id">
): string {
  if (listing.property_id) {
    return `property:${listing.property_id}`;
  }
  if (listing.platform && listing.platform_listing_id) {
    return `platform:${listing.platform}:${listing.platform_listing_id}`;
  }
  if (listing.platform_listing_id) {
    return `listing:${listing.platform_listing_id}`;
  }
  return "";
}

export function applyListingsPanelFilters(
  listings: ListingCardRead[],
  filters: ListingsPanelFilters
): ListingCardRead[] {
  const scopedListings = filters.spatialScope === "inside_zone"
    ? listings.filter((listing) => listing.inside_zone)
    : listings;

  return scopedListings.filter((listing) => {
    const price = getListingDisplayPrice(listing);
    const area = typeof listing.area_m2 === "number" ? listing.area_m2 : null;
    const minPrice = filters.minPrice !== "" ? Number(filters.minPrice) : null;
    const maxPrice = filters.maxPrice !== "" ? Number(filters.maxPrice) : null;
    const minSize = filters.minSize !== "" ? Number(filters.minSize) : null;
    const maxSize = filters.maxSize !== "" ? Number(filters.maxSize) : null;

    if (minPrice !== null && (price === null || price < minPrice)) return false;
    if (maxPrice !== null && (price === null || price > maxPrice)) return false;
    if (filters.usageType !== "all" && listing.usage_type != null && listing.usage_type !== filters.usageType) return false;
    if (minSize !== null && (area === null || area < minSize)) return false;
    if (maxSize !== null && (area === null || area > maxSize)) return false;
    return true;
  });
}
