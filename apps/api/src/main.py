import logging
from contextlib import asynccontextmanager

from api.routes.geocode import router as geocode_router
from api.routes.health import router as health_router
from api.routes.jobs import router as jobs_router
from api.routes.journeys import router as journeys_router
from api.routes.listings import router as listings_router
from api.routes.transport import router as transport_router
from api.routes.zones import router as zones_router
from core.config import ConfigurationError, get_settings
from core.container import AppContainer, reset_container, set_container
from core.db import close_db, init_db
from core.logging import configure_logging
from core.middleware import request_id_middleware
from core.redis import close_redis, get_redis, init_redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from workers.bootstrap import init_workers, shutdown_workers

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    settings = get_settings()
    init_db(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout_seconds=settings.db_pool_timeout_seconds,
    )
    init_redis(settings.redis_url)

    container = AppContainer()
    container.config.from_dict(
        {
            "valhalla_url": settings.valhalla_url,
            "otp_url": settings.otp_url,
            "http_timeout_seconds": 5.0,
        }
    )
    container.redis_client.override(get_redis())
    set_container(container)

    init_workers(broker_kind=settings.dramatiq_broker, redis_url=settings.redis_url)
    logger.info("application started")
    try:
        yield
    finally:
        shutdown_workers()
        container.unwire()
        reset_container()
        await close_db()
        await close_redis()
        logger.info("application stopped")


app = FastAPI(title="Find Ideal Estate API", version="0.1.0", lifespan=lifespan)
app.middleware("http")(request_id_middleware)

# CORS must allow credentials because frontend uses cookie-backed anonymous sessions.
_cors_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(geocode_router)
app.include_router(transport_router)
app.include_router(journeys_router)
app.include_router(jobs_router)
app.include_router(listings_router)
app.include_router(zones_router)

if __name__ == "__main__":
    try:
        get_settings()
    except ConfigurationError as exc:
        raise SystemExit(f"ConfigurationError: {exc}") from exc
