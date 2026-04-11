import asyncio
import threading
from types import SimpleNamespace

from workers.queue import QUEUE_CONCURRENCY, QUEUE_NAMES
from workers.runner import (
    init_worker_runtime,
    parse_queue_names,
    resolve_worker_plan,
    run_worker_coroutine,
    shutdown_worker_runtime,
    start_worker_runtime_loop,
    stop_worker_runtime_loop,
    should_init_runtime_on_start,
)


def test_parse_queue_names_defaults_to_all_queues():
    assert parse_queue_names(None) == list(QUEUE_NAMES)


def test_parse_queue_names_validates_unknown_queue():
    try:
        parse_queue_names("transport,unknown")
    except ValueError as exc:
        assert "unknown" in str(exc)
    else:
        raise AssertionError("parse_queue_names must fail on unknown queue")


def test_resolve_worker_plan_uses_phase2_concurrency_table():
    plan = resolve_worker_plan(["transport", "zones", "reports"])
    assert plan == [
        ("transport", QUEUE_CONCURRENCY["transport"]),
        ("zones", QUEUE_CONCURRENCY["zones"]),
        ("reports", QUEUE_CONCURRENCY["reports"]),
    ]


def test_init_worker_runtime_initializes_db_redis_and_container(monkeypatch):
    calls: list[tuple[str, object]] = []
    fake_container = SimpleNamespace(
        config=SimpleNamespace(from_dict=lambda payload: calls.append(("config", payload))),
        redis_client=SimpleNamespace(override=lambda client: calls.append(("redis_client", client))),
    )
    fake_settings = SimpleNamespace(
        database_url="postgresql://db",
        db_pool_size=11,
        db_max_overflow=7,
        db_pool_timeout_seconds=33,
        redis_url="redis://redis/0",
        valhalla_url="http://valhalla",
        otp_url="http://otp",
    )

    monkeypatch.setattr("workers.runner.get_settings", lambda: fake_settings)
    monkeypatch.setattr(
        "workers.runner.init_db",
        lambda *args, **kwargs: calls.append(("init_db", {"args": args, "kwargs": kwargs})),
    )
    monkeypatch.setattr("workers.runner.init_redis", lambda url: calls.append(("init_redis", url)))
    monkeypatch.setattr("workers.runner.get_redis", lambda: "redis-client")
    monkeypatch.setattr("workers.runner.set_container", lambda container: calls.append(("set_container", container)))
    monkeypatch.setattr("workers.runner.AppContainer", lambda: fake_container)

    container = init_worker_runtime()

    assert container is fake_container
    assert calls[0] == (
        "init_db",
        {
            "args": ("postgresql://db",),
            "kwargs": {
                "pool_size": 11,
                "max_overflow": 7,
                "pool_timeout_seconds": 33,
            },
        },
    )
    assert ("init_redis", "redis://redis/0") in calls
    assert ("redis_client", "redis-client") in calls
    assert any(name == "config" for name, _ in calls)
    assert any(name == "set_container" for name, _ in calls)


def test_shutdown_worker_runtime_closes_resources(monkeypatch):
    calls: list[str] = []
    fake_container = SimpleNamespace(unwire=lambda: calls.append("unwire"))

    monkeypatch.setattr("workers.runner.reset_container", lambda: calls.append("reset_container"))

    async def _fake_close_db():
        calls.append("close_db")

    async def _fake_close_redis():
        calls.append("close_redis")

    monkeypatch.setattr("workers.runner.close_db", _fake_close_db)
    monkeypatch.setattr("workers.runner.close_redis", _fake_close_redis)

    asyncio.run(shutdown_worker_runtime(fake_container))

    assert calls == ["unwire", "reset_container", "close_db", "close_redis"]


def test_should_init_runtime_on_start_defaults_true(monkeypatch):
    monkeypatch.delenv("WORKER_INIT_RUNTIME_ON_START", raising=False)
    assert should_init_runtime_on_start() is True


def test_should_init_runtime_on_start_accepts_falsey_values(monkeypatch):
    monkeypatch.setenv("WORKER_INIT_RUNTIME_ON_START", "0")
    assert should_init_runtime_on_start() is False


def test_run_worker_coroutine_falls_back_to_asyncio_run():
    async def _sample() -> str:
        return "fallback"

    assert run_worker_coroutine(_sample()) == "fallback"


def test_run_worker_coroutine_uses_shared_runtime_loop():
    async def _sample() -> str:
        return threading.current_thread().name

    start_worker_runtime_loop()
    try:
        assert run_worker_coroutine(_sample()) == "dramatiq-runtime-loop"
    finally:
        stop_worker_runtime_loop()
