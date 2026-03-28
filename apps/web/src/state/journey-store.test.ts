import { describe, expect, it } from "vitest";
import { useJourneyStore } from "./journey-store";

describe("journey-store", () => {
  it("clears transport and zone runtime state when switching to a new journey", () => {
    useJourneyStore.setState({
      journeyId: "journey-old",
      listingsFilters: {
        minPrice: "1000",
        maxPrice: "5000",
        usageType: "residential",
        spatialScope: "inside_zone",
        minSize: "40",
        maxSize: "120"
      },
      selectedListingKey: "property:prop-old",
      selectedTransportId: "transport-old",
      selectedZoneId: "zone-old",
      selectedZoneFingerprint: "fp-old",
      selectedAddress: {
        label: "Endereco antigo",
        normalized: "endereco antigo",
        locationType: "street",
        lat: -23.55,
        lon: -46.63
      },
      addressQuery: "Rua antiga",
      transportJobId: "job-transport-old",
      zoneGenerationJobId: "job-zone-old",
      zoneEnrichmentJobId: "job-enrich-old"
    });

    useJourneyStore.getState().setJourneyId("journey-new");

    const state = useJourneyStore.getState();
    expect(state.journeyId).toBe("journey-new");
    expect(state.listingsFilters).toEqual({
      minPrice: "",
      maxPrice: "",
      usageType: "all",
      spatialScope: "all",
      minSize: "",
      maxSize: ""
    });
    expect(state.selectedListingKey).toBeNull();
    expect(state.selectedTransportId).toBeNull();
    expect(state.selectedZoneId).toBeNull();
    expect(state.selectedZoneFingerprint).toBeNull();
    expect(state.selectedAddress).toBeNull();
    expect(state.addressQuery).toBe("");
    expect(state.transportJobId).toBeNull();
    expect(state.zoneGenerationJobId).toBeNull();
    expect(state.zoneEnrichmentJobId).toBeNull();

    state.resetJourney();
  });

  it("clears the selected street when switching to a different zone", () => {
    useJourneyStore.setState({
      listingsFilters: {
        minPrice: "1500",
        maxPrice: "4000",
        usageType: "commercial",
        spatialScope: "inside_zone",
        minSize: "30",
        maxSize: "90"
      },
      selectedListingKey: "property:prop-old",
      selectedZoneId: "zone-old",
      selectedZoneFingerprint: "fp-old",
      selectedAddress: {
        label: "Rua antiga, Vila Leopoldina, Sao Paulo-SP",
        normalized: "rua antiga, vila leopoldina, sao paulo-sp",
        locationType: "street",
        lat: -23.55,
        lon: -46.63
      },
      addressQuery: "Rua antiga"
    });

    useJourneyStore.getState().setSelectedZone("zone-new", "fp-new");

    const state = useJourneyStore.getState();
    expect(state.selectedZoneId).toBe("zone-new");
    expect(state.selectedZoneFingerprint).toBe("fp-new");
    expect(state.listingsFilters).toEqual({
      minPrice: "",
      maxPrice: "",
      usageType: "all",
      spatialScope: "all",
      minSize: "",
      maxSize: ""
    });
    expect(state.selectedListingKey).toBeNull();
    expect(state.selectedAddress).toBeNull();
    expect(state.addressQuery).toBe("");

    state.resetJourney();
  });
});