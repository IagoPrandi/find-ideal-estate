import type { FavoriteZoneEntry } from "../api/client";
import { formatCurrencyBr } from "./listingFormat";

export type ZoneMetricId =
  | "zone_travel_time"
  | "zone_green_percentage"
  | "zone_flood_percentage"
  | "zone_crime_density"
  | "zone_homicide_density"
  | "zone_robbery_density"
  | "zone_avg_unit_price"
  | "zone_avg_price";

export type ZoneMetricDirection = "higher_better" | "lower_better";

type ZoneMetricDefinition = {
  id: ZoneMetricId;
  label: string;
  shortLabel: string;
  direction: ZoneMetricDirection;
  defaultSelected?: boolean;
  getValue: (entry: FavoriteZoneEntry) => number | null;
  formatValue: (value: number | null) => string;
};

function formatMinutes(value: number | null) {
  if (value === null || !Number.isFinite(value)) return "Sem base";
  return `${Math.round(value)} min`;
}

function formatPercentage(value: number | null) {
  if (value === null || !Number.isFinite(value)) return "Sem base";
  return `${value.toFixed(1)}%`;
}

function formatDensity(value: number | null) {
  if (value === null || !Number.isFinite(value)) return "Sem base";
  return `${value.toFixed(2)}/km²`;
}

function formatPrice(value: number | null) {
  if (value === null || !Number.isFinite(value)) return "Sem base";
  return formatCurrencyBr(value);
}

function formatUnitPrice(value: number | null) {
  if (value === null || !Number.isFinite(value)) return "Sem base";
  return `${formatCurrencyBr(value)}/m²`;
}

export const ZONE_METRIC_DEFINITIONS: ZoneMetricDefinition[] = [
  {
    id: "zone_travel_time",
    label: "Menor tempo de viagem",
    shortLabel: "Tempo",
    direction: "lower_better",
    defaultSelected: true,
    getValue: (entry) => entry.payload.metrics.travel_time_minutes ?? null,
    formatValue: formatMinutes,
  },
  {
    id: "zone_green_percentage",
    label: "Mais arborização",
    shortLabel: "Verde",
    direction: "higher_better",
    defaultSelected: true,
    getValue: (entry) => entry.payload.metrics.green_percentage ?? null,
    formatValue: formatPercentage,
  },
  {
    id: "zone_flood_percentage",
    label: "Menor risco de alagamento",
    shortLabel: "Alagamento",
    direction: "lower_better",
    getValue: (entry) => entry.payload.metrics.flood_percentage ?? null,
    formatValue: formatPercentage,
  },
  {
    id: "zone_crime_density",
    label: "Menos crimes",
    shortLabel: "Crimes/km²",
    direction: "lower_better",
    defaultSelected: true,
    getValue: (entry) => entry.payload.metrics.crime_density_per_km2 ?? null,
    formatValue: formatDensity,
  },
  {
    id: "zone_homicide_density",
    label: "Menos homicídios",
    shortLabel: "Homicídios/km²",
    direction: "lower_better",
    getValue: (entry) => entry.payload.metrics.homicide_density_per_km2 ?? null,
    formatValue: formatDensity,
  },
  {
    id: "zone_robbery_density",
    label: "Menos roubos",
    shortLabel: "Roubos/km²",
    direction: "lower_better",
    getValue: (entry) => entry.payload.metrics.robbery_density_per_km2 ?? null,
    formatValue: formatDensity,
  },
  {
    id: "zone_avg_unit_price",
    label: "Menor preço m²",
    shortLabel: "Preço m²",
    direction: "lower_better",
    defaultSelected: true,
    getValue: (entry) => entry.payload.metrics.zone_average_unit_price ?? null,
    formatValue: formatUnitPrice,
  },
  {
    id: "zone_avg_price",
    label: "Menor preço médio",
    shortLabel: "Preço médio",
    direction: "lower_better",
    getValue: (entry) => entry.payload.metrics.zone_average_price ?? null,
    formatValue: formatPrice,
  },
];

export const ALL_ZONE_METRIC_IDS = ZONE_METRIC_DEFINITIONS.map((m) => m.id);
export const DEFAULT_ZONE_METRIC_IDS = ZONE_METRIC_DEFINITIONS
  .filter((m) => m.defaultSelected)
  .map((m) => m.id);

export function isZoneMetricId(value: string): value is ZoneMetricId {
  return ALL_ZONE_METRIC_IDS.includes(value as ZoneMetricId);
}

export function getZoneMetricDefinition(metricId: ZoneMetricId) {
  return ZONE_METRIC_DEFINITIONS.find((m) => m.id === metricId) || ZONE_METRIC_DEFINITIONS[0];
}

export function formatZoneMetricValue(entry: FavoriteZoneEntry, metricId: ZoneMetricId) {
  const def = getZoneMetricDefinition(metricId);
  return def.formatValue(def.getValue(entry));
}

export function buildZoneMetricWinCounts(
  zones: FavoriteZoneEntry[],
  selectedMetricIds: ZoneMetricId[],
) {
  const winCounts = new Map<string, number>();
  for (const zone of zones) {
    winCounts.set(zone.zoneKey, 0);
  }

  for (const metricId of selectedMetricIds) {
    const def = getZoneMetricDefinition(metricId);
    const values = zones
      .map((z) => {
        const v = def.getValue(z);
        return typeof v === "number" && Number.isFinite(v) ? { zoneKey: z.zoneKey, value: v } : null;
      })
      .filter((e): e is { zoneKey: string; value: number } => e !== null);

    if (values.length === 0) continue;

    const best = def.direction === "lower_better"
      ? Math.min(...values.map((e) => e.value))
      : Math.max(...values.map((e) => e.value));

    for (const entry of values) {
      if (entry.value === best) {
        winCounts.set(entry.zoneKey, (winCounts.get(entry.zoneKey) || 0) + 1);
      }
    }
  }

  return winCounts;
}

function computeZoneCompositeScore(
  entry: FavoriteZoneEntry,
  selectedMetricIds: ZoneMetricId[],
  pool: FavoriteZoneEntry[],
) {
  if (selectedMetricIds.length === 0) return 0;
  let sum = 0;
  for (const metricId of selectedMetricIds) {
    const def = getZoneMetricDefinition(metricId);
    const itemValue = def.getValue(entry);
    const values = pool
      .map((z) => def.getValue(z))
      .filter((v): v is number => typeof v === "number" && Number.isFinite(v));
    if (itemValue === null || values.length === 0) {
      sum += 1;
      continue;
    }
    const min = Math.min(...values);
    const max = Math.max(...values);
    if (min === max) continue;
    const normalized = def.direction === "lower_better"
      ? (itemValue - min) / (max - min)
      : (max - itemValue) / (max - min);
    sum += normalized;
  }
  return sum / selectedMetricIds.length;
}

export function buildZoneRanking(
  zones: FavoriteZoneEntry[],
  selectedMetricIds: ZoneMetricId[],
): FavoriteZoneEntry[] {
  const winCounts = buildZoneMetricWinCounts(zones, selectedMetricIds);
  return [...zones].sort((a, b) => {
    const aWins = winCounts.get(a.zoneKey) || 0;
    const bWins = winCounts.get(b.zoneKey) || 0;
    if (aWins !== bWins) return bWins - aWins;
    if (selectedMetricIds.length > 0) {
      const aScore = computeZoneCompositeScore(a, selectedMetricIds, zones);
      const bScore = computeZoneCompositeScore(b, selectedMetricIds, zones);
      if (aScore !== bScore) return aScore - bScore;
    }
    return b.savedAt.localeCompare(a.savedAt);
  });
}
