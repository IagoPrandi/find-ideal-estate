from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _normalize_database_url(database_url: str) -> str:
    def _normalize_asyncpg_query(url: str) -> str:
        parts = urlsplit(url)
        query_items = parse_qsl(parts.query, keep_blank_values=True)
        normalized_items: list[tuple[str, str]] = []
        for key, value in query_items:
            normalized_items.append(("ssl" if key == "sslmode" else key, value))
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(normalized_items), parts.fragment))

    if database_url.startswith("postgresql+asyncpg://"):
        return _normalize_asyncpg_query(database_url)
    if database_url.startswith("postgresql://"):
        return _normalize_asyncpg_query(database_url.replace("postgresql://", "postgresql+asyncpg://", 1))
    if database_url.startswith("postgres://"):
        return _normalize_asyncpg_query(database_url.replace("postgres://", "postgresql+asyncpg://", 1))
    return database_url


def init_db(
    database_url: str,
    *,
    pool_size: int = 20,
    max_overflow: int = 20,
    pool_timeout_seconds: int = 60,
) -> None:
    global _engine, _sessionmaker
    _engine = create_async_engine(
        _normalize_database_url(database_url),
        pool_pre_ping=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout_seconds,
    )
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)


def get_engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("Database engine is not initialized")
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        raise RuntimeError("Database sessionmaker is not initialized")
    return _sessionmaker


async def db_healthcheck() -> bool:
    if _engine is None:
        return False
    try:
        async with _engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def close_db() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
    _sessionmaker = None
