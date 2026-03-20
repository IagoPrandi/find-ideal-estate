from redis.asyncio import Redis

_redis: Redis | None = None


def init_redis(redis_url: str) -> None:
    global _redis
    _redis = Redis.from_url(redis_url, decode_responses=True)


def get_redis() -> Redis:
    if _redis is None:
        raise RuntimeError("Redis client is not initialized")
    return _redis


async def redis_healthcheck() -> bool:
    if _redis is None:
        return False
    try:
        await _redis.execute_command("PING")  # type: ignore[no-untyped-call]
        return True
    except Exception:
        return False


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
