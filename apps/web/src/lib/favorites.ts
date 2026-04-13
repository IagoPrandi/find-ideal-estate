import type { ListingCardRead } from "../api/client";
import type { ZoneFavoriteAnalytics } from "../api/schemas";
import { formatCurrencyBr, getListingDisplayPrice } from "./listingFormat";

export type FavoriteMetricId =
  | "listing_total_price"
  | "listing_unit_price"
  | "listing_area_m2"
  | "listing_bedrooms"
  | "zone_homicide_rate"
  | "zone_robbery_rate"
  | "zone_theft_rate"
  | "zone_crime_rate"
  | "zone_green_percentage"
  | "zone_flood_percentage";

export type FavoriteMetricDirection = "higher_better" | "lower_better";

export type FavoriteComparisonItem = {
  listingKey: string;
  savedAt: string;
  listing: ListingCardRead;
  analytics: ZoneFavoriteAnalytics | null;
};

type FavoriteMetricDefinition = {
  id: FavoriteMetricId;
  label: string;
  shortLabel: string;
  description: string;
  direction: FavoriteMetricDirection;
  defaultSelected?: boolean;
  getValue: (item: FavoriteComparisonItem) => number | null;
  formatValue: (value: number | null, item: FavoriteComparisonItem) => string;
};

function formatDensity(value: number | null) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "Sem base";
  }
  const digits = Math.abs(value) >= 10 ? 1 : Math.abs(value) >= 1 ? 2 : 4;
  return `${new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value)}/km²`;
}

function formatPercentage(value: number | null) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "Sem base";
  }
  return `${new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(value)}%`;
}

function formatPlainNumber(value: number | null) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "Sem base";
  }
  return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 }).format(value);
}

function formatArea(value: number | null) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "Sem base";
  }
  return `${new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 }).format(value)} m²`;
}

function formatCurrencyPerSquareMeter(value: number | null) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "Sem base";
  }
  return `${formatCurrencyBr(value)}/m²`;
}

export const FAVORITE_METRIC_DEFINITIONS: FavoriteMetricDefinition[] = [
  {
    id: "listing_total_price",
    label: "Menor valor total",
    shortLabel: "Valor total",
    description: "Compara o custo total atual do anúncio, somando aluguel, condomínio e IPTU quando disponíveis.",
    direction: "lower_better",
    defaultSelected: true,
    getValue: (item) => getListingDisplayPrice(item.listing),
    formatValue: (value) => formatCurrencyBr(value),
  },
  {
    id: "listing_unit_price",
    label: "Menor preço m²",
    shortLabel: "Preço m²",
    description: "Compara o valor atual por metro quadrado do imóvel.",
    direction: "lower_better",
    defaultSelected: true,
    getValue: (item) => (typeof item.listing.current_unit_price === "number" ? item.listing.current_unit_price : null),
    formatValue: (value) => formatCurrencyPerSquareMeter(value),
  },
  {
    id: "listing_area_m2",
    label: "Maior área",
    shortLabel: "Área",
    description: "Compara a área útil informada no anúncio.",
    direction: "higher_better",
    getValue: (item) => (typeof item.listing.area_m2 === "number" ? item.listing.area_m2 : null),
    formatValue: (value) => formatArea(value),
  },
  {
    id: "listing_bedrooms",
    label: "Mais quartos",
    shortLabel: "Quartos",
    description: "Compara a quantidade de quartos do imóvel.",
    direction: "higher_better",
    getValue: (item) => (typeof item.listing.bedrooms === "number" ? item.listing.bedrooms : null),
    formatValue: (value) => formatPlainNumber(value),
  },
  {
    id: "zone_homicide_rate",
    label: "Menos homicídio",
    shortLabel: "Homicídio",
    description: "Compara a densidade de homicídios por quilômetro quadrado.",
    direction: "lower_better",
    getValue: (item) => item.analytics?.metrics.homicide_density_per_km2 ?? null,
    formatValue: (value) => formatDensity(value),
  },
  {
    id: "zone_robbery_rate",
    label: "Menos roubo",
    shortLabel: "Roubo",
    description: "Compara a densidade de roubos por quilômetro quadrado.",
    direction: "lower_better",
    defaultSelected: true,
    getValue: (item) => item.analytics?.metrics.robbery_density_per_km2 ?? null,
    formatValue: (value) => formatDensity(value),
  },
  {
    id: "zone_theft_rate",
    label: "Menos furto",
    shortLabel: "Furto",
    description: "Compara a densidade de furtos por quilômetro quadrado.",
    direction: "lower_better",
    defaultSelected: true,
    getValue: (item) => item.analytics?.metrics.theft_density_per_km2 ?? null,
    formatValue: (value) => formatDensity(value),
  },
  {
    id: "zone_crime_rate",
    label: "Menos crimes",
    shortLabel: "Crimes",
    description: "Compara a soma padronizada de homicídios, roubos e furtos por quilômetro quadrado.",
    direction: "lower_better",
    getValue: (item) => item.analytics?.metrics.crime_density_per_km2 ?? null,
    formatValue: (value) => formatDensity(value),
  },
  {
    id: "zone_green_percentage",
    label: "Mais arborização",
    shortLabel: "Arborização",
    description: "Compara o percentual de cobertura vegetal na zona.",
    direction: "higher_better",
    defaultSelected: true,
    getValue: (item) => item.analytics?.metrics.green_percentage ?? null,
    formatValue: (value) => formatPercentage(value),
  },
  {
    id: "zone_flood_percentage",
    label: "Menor risco de alagamento",
    shortLabel: "Alagamento",
    description: "Compara o percentual da zona em área com risco de alagamento.",
    direction: "lower_better",
    getValue: (item) => item.analytics?.metrics.flood_percentage ?? null,
    formatValue: (value, item) => {
      const percentage = formatPercentage(value);
      const label = item.analytics?.metrics.flood_risk_label;
      return label ? `${percentage} · ${label}` : percentage;
    },
  },
];

export const ALL_FAVORITE_METRIC_IDS = FAVORITE_METRIC_DEFINITIONS.map((metric) => metric.id);
export const DEFAULT_FAVORITE_METRIC_IDS = FAVORITE_METRIC_DEFINITIONS.filter((metric) => metric.defaultSelected).map((metric) => metric.id);

export function buildZoneFavoriteAnalyticsQueryKey(
  journeyId: string,
  zoneFingerprint: string,
  searchType: string,
  usageType: string,
) {
  return ["zone-favorite-analytics", journeyId, zoneFingerprint, searchType, usageType] as const;
}

export function buildZoneFavoriteAnalyticsRequestKey(
  journeyId: string,
  zoneFingerprint: string,
  searchType: string,
  usageType: string,
) {
  return [journeyId, zoneFingerprint, searchType, usageType].join(":");
}

export function isFavoriteMetricId(value: string): value is FavoriteMetricId {
  return ALL_FAVORITE_METRIC_IDS.includes(value as FavoriteMetricId);
}

export function getFavoriteMetricDefinition(metricId: FavoriteMetricId) {
  return FAVORITE_METRIC_DEFINITIONS.find((metric) => metric.id === metricId) || FAVORITE_METRIC_DEFINITIONS[0];
}

export function getFavoriteMetricValue(item: FavoriteComparisonItem, metricId: FavoriteMetricId) {
  return getFavoriteMetricDefinition(metricId).getValue(item);
}

export function formatFavoriteMetricValue(item: FavoriteComparisonItem, metricId: FavoriteMetricId) {
  const definition = getFavoriteMetricDefinition(metricId);
  return definition.formatValue(definition.getValue(item), item);
}

export function buildFavoriteMetricWinCounts(
  items: FavoriteComparisonItem[],
  selectedMetricIds: FavoriteMetricId[],
) {
  const winCounts = new Map<string, number>();

  for (const item of items) {
    winCounts.set(item.listingKey, 0);
  }

  for (const metricId of selectedMetricIds) {
    const definition = getFavoriteMetricDefinition(metricId);
    const metricValues = items
      .map((item) => {
        const value = definition.getValue(item);
        return typeof value === "number" && Number.isFinite(value)
          ? { listingKey: item.listingKey, value }
          : null;
      })
      .filter((entry): entry is { listingKey: string; value: number } => entry !== null);

    if (metricValues.length === 0) {
      continue;
    }

    const winningValue = definition.direction === "lower_better"
      ? Math.min(...metricValues.map((entry) => entry.value))
      : Math.max(...metricValues.map((entry) => entry.value));

    for (const entry of metricValues) {
      if (entry.value === winningValue) {
        winCounts.set(entry.listingKey, (winCounts.get(entry.listingKey) || 0) + 1);
      }
    }
  }

  return winCounts;
}

export function getFavoriteMetricTooltip(metricId: FavoriteMetricId) {
  const definition = getFavoriteMetricDefinition(metricId);
  const directionLabel = definition.direction === "lower_better" ? "Quanto menor, melhor." : "Quanto maior, melhor.";
  return `${definition.label}. ${definition.description} ${directionLabel}`;
}

function getSingleMetricSortValue(item: FavoriteComparisonItem, metricId: FavoriteMetricId) {
  const definition = getFavoriteMetricDefinition(metricId);
  const value = definition.getValue(item);
  if (value === null) {
    return definition.direction === "lower_better" ? Number.POSITIVE_INFINITY : Number.NEGATIVE_INFINITY;
  }
  return definition.direction === "lower_better" ? value : -value;
}

export function compareFavoriteItems(
  left: FavoriteComparisonItem,
  right: FavoriteComparisonItem,
  selectedMetricIds: FavoriteMetricId[],
) {
  if (selectedMetricIds.length === 0) {
    return right.savedAt.localeCompare(left.savedAt);
  }

  if (selectedMetricIds.length === 1) {
    const metricId = selectedMetricIds[0];
    const difference = getSingleMetricSortValue(left, metricId) - getSingleMetricSortValue(right, metricId);
    if (difference !== 0) {
      return difference;
    }
  } else {
    const leftScore = computeFavoriteCompositeScore(left, selectedMetricIds);
    const rightScore = computeFavoriteCompositeScore(right, selectedMetricIds);
    if (leftScore !== rightScore) {
      return leftScore - rightScore;
    }
  }

  return right.savedAt.localeCompare(left.savedAt);
}

export function computeFavoriteCompositeScore(
  item: FavoriteComparisonItem,
  selectedMetricIds: FavoriteMetricId[],
  comparisonPool?: FavoriteComparisonItem[],
) {
  const pool = comparisonPool || [item];
  if (selectedMetricIds.length === 0) {
    return 0;
  }

  let sum = 0;
  for (const metricId of selectedMetricIds) {
    const definition = getFavoriteMetricDefinition(metricId);
    const itemValue = definition.getValue(item);
    const values = pool
      .map((current) => definition.getValue(current))
      .filter((value): value is number => typeof value === "number" && Number.isFinite(value));

    if (itemValue === null || values.length === 0) {
      sum += 1;
      continue;
    }

    const min = Math.min(...values);
    const max = Math.max(...values);
    if (min === max) {
      continue;
    }

    const normalized = definition.direction === "lower_better"
      ? (itemValue - min) / (max - min)
      : (max - itemValue) / (max - min);
    sum += normalized;
  }

  return sum / selectedMetricIds.length;
}

export function buildFavoriteRanking(
  items: FavoriteComparisonItem[],
  selectedMetricIds: FavoriteMetricId[],
) {
  const metricWinCounts = buildFavoriteMetricWinCounts(items, selectedMetricIds);

  return [...items].sort((left, right) => {
    const leftWins = metricWinCounts.get(left.listingKey) || 0;
    const rightWins = metricWinCounts.get(right.listingKey) || 0;

    if (leftWins !== rightWins) {
      return rightWins - leftWins;
    }

    return compareFavoriteItems(left, right, selectedMetricIds);
  });
}