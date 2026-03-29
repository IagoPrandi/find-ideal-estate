import { create } from "zustand";

export type SearchType = "rent" | "sale";
export type TravelMode = "transit" | "walk" | "car";
export type PublicTransportMode = "bus" | "rail" | "mixed";
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

export type ListingsSpatialScope = "all" | "inside_zone";
export type ListingsUsageFilter = "all" | "residential" | "commercial";

export type ListingsPanelFilters = {
  minPrice: string;
  maxPrice: string;
  usageType: ListingsUsageFilter;
  spatialScope: ListingsSpatialScope;
  minSize: string;
  maxSize: string;
};

type JourneyState = {
  journeyId: string | null;
  config: JourneyConfig;
  listingsFilters: ListingsPanelFilters;
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
  modal: "transit",
  publicTransportMode: "mixed",
  time: 30,
  zoneRadiusMeters: 1200,
  transportSearchRadiusMeters: 1200,
  greenVegetationLevel: "medium",
  enrichments: {
    safety: true,
    green: false,
    flood: true,
    pois: true
  }
};

export const defaultListingsPanelFilters: ListingsPanelFilters = {
  minPrice: "",
  maxPrice: "",
  usageType: "all",
  spatialScope: "all",
  minSize: "",
  maxSize: ""
};

export const useJourneyStore = create<JourneyState>((set) => ({
  journeyId: null,
  config: defaultConfig,
  listingsFilters: defaultListingsPanelFilters,
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
        listingsFilters: defaultListingsPanelFilters,
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
  setConfig: (updater) => set((state) => ({ config: { ...state.config, ...updater } })),
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
        listingsFilters: defaultListingsPanelFilters,
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
  resetListingsFilters: () => set({ listingsFilters: defaultListingsPanelFilters }),
  setSelectedListingKey: (selectedListingKey) => set({ selectedListingKey }),
  setSelectedPoiKey: (selectedPoiKey) => set({ selectedPoiKey }),
  setActivePoiCategory: (activePoiCategory) => set({ activePoiCategory }),
  setJobIds: (payload) => set((state) => ({ ...state, ...payload })),
  resetJourney: () =>
    set({
      journeyId: null,
      config: defaultConfig,
      listingsFilters: defaultListingsPanelFilters,
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