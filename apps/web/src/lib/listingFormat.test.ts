import { describe, expect, it } from "vitest";

import { getListingDisplayPrice, getListingSelectionKey, parseFiniteNumber, resolvePlatformImageUrl } from "./listingFormat";

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
});