from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from modules.listings.models import ZoneCacheStatus  # noqa: E402
from workers.handlers import prewarm as prewarm_handler  # noqa: E402


def test_build_prewarm_targets_deduplicates_same_normalized_address(monkeypatch) -> None:
    async def _fake_get_prewarm_targets(*, lookback_hours: int, limit: int):
        del lookback_hours, limit
        return [
            {
                "search_location_normalized": "rua guaipa vila leopoldina sao paulo sp",
                "search_location_label": "Rua Guaipa, Vila Leopoldina, Sao Paulo, SP",
                "search_location_type": "street",
                "search_type": "rent",
                "usage_type": "residential",
                "zone_fingerprint": "zone-a",
                "demand_count": 3,
                "cache_age_hours": 24.0,
            },
            {
                "search_location_normalized": "rua guaipa vila leopoldina sao paulo sp",
                "search_location_label": "Rua Guaipa, Vila Leopoldina, Sao Paulo, SP",
                "search_location_type": "street",
                "search_type": "rent",
                "usage_type": "residential",
                "zone_fingerprint": "zone-a",
                "demand_count": 1,
                "cache_age_hours": 12.0,
            },
        ]

    class _FakeRegistry:
        def default_free_platforms(self):
            return ["quintoandar"]

    monkeypatch.setattr(prewarm_handler, "get_prewarm_targets", _fake_get_prewarm_targets)
    monkeypatch.setattr(prewarm_handler, "get_platform_registry", lambda: _FakeRegistry())

    targets = asyncio.run(prewarm_handler._build_prewarm_targets(lookback_hours=24, limit=100))

    assert len(targets) == 1
    assert targets[0].search_location_normalized == "rua guaipa vila leopoldina sao paulo sp"


def test_listings_prewarm_step_reuses_single_session_per_platform(monkeypatch) -> None:
    job_id = uuid4()
    start_calls: list[str] = []
    close_calls: list[str] = []
    scrape_calls: list[str] = []
    persist_calls: list[tuple[str, str, str]] = []
    marked_cache_ids: list[str] = []

    async def _fake_get_prewarm_targets(*, lookback_hours: int, limit: int):
        del lookback_hours, limit
        return [
            {
                "search_location_normalized": "rua guaipa vila leopoldina sao paulo sp",
                "search_location_label": "Rua Guaipa, Vila Leopoldina, Sao Paulo, SP",
                "search_location_type": "street",
                "search_type": "rent",
                "usage_type": "residential",
                "zone_fingerprint": "zone-a",
                "demand_count": 3,
                "cache_age_hours": 24.0,
            },
            {
                "search_location_normalized": "avenida paulista bela vista sao paulo sp",
                "search_location_label": "Avenida Paulista, Bela Vista, Sao Paulo, SP",
                "search_location_type": "street",
                "search_type": "rent",
                "usage_type": "residential",
                "zone_fingerprint": "zone-b",
                "demand_count": 2,
                "cache_age_hours": 36.0,
            },
        ]

    class _FakeScraper:
        def __init__(self, search_address: str, search_type: str = "rent", platform_config=None):
            del platform_config
            self.search_address = search_address
            self.search_type = search_type

        async def start_session(self) -> None:
            start_calls.append(self.search_type)

        async def close_session(self) -> None:
            close_calls.append(self.search_type)

        async def scrape_in_session(self, search_address: str):
            scrape_calls.append(search_address)
            return [
                {
                    "platform": "quintoandar",
                    "platform_listing_id": search_address,
                    "url": "https://example.org/imovel",
                    "lat": -23.55,
                    "lon": -46.63,
                    "price_brl": 3200,
                    "area_m2": 55,
                    "bedrooms": 2,
                    "bathrooms": 1,
                    "parking": 1,
                    "address": search_address,
                    "condo_fee_brl": 500,
                    "iptu_brl": 120,
                }
            ]

    class _FakeRegistry:
        def default_free_platforms(self):
            return ["quintoandar"]

        def scraper_class_for(self, platform: str):
            assert platform == "quintoandar"
            return _FakeScraper

        def scraper_config_for(self, platform: str):
            assert platform == "quintoandar"
            return {}

    async def _fake_update_job_execution_state(*_args, **_kwargs):
        return None

    async def _fake_create_cache_record(_normalized, **_kwargs):
        return uuid4()

    async def _fake_get_cache_record(_normalized):
        return {"status": ZoneCacheStatus.PENDING}

    async def _fake_transition_cache_status(*_args, **_kwargs):
        return None

    async def _fake_mark_cache_prewarmed(cache_id, **_kwargs):
        marked_cache_ids.append(str(cache_id))

    async def _fake_persist_listings(
        listings,
        platform,
        search_type,
        search_location_normalized,
    ):
        persist_calls.append((platform, search_type, search_location_normalized))
        return len(listings)

    async def _fake_publish_job_event(*_args, **_kwargs):
        return None

    async def _fake_emit_stage_progress(*_args, **_kwargs):
        return None

    async def _fake_check_cancellation(*_args, **_kwargs):
        return None

    async def _fake_record_degradation_event(*_args, **_kwargs):
        return None

    async def _fake_record_success_rate_degradation_if_needed(*_args, **_kwargs):
        return None

    @asynccontextmanager
    async def _fake_scraping_lock(_normalized, timeout_seconds=0):
        del timeout_seconds
        yield True

    monkeypatch.setattr(prewarm_handler, "get_job", lambda _job_id: asyncio.sleep(0, result=SimpleNamespace(result_ref={})))
    monkeypatch.setattr(prewarm_handler, "get_prewarm_targets", _fake_get_prewarm_targets)
    monkeypatch.setattr(prewarm_handler, "get_platform_registry", lambda: _FakeRegistry())
    monkeypatch.setattr(prewarm_handler, "update_job_execution_state", _fake_update_job_execution_state)
    monkeypatch.setattr(prewarm_handler, "create_cache_record", _fake_create_cache_record)
    monkeypatch.setattr(prewarm_handler, "get_cache_record", _fake_get_cache_record)
    monkeypatch.setattr(prewarm_handler, "transition_cache_status", _fake_transition_cache_status)
    monkeypatch.setattr(prewarm_handler, "mark_cache_prewarmed", _fake_mark_cache_prewarmed)
    monkeypatch.setattr(prewarm_handler, "_persist_listings", _fake_persist_listings)
    monkeypatch.setattr(prewarm_handler, "publish_job_event", _fake_publish_job_event)
    monkeypatch.setattr(prewarm_handler, "emit_stage_progress", _fake_emit_stage_progress)
    monkeypatch.setattr(prewarm_handler, "check_cancellation", _fake_check_cancellation)
    monkeypatch.setattr(prewarm_handler, "scraping_lock", _fake_scraping_lock)
    monkeypatch.setattr(prewarm_handler, "_record_degradation_event", _fake_record_degradation_event)
    monkeypatch.setattr(
        prewarm_handler,
        "_record_success_rate_degradation_if_needed",
        _fake_record_success_rate_degradation_if_needed,
    )

    asyncio.run(prewarm_handler._listings_prewarm_step(job_id))

    assert start_calls == ["rent"]
    assert close_calls == ["rent"]
    assert scrape_calls == [
        "Rua Guaipa, Vila Leopoldina, Sao Paulo, SP",
        "Avenida Paulista, Bela Vista, Sao Paulo, SP",
    ]
    assert persist_calls == [
        ("quintoandar", "rent", "rua guaipa vila leopoldina sao paulo sp"),
        ("quintoandar", "rent", "avenida paulista bela vista sao paulo sp"),
    ]
    assert len(marked_cache_ids) == 2


def test_enqueue_manual_listings_prewarm_deduplicates_addresses(monkeypatch) -> None:
    created_payloads: list[dict[str, object]] = []

    async def _fake_create_internal_job(*, job_type, current_stage=None, result_ref=None):
        created_payloads.append(
            {
                "job_type": job_type,
                "current_stage": current_stage,
                "result_ref": result_ref or {},
            }
        )
        return SimpleNamespace(job=SimpleNamespace(id=uuid4()))

    monkeypatch.setattr(prewarm_handler, "create_internal_job", _fake_create_internal_job)

    job_id = asyncio.run(
        prewarm_handler.enqueue_manual_listings_prewarm(
            [
                "Rua Botucatu, Vila Mariana, Sao Paulo, SP",
                "Rua Botucatu, Vila Mariana, Sao Paulo, SP",
                "Avenida Antonio Joaquim de Moura Andrade, Moema, Sao Paulo, SP",
            ]
        )
    )

    assert job_id is not None
    assert len(created_payloads) == 1
    manual_targets = created_payloads[0]["result_ref"]["manual_targets"]
    assert len(manual_targets) == 2


def test_platform_budget_defaults_to_sixty_seconds_and_caps_overrides(monkeypatch) -> None:
    monkeypatch.delenv("LISTINGS_PREWARM_MAX_ADDRESS_DURATION_SECONDS", raising=False)

    assert prewarm_handler._platform_budget_seconds({}) == 60.0
    assert prewarm_handler._platform_budget_seconds({"max_address_duration_seconds": 120}) == 60.0
    assert prewarm_handler._platform_budget_seconds({"max_address_duration_seconds": 30}) == 30.0
    assert prewarm_handler._platform_budget_seconds({"max_platform_duration_seconds": 45}) == 45.0


def test_listings_prewarm_step_resets_budget_for_each_platform_timeout(monkeypatch) -> None:
    job_id = uuid4()
    start_calls: list[str] = []
    close_calls: list[str] = []
    scrape_calls: list[str] = []
    published_events: list[tuple[str, dict[str, object]]] = []

    class _FakeScraper:
        def __init__(self, search_address: str, search_type: str = "rent", platform_config=None):
            del platform_config, search_address
            self.search_type = search_type

        async def start_session(self) -> None:
            start_calls.append(self.search_type)

        async def close_session(self) -> None:
            close_calls.append(self.search_type)

        async def scrape_in_session(self, search_address: str):
            scrape_calls.append(search_address)
            await asyncio.sleep(0.2)
            return []

    class _FakeRegistry:
        def default_free_platforms(self):
            return ["quintoandar", "zapimoveis"]

        def scraper_class_for(self, platform: str):
            assert platform in {"quintoandar", "zapimoveis"}
            return _FakeScraper

        def scraper_config_for(self, platform: str):
            assert platform in {"quintoandar", "zapimoveis"}
            return {}

    async def _fake_get_job(_job_id):
        return SimpleNamespace(
            result_ref={
                "manual_targets": [
                    {
                        "search_location_normalized": "rua botucatu vila mariana sao paulo sp",
                        "search_location_label": "Rua Botucatu, Vila Mariana, Sao Paulo, SP",
                        "search_location_type": "address",
                        "search_type": "rent",
                        "usage_type": "residential",
                        "zone_fingerprint": None,
                        "demand_count": 1,
                        "cache_age_hours": 1000000000.0,
                    }
                ],
                "max_address_duration_seconds": 0.05,
            }
        )

    async def _fake_update_job_execution_state(*_args, **_kwargs):
        return None

    async def _fake_create_cache_record(_normalized, **_kwargs):
        return uuid4()

    async def _fake_get_cache_record(_normalized):
        return {"status": ZoneCacheStatus.PENDING}

    async def _fake_transition_cache_status(*_args, **_kwargs):
        return None

    async def _fake_mark_cache_prewarmed(*_args, **_kwargs):
        return None

    async def _fake_persist_listings(
        listings,
        platform,
        search_type,
        search_location_normalized,
    ):
        del listings, platform, search_type, search_location_normalized
        return 0

    async def _fake_publish_job_event(_job_id, event_type, **kwargs):
        published_events.append((event_type, kwargs))

    async def _fake_emit_stage_progress(*_args, **_kwargs):
        return None

    async def _fake_check_cancellation(*_args, **_kwargs):
        return None

    async def _fake_record_degradation_event(*_args, **_kwargs):
        return None

    async def _fake_record_success_rate_degradation_if_needed(*_args, **_kwargs):
        return None

    @asynccontextmanager
    async def _fake_scraping_lock(_normalized, timeout_seconds=0):
        del timeout_seconds
        yield True

    monkeypatch.setattr(prewarm_handler, "get_job", _fake_get_job)
    monkeypatch.setattr(prewarm_handler, "get_platform_registry", lambda: _FakeRegistry())
    monkeypatch.setattr(prewarm_handler, "update_job_execution_state", _fake_update_job_execution_state)
    monkeypatch.setattr(prewarm_handler, "create_cache_record", _fake_create_cache_record)
    monkeypatch.setattr(prewarm_handler, "get_cache_record", _fake_get_cache_record)
    monkeypatch.setattr(prewarm_handler, "transition_cache_status", _fake_transition_cache_status)
    monkeypatch.setattr(prewarm_handler, "mark_cache_prewarmed", _fake_mark_cache_prewarmed)
    monkeypatch.setattr(prewarm_handler, "_persist_listings", _fake_persist_listings)
    monkeypatch.setattr(prewarm_handler, "publish_job_event", _fake_publish_job_event)
    monkeypatch.setattr(prewarm_handler, "emit_stage_progress", _fake_emit_stage_progress)
    monkeypatch.setattr(prewarm_handler, "check_cancellation", _fake_check_cancellation)
    monkeypatch.setattr(prewarm_handler, "scraping_lock", _fake_scraping_lock)
    monkeypatch.setattr(prewarm_handler, "_record_degradation_event", _fake_record_degradation_event)
    monkeypatch.setattr(
        prewarm_handler,
        "_record_success_rate_degradation_if_needed",
        _fake_record_success_rate_degradation_if_needed,
    )

    asyncio.run(prewarm_handler._listings_prewarm_step(job_id))

    assert start_calls == ["rent", "rent"]
    assert close_calls == ["rent", "rent"]
    assert scrape_calls == [
        "Rua Botucatu, Vila Mariana, Sao Paulo, SP",
        "Rua Botucatu, Vila Mariana, Sao Paulo, SP",
    ]
    timeout_events = [
        kwargs
        for event_type, kwargs in published_events
        if event_type == "prewarm.address.timeout"
    ]
    assert len(timeout_events) == 2
    assert all(event["payload_json"]["budget_scope"] == "platform" for event in timeout_events)


def test_process_target_cleans_up_scraping_status_on_unexpected_failure(monkeypatch) -> None:
    job_id = uuid4()
    cache_id = uuid4()
    transitions: list[tuple[object, object]] = []

    class _FakeScraper:
        async def scrape_in_session(self, _search_address: str):
            return []

    async def _fake_persist_job_context(*_args, **_kwargs):
        return None

    async def _fake_create_cache_record(_normalized, **_kwargs):
        return cache_id

    async def _fake_get_cache_record(_normalized):
        return {"status": ZoneCacheStatus.PENDING}

    async def _fake_transition_cache_status(_cache_id, from_status, to_status, **_kwargs):
        transitions.append((from_status, to_status))

    async def _fake_publish_job_event(*_args, **_kwargs):
        return None

    async def _fake_check_cancellation(*_args, **_kwargs):
        return None

    async def _fake_persist_listings(*_args, **_kwargs):
        return 1

    async def _fake_mark_cache_prewarmed(*_args, **_kwargs):
        raise RuntimeError("post scrape exploded")

    async def _fake_record_success_rate_degradation_if_needed(*_args, **_kwargs):
        return None

    @asynccontextmanager
    async def _fake_scraping_lock(_normalized, timeout_seconds=0):
        del timeout_seconds
        yield True

    monkeypatch.setattr(prewarm_handler, "_persist_job_context", _fake_persist_job_context)
    monkeypatch.setattr(prewarm_handler, "create_cache_record", _fake_create_cache_record)
    monkeypatch.setattr(prewarm_handler, "get_cache_record", _fake_get_cache_record)
    monkeypatch.setattr(prewarm_handler, "transition_cache_status", _fake_transition_cache_status)
    monkeypatch.setattr(prewarm_handler, "publish_job_event", _fake_publish_job_event)
    monkeypatch.setattr(prewarm_handler, "check_cancellation", _fake_check_cancellation)
    monkeypatch.setattr(prewarm_handler, "_persist_listings", _fake_persist_listings)
    monkeypatch.setattr(prewarm_handler, "mark_cache_prewarmed", _fake_mark_cache_prewarmed)
    monkeypatch.setattr(
        prewarm_handler,
        "_record_success_rate_degradation_if_needed",
        _fake_record_success_rate_degradation_if_needed,
    )
    monkeypatch.setattr(prewarm_handler, "scraping_lock", _fake_scraping_lock)

    target = prewarm_handler.PrewarmTarget(
        search_location_normalized="rua botucatu, vila mariana, sao paulo, sp",
        search_location_label="Rua Botucatu, Vila Mariana, Sao Paulo, SP",
        search_location_type="address",
        search_type="rent",
        usage_type="residential",
        zone_fingerprint=None,
        platforms=("quintoandar",),
        demand_count=1,
        cache_age_hours=1.0,
    )

    with pytest.raises(RuntimeError, match="post scrape exploded"):
        asyncio.run(
            prewarm_handler._process_target(
                job_id=job_id,
                ctx={},
                target=target,
                platform_sessions={("quintoandar", "rent"): _FakeScraper()},
            )
        )

    assert transitions == [
        (ZoneCacheStatus.PENDING, ZoneCacheStatus.SCRAPING),
        (ZoneCacheStatus.SCRAPING, ZoneCacheStatus.COMPLETE),
        (ZoneCacheStatus.SCRAPING, ZoneCacheStatus.CANCELLED_PARTIAL),
    ]


def test_listings_prewarm_actor_initializes_and_shuts_down_runtime(monkeypatch) -> None:
    runtime_calls: list[object] = []
    job_id = uuid4()

    monkeypatch.setattr(prewarm_handler, "run_job_with_retry", lambda *args, **kwargs: asyncio.sleep(0))
    monkeypatch.setattr("workers.runner.init_worker_runtime", lambda: runtime_calls.append("init") or object())

    async def _fake_shutdown_worker_runtime(container):
        runtime_calls.append(("shutdown", container is not None))

    monkeypatch.setattr("workers.runner.shutdown_worker_runtime", _fake_shutdown_worker_runtime)

    prewarm_handler.listings_prewarm_actor(str(job_id))

    assert runtime_calls[0] == "init"
    assert runtime_calls[1] == ("shutdown", True)
