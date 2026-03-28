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
            "lat": -23.5209,
            "lon": -46.7270,
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
        "platforms_completed": ["quintoandar"],
        "expires_at": datetime.now(tz=timezone.utc) + timedelta(hours=6),
        "scraped_at": datetime.now(tz=timezone.utc),
        "created_at": datetime.now(tz=timezone.utc) - timedelta(minutes=2),
    }
    calls = {"record": 0, "create_cache": 0, "enqueue": 0}
    fetch_calls: list[dict[str, object]] = []

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
        fetch_calls.append(_kwargs)
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
    assert fetch_calls[0]["platforms"] == ["quintoandar"]
    assert fetch_calls[0]["observed_since"] == cache_partial["created_at"]
    assert calls["record"] == 1
    assert calls["create_cache"] == 1
    assert calls["enqueue"] == 1


def test_listings_search_stale_cache_hit_triggers_background_revalidation(monkeypatch) -> None:
    stale_cache = {
        "status": "complete",
        "zone_fingerprint": "zone-a",
        "platforms_completed": ["quintoandar", "zapimoveis"],
        "expires_at": datetime.now(tz=timezone.utc) + timedelta(hours=6),
        "scraped_at": datetime.now(tz=timezone.utc) - timedelta(hours=3),
        "created_at": datetime.now(tz=timezone.utc) - timedelta(hours=3, minutes=5),
    }
    calls = {"record": 0, "create_cache": 0, "enqueue": 0}
    fetch_calls: list[dict[str, object]] = []

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
        fetch_calls.append(_kwargs)
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
    assert fetch_calls[0]["platforms"] == ["quintoandar", "zapimoveis"]
    assert fetch_calls[0]["observed_since"] == stale_cache["created_at"]
    assert calls["record"] == 1
    assert calls["create_cache"] == 1
    assert calls["enqueue"] == 1


def test_listings_search_fresh_cache_hit_does_not_enqueue_revalidation(monkeypatch) -> None:
    fresh_cache = {
        "status": "complete",
        "zone_fingerprint": "zone-a",
        "platforms_completed": ["quintoandar", "zapimoveis"],
        "expires_at": datetime.now(tz=timezone.utc) + timedelta(hours=6),
        "scraped_at": datetime.now(tz=timezone.utc) - timedelta(minutes=30),
        "created_at": datetime.now(tz=timezone.utc) - timedelta(minutes=35),
    }
    calls = {"record": 0, "create_cache": 0, "enqueue": 0}
    fetch_calls: list[dict[str, object]] = []

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
        fetch_calls.append(_kwargs)
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
    assert fetch_calls[0]["platforms"] == ["quintoandar", "zapimoveis"]
    assert fetch_calls[0]["observed_since"] == fresh_cache["created_at"]
    assert calls["record"] == 1
    assert calls["create_cache"] == 0
    assert calls["enqueue"] == 0


def test_get_zone_listings_uses_cache_completed_platforms(monkeypatch) -> None:
    cache = {
        "status": "partial",
        "zone_fingerprint": "zone-a",
        "platforms_completed": ["quintoandar"],
        "platforms_failed": ["vivareal", "zapimoveis"],
        "expires_at": datetime.now(tz=timezone.utc) + timedelta(hours=6),
        "scraped_at": datetime.now(tz=timezone.utc),
        "created_at": datetime.now(tz=timezone.utc) - timedelta(minutes=4),
    }
    fetch_calls: list[dict[str, object]] = []

    class _Registry:
        def default_free_platforms(self):
            return ["quintoandar", "vivareal", "zapimoveis"]

        def resolve_names(self, names):
            return list(names)

    async def _fake_get_cache_record(_zfp, _cfg):
        return cache

    def _fake_cache_is_usable(record):
        return bool(record)

    async def _fake_fetch_listing_cards_for_zone(**kwargs):
        fetch_calls.append(kwargs)
        return _fake_cards()

    monkeypatch.setattr("api.routes.listings.get_platform_registry", lambda: _Registry())
    monkeypatch.setattr("api.routes.listings.get_cache_record", _fake_get_cache_record)
    monkeypatch.setattr("api.routes.listings.cache_is_usable", _fake_cache_is_usable)
    monkeypatch.setattr(
        "api.routes.listings.fetch_listing_cards_for_zone",
        _fake_fetch_listing_cards_for_zone,
    )

    journey_id = uuid4()
    with TestClient(app) as client:
        response = client.get(
            f"/journeys/{journey_id}/zones/zone-a/listings?search_type=rent&usage_type=residential"
        )

    assert response.status_code == 200
    assert response.json()["total_count"] == 1
    assert response.json()["listings"][0]["lat"] == -23.5209
    assert response.json()["listings"][0]["lon"] == -46.727
    assert fetch_calls[0]["platforms"] == ["quintoandar"]
    assert fetch_calls[0]["observed_since"] == cache["created_at"]


def test_get_zone_listings_falls_back_to_overlapping_partial_cache(monkeypatch) -> None:
    partial_cache = {
        "status": "partial",
        "zone_fingerprint": "zone-overlap",
        "platforms_completed": ["quintoandar"],
        "platforms_failed": ["vivareal", "zapimoveis"],
        "expires_at": datetime.now(tz=timezone.utc) + timedelta(hours=6),
        "scraped_at": datetime.now(tz=timezone.utc) - timedelta(minutes=10),
        "created_at": datetime.now(tz=timezone.utc) - timedelta(minutes=12),
    }
    fetch_calls: list[dict[str, object]] = []

    class _Registry:
        def default_free_platforms(self):
            return ["quintoandar", "vivareal", "zapimoveis"]

        def resolve_names(self, names):
            return list(names)

    async def _fake_get_cache_record(_zfp, _cfg):
        return None

    async def _fake_find_partial_hit(_zfp, _cfg):
        return partial_cache

    def _fake_cache_is_usable(record):
        return bool(record)

    async def _fake_fetch_listing_cards_for_zone(**kwargs):
        fetch_calls.append(kwargs)
        return _fake_cards()

    monkeypatch.setattr("api.routes.listings.get_platform_registry", lambda: _Registry())
    monkeypatch.setattr("api.routes.listings.get_cache_record", _fake_get_cache_record)
    monkeypatch.setattr(
        "api.routes.listings.find_partial_hit_from_overlapping_zone",
        _fake_find_partial_hit,
    )
    monkeypatch.setattr("api.routes.listings.cache_is_usable", _fake_cache_is_usable)
    monkeypatch.setattr(
        "api.routes.listings.fetch_listing_cards_for_zone",
        _fake_fetch_listing_cards_for_zone,
    )

    journey_id = uuid4()
    with TestClient(app) as client:
        response = client.get(
            f"/journeys/{journey_id}/zones/zone-a/listings?search_type=rent&usage_type=residential"
        )

    assert response.status_code == 200
    assert response.json()["source"] == "cache"
    assert response.json()["total_count"] == 1
    assert fetch_calls[0]["zone_fingerprint"] == "zone-a"
    assert fetch_calls[0]["platforms"] == ["quintoandar"]
    assert fetch_calls[0]["observed_since"] == partial_cache["created_at"]


def test_get_zone_listings_supports_all_spatial_scope(monkeypatch) -> None:
    cache = {
        "status": "complete",
        "zone_fingerprint": "zone-a",
        "platforms_completed": ["quintoandar", "zapimoveis"],
        "platforms_failed": [],
        "expires_at": datetime.now(tz=timezone.utc) + timedelta(hours=6),
        "scraped_at": datetime.now(tz=timezone.utc),
        "created_at": datetime.now(tz=timezone.utc) - timedelta(minutes=4),
    }
    fetch_calls: list[dict[str, object]] = []

    class _Registry:
        def default_free_platforms(self):
            return ["quintoandar", "zapimoveis"]

        def resolve_names(self, names):
            return list(names)

    async def _fake_get_cache_record(_zfp, _cfg):
        return cache

    def _fake_cache_is_usable(record):
        return bool(record)

    async def _fake_fetch_listing_cards_for_zone(**kwargs):
        fetch_calls.append(kwargs)
        cards = _fake_cards()
        cards[0]["inside_zone"] = False
        cards[0]["has_coordinates"] = False
        cards[0]["lat"] = None
        cards[0]["lon"] = None
        return cards

    monkeypatch.setattr("api.routes.listings.get_platform_registry", lambda: _Registry())
    monkeypatch.setattr("api.routes.listings.get_cache_record", _fake_get_cache_record)
    monkeypatch.setattr("api.routes.listings.cache_is_usable", _fake_cache_is_usable)
    monkeypatch.setattr(
        "api.routes.listings.fetch_listing_cards_for_zone",
        _fake_fetch_listing_cards_for_zone,
    )

    journey_id = uuid4()
    with TestClient(app) as client:
        response = client.get(
            f"/journeys/{journey_id}/zones/zone-a/listings?search_type=rent&usage_type=residential&spatial_scope=all"
        )

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 1
    assert body["listings"][0]["inside_zone"] is False
    assert body["listings"][0]["has_coordinates"] is False
    assert fetch_calls[0]["spatial_scope"] == "all"


def test_listings_search_cache_miss_returns_job_id(monkeypatch) -> None:
    created_job_id = uuid4()

    class _Registry:
        def default_free_platforms(self):
            return ["quintoandar", "vivareal", "zapimoveis"]

        def resolve_names(self, names):
            return list(names)

    async def _fake_get_cache_record(_zfp, _cfg):
        return None

    async def _fake_partial(_zfp, _cfg):
        return None

    def _fake_cache_is_usable(record):
        return bool(record)

    async def _fake_record_search_request(**_kwargs):
        return None

    async def _fake_create_cache_record(_zfp, _cfg):
        return None

    async def _fake_enqueue(**_kwargs):
        return created_job_id

    monkeypatch.setattr("api.routes.listings.get_platform_registry", lambda: _Registry())
    monkeypatch.setattr("api.routes.listings.get_cache_record", _fake_get_cache_record)
    monkeypatch.setattr("api.routes.listings.find_partial_hit_from_overlapping_zone", _fake_partial)
    monkeypatch.setattr("api.routes.listings.cache_is_usable", _fake_cache_is_usable)
    monkeypatch.setattr("api.routes.listings.record_search_request", _fake_record_search_request)
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
    assert body["source"] == "none"
    assert body["job_id"] == str(created_job_id)
    assert body["freshness_status"] == "queued_for_next_prewarm"


def test_get_zone_listings_no_cache_exposes_active_job_id(monkeypatch) -> None:
    active_job_id = uuid4()

    class _Registry:
        def default_free_platforms(self):
            return ["quintoandar", "vivareal", "zapimoveis"]

        def resolve_names(self, names):
            return list(names)

    async def _fake_get_cache_record(_zfp, _cfg):
        return None

    async def _fake_partial(_zfp, _cfg):
        return None

    def _fake_cache_is_usable(record):
        return bool(record)

    async def _fake_find_active_job(_journey_id, _zone_fp):
        return active_job_id

    monkeypatch.setattr("api.routes.listings.get_platform_registry", lambda: _Registry())
    monkeypatch.setattr("api.routes.listings.get_cache_record", _fake_get_cache_record)
    monkeypatch.setattr("api.routes.listings.find_partial_hit_from_overlapping_zone", _fake_partial)
    monkeypatch.setattr("api.routes.listings.cache_is_usable", _fake_cache_is_usable)
    monkeypatch.setattr("api.routes.listings._find_active_listings_job_id", _fake_find_active_job)

    journey_id = uuid4()
    with TestClient(app) as client:
        response = client.get(
            f"/journeys/{journey_id}/zones/zone-a/listings?search_type=rent&usage_type=residential"
        )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "none"
    assert body["job_id"] == str(active_job_id)
    assert body["freshness_status"] == "no_cache"
