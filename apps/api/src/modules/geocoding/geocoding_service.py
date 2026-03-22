from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

import httpx
from core.db import get_engine
from core.redis import get_redis
from sqlalchemy import text

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 86_400  # 24h
_RATE_LIMIT_WINDOW_SECONDS = 60
_RATE_LIMIT_MAX = 30
_DEBOUNCE_MS = 300


def _normalize_query(q: str) -> str:
    return q.strip().lower()


def _cache_key(normalized: str) -> str:
    digest = hashlib.sha256(normalized.encode()).hexdigest()[:16]
    return f"geocode:v1:{digest}"


def _ratelimit_key(session_id: str) -> str:
    window = int(time.time()) // _RATE_LIMIT_WINDOW_SECONDS
    return f"geocode_rl:{session_id}:{window}"


def _debounce_key(session_id: str) -> str:
    return f"geocode_db:{session_id}"


async def _check_rate_limit(session_id: str) -> bool:
    """Return True if request is allowed, False if rate-limited."""
    redis = get_redis()
    key = _ratelimit_key(session_id)
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, _RATE_LIMIT_WINDOW_SECONDS + 1)
    return int(count) <= _RATE_LIMIT_MAX


async def _write_ledger(
    *,
    session_id: str,
    cache_hit: bool,
    status: str,
) -> None:
    try:
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO external_usage_ledger
                        (provider, operation_type, session_id, cache_hit, status)
                    VALUES
                        ('mapbox', 'geocode', :session_id, :cache_hit, :status)
                    """
                ),
                {"session_id": session_id, "cache_hit": cache_hit, "status": status},
            )
    except Exception:
        logger.exception("failed to write external_usage_ledger entry")


async def geocode(
    q: str,
    session_id: str,
    mapbox_token: str,
) -> dict[str, Any]:
    """
    Proxy a geocoding request to the Mapbox Search Box API.

    Returns a dict with keys:
      - suggestions: list of suggestion objects from Mapbox
      - cache_hit: bool
    Raises ValueError on rate limit.
    """
    normalized = _normalize_query(q)
    redis = get_redis()

    # 1. Debounce: if last call from this session was < 300ms ago for same query,
    #    return cached result immediately.
    debounce_key = _debounce_key(session_id)
    last_db_entry = await redis.get(debounce_key)
    if last_db_entry is not None:
        db_data = json.loads(last_db_entry)
        elapsed_ms = (time.time() - db_data["ts"]) * 1000
        if elapsed_ms < _DEBOUNCE_MS and db_data.get("q") == normalized:
            cached = await redis.get(_cache_key(normalized))
            if cached is not None:
                await _write_ledger(session_id=session_id, cache_hit=True, status="debounced")
                result = json.loads(cached)
                result["cache_hit"] = True
                return result

    # 2. Check cache.
    cache_key = _cache_key(normalized)
    cached = await redis.get(cache_key)
    if cached is not None:
        await _write_ledger(session_id=session_id, cache_hit=True, status="cached")
        result = json.loads(cached)
        result["cache_hit"] = True
        return result

    # 3. Rate limit (only counted for real API calls).
    allowed = await _check_rate_limit(session_id)
    if not allowed:
        await _write_ledger(session_id=session_id, cache_hit=False, status="rate_limited")
        raise ValueError("rate_limit_exceeded")

    # 4. Call Mapbox Search Box API.
    url = "https://api.mapbox.com/search/searchbox/v1/suggest"
    params = {
        "q": q,
        "access_token": mapbox_token,
        "session_token": session_id,
        "language": "pt",
        "country": "BR",
        "limit": 10,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    suggestions = data.get("suggestions", [])
    payload = {"suggestions": suggestions}

    # 5. Store in cache.
    await redis.set(cache_key, json.dumps(payload), ex=_CACHE_TTL_SECONDS)

    # 6. Update debounce tracker.
    await redis.set(
        debounce_key,
        json.dumps({"q": normalized, "ts": time.time()}),
        ex=2,  # 2s is plenty for debounce window
    )

    await _write_ledger(session_id=session_id, cache_hit=False, status="ok")

    payload["cache_hit"] = False
    return payload
