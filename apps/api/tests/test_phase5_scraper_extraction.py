"""M5.3 structural tests for Playwright scraper DOM-fallback and payload extraction.

These tests exercise the extraction logic (DOM parsing + API payload parsing)
with synthetic fixtures, substituting for live network tests that require internet
access (verified externally via `scripts/verify_m5_3_scrapers_live.py`).

Acceptance criterion: each scraper must be able to produce ≥ 5 listings from
either an API payload or DOM fallback rows.
"""
from __future__ import annotations

import os
import sys

# Ensure the API source tree is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from modules.listings.classification import infer_listing_usage_type_from_url  # noqa: E402
from modules.listings.scrapers.loft import (  # noqa: E402
    _build_loft_scrape_url,
    _extract_from_loft_next_data,
    _parse_loft_listing,
)
from modules.listings.scrapers.quintoandar import (  # noqa: E402
    _extract_from_quintoandar_dom_rows,
    _extract_from_quintoandar_payload,
    _extract_quintoandar_coordinate_map,
    _parse_quintoandar_house,
    _to_quintoandar_location_slug,
)
from modules.listings.scrapers.vivareal import (  # noqa: E402
    _extract_from_dom_rows,
    _extract_from_glue_payload,
    _extract_listing_card_image_url,
)
from modules.listings.scrapers.zapimoveis import (  # noqa: E402
    _extract_from_glue_payload as zap_extract_glue,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_glue_payload(n: int, platform: str = "vivareal") -> dict:
    """Minimal Glue API payload with `n` listings."""
    domain = "vivareal.com.br" if platform == "vivareal" else "zapimoveis.com.br"
    listings = []
    for i in range(1, n + 1):
        listings.append({
            "listing": {
                "id": f"1000{i:04d}",
                "listingId": f"1000{i:04d}",
                "address": {
                    "point": {"lat": -23.56 + i * 0.001, "lon": -46.65 + i * 0.001},
                    "street": f"Rua Teste {i}",
                    "neighborhood": "Pinheiros",
                    "city": "São Paulo",
                    "stateAcronym": "SP",
                },
                "pricingInfos": [
                    {
                        "businessType": "RENTAL",
                        "rentalTotalPrice": f"{2000 + i * 100!s}",
                        "monthlyCondoFee": "300",
                        "yearlyIptu": "1200",
                    }
                ],
                "usableAreas": [f"{45 + i}"],
                "bedrooms": [f"{(i % 3) + 1}"],
                "bathrooms": ["1"],
                "parkingSpaces": ["1"],
            },
            "link": {"href": f"https://www.{domain}/imovel/1000{i:04d}/"},
        })
    return {"search": {"result": {"listings": listings}}}


def _make_dom_rows(n: int, platform: str = "vivareal") -> list[dict]:
    """Synthetic DOM anchor rows matching the JS evaluate output shape."""
    rows = []
    for i in range(1, n + 1):
        rows.append({
            "href": f"/imovel/{2000 + i}/nome-do-imovel-{i}/",
            "image_url": f"/{platform}/thumb-{i}.webp",
            "text": (
                f"Apartamento {i} quarto  "
                f"R$ {2000 + i * 100:,}  "
                f"{50 + i} m²  "
                f"1 banheiro"
            ),
        })
    return rows


def _make_quintoandar_dom_rows(n: int) -> list[dict]:
    rows = []
    for i in range(1, n + 1):
        rows.append({
            "href": f"/imovel/{3000 + i}",
            "image_url": f"/thumbs/qa-{i}.webp",
            "text": (
                f"Apartamento {i} quarto  "
                f"R$ {2500 + i * 100:,}  "
                f"{60 + i} m²"
            ),
        })
    return rows


def _make_quintoandar_api_payload(n: int) -> dict:
    """Minimal QuintoAndar client-api payload."""
    houses = {
        str(4000 + i): {
            "id": str(4000 + i),
            "lat": -23.56 + i * 0.001,
            "lon": -46.65 + i * 0.001,
            "rentPrice": 2000 + i * 100,
            "area": 55 + i,
            "bedrooms": (i % 3) + 1,
            "bathrooms": 1,
            "slug": f"/imovel/{4000 + i}",
            "address": "Rua Teste",
            "neighbourhood": "Pinheiros",
            "city": "São Paulo",
        }
        for i in range(1, n + 1)
    }
    return {"data": {"search": {"result": {"hits": {"hits": [
        {"_source": {**h, "type": "RESIDENTIAL"}}
        for h in houses.values()
    ]}}}}}


def _make_loft_next_payload(n: int, search_type: str = "rent") -> dict:
    listings = []
    for i in range(1, n + 1):
        listing = {
            "id": f"loft{i:04d}",
            "price": 650000 + i * 1000 if search_type == "sale" else None,
            "rentalPrice": 3000 + i * 100,
            "complexFee": 450,
            "propertyTax": 90,
            "area": 55 + i,
            "bedrooms": 2,
            "restrooms": 1,
            "parkingSpots": 1,
            "image": "banner.jpg",
            "address": {
                "streetFullName": "Rua Guaipá",
                "neighborhood": "Vila Leopoldina",
                "city": "São Paulo",
                "state": "SP",
                "lat": "-23.5212571",
                "lng": "-46.7304601",
            },
        }
        listings.append({"listing": listing, "listingsCount": 1, "groupedListings": []})
    return {
        "props": {
            "pageProps": {
                "dehydratedState": {
                    "queries": [
                        {
                            "state": {
                                "data": {
                                    "listings": listings,
                                    "pagination": {
                                        "page": 0,
                                        "hitsPerPage": 38,
                                        "totalPages": 1,
                                    },
                                }
                            }
                        }
                    ]
                }
            }
        }
    }


# ---------------------------------------------------------------------------
# Loft
# ---------------------------------------------------------------------------

class TestLoftExtraction:
    def test_builds_address_search_urls_for_sale_and_rent(self) -> None:
        sale_url = _build_loft_scrape_url("Rua Guaipá", "sale")
        rent_url = _build_loft_scrape_url("Rua Guaipá", "rent")

        assert sale_url.startswith("https://loft.com.br/venda/imoveis/sp/sao-paulo?")
        assert rent_url.startswith("https://loft.com.br/aluguel/imoveis/sp/sao-paulo?")
        assert "q=Rua+Guaip" in sale_url

    def test_next_data_yields_five_listings(self) -> None:
        payload = _make_loft_next_payload(8)
        results, pagination = _extract_from_loft_next_data(payload, "rent")

        assert len(results) >= 5
        assert pagination["totalPages"] == 1
        for r in results:
            assert r["platform"] == "loft"
            assert r["platform_listing_id"]
            assert r["url"].startswith("https://loft.com.br/imovel/")

    def test_parser_uses_rental_price_for_rent(self) -> None:
        result = _parse_loft_listing(
            {
                "id": "c94at7ar",
                "price": 915000,
                "rentalPrice": 5500,
                "area": 99,
                "bedrooms": 2,
                "restrooms": 2,
                "parkingSpots": 1,
                "image": "banner.jpg",
                "address": {
                    "streetFullName": "Rua Guaipá",
                    "neighborhood": "Vila Leopoldina",
                    "city": "São Paulo",
                    "state": "SP",
                    "lat": "-23.5212571",
                    "lng": "-46.7304601",
                },
            },
            "rent",
        )

        assert result is not None
        assert result["price_brl"] == 5500.0
        assert result["lat"] == -23.5212571
        assert result["lon"] == -46.7304601
        assert result["image_url"] == "https://content.loft.com.br/homes/c94at7ar/mobile_banner.jpg"

    def test_parser_uses_sale_price_for_sale(self) -> None:
        result = _parse_loft_listing(
            {
                "id": "1qo6sje",
                "price": 590000,
                "rentalPrice": 4500,
                "address": {"streetFullName": "Rua Guaipu"},
            },
            "sale",
        )

        assert result is not None
        assert result["price_brl"] == 590000.0


# ---------------------------------------------------------------------------
# VivaReal
# ---------------------------------------------------------------------------

class TestVivaRealExtraction:
    def test_glue_payload_yields_five_listings(self) -> None:
        payload = _make_glue_payload(8, "vivareal")
        results = _extract_from_glue_payload(payload, "vivareal", "rent")
        assert len(results) >= 5
        for r in results:
            assert r["platform"] == "vivareal"
            assert r["platform_listing_id"]
            assert r["url"]

    def test_dom_fallback_yields_five_listings(self) -> None:
        rows = _make_dom_rows(8, "vivareal")
        results = _extract_from_dom_rows(rows, "vivareal")
        assert len(results) >= 5
        for r in results:
            assert r["platform"] == "vivareal"
            assert r["platform_listing_id"]
            assert r["url"].startswith("https://")

    def test_dom_fallback_skips_rows_without_id(self) -> None:
        rows = [{"href": "/sem-numero/", "text": "Apartamento"}]
        results = _extract_from_dom_rows(rows, "vivareal")
        assert results == []

    def test_dom_fallback_parses_price_and_area(self) -> None:
        rows = [{"href": "/imovel/123456/", "text": "R$ 3.500,00  75 m²  2 quartos"}]
        results = _extract_from_dom_rows(rows, "vivareal")
        assert len(results) == 1
        r = results[0]
        assert r["area_m2"] == 75.0
        assert r["bedrooms"] == 2

    def test_dom_fallback_preserves_image_url(self) -> None:
        rows = [{"href": "/imovel/123456/", "text": "R$ 3.500,00  75 m²  2 quartos", "image_url": "/thumbs/vr-1.webp"}]
        results = _extract_from_dom_rows(rows, "vivareal")

        assert len(results) == 1
        assert results[0]["image_url"] == "https://www.vivareal.com.br/thumbs/vr-1.webp"

    def test_glue_payload_normalizes_relative_media_url(self) -> None:
        image_url = _extract_listing_card_image_url(
            {
                "medias": [
                    {
                        "url": "/thumbs/vr-2.webp"
                    }
                ]
            },
            "vivareal",
        )

        assert image_url == "https://www.vivareal.com.br/thumbs/vr-2.webp"

    def test_glue_payload_uses_approximate_point_coordinates(self) -> None:
        payload = {
            "search": {
                "result": {
                    "listings": [
                        {
                            "listing": {
                                "id": "999001",
                                "address": {
                                    "point": {
                                        "source": "GOOGLE",
                                        "approximateLat": -23.521,
                                        "approximateLon": -46.729,
                                        "radius": 250,
                                    },
                                    "street": "Rua Guaipa",
                                    "neighborhood": "Vila Leopoldina",
                                    "city": "São Paulo",
                                    "stateAcronym": "SP",
                                },
                                "pricingInfos": [
                                    {
                                        "businessType": "RENTAL",
                                        "rentalTotalPrice": "3200",
                                    }
                                ],
                            },
                            "link": {"href": "https://www.vivareal.com.br/imovel/apto-id-999001/"},
                        }
                    ]
                }
            }
        }

        results = _extract_from_glue_payload(payload, "vivareal", "rent")
        assert len(results) == 1
        assert results[0]["lat"] == -23.521
        assert results[0]["lon"] == -46.729

    def test_glue_payload_ignores_template_media_urls(self) -> None:
        image_url = _extract_listing_card_image_url(
            {
                "medias": [
                    {
                        "url": "https://resizedimgs.vivareal.com/img/vr-listing/abc/{description}.webp?action={action}&dimension={width}x{height}"
                    }
                ]
            }
        )

        assert image_url is None


class TestListingUsageInferenceFromUrl:
    def test_marks_commercial_from_listing_url(self) -> None:
        usage_type = infer_listing_usage_type_from_url(
            "https://www.zapimoveis.com.br/imovel/aluguel-conjunto-comercial-sala-bela-vista-centro-sao-paulo-sp-31m2-id-2877617488/",
            2,
        )

        assert usage_type == "commercial"

    def test_prioritizes_commercial_when_bedrooms_are_missing_even_with_residential_url(self) -> None:
        usage_type = infer_listing_usage_type_from_url(
            "https://www.zapimoveis.com.br/imovel/aluguel-apartamento-pinheiros-sao-paulo-sp-70m2-id-123456/",
            0,
        )

        assert usage_type == "commercial"

    def test_falls_back_to_bedrooms_when_url_has_no_signal(self) -> None:
        assert infer_listing_usage_type_from_url("https://www.example.com/imovel/123", 0) == "commercial"
        assert infer_listing_usage_type_from_url("https://www.example.com/imovel/123", 2) == "residential"


# ---------------------------------------------------------------------------
# ZapImoveis
# ---------------------------------------------------------------------------

class TestZapImoveisExtraction:
    def test_glue_payload_yields_five_listings(self) -> None:
        payload = _make_glue_payload(8, "zapimoveis")
        results = zap_extract_glue(payload, "zapimoveis", "rent")
        assert len(results) >= 5
        for r in results:
            assert r["platform"] == "zapimoveis"
            assert r["platform_listing_id"]

    def test_dom_fallback_yields_five_listings(self) -> None:
        rows = _make_dom_rows(8, "zapimoveis")
        results = _extract_from_dom_rows(rows, "zapimoveis")
        assert len(results) >= 5

    def test_dom_fallback_normalizes_image_url(self) -> None:
        rows = [{"href": "/imovel/123456/", "text": "R$ 3.500,00  75 m²  2 quartos", "image_url": "/thumbs/zap-1.webp"}]
        results = _extract_from_dom_rows(rows, "zapimoveis")

        assert len(results) == 1
        assert results[0]["image_url"] == "https://www.zapimoveis.com.br/thumbs/zap-1.webp"

    def test_glue_payload_uses_approximate_point_coordinates(self) -> None:
        payload = {
            "search": {
                "result": {
                    "listings": [
                        {
                            "listing": {
                                "id": "999002",
                                "address": {
                                    "point": {
                                        "source": "GOOGLE",
                                        "approximateLat": -23.522,
                                        "approximateLon": -46.728,
                                        "radius": 140,
                                    },
                                    "street": "Rua Guaipa",
                                    "neighborhood": "Vila Leopoldina",
                                    "city": "São Paulo",
                                    "stateAcronym": "SP",
                                },
                                "pricingInfos": [
                                    {
                                        "businessType": "RENTAL",
                                        "rentalTotalPrice": "3300",
                                    }
                                ],
                            },
                            "link": {"href": "https://www.zapimoveis.com.br/imovel/apto-id-999002/"},
                        }
                    ]
                }
            }
        }

        results = zap_extract_glue(payload, "zapimoveis", "rent")
        assert len(results) == 1
        assert results[0]["lat"] == -23.522
        assert results[0]["lon"] == -46.728


# ---------------------------------------------------------------------------
# QuintoAndar
# ---------------------------------------------------------------------------

class TestQuintoAndarExtraction:
    def test_location_slug_uses_neighborhood_for_street_search(self) -> None:
        slug = _to_quintoandar_location_slug(
            "Rua Guaipa, Vila Leopoldina, Sao Paulo, SP"
        )

        assert slug == "vila-leopoldina-sao-paulo-sp-brasil"

    def test_location_slug_keeps_two_part_neighborhood_search(self) -> None:
        slug = _to_quintoandar_location_slug("Vila Leopoldina, Sao Paulo-SP")

        assert slug == "vila-leopoldina-sao-paulo-sp-brasil"

    def test_location_slug_uses_city_only_for_street_plus_city(self) -> None:
        slug = _to_quintoandar_location_slug("Rua Guaipa, Sao Paulo-SP")

        assert slug == "sao-paulo-sp-brasil"

    def test_dom_fallback_yields_five_listings(self) -> None:
        rows = _make_quintoandar_dom_rows(8)
        results = _extract_from_quintoandar_dom_rows(rows)
        assert len(results) >= 5
        for r in results:
            assert r["platform"] == "quintoandar"
            assert r["platform_listing_id"]
            assert r["url"].startswith("https://www.quintoandar.com.br")

    def test_payload_normalizes_cover_image_filename(self) -> None:
        result = _parse_quintoandar_house(
            "4001",
            {
                "id": "4001",
                "rentPrice": 3200,
                "coverImage": "894723853-808.334581783361IMG2447.JPG",
                "address": "Rua Teste",
                "neighbourhood": "Pinheiros",
                "city": "São Paulo",
            },
            "rent",
        )

        assert result is not None
        assert result["image_url"] == "https://www.quintoandar.com.br/img/med/894723853-808.334581783361IMG2447.JPG"

    def test_dom_fallback_skips_rows_without_id(self) -> None:
        rows = [{"href": "/sem-numero/", "text": "Apartamento"}]
        results = _extract_from_quintoandar_dom_rows(rows)
        assert results == []

    def test_dom_fallback_parses_price_area_bedrooms(self) -> None:
        rows = [{"href": "/imovel/654321", "text": "R$ 4.200,00  80 m²  3 quartos"}]
        results = _extract_from_quintoandar_dom_rows(rows)
        assert len(results) == 1
        r = results[0]
        assert r["area_m2"] == 80.0
        assert r["bedrooms"] == 3
        assert r["url"] == "https://www.quintoandar.com.br/imovel/654321"

    def test_dom_fallback_preserves_image_url(self) -> None:
        rows = [{"href": "/imovel/654321", "text": "R$ 4.200,00  80 m²  3 quartos", "image_url": "/thumbs/qa-1.webp"}]
        results = _extract_from_quintoandar_dom_rows(rows)

        assert len(results) == 1
        assert results[0]["image_url"] == "https://www.quintoandar.com.br/thumbs/qa-1.webp"

    def test_api_payload_extraction(self) -> None:
        """Ensure _extract_from_quintoandar_payload handles nested API formats."""
        # The current extractor handles flat house dicts; test with a simple flat case
        flat_payload = {"houses": {
            str(5000 + i): {
                "lat": -23.56,
                "lon": -46.65,
                "rentPrice": 3000 + i * 100,
                "area": 60 + i,
                "bedrooms": 2,
                "bathrooms": 1,
                "slug": f"/imovel/{5000 + i}",
            }
            for i in range(1, 7)
        }}
        results = _extract_from_quintoandar_payload(flat_payload, "rent")
        assert len(results) >= 5

    def test_api_payload_extraction_es_hits_source(self) -> None:
        payload = {
            "data": {
                "search": {
                    "result": {
                        "hits": {
                            "hits": [
                                {
                                    "_id": f"{7000 + i}",
                                    "_source": {
                                        "id": f"{7000 + i}",
                                        "lat": -23.56 + i * 0.001,
                                        "lon": -46.65 + i * 0.001,
                                        "rentPrice": 3000 + i * 100,
                                        "area": 65 + i,
                                        "bedrooms": 2,
                                        "bathrooms": 1,
                                        "slug": f"/imovel/{7000 + i}",
                                    },
                                }
                                for i in range(1, 7)
                            ]
                        }
                    }
                }
            }
        }

        results = _extract_from_quintoandar_payload(payload, "rent")
        assert len(results) >= 5

    def test_coordinate_payload_extraction_maps_ids_to_lat_lon(self) -> None:
        payload = {
            "hits": {
                "hits": [
                    {
                        "_id": "qa-1",
                        "_source": {
                            "id": "qa-1",
                            "location": {"lat": -23.52, "lon": -46.72},
                        },
                    },
                    {
                        "_id": "qa-2",
                        "_source": {
                            "id": "qa-2",
                            "location": {"lat": -23.53, "lng": -46.73},
                        },
                    },
                ]
            }
        }

        result = _extract_quintoandar_coordinate_map(payload)

        assert result == {
            "qa-1": (-23.52, -46.72),
            "qa-2": (-23.53, -46.73),
        }
