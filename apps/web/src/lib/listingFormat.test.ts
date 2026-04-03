import { describe, expect, it } from "vitest";

import { applyListingsPanelFilters, getListingDisplayPrice, getListingSelectionKey, parseFiniteNumber, resolvePlatformImageUrl } from "./listingFormat";

describe("parseFiniteNumber", () => {
  it("preserves backend decimal strings with dot separator", () => {
    expect(parseFiniteNumber("1000.00")).toBe(1000);
    expect(parseFiniteNumber("826.00")).toBe(826);
  });

  it("parses brazilian formatted currency strings", () => {
    expect(parseFiniteNumber("1.000,00")).toBe(1000);
    expect(parseFiniteNumber("R$ 1.991,00")).toBe(1991);
  });

  it("parses thousand-separated integer strings without decimals", () => {
    expect(parseFiniteNumber("100.000")).toBe(100000);
    expect(parseFiniteNumber("100,000")).toBe(100000);
  });

  it("sums listing price, condo fee, and iptu for display", () => {
    expect(
      getListingDisplayPrice({
        current_best_price: "1000.00",
        condo_fee: "826.00",
        iptu: "165.00"
      })
    ).toBe(1991);
  });

  it("resolves relative and protocol-relative image URLs", () => {
    expect(resolvePlatformImageUrl("/listing-image.webp", "vivareal")).toBe("https://www.vivareal.com.br/listing-image.webp");
    expect(resolvePlatformImageUrl("//images.example.com/photo.jpg", "zapimoveis")).toBe("https://images.example.com/photo.jpg");
  });

  it("builds a stable selection key for cards and map points", () => {
    expect(getListingSelectionKey({ property_id: "prop-1", platform: "quintoandar", platform_listing_id: "qa-1" })).toBe("property:prop-1");
    expect(getListingSelectionKey({ property_id: null, platform: "zapimoveis", platform_listing_id: "zap-1" })).toBe("platform:zapimoveis:zap-1");
  });

  it("orders filtered listings from lowest display price to highest by default", () => {
    const ordered = applyListingsPanelFilters(
      [
        {
          property_id: "prop-1",
          platform: "quintoandar",
          platform_listing_id: "qa-1",
          current_best_price: "3500",
          condo_fee: "500",
          iptu: "100",
          inside_zone: true,
          usage_type: "residential"
        },
        {
          property_id: "prop-2",
          platform: "vivareal",
          platform_listing_id: "vr-1",
          current_best_price: "4200",
          condo_fee: "300",
          iptu: "50",
          inside_zone: true,
          usage_type: "residential"
        },
        {
          property_id: "prop-3",
          platform: "zapimoveis",
          platform_listing_id: "zap-1",
          current_best_price: "3900",
          condo_fee: "250",
          iptu: "25",
          inside_zone: true,
          usage_type: "residential"
        }
      ] as never,
      {
        minPrice: "",
        maxPrice: "",
        usageType: "all",
        spatialScope: "all",
        minSize: "",
        maxSize: "",
        sortField: "price",
        sortDirection: "asc"
      }
    );

    expect(ordered.map((listing) => listing.property_id)).toEqual(["prop-1", "prop-3", "prop-2"]);
  });

  it("orders filtered listings from highest display price to lowest when toggled", () => {
    const ordered = applyListingsPanelFilters(
      [
        {
          property_id: "prop-1",
          platform: "quintoandar",
          platform_listing_id: "qa-1",
          current_best_price: "3500",
          condo_fee: "500",
          iptu: "100",
          inside_zone: true,
          usage_type: "residential"
        },
        {
          property_id: "prop-2",
          platform: "vivareal",
          platform_listing_id: "vr-1",
          current_best_price: "4200",
          condo_fee: "300",
          iptu: "50",
          inside_zone: true,
          usage_type: "residential"
        },
        {
          property_id: "prop-3",
          platform: "zapimoveis",
          platform_listing_id: "zap-1",
          current_best_price: "3900",
          condo_fee: "250",
          iptu: "25",
          inside_zone: true,
          usage_type: "residential"
        }
      ] as never,
      {
        minPrice: "",
        maxPrice: "",
        usageType: "all",
        spatialScope: "all",
        minSize: "",
        maxSize: "",
        sortField: "price",
        sortDirection: "desc"
      }
    );

    expect(ordered.map((listing) => listing.property_id)).toEqual(["prop-2", "prop-3", "prop-1"]);
  });

  it("orders filtered listings by size when requested", () => {
    const ordered = applyListingsPanelFilters(
      [
        {
          property_id: "prop-1",
          platform: "quintoandar",
          platform_listing_id: "qa-1",
          current_best_price: "3500",
          condo_fee: "500",
          iptu: "100",
          area_m2: 70,
          inside_zone: true,
          usage_type: "residential"
        },
        {
          property_id: "prop-2",
          platform: "vivareal",
          platform_listing_id: "vr-1",
          current_best_price: "4200",
          condo_fee: "300",
          iptu: "50",
          area_m2: 90,
          inside_zone: true,
          usage_type: "residential"
        },
        {
          property_id: "prop-3",
          platform: "zapimoveis",
          platform_listing_id: "zap-1",
          current_best_price: "3900",
          condo_fee: "250",
          iptu: "25",
          area_m2: 50,
          inside_zone: true,
          usage_type: "residential"
        }
      ] as never,
      {
        minPrice: "",
        maxPrice: "",
        usageType: "all",
        spatialScope: "all",
        minSize: "",
        maxSize: "",
        sortField: "size",
        sortDirection: "asc"
      }
    );

    expect(ordered.map((listing) => listing.property_id)).toEqual(["prop-3", "prop-1", "prop-2"]);
  });
});