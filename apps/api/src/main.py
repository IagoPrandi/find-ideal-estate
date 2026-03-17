import logging
from contextlib import asynccontextmanager

from api.routes.health import router as health_router
from core.config import ConfigurationError, get_settings
from core.db import close_db, init_db
from core.logging import configure_logging
from core.middleware import request_id_middleware
from core.redis import close_redis, init_redis
from fastapi import FastAPI

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    settings = get_settings()
    init_db(settings.database_url)
    init_redis(settings.redis_url)
    logger.info("application started")
    try:
        yield
    finally:
        await close_db()
        await close_redis()
        logger.info("application stopped")


app = FastAPI(title="Find Ideal Estate API", version="0.1.0", lifespan=lifespan)
app.middleware("http")(request_id_middleware)
app.include_router(health_router)


if __name__ == "__main__":
    try:
        get_settings()
    except ConfigurationError as exc:
        raise SystemExit(f"ConfigurationError: {exc}") from exc
