import type { Step3ComparisonExtremes } from "./types";

type ComparisonRow = {
  analytics: {
    priceValue: number | null;
    sizeM2: number | null;
    distanceTransportM: number | null;
    poiCountWithinRadius: number;
  };
};

export function computeComparisonExtremes(rows: ComparisonRow[]): Step3ComparisonExtremes {
  const numeric = {
    price: rows.map((item) => item.analytics.priceValue).filter((value): value is number => value !== null),
    size: rows.map((item) => item.analytics.sizeM2).filter((value): value is number => value !== null),
    transport: rows.map((item) => item.analytics.distanceTransportM).filter((value): value is number => value !== null),
    poiCount: rows.map((item) => item.analytics.poiCountWithinRadius).filter((value) => Number.isFinite(value))
  };

  const resolveMinMax = (values: number[]) => {
    if (values.length === 0) {
      return { min: null as number | null, max: null as number | null };
    }
    return {
      min: Math.min(...values),
      max: Math.max(...values)
    };
  };

  return {
    price: resolveMinMax(numeric.price),
    size: resolveMinMax(numeric.size),
    transport: resolveMinMax(numeric.transport),
    poiCount: resolveMinMax(numeric.poiCount)
  };
}

export function getComparisonCellClass(
  value: number | null,
  min: number | null,
  max: number | null,
  strategy: "lower-better" | "higher-better"
): string {
  if (value === null || min === null || max === null) {
    return "text-slate-800";
  }
  const isClose = (a: number, b: number) => Math.abs(a - b) < 0.0001;
  const isBest = strategy === "lower-better" ? isClose(value, min) : isClose(value, max);
  const isWorst = strategy === "lower-better" ? isClose(value, max) : isClose(value, min);
  if (isBest && isWorst) {
    return "font-semibold text-slate-800";
  }
  if (isBest) {
    return "font-semibold text-success";
  }
  if (isWorst) {
    return "font-semibold text-danger";
  }
  return "text-slate-800";
}

export function resolveRawListingText(
  item: Record<string, unknown>,
  formatCurrencyBr: (value: unknown) => string
) {
  const price = item.price || item.rent_price || item.sale_price || item.total_price;
  const address =
    (item.address as string | undefined) ||
    (item.street as string | undefined) ||
    (item.title as string | undefined) ||
    "Endereço não informado";
  const url =
    (item.url as string | undefined) ||
    (item.listing_url as string | undefined) ||
    (item.link as string | undefined) ||
    "";
  return {
    priceLabel: formatCurrencyBr(price),
    address,
    url
  };
}
