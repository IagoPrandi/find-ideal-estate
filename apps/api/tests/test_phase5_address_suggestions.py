from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/find_ideal_estate")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("MAPBOX_ACCESS_TOKEN", "pk.testtoken123")
os.environ.setdefault("MAPTILER_API_KEY", "test")
os.environ.setdefault("VALHALLA_URL", "http://localhost:8002")
os.environ.setdefault("OTP_URL", "http://localhost:8080")

from src.modules.listings.address_suggestions import (  # noqa: E402
    _format_street_address,
    _cache_key,
    get_zone_address_suggestions,
)
from src.modules.zones.isochrone_proxy import build_isochrone_proxy_circle  # noqa: E402


def test_format_street_address_matches_scraper_expectation() -> None:
    assert (
        _format_street_address("Rua Schilling", "Vila Leopoldina", "Sao Paulo", "SP")
        == "Rua Schilling, Vila Leopoldina, Sao Paulo, SP"
    )


def test_build_isochrone_proxy_circle_matches_equivalent_area_bbox() -> None:
    proxy_circle = build_isochrone_proxy_circle(
        lon=-46.727036999999946,
        lat=-23.520907999999263,
        area_m2=3141592.653589793,
    )

    assert proxy_circle["geometry"]["type"] == "Polygon"
    assert len(proxy_circle["geometry"]["coordinates"][0]) == 65
    assert proxy_circle["bbox"] == pytest.approx(
        (-46.736834, -23.529891, -46.717240, -23.511925),
        abs=1e-6,
    )


@pytest.mark.anyio
async def test_get_zone_address_suggestions_formats_labels_from_tilequery_flow() -> None:
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.set = AsyncMock(return_value=True)
    geometry = {
        "type": "Polygon",
        "coordinates": [[
            [-46.730000, -23.525000],
            [-46.720000, -23.525000],
            [-46.720000, -23.515000],
            [-46.730000, -23.515000],
            [-46.730000, -23.525000],
        ]],
    }

    with (
        patch("src.modules.listings.address_suggestions.get_redis", return_value=redis_mock),
        patch(
            "src.modules.listings.address_suggestions._generate_points_within_geometry",
            return_value=[(-46.727037, -23.520908)],
        ),
        patch(
            "src.modules.listings.address_suggestions._tilequery_road_names",
            new=AsyncMock(return_value={"Rua Schilling"}),
        ),
        patch(
            "src.modules.listings.address_suggestions._reverse_geocode_context",
            new=AsyncMock(return_value=("Vila Leopoldina", "Sao Paulo", "SP")),
        ),
        patch("httpx.AsyncClient") as mock_client_cls,
    ):
        mock_client_cls.return_value.__aenter__.return_value = MagicMock()
        suggestions = await get_zone_address_suggestions(
            access_token="pk.testtoken123",
            zone_fingerprint="zone-fp-123",
            geometry=geometry,
            bbox=(-46.73, -23.525, -46.72, -23.515),
            centroid=(-46.727037, -23.520908),
            modal="transit",
            search_radius_m=900.0,
            q="schi",
        )

    assert suggestions == [
        {
            "label": "Rua Schilling, Vila Leopoldina, Sao Paulo, SP",
            "normalized": "rua schilling, vila leopoldina, sao paulo, sp",
            "location_type": "street",
            "lat": -23.520908,
            "lon": -46.727037,
        }
    ]
    redis_mock.get.assert_awaited_once_with(_cache_key("zone-fp-123"))
    redis_mock.set.assert_awaited_once()
    assert redis_mock.set.await_args.args[0] == _cache_key("zone-fp-123")


@pytest.mark.anyio
@pytest.mark.parametrize("modal", ["walking", "car"])
async def test_get_zone_address_suggestions_uses_single_radial_lookup_for_direct_modes(modal: str) -> None:
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.set = AsyncMock(return_value=True)
    geometry = {
        "type": "Polygon",
        "coordinates": [[
            [-46.730000, -23.525000],
            [-46.720000, -23.525000],
            [-46.720000, -23.515000],
            [-46.730000, -23.515000],
            [-46.730000, -23.525000],
        ]],
    }
    generate_points_mock = MagicMock(return_value=[(-46.727037, -23.520908)])
    tilequery_mock = AsyncMock(return_value={"Rua Augusta", "Rua Frei Caneca"})
    reverse_mock = AsyncMock(return_value=("Consolacao", "Sao Paulo", "SP"))

    with (
        patch("src.modules.listings.address_suggestions.get_redis", return_value=redis_mock),
        patch(
            "src.modules.listings.address_suggestions._generate_points_within_geometry",
            generate_points_mock,
        ),
        patch(
            "src.modules.listings.address_suggestions._tilequery_road_names",
            new=tilequery_mock,
        ),
        patch(
            "src.modules.listings.address_suggestions._reverse_geocode_context",
            new=reverse_mock,
        ),
        patch("httpx.AsyncClient") as mock_client_cls,
    ):
        mock_client_cls.return_value.__aenter__.return_value = MagicMock()
        suggestions = await get_zone_address_suggestions(
            access_token="pk.testtoken123",
            zone_fingerprint=f"zone-fp-{modal}",
            geometry=geometry,
            bbox=(-46.73, -23.525, -46.72, -23.515),
            centroid=(-46.727037, -23.520908),
            modal=modal,
            search_radius_m=1200.0,
            q="",
        )

    assert suggestions == [
        {
            "label": "Rua Augusta, Consolacao, Sao Paulo, SP",
            "normalized": "rua augusta, consolacao, sao paulo, sp",
            "location_type": "street",
            "lat": -23.520908,
            "lon": -46.727037,
        },
        {
            "label": "Rua Frei Caneca, Consolacao, Sao Paulo, SP",
            "normalized": "rua frei caneca, consolacao, sao paulo, sp",
            "location_type": "street",
            "lat": -23.520908,
            "lon": -46.727037,
        },
    ]
    generate_points_mock.assert_not_called()
    tilequery_mock.assert_awaited_once()
    assert tilequery_mock.await_args.kwargs["radius_m"] == 1200.0
    reverse_mock.assert_awaited_once()
    assert reverse_mock.await_args.kwargs["lon"] == -46.727037
    assert reverse_mock.await_args.kwargs["lat"] == -23.520908


@pytest.mark.anyio
async def test_get_zone_address_suggestions_filters_cached_combobox_options() -> None:
    cached_suggestions = [
        {
            "label": "Rua Schilling, Vila Leopoldina, Sao Paulo-SP",
            "normalized": "rua schilling, vila leopoldina, sao paulo-sp",
            "location_type": "street",
            "lat": -23.520908,
            "lon": -46.727037,
        },
        {
            "label": "Rua Carlos Weber, Vila Leopoldina, Sao Paulo-SP",
            "normalized": "rua carlos weber, vila leopoldina, sao paulo-sp",
            "location_type": "street",
            "lat": -23.521000,
            "lon": -46.728000,
        },
    ]
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=json.dumps(cached_suggestions, ensure_ascii=False))
    redis_mock.set = AsyncMock(return_value=True)

    with (
        patch("src.modules.listings.address_suggestions.get_redis", return_value=redis_mock),
        patch("httpx.AsyncClient") as mock_client_cls,
    ):
        suggestions = await get_zone_address_suggestions(
            access_token="pk.testtoken123",
            zone_fingerprint="zone-fp-123",
            geometry={"type": "Polygon", "coordinates": []},
            bbox=(-46.73, -23.525, -46.72, -23.515),
            centroid=(-46.727037, -23.520908),
            modal="walking",
            search_radius_m=1200.0,
            q="carlos",
        )

    assert suggestions == [cached_suggestions[1]]
    redis_mock.get.assert_awaited_once_with(_cache_key("zone-fp-123"))
    mock_client_cls.assert_not_called()