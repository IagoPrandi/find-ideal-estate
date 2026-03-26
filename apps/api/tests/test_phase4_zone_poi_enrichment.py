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
        self.update_calls: list[dict[str, object]] = []

    async def execute(self, statement, params):
        sql = str(statement)
        if "SELECT" in sql and "FROM zones z" in sql:
            return _FakeResult(first_row=self.zone_row)
        if "UPDATE zones" in sql and "SET poi_counts" in sql:
            self.update_calls.append(dict(params))
            return _FakeResult()
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
        "fingerprint": "zone-fp-123",
        "lon": -46.727036999999946,
        "lat": -23.520907999999263,
        "xmin": -46.73879353133167,
        "ymin": -23.53168773409916,
        "xmax": -46.71528046866825,
        "ymax": -23.51012826589938,
    }
    read_conn = _FakeConn(zone_row=zone_row)
    write_conn = _FakeConn()
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.set = AsyncMock(return_value=True)

    with (
        patch("src.modules.zones.enrichment.get_engine", return_value=_FakeEngine([read_conn, write_conn])),
        patch("src.modules.zones.enrichment.get_redis", return_value=redis_mock),
        patch(
            "src.modules.zones.enrichment.get_settings",
            return_value=SimpleNamespace(mapbox_access_token="pk.testtoken123"),
        ),
        patch("httpx.AsyncClient") as mock_client_cls,
    ):
        response_mock = MagicMock()
        response_mock.raise_for_status = MagicMock()
        response_mock.json = MagicMock(return_value={"features": [{}, {}, {}]})
        client_get = AsyncMock(return_value=response_mock)
        mock_client_cls.return_value.__aenter__.return_value.get = client_get

        result = await enrich_zone_pois(zone_id)

    assert result == {
        "zone_id": str(zone_id),
        "poi_counts": {
            "school": 3,
            "supermarket": 3,
            "pharmacy": 3,
            "park": 3,
        },
    }
    assert len(client_get.await_args_list) == 4
    first_call = client_get.await_args_list[0]
    assert first_call.args[0] == "https://api.mapbox.com/search/searchbox/v1/forward"
    assert first_call.kwargs["params"]["types"] == "poi"
    assert first_call.kwargs["params"]["bbox"] == "-46.738794,-23.531688,-46.715280,-23.510128"
    assert first_call.kwargs["params"]["proximity"] == "-46.727037,-23.520908"
    assert write_conn.update_calls == [
        {
            "zone_id": zone_id,
            "poi_counts": json.dumps(
                {"school": 3, "supermarket": 3, "pharmacy": 3, "park": 3},
                ensure_ascii=True,
            ),
        }
    ]