export type ReferencePoint = {
  name: string;
  lat: number;
  lon: number;
};

export type InterestPoint = {
  id: string;
  label: string;
  category: string;
  lat: number;
  lon: number;
};

export type PropertyMode = "rent" | "buy";

export type ListingSortMode = "price-asc" | "price-desc" | "size-desc" | "size-asc";

export type SearchSuggestionType = "neighborhood" | "street" | "reference";

export type SearchSuggestion = {
  label: string;
  normalized: string;
  type: SearchSuggestionType;
};

export type Step3ComparisonExtremes = {
  price: { min: number | null; max: number | null };
  size: { min: number | null; max: number | null };
  transport: { min: number | null; max: number | null };
  poiCount: { min: number | null; max: number | null };
};

export type Step3MonthlyVariation = {
  pct: number | null;
  trend: "up" | "down" | "flat" | "n/d";
};
