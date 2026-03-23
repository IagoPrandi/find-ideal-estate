import type { PriceRollupRead, ZoneDetailResponse } from "../../api/schemas";
import type { Step3MonthlyVariation } from "./types";

export function computeMonthlyVariationFromRollups(priceRollups: PriceRollupRead[]): Step3MonthlyVariation {
  const monthlyMap = new Map<string, { total: number; count: number }>();
  for (const row of priceRollups) {
    const monthKey = String(row.date || "").slice(0, 7);
    const median = Number(row.median_price || 0);
    if (!monthKey || monthKey.length !== 7 || !Number.isFinite(median) || median <= 0) {
      continue;
    }
    const current = monthlyMap.get(monthKey) || { total: 0, count: 0 };
    current.total += median;
    current.count += 1;
    monthlyMap.set(monthKey, current);
  }

  const months = Array.from(monthlyMap.keys()).sort((a, b) => b.localeCompare(a));
  if (months.length < 2) {
    return { pct: null as number | null, trend: "n/d" as const };
  }

  const currentMonth = monthlyMap.get(months[0]);
  const previousMonth = monthlyMap.get(months[1]);
  if (!currentMonth || !previousMonth || currentMonth.count === 0 || previousMonth.count === 0) {
    return { pct: null as number | null, trend: "n/d" as const };
  }

  const currentMedian = currentMonth.total / currentMonth.count;
  const previousMedian = previousMonth.total / previousMonth.count;
  if (!Number.isFinite(previousMedian) || previousMedian <= 0) {
    return { pct: null as number | null, trend: "n/d" as const };
  }

  const pct = ((currentMedian - previousMedian) / previousMedian) * 100;
  const trend: Step3MonthlyVariation["trend"] =
    Math.abs(pct) < 0.01 ? "flat" : pct > 0 ? "up" : "down";
  return { pct, trend };
}

export function computeTopPoiCategories(zoneDetailData: ZoneDetailResponse | null): Array<[string, number]> {
  return Object.entries(zoneDetailData?.poi_count_by_category || {})
    .filter(([, count]) => Number.isFinite(count))
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6);
}
