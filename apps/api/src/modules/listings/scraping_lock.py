"""Redis-backed distributed scraping lock (M5.2).

Prevents two workers from scraping the same zone+config simultaneously.
Lock key: scraping_lock:{fingerprint}:{config_hash}
TTL: 300 seconds (5 min) — auto-expires if worker crashes without releasing.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from core.redis import get_redis

LOCK_TTL_SECONDS = 300


def _lock_key(zone_fingerprint: str, config_hash: str) -> str:
    return f"scraping_lock:{zone_fingerprint}:{config_hash}"


async def try_acquire_lock(zone_fingerprint: str, config_hash: str) -> bool:
    """
    Try to acquire the scraping lock.
    Returns True on success (NX set), False if already held.
    """
    redis = get_redis()
    key = _lock_key(zone_fingerprint, config_hash)
    result = await redis.set(key, "1", ex=LOCK_TTL_SECONDS, nx=True)
    return result is True


async def release_lock(zone_fingerprint: str, config_hash: str) -> None:
    """Release the scraping lock."""
    redis = get_redis()
    key = _lock_key(zone_fingerprint, config_hash)
    await redis.delete(key)


@asynccontextmanager
async def scraping_lock(
    zone_fingerprint: str,
    config_hash: str,
    timeout_seconds: float = 120.0,
) -> AsyncIterator[bool]:
    """
    Async context manager that acquires the scraping lock.

    Yields True if lock was acquired (proceed with scraping).
    Yields False if lock was not acquired. In this case, waits for
    `timeout_seconds` before returning so caller can re-open cache.

    Lock is released in `finally` even on exceptions.

    Usage::

        async with scraping_lock(fp, ch) as acquired:
            if not acquired:
                # another worker already scraping
                return
            ... scrape ...
    """
    acquired = await try_acquire_lock(zone_fingerprint, config_hash)
    if (not acquired) and timeout_seconds > 0:
        await asyncio.sleep(timeout_seconds)

    try:
        yield acquired
    finally:
        if acquired:
            await release_lock(zone_fingerprint, config_hash)
