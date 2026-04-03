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


def test_listings_search_without_address_cache_queues_new_scrape(monkeypatch) -> None:
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

    async def _fake_address_cache(_normalized, **_kwargs):
        return None

    def _fake_cache_is_usable(record):
        return bool(record)

    async def _fake_record_search_request(**_kwargs):
        calls["record"] += 1

    async def _fake_fetch_listing_cards_for_zone(**_kwargs):
        fetch_calls.append(_kwargs)
        return _fake_cards()

    async def _fake_create_cache_record(_normalized, **_kwargs):
        calls["create_cache"] += 1

    async def _fake_enqueue(**_kwargs):
        calls["enqueue"] += 1
        return uuid4()

    async def _fake_find_active_job(*_args, **_kwargs):
        return None

    monkeypatch.setattr("api.routes.listings.get_platform_registry", lambda: _Registry())
    monkeypatch.setattr("api.routes.listings.get_cache_record", _fake_get_cache_record)
    monkeypatch.setattr(
        "api.routes.listings.find_usable_cache_for_search_location", _fake_address_cache
    )
    monkeypatch.setattr("api.routes.listings.cache_is_usable", _fake_cache_is_usable)
    monkeypatch.setattr("api.routes.listings.record_search_request", _fake_record_search_request)
    monkeypatch.setattr(
        "api.routes.listings.fetch_listing_cards_for_zone",
        _fake_fetch_listing_cards_for_zone,
    )
    monkeypatch.setattr("api.routes.listings.create_cache_record", _fake_create_cache_record)
    monkeypatch.setattr("api.routes.listings._enqueue_listings_scrape_job", _fake_enqueue)
    monkeypatch.setattr("api.routes.listings._find_active_listings_job_id", _fake_find_active_job)

    journey_id = uuid4()
    with TestClient(app) as client:
        response = client.post(
            f"/journeys/{journey_id}/listings/search",
            json=_payload(),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "none"
    assert body["freshness_status"] == "queued_for_next_prewarm"
    assert len(fetch_calls) == 0
    assert calls["record"] == 1
    assert calls["create_cache"] == 1
    assert calls["enqueue"] == 1


def test_listings_search_old_cache_hit_remains_valid_without_revalidation(monkeypatch) -> None:
    old_cache = {
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
        return None

    async def _fake_address_cache(_normalized, **_kwargs):
        return old_cache

    def _fake_cache_is_usable(record):
        return bool(record)

    async def _fake_record_search_request(**_kwargs):
        calls["record"] += 1

    async def _fake_fetch_listing_cards_for_zone(**_kwargs):
        fetch_calls.append(_kwargs)
        return _fake_cards()

    async def _fake_create_cache_record(_normalized, **_kwargs):
        calls["create_cache"] += 1

    async def _fake_enqueue(**_kwargs):
        calls["enqueue"] += 1
        return uuid4()

    async def _fake_find_active_job(*_args, **_kwargs):
        return None

    monkeypatch.setattr("api.routes.listings.get_platform_registry", lambda: _Registry())
    monkeypatch.setattr("api.routes.listings.get_cache_record", _fake_get_cache_record)
    monkeypatch.setattr(
        "api.routes.listings.find_usable_cache_for_search_location", _fake_address_cache
    )
    monkeypatch.setattr("api.routes.listings.cache_is_usable", _fake_cache_is_usable)
    monkeypatch.setattr("api.routes.listings.record_search_request", _fake_record_search_request)
    monkeypatch.setattr(
        "api.routes.listings.fetch_listing_cards_for_zone",
        _fake_fetch_listing_cards_for_zone,
    )
    monkeypatch.setattr("api.routes.listings.create_cache_record", _fake_create_cache_record)
    monkeypatch.setattr("api.routes.listings._enqueue_listings_scrape_job", _fake_enqueue)
    monkeypatch.setattr("api.routes.listings._find_active_listings_job_id", _fake_find_active_job)

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
    assert fetch_calls[0]["observed_since"] == old_cache["created_at"]
    assert calls["record"] == 1
    assert calls["create_cache"] == 0
    assert calls["enqueue"] == 0


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
        return None

    async def _fake_address_cache(_normalized, **_kwargs):
        return fresh_cache

    def _fake_cache_is_usable(record):
        return bool(record)

    async def _fake_record_search_request(**_kwargs):
        calls["record"] += 1

    async def _fake_fetch_listing_cards_for_zone(**_kwargs):
        fetch_calls.append(_kwargs)
        return _fake_cards()

    async def _fake_create_cache_record(_normalized, **_kwargs):
        calls["create_cache"] += 1

    async def _fake_enqueue(**_kwargs):
        calls["enqueue"] += 1
        return uuid4()

    monkeypatch.setattr("api.routes.listings.get_platform_registry", lambda: _Registry())
    monkeypatch.setattr("api.routes.listings.get_cache_record", _fake_get_cache_record)
    monkeypatch.setattr(
        "api.routes.listings.find_usable_cache_for_search_location", _fake_address_cache
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

    async def _fake_get_cache_record(_normalized):
        return cache

    async def _fake_latest_search(_journey_id, _zone_fp):
        return {"search_location_normalized": _payload()["search_location_normalized"]}

    def _fake_cache_is_usable(record):
        return bool(record)

    async def _fake_fetch_listing_cards_for_zone(**kwargs):
        fetch_calls.append(kwargs)
        return _fake_cards()

    monkeypatch.setattr("api.routes.listings.get_platform_registry", lambda: _Registry())
    monkeypatch.setattr("api.routes.listings.get_cache_record", _fake_get_cache_record)
    monkeypatch.setattr("api.routes.listings.get_latest_search_request_for_zone", _fake_latest_search)
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
    assert response.json()["freshness_status"] == "fresh"
    assert response.json()["listings"][0]["lat"] == -23.5209
    assert response.json()["listings"][0]["lon"] == -46.727
    assert fetch_calls[0]["platforms"] == ["quintoandar"]
    assert fetch_calls[0]["observed_since"] == cache["created_at"]


def test_get_zone_listings_reuses_latest_search_address_cache_across_zones(monkeypatch) -> None:
    reused_cache = {
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

    async def _fake_get_cache_record(_normalized):
        return reused_cache

    async def _fake_latest_search(_journey_id, _zone_fp):
        return {"search_location_normalized": _payload()["search_location_normalized"]}

    def _fake_cache_is_usable(record):
        return bool(record)

    async def _fake_fetch_listing_cards_for_zone(**kwargs):
        fetch_calls.append(kwargs)
        return _fake_cards()

    monkeypatch.setattr("api.routes.listings.get_platform_registry", lambda: _Registry())
    monkeypatch.setattr("api.routes.listings.get_cache_record", _fake_get_cache_record)
    monkeypatch.setattr("api.routes.listings.get_latest_search_request_for_zone", _fake_latest_search)
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
    assert response.json()["freshness_status"] == "fresh"
    assert response.json()["total_count"] == 1
    assert fetch_calls[0]["zone_fingerprint"] == "zone-a"
    assert fetch_calls[0]["platforms"] == ["quintoandar"]
    assert fetch_calls[0]["observed_since"] == reused_cache["created_at"]


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

    async def _fake_get_cache_record(_normalized):
        return cache

    async def _fake_latest_search(_journey_id, _zone_fp):
        return {"search_location_normalized": _payload()["search_location_normalized"]}

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
    monkeypatch.setattr("api.routes.listings.get_latest_search_request_for_zone", _fake_latest_search)
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
    assert body["freshness_status"] == "fresh"
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

    async def _fake_address_cache(_normalized, **_kwargs):
        return None

    def _fake_cache_is_usable(record):
        return bool(record)

    async def _fake_record_search_request(**_kwargs):
        return None

    async def _fake_create_cache_record(_normalized, **_kwargs):
        return None

    async def _fake_enqueue(**_kwargs):
        return created_job_id

    async def _fake_find_active_job(*_args, **_kwargs):
        return None

    monkeypatch.setattr("api.routes.listings.get_platform_registry", lambda: _Registry())
    monkeypatch.setattr("api.routes.listings.get_cache_record", _fake_get_cache_record)
    monkeypatch.setattr(
        "api.routes.listings.find_usable_cache_for_search_location", _fake_address_cache
    )
    monkeypatch.setattr("api.routes.listings.cache_is_usable", _fake_cache_is_usable)
    monkeypatch.setattr("api.routes.listings.record_search_request", _fake_record_search_request)
    monkeypatch.setattr("api.routes.listings.create_cache_record", _fake_create_cache_record)
    monkeypatch.setattr("api.routes.listings._enqueue_listings_scrape_job", _fake_enqueue)
    monkeypatch.setattr("api.routes.listings._find_active_listings_job_id", _fake_find_active_job)

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

def test_listings_search_reuses_cache_across_different_zones_and_configs(monkeypatch) -> None:
    """
    Verify that cache is address-scoped: the same address reuses cache across zone/config.
    """
    class _Registry:
        def default_free_platforms(self):
            return ["quintoandar", "zapimoveis"]

        def resolve_names(self, names):
            return list(names)

    async def _fake_get_cache_record(_zfp, _cfg):
        return None

    async def _fake_address_cache(_normalized, **_kwargs):
        return {
            "status": "complete",
            "zone_fingerprint": "zone-a",
            "platforms_completed": ["quintoandar", "zapimoveis"],
            "expires_at": datetime.now(tz=timezone.utc) + timedelta(hours=6),
            "scraped_at": datetime.now(tz=timezone.utc),
            "created_at": datetime.now(tz=timezone.utc) - timedelta(minutes=5),
        }

    def _fake_cache_is_usable(record):
        return bool(record)

    async def _fake_record_search_request(**_kwargs):
        return None

    async def _fake_create_cache_record(_normalized, **_kwargs):
        raise AssertionError("create_cache_record should not be called on cache hit")

    async def _fake_enqueue(**_kwargs):
        raise AssertionError("_enqueue_listings_scrape_job should not be called on cache hit")

    monkeypatch.setattr("api.routes.listings.get_platform_registry", lambda: _Registry())
    monkeypatch.setattr("api.routes.listings.get_cache_record", _fake_get_cache_record)
    monkeypatch.setattr(
        "api.routes.listings.find_usable_cache_for_search_location", _fake_address_cache
    )
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
    assert body["source"] == "cache"

    payload_zone_b = _payload()
    payload_zone_b["zone_fingerprint"] = "zone-b"
    payload_zone_b["platforms"] = ["vivareal"]
    
    with TestClient(app) as client:
        response = client.post(
            f"/journeys/{journey_id}/listings/search",
            json=payload_zone_b,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "cache"




def test_get_zone_listings_no_cache_exposes_active_job_id(monkeypatch) -> None:
    active_job_id = uuid4()

    class _Registry:
        def default_free_platforms(self):
            return ["quintoandar", "vivareal", "zapimoveis"]

        def resolve_names(self, names):
            return list(names)

    async def _fake_get_cache_record(_normalized):
        return None

    async def _fake_latest_search(_journey_id, _zone_fp):
        return {"search_location_normalized": _payload()["search_location_normalized"]}

    def _fake_cache_is_usable(record):
        return bool(record)

    async def _fake_find_active_job(_journey_id, zone_fingerprint=None, search_location_normalized=None):
        del zone_fingerprint, search_location_normalized
        return active_job_id

    monkeypatch.setattr("api.routes.listings.get_platform_registry", lambda: _Registry())
    monkeypatch.setattr("api.routes.listings.get_cache_record", _fake_get_cache_record)
    monkeypatch.setattr("api.routes.listings.get_latest_search_request_for_zone", _fake_latest_search)
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


def test_listings_search_normalizes_address_before_active_job_lookup(monkeypatch) -> None:
    calls = {"record": 0}

    class _Registry:
        def default_free_platforms(self):
            return ["quintoandar", "zapimoveis"]

        def resolve_names(self, names):
            return list(names)

    async def _fake_address_cache(_normalized, **_kwargs):
        return None

    def _fake_cache_is_usable(record):
        return bool(record)

    async def _fake_record_search_request(**kwargs):
        calls["record"] += 1
        assert kwargs["search_location_normalized"] == (
            "avenida brigadeiro luis antonio, jardim paulista, sao paulo, sp"
        )

    async def _fake_find_active_job(_journey_id, zone_fingerprint=None, search_location_normalized=None):
        del zone_fingerprint
        assert search_location_normalized == (
            "avenida brigadeiro luis antonio, jardim paulista, sao paulo, sp"
        )
        return uuid4()

    async def _fake_create_cache_record(_normalized, **_kwargs):
        raise AssertionError("create_cache_record should not be called when active job is reused")

    async def _fake_enqueue(**_kwargs):
        raise AssertionError("_enqueue_listings_scrape_job should not be called when active job is reused")

    monkeypatch.setattr("api.routes.listings.get_platform_registry", lambda: _Registry())
    monkeypatch.setattr(
        "api.routes.listings.find_usable_cache_for_search_location", _fake_address_cache
    )
    monkeypatch.setattr("api.routes.listings.cache_is_usable", _fake_cache_is_usable)
    monkeypatch.setattr("api.routes.listings.record_search_request", _fake_record_search_request)
    monkeypatch.setattr("api.routes.listings._find_active_listings_job_id", _fake_find_active_job)
    monkeypatch.setattr("api.routes.listings.create_cache_record", _fake_create_cache_record)
    monkeypatch.setattr("api.routes.listings._enqueue_listings_scrape_job", _fake_enqueue)

    journey_id = uuid4()
    payload = _payload()
    payload["search_location_normalized"] = (
        "  Avenida Brigadeiro Luís Antônio,   Jardim Paulista, São Paulo, SP  "
    )

    with TestClient(app) as client:
        response = client.post(
            f"/journeys/{journey_id}/listings/search",
            json=payload,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "none"
    assert body["freshness_status"] == "queued_for_next_prewarm"
    assert calls["record"] == 1
