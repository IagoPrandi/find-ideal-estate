from __future__ import annotations

import argparse
import asyncio
import os
import signal
import threading
import time
from collections.abc import Awaitable, Iterable
from typing import TypeVar

from core.config import get_settings
from core.container import AppContainer, reset_container, set_container
from core.db import close_db, init_db
from core.logging import configure_logging
from core.redis import close_redis, get_redis, init_redis
from dramatiq.worker import Worker
from workers.queue import QUEUE_CONCURRENCY, QUEUE_NAMES, configure_broker

T = TypeVar("T")

_runtime_loop: asyncio.AbstractEventLoop | None = None
_runtime_loop_thread: threading.Thread | None = None


def parse_queue_names(raw_value: str | None) -> list[str]:
    if not raw_value:
        return list(QUEUE_NAMES)
    names = [item.strip() for item in raw_value.split(",") if item.strip()]
    if not names:
        return list(QUEUE_NAMES)
    invalid = [name for name in names if name not in QUEUE_CONCURRENCY]
    if invalid:
        invalid_render = ", ".join(invalid)
        raise ValueError(f"Unsupported queue names: {invalid_render}")
    return names


def _env_queue_concurrency(queue_name: str, default: int) -> int:
    env_key = f"WORKER_CONCURRENCY_{queue_name.upper()}"
    raw_value = os.getenv(env_key) or os.getenv("WORKER_CONCURRENCY_DEFAULT")
    if raw_value is None:
        return default
    try:
        parsed = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{env_key} must be an integer") from exc
    return max(1, parsed)


def resolve_worker_plan(queue_names: Iterable[str]) -> list[tuple[str, int]]:
    return [
        (queue_name, _env_queue_concurrency(queue_name, QUEUE_CONCURRENCY[queue_name]))
        for queue_name in queue_names
    ]



def should_init_runtime_on_start() -> bool:
    return os.getenv("WORKER_INIT_RUNTIME_ON_START", "1").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def should_combine_worker_queues() -> bool:
    return os.getenv("WORKER_COMBINED_QUEUES", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _load_handlers() -> None:
    # Import side effect: actor declarations.
    from workers.handlers import enrichment, listings, prewarm, transport, zones  # noqa: F401


def init_worker_runtime() -> AppContainer:
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
    return container


async def init_worker_runtime_async() -> AppContainer:
    return init_worker_runtime()


def start_worker_runtime_loop() -> None:
    global _runtime_loop, _runtime_loop_thread
    if _runtime_loop is not None and _runtime_loop.is_running():
        return

    ready = threading.Event()

    def _loop_main() -> None:
        global _runtime_loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        _runtime_loop = loop
        ready.set()
        loop.run_forever()

        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()

    _runtime_loop_thread = threading.Thread(
        target=_loop_main,
        name="dramatiq-runtime-loop",
        daemon=True,
    )
    _runtime_loop_thread.start()
    ready.wait(timeout=5)
    if _runtime_loop is None or not _runtime_loop.is_running():
        raise RuntimeError("Worker runtime loop failed to start")


def run_worker_coroutine(awaitable: Awaitable[T]) -> T:
    loop = _runtime_loop
    if loop is None or not loop.is_running():
        return asyncio.run(awaitable)

    future = asyncio.run_coroutine_threadsafe(awaitable, loop)
    return future.result()


def stop_worker_runtime_loop() -> None:
    global _runtime_loop, _runtime_loop_thread
    loop = _runtime_loop
    thread = _runtime_loop_thread
    if loop is not None and loop.is_running():
        loop.call_soon_threadsafe(loop.stop)
    if thread is not None:
        thread.join(timeout=5)
    _runtime_loop = None
    _runtime_loop_thread = None


async def shutdown_worker_runtime(container: AppContainer) -> None:
    container.unwire()
    reset_container()
    await close_db()
    await close_redis()


def start_workers(
    *,
    broker_kind: str,
    redis_url: str,
    queue_names: list[str],
) -> tuple[object, list[Worker]]:
    broker = configure_broker(broker_kind, redis_url)
    _load_handlers()

    if should_combine_worker_queues():
        worker_threads = _env_queue_concurrency("combined", 1)
        worker = Worker(broker, queues=set(queue_names), worker_threads=worker_threads)
        worker.start()
        return broker, [worker]

    workers: list[Worker] = []
    for queue_name, worker_threads in resolve_worker_plan(queue_names):
        worker = Worker(broker, queues={queue_name}, worker_threads=worker_threads)
        worker.start()
        workers.append(worker)

    return broker, workers


def stop_workers(workers: list[Worker]) -> None:
    for worker in workers:
        worker.stop()
    for worker in workers:
        worker.join()


def _wait_for_shutdown() -> None:
    shutdown_event = threading.Event()

    def _set_shutdown(_signum: int, _frame) -> None:
        shutdown_event.set()

    signal.signal(signal.SIGINT, _set_shutdown)
    signal.signal(signal.SIGTERM, _set_shutdown)

    while not shutdown_event.is_set():
        time.sleep(0.5)


def main() -> None:
    configure_logging()
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Run Dramatiq workers with queue-specific concurrency"
    )
    parser.add_argument(
        "--broker",
        default=os.getenv("DRAMATIQ_BROKER", settings.dramatiq_broker),
    )
    parser.add_argument("--redis-url", default=os.getenv("REDIS_URL", settings.redis_url))
    parser.add_argument(
        "--queues",
        default=os.getenv("WORKER_QUEUES"),
        help="Comma-separated queue names. Defaults to all known queues.",
    )
    args = parser.parse_args()

    container: AppContainer | None = None
    if should_init_runtime_on_start():
        start_worker_runtime_loop()
        container = run_worker_coroutine(init_worker_runtime_async())
    queue_names = parse_queue_names(args.queues)
    _, workers = start_workers(
        broker_kind=args.broker,
        redis_url=args.redis_url,
        queue_names=queue_names,
    )

    try:
        _wait_for_shutdown()
    finally:
        stop_workers(workers)
        if container is not None:
            run_worker_coroutine(shutdown_worker_runtime(container))
            stop_worker_runtime_loop()


if __name__ == "__main__":
    main()
