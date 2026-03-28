from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from uuid import uuid4

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/find_ideal_estate")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("MAPBOX_ACCESS_TOKEN", "test")
os.environ.setdefault("MAPTILER_API_KEY", "test")
os.environ.setdefault("VALHALLA_URL", "http://localhost:8002")
os.environ.setdefault("OTP_URL", "http://localhost:8080")

from src.workers.handlers import enrichment as enrichment_handler  # noqa: E402


class _FakeResult:
    def mappings(self):
        return self

    def first(self):
        return None


class _FakeConn:
    async def execute(self, _statement, _params):
        return _FakeResult()


class _FakeBeginCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeEngine:
    def __init__(self):
        self._conn = _FakeConn()

    def begin(self):
        return _FakeBeginCtx(self._conn)


def test_extract_enrichment_flags_accepts_new_and_legacy_shapes() -> None:
    parsed_new = enrichment_handler._extract_enrichment_flags(
        {
            "enrichments": {
                "green": False,
                "flood": True,
                "safety": False,
                "pois": True,
            }
        }
    )
    assert parsed_new == {
        "green": False,
        "flood": True,
        "safety": False,
        "pois": True,
    }

    parsed_legacy = enrichment_handler._extract_enrichment_flags(
        {
            "zone_detail_include_green": 0,
            "zone_detail_include_flood": 1,
            "zone_detail_include_public_safety": "false",
            "zone_detail_include_pois": "true",
        }
    )
    assert parsed_legacy == {
        "green": False,
        "flood": True,
        "safety": False,
        "pois": True,
    }


def test_dispatch_enrichment_subjobs_runs_only_selected(monkeypatch) -> None:
    calls: list[str] = []

    async def _green(_zone_id):
        calls.append("green")
        return {"green_area_m2": 1.0}

    async def _flood(_zone_id):
        calls.append("flood")
        return {"flood_area_m2": 2.0}

    async def _safety(_zone_id):
        calls.append("safety")
        return {"safety_incidents_count": 3}

    async def _pois(_zone_id):
        calls.append("pois")
        return {"poi_counts": {"school": 4}}

    monkeypatch.setattr("src.workers.handlers.enrichment.get_engine", lambda: _FakeEngine())
    monkeypatch.setattr("src.workers.handlers.enrichment.enrich_zone_green", _green)
    monkeypatch.setattr("src.workers.handlers.enrichment.enrich_zone_flood", _flood)
    monkeypatch.setattr("src.workers.handlers.enrichment.enrich_zone_safety", _safety)
    monkeypatch.setattr("src.workers.handlers.enrichment.enrich_zone_pois", _pois)

    result = asyncio.run(
        enrichment_handler.dispatch_enrichment_subjobs(
            uuid4(),
            {
                "green": False,
                "flood": True,
                "safety": False,
                "pois": True,
            },
        )
    )

    assert calls == ["flood", "pois"]
    assert result == {
        "green_area_m2": None,
        "flood_area_m2": 2.0,
        "safety_incidents_count": None,
        "poi_counts": {"school": 4},
    }
