import type { ZoneDetailResponse } from "../../api/schemas";
import { haversineMeters } from "../../lib/geo";
import { formatCurrencyBr, normalizeCategory, parseFiniteNumber } from "../../lib/listingFormat";
import type { InterestPoint } from "../steps/types";
import type { ListingFeature } from "../steps/step3Types";

export function getListingKey(feature: ListingFeature, index: number): string {
  const props = feature.properties || {};
  const stableId =
    (props.property_id as string | undefined) ||
    (props.platform_listing_id as string | undefined) ||
    (props.listing_id as string | undefined);
  if (stableId) {
    return String(stableId);
  }
  if (feature.geometry?.coordinates?.length) {
    return `${index}_${feature.geometry.coordinates.join("_")}`;
  }
  return `${index}_${JSON.stringify(props)}`;
}

export function resolveListingFeatureText(feature: ListingFeature): {
  priceLabel: string;
  address: string;
  url: string;
} {
  const props = feature.properties || {};
  const price =
    (props.price as number | undefined) ||
    (props.rent_price as number | undefined) ||
    (props.sale_price as number | undefined) ||
    (props.total_price as number | undefined);
  const address =
    (props.address as string | undefined) ||
    (props.street as string | undefined) ||
    (props.title as string | undefined) ||
    "Endereço não informado";
  const url =
    (props.url as string | undefined) ||
    (props.listing_url as string | undefined) ||
    (props.link as string | undefined) ||
    "";
  return {
    priceLabel: formatCurrencyBr(price),
    address,
    url
  };
}

export type ListingAnalyticsComputed = {
  listingKey: string;
  priceValue: number | null;
  sizeM2: number | null;
  bedrooms: number | null;
  distanceTransportM: number | null;
  platform: string;
  poiCountWithinRadius: number;
  nearestPoiByCategory: Array<{ category: string; distanceM: number | null }>;
};

export function computeListingAnalytics(
  feature: ListingFeature,
  index: number,
  ctx: {
    interests: InterestPoint[];
    zoneDetailData: ZoneDetailResponse | null;
    poiCountRadiusM: number;
  }
): ListingAnalyticsComputed {
  const { interests, zoneDetailData, poiCountRadiusM } = ctx;
  const props = feature.properties || {};
  const priceValue =
    parseFiniteNumber(props.price) ??
    parseFiniteNumber(props.rent_price) ??
    parseFiniteNumber(props.sale_price) ??
    parseFiniteNumber(props.total_price);
  const sizeM2 =
    parseFiniteNumber(props.area_m2) ??
    parseFiniteNumber(props.area) ??
    parseFiniteNumber(props.area_total_m2) ??
    parseFiniteNumber(props.private_area) ??
    parseFiniteNumber(props.usable_area);
  const bedrooms =
    parseFiniteNumber(props.bedrooms) ??
    parseFiniteNumber(props.beds) ??
    parseFiniteNumber(props.quartos);
  const distanceTransportM =
    parseFiniteNumber(props.distance_transport_m) ??
    parseFiniteNumber(props.dist_transport_m) ??
    parseFiniteNumber(props.distance_to_transport_m);
  const platform =
    String(props.source || props.platform || props.site || "")
      .trim()
      .toUpperCase() || "PLATAFORMA N/D";
  const listingKey = getListingKey(feature, index);

  let poiCountWithinRadius = 0;
  const nearestPoiByCategory: Array<{ category: string; distanceM: number | null }> = [];

  if (feature.geometry?.type === "Point" && feature.geometry.coordinates) {
    const [lon, lat] = feature.geometry.coordinates;
    const categoriesPriority =
      interests.length > 0
        ? Array.from(new Set(interests.map((item) => item.category))).filter(Boolean)
        : Object.entries(zoneDetailData?.poi_count_by_category || {})
            .sort((a, b) => b[1] - a[1])
            .map(([category]) => category)
            .slice(0, 3);

    const nearestByNormalized = new Map<string, { category: string; distanceM: number | null }>();
    categoriesPriority.forEach((category) => {
      nearestByNormalized.set(normalizeCategory(category), { category, distanceM: null });
    });

    for (const poi of zoneDetailData?.poi_points || []) {
      if (!Number.isFinite(poi.lon) || !Number.isFinite(poi.lat)) {
        continue;
      }
      const distanceM = haversineMeters(lat, lon, poi.lat, poi.lon);
      if (distanceM <= poiCountRadiusM) {
        poiCountWithinRadius += 1;
      }
      const poiCategory = String(poi.category || "outros");
      const normalized = normalizeCategory(poiCategory);
      const current = nearestByNormalized.get(normalized);
      if (!current) {
        continue;
      }
      if (current.distanceM === null || distanceM < current.distanceM) {
        current.distanceM = distanceM;
        current.category = poiCategory;
      }
    }

    nearestPoiByCategory.push(...nearestByNormalized.values());
  }

  return {
    listingKey,
    priceValue,
    sizeM2,
    bedrooms,
    distanceTransportM,
    platform,
    poiCountWithinRadius,
    nearestPoiByCategory
  };
}
