import os
import sys
from pathlib import Path

import httpx
import pytest

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/find_ideal_estate")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("MAPBOX_ACCESS_TOKEN", "test")
os.environ.setdefault("MAPTILER_API_KEY", "test")
os.environ.setdefault("VALHALLA_URL", "http://localhost:8002")
os.environ.setdefault("OTP_URL", "http://localhost:8080")

from src.modules.transport.valhalla_adapter import (  # noqa: E402
    GeoPoint,
    ValhallaAdapter,
    ValhallaCommunicationError,
)


class _FakeRedis:
    def __init__(self) -> None:
        self.storage: dict[str, str] = {}
        self.ttl_by_key: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        return self.storage.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.storage[key] = value
        self.ttl_by_key[key] = ttl


@pytest.mark.anyio
async def test_phase3_valhalla_route_uses_cache_key_and_ttl() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.path == "/route"
        return httpx.Response(
            status_code=200,
            json={"trip": {"summary": {"length": 3.2, "time": 540}}},
        )

    redis_client = _FakeRedis()
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(base_url="http://valhalla.test", transport=transport) as client:
        adapter = ValhallaAdapter(base_url="http://valhalla.test", redis_client=redis_client, http_client=client)
        origin = GeoPoint(lat=-23.55052, lon=-46.63331)
        dest = GeoPoint(lat=-23.56111, lon=-46.65522)

        first = await adapter.route(origin, dest, costing="pedestrian")
        second = await adapter.route(origin, dest, costing="pedestrian")

    assert first.distance_km == pytest.approx(3.2)
    assert first.duration_sec == pytest.approx(540.0)
    assert second.distance_km == pytest.approx(3.2)
    assert calls == 1

    cache_key = "valhalla:pedestrian:-23.550520:-46.633310:-23.561110:-46.655220"
    assert cache_key in redis_client.storage
    assert redis_client.ttl_by_key[cache_key] == 24 * 60 * 60


@pytest.mark.anyio
async def test_phase3_valhalla_route_timeout_maps_to_domain_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(base_url="http://valhalla.test", transport=transport) as client:
        adapter = ValhallaAdapter(base_url="http://valhalla.test", http_client=client)
        with pytest.raises(ValhallaCommunicationError, match="Timed out"):
            await adapter.route(
                GeoPoint(lat=-23.55, lon=-46.63),
                GeoPoint(lat=-23.56, lon=-46.64),
                costing="pedestrian",
            )


@pytest.mark.anyio
async def test_phase3_valhalla_isochrone_returns_geojson_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/isochrone"
        return httpx.Response(
            status_code=200,
            json={
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Polygon", "coordinates": []},
                        "properties": {"contour": 10},
                    }
                ],
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(base_url="http://valhalla.test", transport=transport) as client:
        adapter = ValhallaAdapter(base_url="http://valhalla.test", http_client=client)
        geojson = await adapter.isochrone(
            origin=GeoPoint(lat=-23.55, lon=-46.63),
            costing="pedestrian",
            contours_minutes=[10],
        )

    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) == 1


@pytest.mark.anyio
async def test_phase3_valhalla_isochrone_http_400_preserves_error_detail() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/isochrone"
        return httpx.Response(
            status_code=400,
            json={
                "error_code": 171,
                "error": "No suitable edges near location",
                "status_code": 400,
                "status": "Bad Request",
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(base_url="http://valhalla.test", transport=transport) as client:
        adapter = ValhallaAdapter(base_url="http://valhalla.test", http_client=client)
        with pytest.raises(ValhallaCommunicationError, match="HTTP 400: No suitable edges near location"):
            await adapter.isochrone(
                origin=GeoPoint(lat=-19.919763080281186, lon=-43.9538221025058),
                costing="pedestrian",
                contours_minutes=[30],
            )
