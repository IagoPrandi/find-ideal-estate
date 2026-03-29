export const POI_CATEGORY_ORDER = ["school", "supermarket", "pharmacy", "park", "restaurant", "gym"] as const;

export type PoiCategoryKey = (typeof POI_CATEGORY_ORDER)[number];
export type PoiCategoryFilter = "all" | PoiCategoryKey;

export type ZonePoiPointLike = {
  kind?: string | null;
  id?: string | null;
  name?: string | null;
  category?: string | null;
  address?: string | null;
  lat: number;
  lon: number;
};

export type ZonePoiBackfillCandidate = {
  poi_counts?: Record<string, number> | null;
  poi_points?: ZonePoiPointLike[] | null;
};

const POI_CATEGORY_META: Record<PoiCategoryKey, { label: string; singularLabel: string; color: string; iconId: string }> = {
  school: {
    label: "Escolas",
    singularLabel: "Escola",
    color: "#2563eb",
    iconId: "poi-school-icon"
  },
  supermarket: {
    label: "Mercados",
    singularLabel: "Mercado",
    color: "#d97706",
    iconId: "poi-supermarket-icon"
  },
  pharmacy: {
    label: "Farmacias",
    singularLabel: "Farmacia",
    color: "#16a34a",
    iconId: "poi-pharmacy-icon"
  },
  park: {
    label: "Parques",
    singularLabel: "Parque",
    color: "#0f766e",
    iconId: "poi-park-icon"
  },
  restaurant: {
    label: "Restaurantes",
    singularLabel: "Restaurante",
    color: "#dc2626",
    iconId: "poi-restaurant-icon"
  },
  gym: {
    label: "Academias",
    singularLabel: "Academia",
    color: "#7c3aed",
    iconId: "poi-gym-icon"
  }
};

const DEFAULT_POI_CATEGORY_META = {
  label: "Outros",
  singularLabel: "POI",
  color: "#64748b",
  iconId: "poi-default-icon"
};

export function getPoiCategoryMeta(category: string | null | undefined) {
  if (category && category in POI_CATEGORY_META) {
    return POI_CATEGORY_META[category as PoiCategoryKey];
  }
  return DEFAULT_POI_CATEGORY_META;
}

export function sortPoiPoints(points: ZonePoiPointLike[]) {
  const categoryIndex = new Map<string, number>(POI_CATEGORY_ORDER.map((category, index) => [category, index]));
  return [...points].sort((left, right) => {
    const leftIndex = categoryIndex.get(left.category || "") ?? Number.MAX_SAFE_INTEGER;
    const rightIndex = categoryIndex.get(right.category || "") ?? Number.MAX_SAFE_INTEGER;
    if (leftIndex !== rightIndex) {
      return leftIndex - rightIndex;
    }
    return (left.name || "").localeCompare(right.name || "", "pt-BR");
  });
}

export function getZonePoiSelectionKey(point: ZonePoiPointLike, zoneFingerprint: string | null, index: number) {
  const stableId = point.id || point.name || `${point.lat}:${point.lon}:${index}`;
  return `${zoneFingerprint || "zone"}:${point.category || "other"}:${stableId}`;
}

export function zoneNeedsPoiBackfill(zone: ZonePoiBackfillCandidate) {
  const poiCounts = zone.poi_counts;
  if (!poiCounts) {
    return false;
  }

  if (zone.poi_points === null || zone.poi_points === undefined) {
    return true;
  }

  return POI_CATEGORY_ORDER.some((category) => !(category in poiCounts));
}