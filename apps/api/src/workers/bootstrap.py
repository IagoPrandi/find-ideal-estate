from __future__ import annotations

import os

from dramatiq.worker import Worker

from workers.queue import configure_broker
from workers.runner import parse_queue_names, start_workers, stop_workers
from workers.watchdog import start_watchdog, stop_watchdog

_running_workers: list[Worker] = []


def _should_start_in_process_workers() -> bool:
    return os.getenv("START_DRAMATIQ_WORKERS_IN_PROCESS", "0").strip().lower() in {"1", "true", "yes", "on"}


def init_workers(*, broker_kind: str, redis_url: str) -> None:
    global _running_workers
    normalized = (broker_kind or "stub").strip().lower()
    if _should_start_in_process_workers() and normalized != "stub":
        _, _running_workers = start_workers(
            broker_kind=normalized,
            redis_url=redis_url,
            queue_names=parse_queue_names(os.getenv("WORKER_QUEUES")),
        )
    else:
        configure_broker(normalized, redis_url)

        # Import handlers after broker setup so actors bind to the configured broker.
        from workers.handlers import enrichment, listings, prewarm, transport, zones  # noqa: F401

    start_watchdog()


def shutdown_workers() -> None:
    global _running_workers
    stop_watchdog()
    if _running_workers:
        stop_workers(_running_workers)
        _running_workers = []
