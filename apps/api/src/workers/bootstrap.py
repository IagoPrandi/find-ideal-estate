from __future__ import annotations

from workers.queue import configure_broker
from workers.watchdog import start_watchdog, stop_watchdog


def init_workers(*, broker_kind: str, redis_url: str) -> None:
    normalized = (broker_kind or "stub").strip().lower()
    configure_broker(normalized, redis_url)

    # Import handlers after broker setup so actors bind to the configured broker.
    from workers.handlers import enrichment, transport, zones  # noqa: F401

    start_watchdog()


def shutdown_workers() -> None:
    stop_watchdog()
