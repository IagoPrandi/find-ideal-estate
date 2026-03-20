from __future__ import annotations

import argparse
import os
import signal
import threading
import time
from typing import Iterable

from dramatiq.worker import Worker
from workers.queue import QUEUE_CONCURRENCY, QUEUE_NAMES, configure_broker


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


def resolve_worker_plan(queue_names: Iterable[str]) -> list[tuple[str, int]]:
    return [(queue_name, QUEUE_CONCURRENCY[queue_name]) for queue_name in queue_names]


def _load_handlers() -> None:
    # Import side effect: actor declarations.
    from workers.handlers import transport  # noqa: F401


def start_workers(
    *,
    broker_kind: str,
    redis_url: str,
    queue_names: list[str],
) -> tuple[object, list[Worker]]:
    broker = configure_broker(broker_kind, redis_url)
    _load_handlers()

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
    parser = argparse.ArgumentParser(
        description="Run Dramatiq workers with queue-specific concurrency"
    )
    parser.add_argument("--broker", default=os.getenv("DRAMATIQ_BROKER", "redis"))
    parser.add_argument("--redis-url", default=os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    parser.add_argument(
        "--queues",
        default=os.getenv("WORKER_QUEUES"),
        help="Comma-separated queue names. Defaults to all known queues.",
    )
    args = parser.parse_args()

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


if __name__ == "__main__":
    main()
