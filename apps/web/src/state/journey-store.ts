import { create } from "zustand";

export type SearchType = "rent" | "sale";
export type TravelMode = "transit" | "walk" | "car";
export type PublicTransportMode = "bus" | "rail" | "mixed";
export type ListingsSpatialScope = "all" | "inside_zone";
export type ListingsAddressScope = "all_addresses" | "selected_address";
export type ListingsUsageFilter = "all" | "residential" | "commercial";
export type ListingsSortField = "price" | "size";
export type ListingsSortDirection = "asc" | "desc";
export const GREEN_VEGETATION_LEVELS = ["low", "medium", "high"] as const;
export type GreenVegetationLevel = (typeof GREEN_VEGETATION_LEVELS)[number];

export const GREEN_VEGETATION_LABELS: Record<GreenVegetationLevel, string> = {
  low: "Pouca vegetação",
  medium: "Média vegetação",
  high: "Muita vegetação"
};

export const INCLUDED_GREEN_VEGETATION_LEVELS: Record<GreenVegetationLevel, GreenVegetationLevel[]> = {
  low: ["low"],
  medium: ["low", "medium"],
  high: ["low", "medium", "high"]
};

export function getIncludedGreenVegetationLevels(level: GreenVegetationLevel): GreenVegetationLevel[] {
  return INCLUDED_GREEN_VEGETATION_LEVELS[level];
}

export type JourneyConfig = {
  type: SearchType;
  propertyUsageType: ListingsUsageFilter;
  modal: TravelMode;
  publicTransportMode: PublicTransportMode;
  time: number;
  zoneRadiusMeters: number;
  transportSearchRadiusMeters: number;
  greenVegetationLevel: GreenVegetationLevel;
  enrichments: {
    safety: boolean;
    green: boolean;
    flood: boolean;
    pois: boolean;
  };
};

export type PickedCoord = {
  lat: number;
  lon: number;
  label?: string;
};

export type SelectedAddress = {
  label: string;
  normalized: string;
  locationType: string;
  lat: number;
  lon: number;
};

export type ListingsPanelFilters = {
  minPrice: string;
  maxPrice: string;
  usageType: ListingsUsageFilter;
  spatialScope: ListingsSpatialScope;
  minSize: string;
  maxSize: string;
  sortField: ListingsSortField;
  sortDirection: ListingsSortDirection;
};

type JourneyState = {
  journeyId: string | null;
  config: JourneyConfig;
  listingsFilters: ListingsPanelFilters;
  listingsAddressScope: ListingsAddressScope;
  selectedListingKey: string | null;
  selectedPoiKey: string | null;
  activePoiCategory: string;
  pickedCoord: PickedCoord | null;
  primaryReferenceLabel: string;
  selectedTransportId: string | null;
  selectedZoneId: string | null;
  selectedZoneFingerprint: string | null;
  selectedAddress: SelectedAddress | null;
  addressQuery: string;
  transportJobId: string | null;
  zoneGenerationJobId: string | null;
  zoneEnrichmentJobId: string | null;
  listingsJobId: string | null;
  setJourneyId: (journeyId: string | null) => void;
  setConfig: (updater: Partial<JourneyConfig>) => void;
  setEnrichment: (key: keyof JourneyConfig["enrichments"], value: boolean) => void;
  setPickedCoord: (coord: PickedCoord | null) => void;
  setPrimaryReferenceLabel: (label: string) => void;
  setSelectedTransportId: (transportId: string | null) => void;
  setSelectedZone: (zoneId: string | null, zoneFingerprint: string | null) => void;
  setSelectedAddress: (address: SelectedAddress | null) => void;
  setAddressQuery: (query: string) => void;
  setListingsFilters: (updater: Partial<ListingsPanelFilters>) => void;
  setListingsAddressScope: (scope: ListingsAddressScope) => void;
  resetListingsFilters: () => void;
  setSelectedListingKey: (selectedListingKey: string | null) => void;
  setSelectedPoiKey: (selectedPoiKey: string | null) => void;
  setActivePoiCategory: (activePoiCategory: string) => void;
  setJobIds: (payload: {
    transportJobId?: string | null;
    zoneGenerationJobId?: string | null;
    zoneEnrichmentJobId?: string | null;
    listingsJobId?: string | null;
  }) => void;
  resetJourney: () => void;
};

const defaultConfig: JourneyConfig = {
  type: "rent",
  propertyUsageType: "residential",
  modal: "transit",
  publicTransportMode: "bus",
  time: 15,
  zoneRadiusMeters: 100,
  transportSearchRadiusMeters: 200,
  greenVegetationLevel: "medium",
  enrichments: {
    safety: false,
    green: false,
    flood: true,
    pois: true
  }
};

export function buildDefaultListingsPanelFilters(
  config: Pick<JourneyConfig, "propertyUsageType"> = defaultConfig
): ListingsPanelFilters {
  return {
    minPrice: "",
    maxPrice: "",
    usageType: config.propertyUsageType,
    spatialScope: "inside_zone",
    minSize: "",
    maxSize: "",
    sortField: "price",
    sortDirection: "asc"
  };
}

export const defaultListingsPanelFilters: ListingsPanelFilters = buildDefaultListingsPanelFilters();

export const useJourneyStore = create<JourneyState>((set) => ({
  journeyId: null,
  config: defaultConfig,
  listingsFilters: defaultListingsPanelFilters,
  listingsAddressScope: "all_addresses",
  selectedListingKey: null,
  selectedPoiKey: null,
  activePoiCategory: "all",
  pickedCoord: null,
  primaryReferenceLabel: "",
  selectedTransportId: null,
  selectedZoneId: null,
  selectedZoneFingerprint: null,
  selectedAddress: null,
  addressQuery: "",
  transportJobId: null,
  zoneGenerationJobId: null,
  zoneEnrichmentJobId: null,
  listingsJobId: null,
  setJourneyId: (journeyId) =>
    set((state) => {
      if (state.journeyId === journeyId) {
        return { journeyId };
      }

      return {
        journeyId,
        listingsFilters: buildDefaultListingsPanelFilters(state.config),
        listingsAddressScope: "all_addresses",
        selectedListingKey: null,
        selectedPoiKey: null,
        activePoiCategory: "all",
        selectedTransportId: null,
        selectedZoneId: null,
        selectedZoneFingerprint: null,
        selectedAddress: null,
        addressQuery: "",
        transportJobId: null,
        zoneGenerationJobId: null,
        zoneEnrichmentJobId: null,
        listingsJobId: null
      };
    }),
  setConfig: (updater) =>
    set((state) => {
      const nextConfig = { ...state.config, ...updater };
      const nextState: Partial<JourneyState> = { config: nextConfig };

      if (updater.propertyUsageType && updater.propertyUsageType !== state.config.propertyUsageType) {
        nextState.listingsFilters = {
          ...state.listingsFilters,
          usageType: updater.propertyUsageType,
        };
      }

      return nextState;
    }),
  setEnrichment: (key, value) =>
    set((state) => ({
      config: {
        ...state.config,
        enrichments: {
          ...state.config.enrichments,
          [key]: value
        }
      }
    })),
  setPickedCoord: (pickedCoord) => set({ pickedCoord }),
  setPrimaryReferenceLabel: (primaryReferenceLabel) => set({ primaryReferenceLabel }),
  setSelectedTransportId: (selectedTransportId) => set({ selectedTransportId }),
  setSelectedZone: (selectedZoneId, selectedZoneFingerprint) =>
    set((state) => {
      if (
        state.selectedZoneId === selectedZoneId &&
        state.selectedZoneFingerprint === selectedZoneFingerprint
      ) {
        return { selectedZoneId, selectedZoneFingerprint };
      }

      return {
        selectedZoneId,
        selectedZoneFingerprint,
        listingsFilters: buildDefaultListingsPanelFilters(state.config),
        listingsAddressScope: "all_addresses",
        selectedListingKey: null,
        selectedPoiKey: null,
        activePoiCategory: "all",
        selectedAddress: null,
        addressQuery: "",
        listingsJobId: null
      };
    }),
  setSelectedAddress: (selectedAddress) => set({ selectedAddress }),
  setAddressQuery: (addressQuery) => set({ addressQuery }),
  setListingsFilters: (updater) =>
    set((state) => ({
      listingsFilters: {
        ...state.listingsFilters,
        ...updater
      }
    })),
  setListingsAddressScope: (listingsAddressScope) => set({ listingsAddressScope }),
  resetListingsFilters: () => set((state) => ({ listingsFilters: buildDefaultListingsPanelFilters(state.config) })),
  setSelectedListingKey: (selectedListingKey) => set({ selectedListingKey }),
  setSelectedPoiKey: (selectedPoiKey) => set({ selectedPoiKey }),
  setActivePoiCategory: (activePoiCategory) => set({ activePoiCategory }),
  setJobIds: (payload) => set((state) => ({ ...state, ...payload })),
  resetJourney: () =>
    set({
      journeyId: null,
      config: defaultConfig,
      listingsFilters: buildDefaultListingsPanelFilters(defaultConfig),
      listingsAddressScope: "all_addresses",
      selectedListingKey: null,
      selectedPoiKey: null,
      activePoiCategory: "all",
      pickedCoord: null,
      primaryReferenceLabel: "",
      selectedTransportId: null,
      selectedZoneId: null,
      selectedZoneFingerprint: null,
      selectedAddress: null,
      addressQuery: "",
      transportJobId: null,
      zoneGenerationJobId: null,
      zoneEnrichmentJobId: null,
      listingsJobId: null
    })
}));