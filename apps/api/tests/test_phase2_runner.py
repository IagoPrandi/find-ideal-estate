from workers.queue import QUEUE_CONCURRENCY, QUEUE_NAMES
from workers.runner import parse_queue_names, resolve_worker_plan


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
