import type { ListingsCollection, PriceRollupRead, ZoneDetailResponse } from "../../api/schemas";
import type { ZoneInfoKey } from "../../domain/wizardConstants";
import type {
  ListingSortMode,
  SearchSuggestion,
  SearchSuggestionType,
  Step3ComparisonExtremes,
  Step3MonthlyVariation
} from "./types";

export type ListingFeature = ListingsCollection["features"][number];

export type Step3SortedListingRow = {
  feature: ListingFeature;
  index: number;
  info: { priceLabel: string; address: string; url: string };
  analytics: {
    listingKey: string;
    priceValue: number | null;
    sizeM2: number | null;
    bedrooms: number | null;
    distanceTransportM: number | null;
    platform: string;
    poiCountWithinRadius: number;
    nearestPoiByCategory: Array<{ category: string; distanceM: number | null }>;
  };
};

/** Sub-etapas 4–6 alinhadas ao PRD (comparação → endereço → análise). */
export type Step3WizardSubStep = 4 | 5 | 6;

export type Step3ZonePanelProps = {
  visible: boolean;
  /** Qual painel mostrar quando `visible` (etapas 4–6). */
  wizardSubStep: Step3WizardSubStep;
  zoneDetailData: ZoneDetailResponse | null;
  zoneInfoSelection: Record<ZoneInfoKey, boolean>;
  selectedZoneUid: string;
  isDetailingZone: boolean;
  zoneListingMessage: string;
  onDetailZone: () => void;
  activePanelTab: "listings" | "dashboard";
  onActivePanelTabChange: (tab: "listings" | "dashboard") => void;
  streetQuery: string;
  onStreetQueryChange: (value: string) => void;
  streetSuggestions: SearchSuggestion[];
  selectedStreet: string;
  selectedStreetType: SearchSuggestionType | null;
  suggestionTypeLabel: Record<SearchSuggestionType, string>;
  onStreetSuggestionSelect: (item: SearchSuggestion) => void;
  onZoneListings: () => void;
  isListingZone: boolean;
  finalizeMessage: string;
  runId: string;
  apiBase: string;
  freshnessBadgeText: string;
  listingDiffMessage: string;
  listingSortMode: ListingSortMode;
  onListingSortModeChange: (mode: ListingSortMode) => void;
  poiCountRadiusM: number;
  onPoiCountRadiusChange: (m: number) => void;
  selectedListingsForComparison: Step3SortedListingRow[];
  comparisonExtremes: Step3ComparisonExtremes;
  sortedListings: Step3SortedListingRow[];
  onListingCardClick: (feature: ListingFeature, index: number) => void;
  selectedListingKeys: string[];
  newlyAddedListingKeys: string[];
  listingsWithoutCoords: Array<Record<string, unknown>>;
  parseFiniteNumber: (value: unknown) => number | null;
  formatCurrencyBr: (value: unknown) => string;
  finalListings: ListingFeature[];
  priceRollups: PriceRollupRead[];
  monthlyVariation: Step3MonthlyVariation;
  seedTravelTimeMin: number | null;
  topPoiCategories: Array<[string, number]>;
};
