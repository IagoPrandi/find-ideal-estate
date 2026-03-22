"""Tests for M3.7 geocoding proxy: cache, rate-limit, debounce, ledger write."""

from __future__ import annotations

import json
import os
import sys
import time
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

from src.modules.geocoding.geocoding_service import (  # noqa: E402
    _cache_key,
    _normalize_query,
    geocode,
)

_MAPBOX_TOKEN = "pk.testtoken123"
_SESSION = "test-session-abc"


def _make_redis_mock(cached: str | None = None, ratelimit_count: int = 1) -> MagicMock:
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=cached)
    redis.set = AsyncMock(return_value=True)
    redis.incr = AsyncMock(return_value=ratelimit_count)
    redis.expire = AsyncMock(return_value=True)
    return redis


_MAPBOX_RESPONSE = {
    "suggestions": [
        {"name": "Avenida Paulista", "place_formatted": "São Paulo, SP, Brasil"},
        {"name": "Av. Paulista, 1000", "place_formatted": "São Paulo, SP, Brasil"},
    ]
}


@pytest.mark.anyio
async def test_geocode_cache_miss_calls_mapbox_and_stores_cache() -> None:
    redis_mock = _make_redis_mock(cached=None, ratelimit_count=1)

    with (
        patch("src.modules.geocoding.geocoding_service.get_redis", return_value=redis_mock),
        patch("src.modules.geocoding.geocoding_service.get_engine"),
        patch("src.modules.geocoding.geocoding_service._write_ledger", new=AsyncMock()),
        patch("httpx.AsyncClient") as mock_client_cls,
    ):
        resp_mock = AsyncMock()
        resp_mock.raise_for_status = MagicMock()
        resp_mock.json = MagicMock(return_value=_MAPBOX_RESPONSE)
        mock_client_cls.return_value.__aenter__.return_value.get = AsyncMock(return_value=resp_mock)

        result = await geocode(q="Av Paulista", session_id=_SESSION, mapbox_token=_MAPBOX_TOKEN)

    assert result["suggestions"] == _MAPBOX_RESPONSE["suggestions"]
    assert result["cache_hit"] is False
    # Verify cache was set.
    redis_mock.set.assert_any_await(
        _cache_key(_normalize_query("Av Paulista")),
        json.dumps({"suggestions": _MAPBOX_RESPONSE["suggestions"]}),
        ex=86400,
    )


@pytest.mark.anyio
async def test_geocode_cache_hit_skips_mapbox_call() -> None:
    cached_payload = json.dumps({"suggestions": _MAPBOX_RESPONSE["suggestions"]})

    def _get_side_effect(key: str) -> str | None:
        # debounce_key returns None, cache_key returns cached payload
        if key.startswith("geocode_db:"):
            return None
        return cached_payload

    redis_mock = _make_redis_mock()
    redis_mock.get = AsyncMock(side_effect=_get_side_effect)

    with (
        patch("src.modules.geocoding.geocoding_service.get_redis", return_value=redis_mock),
        patch("src.modules.geocoding.geocoding_service._write_ledger", new=AsyncMock()),
        patch("httpx.AsyncClient") as mock_client_cls,
    ):
        result = await geocode(q="Av Paulista", session_id=_SESSION, mapbox_token=_MAPBOX_TOKEN)

    assert result["cache_hit"] is True
    assert result["suggestions"] == _MAPBOX_RESPONSE["suggestions"]
    # No HTTP call should be made.
    mock_client_cls.assert_not_called()


@pytest.mark.anyio
async def test_geocode_rate_limit_raises_value_error() -> None:
    # No cache hit, rate limit exceeded (count > 30).
    redis_mock = _make_redis_mock(cached=None, ratelimit_count=31)

    with (
        patch("src.modules.geocoding.geocoding_service.get_redis", return_value=redis_mock),
        patch("src.modules.geocoding.geocoding_service._write_ledger", new=AsyncMock()),
        patch("httpx.AsyncClient") as mock_client_cls,
    ):
        with pytest.raises(ValueError, match="rate_limit_exceeded"):
            await geocode(q="Rua Augusta", session_id=_SESSION, mapbox_token=_MAPBOX_TOKEN)

    mock_client_cls.assert_not_called()


@pytest.mark.anyio
async def test_geocode_debounce_returns_cached_without_api_call() -> None:
    normalized = _normalize_query("Av Paulista")
    cached_payload = json.dumps({"suggestions": _MAPBOX_RESPONSE["suggestions"]})

    def _get_side_effect(key: str) -> str | None:
        if key.startswith("geocode_db:"):
            # Return debounce entry indicating last call was 50ms ago (within 300ms window).
            return json.dumps({"q": normalized, "ts": time.time() - 0.05})
        # Cache hit for the same query.
        return cached_payload

    redis_mock = _make_redis_mock()
    redis_mock.get = AsyncMock(side_effect=_get_side_effect)

    with (
        patch("src.modules.geocoding.geocoding_service.get_redis", return_value=redis_mock),
        patch("src.modules.geocoding.geocoding_service._write_ledger", new=AsyncMock()),
        patch("httpx.AsyncClient") as mock_client_cls,
    ):
        result = await geocode(q="Av Paulista", session_id=_SESSION, mapbox_token=_MAPBOX_TOKEN)

    assert result["cache_hit"] is True
    mock_client_cls.assert_not_called()


@pytest.mark.anyio
async def test_geocode_normalize_query() -> None:
    assert _normalize_query("  Av Paulista  ") == "av paulista"
    assert _normalize_query("RUA AUGUSTA") == "rua augusta"


@pytest.mark.anyio
async def test_geocode_cache_key_is_stable() -> None:
    key1 = _cache_key("av paulista")
    key2 = _cache_key("av paulista")
    key_diff = _cache_key("rua augusta")
    assert key1 == key2
    assert key1 != key_diff
    assert key1.startswith("geocode:v1:")
