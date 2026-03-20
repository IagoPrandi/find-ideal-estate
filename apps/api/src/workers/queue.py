from __future__ import annotations

from enum import IntEnum
from typing import Any

import dramatiq
from dramatiq.brokers.stub import StubBroker

QUEUE_TRANSPORT = "transport"
QUEUE_ZONES = "zones"
QUEUE_ENRICHMENT = "enrichment"
QUEUE_SCRAPE_BROWSER = "scrape_browser"
QUEUE_SCRAPE_HTTP = "scrape_http"
QUEUE_DEDUPLICATION = "deduplication"
QUEUE_REPORTS = "reports"
QUEUE_PREWARM = "prewarm"

QUEUE_NAMES = (
    QUEUE_TRANSPORT,
    QUEUE_ZONES,
    QUEUE_ENRICHMENT,
    QUEUE_SCRAPE_BROWSER,
    QUEUE_SCRAPE_HTTP,
    QUEUE_DEDUPLICATION,
    QUEUE_REPORTS,
    QUEUE_PREWARM,
)

QUEUE_CONCURRENCY = {
    QUEUE_TRANSPORT: 4,
    QUEUE_ZONES: 2,
    QUEUE_ENRICHMENT: 4,
    QUEUE_SCRAPE_BROWSER: 1,
    QUEUE_SCRAPE_HTTP: 4,
    QUEUE_DEDUPLICATION: 2,
    QUEUE_REPORTS: 1,
    QUEUE_PREWARM: 1,
}


class Priority(IntEnum):
    USER_REQUEST = 0
    PREWARM = 5


def create_stub_broker() -> StubBroker:
    broker = StubBroker()
    for queue_name in QUEUE_NAMES:
        broker.declare_queue(queue_name)
    return broker


def create_redis_broker(redis_url: str) -> Any:
    try:
        from dramatiq.brokers.redis import RedisBroker
    except Exception as exc:  # pragma: no cover - defensive import for local envs
        raise RuntimeError("Redis broker requires dramatiq[redis] dependencies") from exc

    broker = RedisBroker(url=redis_url)
    for queue_name in QUEUE_NAMES:
        broker.declare_queue(queue_name)
    return broker


def configure_broker(broker_kind: str, redis_url: str) -> Any:
    normalized = (broker_kind or "stub").strip().lower()
    if normalized == "redis":
        broker = create_redis_broker(redis_url)
    elif normalized == "stub":
        broker = create_stub_broker()
    else:
        raise ValueError(f"Unsupported DRAMATIQ_BROKER value: {broker_kind}")

    dramatiq.set_broker(broker)
    return broker
