import os
import sys
from datetime import datetime
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

from src.modules.transport.otp_adapter import OTPAdapter, OTPCommunicationError  # noqa: E402
from src.modules.transport.valhalla_adapter import GeoPoint  # noqa: E402


@pytest.mark.anyio
async def test_phase3_otp_plan_returns_multiple_itineraries_sorted_and_mapped_modes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/otp/transmodel/v3"
        return httpx.Response(
            status_code=200,
            json={
                "data": {
                    "trip": {
                        "tripPatterns": [
                            {
                                "duration": 1900,
                                "walkTime": 400,
                                "legs": [
                                    {"mode": "foot", "duration": 400, "line": None},
                                    {
                                        "mode": "bus",
                                        "duration": 1300,
                                        "line": {"publicCode": "875A-10", "name": "Linha A"},
                                    },
                                ],
                            },
                            {
                                "duration": 1200,
                                "walkTime": 240,
                                "legs": [
                                    {"mode": "foot", "duration": 240, "line": None},
                                    {
                                        "mode": "subway",
                                        "duration": 780,
                                        "line": {"publicCode": None, "name": "Linha 2-Verde"},
                                    },
                                ],
                            },
                        ],
                        "routingErrors": [],
                    }
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(base_url="http://otp.test", transport=transport) as client:
        adapter = OTPAdapter(base_url="http://otp.test", http_client=client)
        result = await adapter.plan(
            origin=GeoPoint(lat=-23.55052, lon=-46.63331),
            dest=GeoPoint(lat=-23.58769, lon=-46.65756),
            trip_datetime=datetime(2026, 3, 18, 8, 30, 0),
        )

    assert len(result.options) == 2
    assert [option.duration_sec for option in result.options] == [1200.0, 1900.0]

    fastest = result.options[0]
    assert fastest.modal_types == ["walk", "metro"]
    assert fastest.lines == ["Linha 2-Verde"]

    second = result.options[1]
    assert second.modal_types == ["walk", "bus"]
    assert second.lines == ["875A-10"]


@pytest.mark.anyio
async def test_phase3_otp_plan_timeout_maps_to_domain_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(base_url="http://otp.test", transport=transport) as client:
        adapter = OTPAdapter(base_url="http://otp.test", http_client=client)
        with pytest.raises(OTPCommunicationError, match="Timed out"):
            await adapter.plan(
                origin=GeoPoint(lat=-23.55, lon=-46.63),
                dest=GeoPoint(lat=-23.56, lon=-46.64),
                trip_datetime=datetime(2026, 3, 18, 8, 30, 0),
            )


@pytest.mark.anyio
async def test_phase3_otp_plan_fallbacks_to_rest_when_graphql_unavailable() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        key = f"{request.method}:{request.url.path}"
        calls.append(key)
        if key == "POST:/otp/transmodel/v3":
            return httpx.Response(status_code=404)
        if key == "GET:/plan":
            return httpx.Response(status_code=404, json={"error": "not found"})
        if key == "GET:/otp/routers/default/plan":
            return httpx.Response(
                status_code=200,
                json={"plan": {"itineraries": [{"duration": 600, "legs": []}]}},
            )
        return httpx.Response(status_code=500, json={"error": "unexpected path"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(base_url="http://otp.test", transport=transport) as client:
        adapter = OTPAdapter(base_url="http://otp.test", http_client=client)
        result = await adapter.plan(
            origin=GeoPoint(lat=-23.55, lon=-46.63),
            dest=GeoPoint(lat=-23.56, lon=-46.64),
            trip_datetime=datetime(2026, 3, 18, 8, 30, 0),
        )

    assert calls == ["POST:/otp/transmodel/v3", "GET:/plan", "GET:/otp/routers/default/plan"]
    assert len(result.options) == 1
    assert result.options[0].duration_sec == 600.0
