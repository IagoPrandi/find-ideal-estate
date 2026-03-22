from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
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

from fastapi.testclient import TestClient  # noqa: E402
from src.main import app  # noqa: E402


def _payload() -> dict[str, object]:
    return {
        "zone_fingerprint": "zone-a",
        "search_location_normalized": "rua guaipa vila leopoldina sao paulo",
        "search_location_label": "Rua Guaipa, Vila Leopoldina, Sao Paulo - SP",
        "search_location_type": "street",
        "search_type": "rent",
        "usage_type": "residential",
        "platforms": ["quintoandar", "zapimoveis"],
    }


def _fake_cards() -> list[dict[str, object]]:
    return [
        {
            "property_id": str(uuid4()),
            "address_normalized": "Rua Guaipa, 100",
            "area_m2": 70.0,
            "bedrooms": 2,
            "bathrooms": 1,
            "parking": 1,
            "usage_type": "residential",
            "current_best_price": "3500",
            "second_best_price": "3600",
            "duplication_badge": "Disponivel em 2 plataformas",
            "platform": "quintoandar",
            "platform_listing_id": "qa-123",
            "url": "https://example.org/qa-123",
            "observed_at": datetime.now(tz=timezone.utc).isoformat(),
        }
    ]


def test_listings_search_partial_hit_triggers_background_revalidation(monkeypatch) -> None:
    cache_partial = {
        "status": "partial",
        "zone_fingerprint": "zone-b",
        "expires_at": datetime.now(tz=timezone.utc) + timedelta(hours=6),
        "scraped_at": datetime.now(tz=timezone.utc),
    }
    calls = {"record": 0, "create_cache": 0, "enqueue": 0}

    class _Registry:
        def default_free_platforms(self):
            return ["quintoandar", "zapimoveis"]

        def resolve_names(self, names):
            return list(names)

    async def _fake_get_cache_record(_zfp, _cfg):
        return None

    async def _fake_partial(_zfp, _cfg):
        return cache_partial

    def _fake_cache_is_usable(record):
        return bool(record)

    async def _fake_record_search_request(**_kwargs):
        calls["record"] += 1

    async def _fake_fetch_listing_cards_for_zone(**_kwargs):
        return _fake_cards()

    async def _fake_create_cache_record(_zfp, _cfg):
        calls["create_cache"] += 1

    async def _fake_enqueue(**_kwargs):
        calls["enqueue"] += 1
        return uuid4()

    monkeypatch.setattr("api.routes.listings.get_platform_registry", lambda: _Registry())
    monkeypatch.setattr("api.routes.listings.get_cache_record", _fake_get_cache_record)
    monkeypatch.setattr(
        "api.routes.listings.find_partial_hit_from_overlapping_zone", _fake_partial
    )
    monkeypatch.setattr("api.routes.listings.cache_is_usable", _fake_cache_is_usable)
    monkeypatch.setattr("api.routes.listings.record_search_request", _fake_record_search_request)
    monkeypatch.setattr(
        "api.routes.listings.fetch_listing_cards_for_zone",
        _fake_fetch_listing_cards_for_zone,
    )
    monkeypatch.setattr("api.routes.listings.create_cache_record", _fake_create_cache_record)
    monkeypatch.setattr("api.routes.listings._enqueue_listings_scrape_job", _fake_enqueue)

    journey_id = uuid4()
    with TestClient(app) as client:
        response = client.post(
            f"/journeys/{journey_id}/listings/search",
            json=_payload(),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "cache"
    assert body["total_count"] == 1
    assert calls["record"] == 1
    assert calls["create_cache"] == 1
    assert calls["enqueue"] == 1


def test_listings_search_stale_cache_hit_triggers_background_revalidation(monkeypatch) -> None:
    stale_cache = {
        "status": "complete",
        "zone_fingerprint": "zone-a",
        "expires_at": datetime.now(tz=timezone.utc) + timedelta(hours=6),
        "scraped_at": datetime.now(tz=timezone.utc) - timedelta(hours=3),
    }
    calls = {"record": 0, "create_cache": 0, "enqueue": 0}

    class _Registry:
        def default_free_platforms(self):
            return ["quintoandar", "zapimoveis"]

        def resolve_names(self, names):
            return list(names)

    async def _fake_get_cache_record(_zfp, _cfg):
        return stale_cache

    async def _fake_partial(_zfp, _cfg):
        return None

    def _fake_cache_is_usable(record):
        return bool(record)

    async def _fake_record_search_request(**_kwargs):
        calls["record"] += 1

    async def _fake_fetch_listing_cards_for_zone(**_kwargs):
        return _fake_cards()

    async def _fake_create_cache_record(_zfp, _cfg):
        calls["create_cache"] += 1

    async def _fake_enqueue(**_kwargs):
        calls["enqueue"] += 1
        return uuid4()

    monkeypatch.setattr("api.routes.listings.get_platform_registry", lambda: _Registry())
    monkeypatch.setattr("api.routes.listings.get_cache_record", _fake_get_cache_record)
    monkeypatch.setattr(
        "api.routes.listings.find_partial_hit_from_overlapping_zone", _fake_partial
    )
    monkeypatch.setattr("api.routes.listings.cache_is_usable", _fake_cache_is_usable)
    monkeypatch.setattr("api.routes.listings.record_search_request", _fake_record_search_request)
    monkeypatch.setattr(
        "api.routes.listings.fetch_listing_cards_for_zone",
        _fake_fetch_listing_cards_for_zone,
    )
    monkeypatch.setattr("api.routes.listings.create_cache_record", _fake_create_cache_record)
    monkeypatch.setattr("api.routes.listings._enqueue_listings_scrape_job", _fake_enqueue)

    journey_id = uuid4()
    with TestClient(app) as client:
        response = client.post(
            f"/journeys/{journey_id}/listings/search",
            json=_payload(),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "cache"
    assert body["freshness_status"] == "stale"
    assert calls["record"] == 1
    assert calls["create_cache"] == 1
    assert calls["enqueue"] == 1


def test_listings_search_fresh_cache_hit_does_not_enqueue_revalidation(monkeypatch) -> None:
    fresh_cache = {
        "status": "complete",
        "zone_fingerprint": "zone-a",
        "expires_at": datetime.now(tz=timezone.utc) + timedelta(hours=6),
        "scraped_at": datetime.now(tz=timezone.utc) - timedelta(minutes=30),
    }
    calls = {"record": 0, "create_cache": 0, "enqueue": 0}

    class _Registry:
        def default_free_platforms(self):
            return ["quintoandar", "zapimoveis"]

        def resolve_names(self, names):
            return list(names)

    async def _fake_get_cache_record(_zfp, _cfg):
        return fresh_cache

    async def _fake_partial(_zfp, _cfg):
        return None

    def _fake_cache_is_usable(record):
        return bool(record)

    async def _fake_record_search_request(**_kwargs):
        calls["record"] += 1

    async def _fake_fetch_listing_cards_for_zone(**_kwargs):
        return _fake_cards()

    async def _fake_create_cache_record(_zfp, _cfg):
        calls["create_cache"] += 1

    async def _fake_enqueue(**_kwargs):
        calls["enqueue"] += 1
        return uuid4()

    monkeypatch.setattr("api.routes.listings.get_platform_registry", lambda: _Registry())
    monkeypatch.setattr("api.routes.listings.get_cache_record", _fake_get_cache_record)
    monkeypatch.setattr(
        "api.routes.listings.find_partial_hit_from_overlapping_zone", _fake_partial
    )
    monkeypatch.setattr("api.routes.listings.cache_is_usable", _fake_cache_is_usable)
    monkeypatch.setattr("api.routes.listings.record_search_request", _fake_record_search_request)
    monkeypatch.setattr(
        "api.routes.listings.fetch_listing_cards_for_zone",
        _fake_fetch_listing_cards_for_zone,
    )
    monkeypatch.setattr("api.routes.listings.create_cache_record", _fake_create_cache_record)
    monkeypatch.setattr("api.routes.listings._enqueue_listings_scrape_job", _fake_enqueue)

    journey_id = uuid4()
    with TestClient(app) as client:
        response = client.post(
            f"/journeys/{journey_id}/listings/search",
            json=_payload(),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "cache"
    assert body["freshness_status"] == "fresh"
    assert calls["record"] == 1
    assert calls["create_cache"] == 0
    assert calls["enqueue"] == 0
