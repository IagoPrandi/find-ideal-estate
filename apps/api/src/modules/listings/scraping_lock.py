"""Redis-backed distributed scraping lock (M5.2).

Prevents two workers from scraping the same normalized address simultaneously.
Lock key: scraping_lock:{normalized_address}
TTL: 300 seconds (5 min) — auto-expires if worker crashes without releasing.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from core.redis import get_redis

LOCK_TTL_SECONDS = 300


def _normalize_lock_part(search_location_normalized: str | None) -> str:
    normalized = (search_location_normalized or "").strip().lower()
    return normalized or "__any__"


def _lock_key(
    search_location_normalized: str | None,
) -> str:
    normalized_part = _normalize_lock_part(search_location_normalized)
    return f"scraping_lock:{normalized_part}"


async def try_acquire_lock(
    search_location_normalized: str | None,
) -> bool:
    """
    Try to acquire the scraping lock.
    Returns True on success (NX set), False if already held.
    """
    redis = get_redis()
    key = _lock_key(search_location_normalized)
    result = await redis.set(key, "1", ex=LOCK_TTL_SECONDS, nx=True)
    return result is True


async def release_lock(
    search_location_normalized: str | None,
) -> None:
    """Release the scraping lock."""
    redis = get_redis()
    key = _lock_key(search_location_normalized)
    await redis.delete(key)


@asynccontextmanager
async def scraping_lock(
    search_location_normalized: str | None,
    timeout_seconds: float = 120.0,
) -> AsyncIterator[bool]:
    """
    Async context manager that acquires the scraping lock.

    Yields True if lock was acquired (proceed with scraping).
    Yields False if lock was not acquired. In this case, waits for
    `timeout_seconds` before returning so caller can re-open cache.

    Lock is released in `finally` even on exceptions.

    Usage::

        async with scraping_lock(search_location_normalized) as acquired:
            if not acquired:
                # another worker already scraping
                return
            ... scrape ...
    """
    acquired = await try_acquire_lock(search_location_normalized)
    if (not acquired) and timeout_seconds > 0:
        await asyncio.sleep(timeout_seconds)

    try:
        yield acquired
    finally:
        if acquired:
            await release_lock(search_location_normalized)
