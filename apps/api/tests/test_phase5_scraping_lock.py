from __future__ import annotations

import asyncio
import importlib
import os
import sys
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from core.db import close_db, get_engine, init_db  # noqa: E402
from core.redis import close_redis, init_redis, redis_healthcheck  # noqa: E402
from src.modules.listings.dedup import (  # noqa: E402
    compute_property_fingerprint,
    upsert_property_and_ad,
)
from src.modules.listings.models import ZoneCacheStatus  # noqa: E402
from src.workers.handlers import listings as listings_handler  # noqa: E402

lock_module = importlib.import_module("src.modules.listings.scraping_lock")
scraping_lock = lock_module.scraping_lock

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/find_ideal_estate")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")


class _FakeRedis:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}
        self._mutex = asyncio.Lock()

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False):
        del ex  # TTL is not needed for this unit test fake.
        async with self._mutex:
            if nx and key in self._store:
                return None
            self._store[key] = value
            return True

    async def delete(self, key: str) -> None:
        async with self._mutex:
            self._store.pop(key, None)


async def _run_single_writer_contention() -> int:
    writes = 0

    async def _worker() -> bool:
        nonlocal writes
        async with scraping_lock("zone-fp", "cfg-hash", timeout_seconds=0.05) as acquired:
            if not acquired:
                return False
            writes += 1
            await asyncio.sleep(0.03)
            return True

    await asyncio.gather(_worker(), _worker())
    return writes


def test_scraping_lock_allows_only_one_writer(monkeypatch) -> None:
    fake_redis = _FakeRedis()
    monkeypatch.setattr(lock_module, "get_redis", lambda: fake_redis)

    writes = asyncio.run(_run_single_writer_contention())

    assert writes == 1


def test_listings_step_reopens_cache_after_lock_contention(monkeypatch) -> None:
    job_id = uuid4()
    stage_messages: list[str] = []
    published_events: list[tuple[str, dict[str, object]]] = []

    async def _fake_load_job_context(_job_id):
        return {
            "zone_fingerprint": "zone-fp",
            "search_address": "Avenida Paulista, 1000",
            "search_type": "rent",
            "usage_type": "residential",
            "platforms": ["quintoandar"],
        }

    async def _fake_emit_stage_progress(_job_id, stage, progress_percent, message):
        del stage, progress_percent
        stage_messages.append(message)

    async def _fake_publish_job_event(_job_id, event_type, **kwargs):
        published_events.append((event_type, kwargs))

    async def _fake_get_cache_record(_zone_fingerprint, _config_hash):
        return {
            "status": ZoneCacheStatus.COMPLETE,
            "zone_fingerprint": "zone-fp",
        }

    @asynccontextmanager
    async def _fake_scraping_lock(_zone_fingerprint, _config_hash, timeout_seconds=120.0):
        del timeout_seconds
        yield False

    monkeypatch.setattr(listings_handler, "_load_job_context", _fake_load_job_context)
    monkeypatch.setattr(listings_handler, "emit_stage_progress", _fake_emit_stage_progress)
    monkeypatch.setattr(listings_handler, "publish_job_event", _fake_publish_job_event)
    monkeypatch.setattr(listings_handler, "get_cache_record", _fake_get_cache_record)
    monkeypatch.setattr(listings_handler, "scraping_lock", _fake_scraping_lock)
    monkeypatch.setattr(listings_handler, "check_cancellation", lambda _job_id: asyncio.sleep(0))

    asyncio.run(listings_handler._listings_scrape_step(job_id))

    assert any("Acquiring scraping lock" in msg for msg in stage_messages)
    assert any("Listings available after waiting for lock" in msg for msg in stage_messages)
    assert len(published_events) == 1
    assert published_events[0][0] == "listings.preliminary.ready"
    assert published_events[0][1]["payload_json"]["source"] == "cache_reopen"


async def _ensure_phase5_listing_schema() -> bool:
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                """
                SELECT
                    to_regclass('public.properties') IS NOT NULL
                    AND to_regclass('public.listing_ads') IS NOT NULL
                    AND to_regclass('public.listing_snapshots') IS NOT NULL
                """
            )
        )
        return bool(result.scalar())


async def _cleanup_listing_test_rows(*, fingerprint: str, platform_listing_id: str) -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                DELETE FROM listing_snapshots
                WHERE listing_ad_id IN (
                    SELECT id FROM listing_ads WHERE platform_listing_id = :plid
                )
                """
            ),
            {"plid": platform_listing_id},
        )
        await conn.execute(
            text("DELETE FROM listing_ads WHERE platform_listing_id = :plid"),
            {"plid": platform_listing_id},
        )
        await conn.execute(
            text("DELETE FROM properties WHERE fingerprint = :fp"),
            {"fp": fingerprint},
        )


async def _count_listing_rows(
    *,
    fingerprint: str,
    platform_listing_id: str,
) -> tuple[int, int, int]:
    engine = get_engine()
    async with engine.connect() as conn:
        prop_count = await conn.execute(
            text("SELECT count(*) FROM properties WHERE fingerprint = :fp"),
            {"fp": fingerprint},
        )
        ad_count = await conn.execute(
            text("SELECT count(*) FROM listing_ads WHERE platform_listing_id = :plid"),
            {"plid": platform_listing_id},
        )
        snapshot_count = await conn.execute(
            text(
                """
                SELECT count(*)
                FROM listing_snapshots ls
                JOIN listing_ads la ON la.id = ls.listing_ad_id
                WHERE la.platform_listing_id = :plid
                """
            ),
            {"plid": platform_listing_id},
        )
        return (
            int(prop_count.scalar_one()),
            int(ad_count.scalar_one()),
            int(snapshot_count.scalar_one()),
        )


@pytest.mark.anyio
async def test_scraping_lock_concurrency_has_no_duplicate_db_writes() -> None:
    init_db(os.environ["DATABASE_URL"])
    init_redis(os.environ["REDIS_URL"])

    zone_fingerprint = f"zone-m52-{uuid4().hex[:8]}"
    config_hash = "cfg-m52"
    platform_listing_id = f"m52-lock-{uuid4().hex[:10]}"

    fingerprint = compute_property_fingerprint(
        address_normalized="Rua Teste Lock, 100",
        lat=-23.5505,
        lon=-46.6333,
        area_m2=70,
        bedrooms=2,
    )
    schema_ready = False

    async def _contending_writer() -> bool:
        async with scraping_lock(zone_fingerprint, config_hash, timeout_seconds=0.05) as acquired:
            if not acquired:
                return False
            await upsert_property_and_ad(
                fingerprint=fingerprint,
                address_normalized="Rua Teste Lock, 100",
                lat=-23.5505,
                lon=-46.6333,
                area_m2=70,
                bedrooms=2,
                bathrooms=1,
                parking=1,
                usage_type="residential",
                platform="quintoandar",
                platform_listing_id=platform_listing_id,
                url="https://example.org/imovel/m52",
                advertised_usage_type="rent",
                price=Decimal("3000"),
                condo_fee=Decimal("500"),
                iptu=Decimal("120"),
                raw_payload={"m5_2_test": True},
            )
            await asyncio.sleep(0.03)
            return True

    try:
        schema_ready = await _ensure_phase5_listing_schema()
        if not schema_ready:
            pytest.skip("Phase 5 schema not migrated. Run alembic upgrade head.")
        if not await redis_healthcheck():
            pytest.skip("Redis is unavailable for M5.2 lock integration test.")

        await _cleanup_listing_test_rows(
            fingerprint=fingerprint,
            platform_listing_id=platform_listing_id,
        )

        outcomes = await asyncio.gather(_contending_writer(), _contending_writer())
        assert sum(1 for ok in outcomes if ok) == 1

        prop_count, ad_count, snapshot_count = await _count_listing_rows(
            fingerprint=fingerprint,
            platform_listing_id=platform_listing_id,
        )
        assert prop_count == 1
        assert ad_count == 1
        assert snapshot_count == 1
    finally:
        if schema_ready:
            await _cleanup_listing_test_rows(
                fingerprint=fingerprint,
                platform_listing_id=platform_listing_id,
            )
        await close_redis()
        await close_db()
