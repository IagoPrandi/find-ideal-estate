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
    get_zone_address_suggestions,
)


def test_format_street_address_matches_scraper_expectation() -> None:
    assert (
        _format_street_address("Rua Schilling", "Vila Leopoldina", "Sao Paulo", "SP")
        == "Rua Schilling, Vila Leopoldina, Sao Paulo-SP"
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
            q="schi",
        )

    assert suggestions == [
        {
            "label": "Rua Schilling, Vila Leopoldina, Sao Paulo-SP",
            "normalized": "rua schilling, vila leopoldina, sao paulo-sp",
            "location_type": "street",
            "lat": -23.520908,
            "lon": -46.727037,
        }
    ]
    redis_mock.set.assert_awaited_once()


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
            q="carlos",
        )

    assert suggestions == [cached_suggestions[1]]
    mock_client_cls.assert_not_called()