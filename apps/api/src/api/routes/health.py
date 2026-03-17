from core.db import db_healthcheck
from core.redis import redis_healthcheck
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    db_ok = await db_healthcheck()
    redis_ok = await redis_healthcheck()
    status = "ok" if db_ok and redis_ok else "degraded"
    return {
        "status": status,
        "db": "ok" if db_ok else "error",
        "redis": "ok" if redis_ok else "error",
    }
