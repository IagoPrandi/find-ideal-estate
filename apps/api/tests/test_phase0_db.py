import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

import src.core.db as db_module  # noqa: E402


def test_init_db_uses_pool_defaults(monkeypatch):
    captured: dict[str, object] = {}

    def _fake_create_async_engine(url: str, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return object()

    def _fake_sessionmaker(engine, expire_on_commit: bool):
        captured["session_engine"] = engine
        captured["expire_on_commit"] = expire_on_commit
        return object()

    monkeypatch.setattr(db_module, "create_async_engine", _fake_create_async_engine)
    monkeypatch.setattr(db_module, "async_sessionmaker", _fake_sessionmaker)

    db_module.init_db("postgresql://user:pass@localhost:5432/app")

    assert captured["url"] == "postgresql+asyncpg://user:pass@localhost:5432/app"
    assert captured["pool_pre_ping"] is True
    assert captured["pool_size"] == 20
    assert captured["max_overflow"] == 20
    assert captured["pool_timeout"] == 60
    assert captured["expire_on_commit"] is False


def test_init_db_accepts_pool_overrides(monkeypatch):
    captured: dict[str, object] = {}

    def _fake_create_async_engine(_url: str, **kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(db_module, "create_async_engine", _fake_create_async_engine)
    monkeypatch.setattr(db_module, "async_sessionmaker", lambda engine, expire_on_commit: object())

    db_module.init_db(
        "postgresql://user:pass@localhost:5432/app",
        pool_size=12,
        max_overflow=8,
        pool_timeout_seconds=45,
    )

    assert captured["pool_size"] == 12
    assert captured["max_overflow"] == 8
    assert captured["pool_timeout"] == 45