import type { ListingSortMode } from "./types";

type SortableAnalytics = {
  priceValue: number | null;
  sizeM2: number | null;
};

/** Ordena linhas decoradas (preço/tamanho) sem mutar o array de entrada. */
export function sortDecoratedListings<T extends { analytics: SortableAnalytics }>(
  rows: T[],
  mode: ListingSortMode
): T[] {
  const decorated = [...rows];
  const withFallback = (value: number | null, fallback: number) => (value === null ? fallback : value);
  decorated.sort((a, b) => {
    if (mode === "price-asc") {
      return (
        withFallback(a.analytics.priceValue, Number.POSITIVE_INFINITY) -
        withFallback(b.analytics.priceValue, Number.POSITIVE_INFINITY)
      );
    }
    if (mode === "price-desc") {
      return (
        withFallback(b.analytics.priceValue, Number.NEGATIVE_INFINITY) -
        withFallback(a.analytics.priceValue, Number.NEGATIVE_INFINITY)
      );
    }
    if (mode === "size-asc") {
      return (
        withFallback(a.analytics.sizeM2, Number.POSITIVE_INFINITY) - withFallback(b.analytics.sizeM2, Number.POSITIVE_INFINITY)
      );
    }
    return (
      withFallback(b.analytics.sizeM2, Number.NEGATIVE_INFINITY) - withFallback(a.analytics.sizeM2, Number.NEGATIVE_INFINITY)
    );
  });
  return decorated;
}
