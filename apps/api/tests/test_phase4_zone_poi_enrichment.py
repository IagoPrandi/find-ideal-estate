from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

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

from src.modules.zones.enrichment import (  # noqa: E402
    _format_bbox,
    _format_proximity,
    _mapbox_poi_params,
    _poi_cache_key,
    _POI_CATEGORIES,
    enrich_zone_pois,
)


class _FakeMappings:
    def __init__(self, *, first_row=None):
        self._first_row = first_row

    def first(self):
        return self._first_row


class _FakeResult:
    def __init__(self, *, first_row=None):
        self._mappings = _FakeMappings(first_row=first_row)

    def mappings(self):
        return self._mappings


class _FakeConn:
    def __init__(self, *, zone_row=None):
        self.zone_row = zone_row

    async def execute(self, statement, params):
        sql = str(statement)
        if "SELECT" in sql and "FROM zones z" in sql:
            return _FakeResult(first_row=self.zone_row)
        raise AssertionError(f"Unexpected SQL executed: {sql}")


class _FakeBeginCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeEngine:
    def __init__(self, conns):
        self._conns = list(conns)

    def begin(self):
        if not self._conns:
            raise AssertionError("No fake connections left")
        return _FakeBeginCtx(self._conns.pop(0))


def test_mapbox_poi_param_formatting_is_stable() -> None:
    bbox = (-46.73879353133167, -23.53168773409916, -46.71528046866825, -23.51012826589938)
    assert _format_bbox(bbox) == "-46.738794,-23.531688,-46.715280,-23.510128"
    assert _format_proximity(-46.727036999999946, -23.520907999999263) == "-46.727037,-23.520908"

    params = _mapbox_poi_params(
        category="school",
        access_token="pk.testtoken123",
        bbox=bbox,
        lon=-46.727036999999946,
        lat=-23.520907999999263,
    )

    assert params["q"] == "school"
    assert params["types"] == "poi"
    assert params["bbox"] == "-46.738794,-23.531688,-46.715280,-23.510128"
    assert params["proximity"] == "-46.727037,-23.520908"


@pytest.mark.anyio
async def test_enrich_zone_pois_uses_forward_endpoint_and_counts_features() -> None:
    zone_id = uuid4()
    zone_row = {
        "zone_fingerprint": "zone-fp-123",
        "poi_source_fingerprint": "zone-fp-123",
        "lon": -46.727036999999946,
        "lat": -23.520907999999263,
        "xmin": -46.73879353133167,
        "ymin": -23.53168773409916,
        "xmax": -46.71528046866825,
        "ymax": -23.51012826589938,
    }
    read_conn = _FakeConn(zone_row=zone_row)
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.set = AsyncMock(return_value=True)
    persist_mock = AsyncMock(return_value=None)
    project_mock = AsyncMock(return_value=None)

    with (
        patch("src.modules.zones.enrichment.get_engine", return_value=_FakeEngine([read_conn])),
        patch("src.modules.zones.enrichment.get_redis", return_value=redis_mock),
        patch("src.modules.zones.enrichment.get_persisted_poi_cache_payload", AsyncMock(return_value=None)),
        patch("src.modules.zones.enrichment.persist_poi_cache_payload", persist_mock),
        patch("src.modules.zones.enrichment.project_poi_payload_to_zone", project_mock),
        patch("src.modules.zones.enrichment.mark_poi_cache_failed", AsyncMock(return_value=None)),
        patch(
            "src.modules.zones.enrichment.get_settings",
            return_value=SimpleNamespace(mapbox_access_token="pk.testtoken123"),
        ),
        patch("httpx.AsyncClient") as mock_client_cls,
    ):
        response_mock = MagicMock()
        response_mock.raise_for_status = MagicMock()
        response_mock.json = MagicMock(
            return_value={
                "features": [
                    {
                        "id": "poi-1",
                        "geometry": {"coordinates": [-46.727, -23.521]},
                        "properties": {"name": "Colegio Centro", "full_address": "Rua A, 10"},
                    },
                    {
                        "id": "poi-2",
                        "geometry": {"coordinates": [-46.726, -23.522]},
                        "properties": {"name": "Mercado Azul", "full_address": "Rua B, 20"},
                    },
                    {
                        "id": "poi-3",
                        "geometry": {"coordinates": [-46.725, -23.523]},
                        "properties": {"name": "Parque Verde", "full_address": "Rua C, 30"},
                    },
                ]
            }
        )
        client_get = AsyncMock(return_value=response_mock)
        mock_client_cls.return_value.__aenter__.return_value.get = client_get

        result = await enrich_zone_pois(zone_id)

    assert result["zone_id"] == str(zone_id)
    assert result["poi_counts"] == {
        "school": 3,
        "supermarket": 3,
        "pharmacy": 3,
        "park": 3,
        "restaurant": 3,
        "gym": 3,
    }
    assert len(result["poi_points"]) == 18
    assert {point["category"] for point in result["poi_points"]} == {
        "school",
        "supermarket",
        "pharmacy",
        "park",
        "restaurant",
        "gym",
    }
    assert len(client_get.await_args_list) == 6
    first_call = client_get.await_args_list[0]
    assert first_call.args[0] == "https://api.mapbox.com/search/searchbox/v1/forward"
    assert first_call.kwargs["params"]["types"] == "poi"
    assert first_call.kwargs["params"]["bbox"] == "-46.738794,-23.531688,-46.715280,-23.510128"
    assert first_call.kwargs["params"]["proximity"] == "-46.727037,-23.520908"
    persist_kwargs = persist_mock.await_args.kwargs
    assert persist_kwargs["zone_fingerprint"] == "zone-fp-123"
    assert persist_kwargs["poi_counts"] == result["poi_counts"]
    assert persist_kwargs["poi_points"] == result["poi_points"]
    assert len(persist_kwargs["poi_entries"]) == 18
    project_mock.assert_awaited_once_with(zone_id, poi_counts=result["poi_counts"], poi_points=result["poi_points"])


@pytest.mark.anyio
async def test_enrich_zone_pois_reuses_canonical_zone_center_from_journey_scope() -> None:
    zone_id = uuid4()
    journey_id = uuid4()
    zone_row = {
        "zone_fingerprint": "zone-c",
        "poi_source_fingerprint": "zone-a",
        "lon": -46.625161,
        "lat": -23.516131,
        "xmin": -46.629078,
        "ymin": -23.519743,
        "xmax": -46.621245,
        "ymax": -23.512520,
    }
    read_conn = _FakeConn(zone_row=zone_row)
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.set = AsyncMock(return_value=True)
    project_mock = AsyncMock(return_value=None)
    persisted_payload = {
        "poi_counts": {category: 2 for category in _POI_CATEGORIES},
        "poi_points": [
            {
                "kind": "poi",
                "id": "poi-a",
                "name": "POI A",
                "category": "school",
                "address": "Rua A, 10",
                "lat": -23.516131,
                "lon": -46.625161,
            }
        ],
    }

    with (
        patch("src.modules.zones.enrichment.get_engine", return_value=_FakeEngine([read_conn])),
        patch("src.modules.zones.enrichment.get_redis", return_value=redis_mock),
        patch(
            "src.modules.zones.enrichment.get_persisted_poi_cache_payload",
            AsyncMock(return_value=persisted_payload),
        ) as persisted_mock,
        patch("src.modules.zones.enrichment.project_poi_payload_to_zone", project_mock),
        patch("src.modules.zones.enrichment.persist_poi_cache_payload", AsyncMock(return_value=None)) as persist_mock,
        patch("httpx.AsyncClient") as mock_client_cls,
    ):
        result = await enrich_zone_pois(zone_id, journey_id=journey_id)

    expected_cache_key = _poi_cache_key(
        zone_fingerprint="zone-a",
        categories=("school", "supermarket", "pharmacy", "park", "restaurant", "gym"),
        bbox=(-46.629078, -23.519743, -46.621245, -23.51252),
    )
    assert persisted_mock.await_args.args == ("zone-a", persisted_mock.await_args.args[1])
    assert result["zone_id"] == str(zone_id)
    assert result["poi_counts"] == persisted_payload["poi_counts"]
    assert result["poi_points"] == persisted_payload["poi_points"]
    redis_mock.set.assert_awaited_once_with(
        expected_cache_key,
        json.dumps(persisted_payload, ensure_ascii=True),
        ex=1800,
    )
    project_mock.assert_awaited_once_with(
        zone_id,
        poi_counts=persisted_payload["poi_counts"],
        poi_points=persisted_payload["poi_points"],
    )
    persist_mock.assert_not_awaited()
    assert not mock_client_cls.called