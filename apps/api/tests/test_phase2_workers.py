import asyncio
from uuid import uuid4

from contracts import JobType
from workers.cancellation import JobCancelledException
from workers.handlers.transport import _transport_search_step
from workers.queue import QUEUE_CONCURRENCY, QUEUE_NAMES, Priority, configure_broker
from workers.retry_policy import JobRetryPolicy
from workers.runtime import run_job_with_retry
from workers.watchdog import sweep_stale_running_jobs


def test_configure_stub_broker_declares_phase2_queues():
    broker = configure_broker("stub", "redis://localhost:6379/0")
    declared = set(getattr(broker, "queues", {}).keys())
    assert set(QUEUE_NAMES).issubset(declared)
    assert set(QUEUE_NAMES).issubset(set(QUEUE_CONCURRENCY))
    assert QUEUE_CONCURRENCY["transport"] == 4
    assert QUEUE_CONCURRENCY["scrape_browser"] == 1
    assert Priority.USER_REQUEST == 0
    assert Priority.PREWARM == 5


def test_retry_policy_transport_search_values():
    rule = JobRetryPolicy.for_job_type(JobType.TRANSPORT_SEARCH)
    assert rule.max_retries == 2
    assert rule.backoff_seconds == (5, 30)


def test_retry_policy_has_rules_for_each_job_type():
    for job_type in JobType:
        rule = JobRetryPolicy.for_job_type(job_type)
        assert rule.max_retries >= 0
        assert len(rule.backoff_seconds) >= 1


def test_run_job_with_retry_completes_for_each_job_type(monkeypatch):
    states = []

    class _FakeStateMiddleware:
        async def mark_running(self, job_id, stage=None):
            states.append("running")

        async def mark_retrying(self, job_id, stage=None, retry_in_seconds=0):
            states.append("retrying")

        async def mark_pending(self, job_id, stage=None):
            states.append("pending")

        async def mark_completed(self, job_id, stage=None):
            states.append("completed")

        async def mark_failed(self, job_id, stage=None, error_message=None):
            states.append("failed")

        async def mark_cancelled_partial(self, job_id, stage=None):
            states.append("cancelled_partial")

    class _FakeHeartbeatMiddleware:
        def __init__(self, ttl_seconds=120):
            self.ttl_seconds = ttl_seconds

        async def beat(self, job_id):
            return None

        async def clear(self, job_id):
            return None

    async def _execute_step():
        return None

    monkeypatch.setattr("workers.runtime.JobStateMiddleware", _FakeStateMiddleware)
    monkeypatch.setattr("workers.runtime.JobHeartbeatMiddleware", _FakeHeartbeatMiddleware)

    for job_type in JobType:
        asyncio.run(
            run_job_with_retry(
                uuid4(),
                job_type,
                stage="phase2-coverage",
                execute_step=_execute_step,
            )
        )

    assert states.count("completed") == len(JobType)
    assert "failed" not in states


def test_run_job_with_retry_retries_then_completes(monkeypatch):
    state_calls = []
    heartbeat_calls = []
    sleep_calls = []

    class _FakeStateMiddleware:
        async def mark_running(self, job_id, stage=None):
            state_calls.append(("running", stage))

        async def mark_retrying(self, job_id, stage=None, retry_in_seconds=0):
            state_calls.append(("retrying", retry_in_seconds))

        async def mark_pending(self, job_id, stage=None):
            state_calls.append(("pending", stage))

        async def mark_completed(self, job_id, stage=None):
            state_calls.append(("completed", stage))

        async def mark_failed(self, job_id, stage=None, error_message=None):
            state_calls.append(("failed", error_message))

        async def mark_cancelled_partial(self, job_id, stage=None):
            state_calls.append(("cancelled_partial", stage))

    class _FakeHeartbeatMiddleware:
        def __init__(self, ttl_seconds=120):
            self.ttl_seconds = ttl_seconds

        @staticmethod
        def heartbeat_key(job_id):
            return f"job_heartbeat:{job_id}"

        async def beat(self, job_id):
            heartbeat_calls.append("beat")

        async def clear(self, job_id):
            heartbeat_calls.append("clear")

    async def _fake_sleep(seconds):
        sleep_calls.append(seconds)

    attempts = {"count": 0}

    async def _execute_step():
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("transient failure")

    monkeypatch.setattr("workers.runtime.JobStateMiddleware", _FakeStateMiddleware)
    monkeypatch.setattr("workers.runtime.JobHeartbeatMiddleware", _FakeHeartbeatMiddleware)
    monkeypatch.setattr("workers.runtime.asyncio.sleep", _fake_sleep)

    asyncio.run(
        run_job_with_retry(
            uuid4(),
            JobType.TRANSPORT_SEARCH,
            stage="transport_search",
            execute_step=_execute_step,
        )
    )

    assert attempts["count"] == 2
    assert ("retrying", 5) in state_calls
    assert ("pending", "transport_search") in state_calls
    assert ("completed", "transport_search") in state_calls
    assert sleep_calls == [5]
    assert heartbeat_calls[-1] == "clear"


def test_run_job_with_retry_marks_cancelled_partial(monkeypatch):
    state_calls = []

    class _FakeStateMiddleware:
        async def mark_running(self, job_id, stage=None):
            state_calls.append("running")

        async def mark_retrying(self, job_id, stage=None, retry_in_seconds=0):
            state_calls.append("retrying")

        async def mark_pending(self, job_id, stage=None):
            state_calls.append("pending")

        async def mark_completed(self, job_id, stage=None):
            state_calls.append("completed")

        async def mark_failed(self, job_id, stage=None, error_message=None):
            state_calls.append("failed")

        async def mark_cancelled_partial(self, job_id, stage=None):
            state_calls.append("cancelled_partial")

    class _FakeHeartbeatMiddleware:
        def __init__(self, ttl_seconds=120):
            self.ttl_seconds = ttl_seconds

        async def beat(self, job_id):
            return None

        async def clear(self, job_id):
            return None

    async def _execute_step():
        raise JobCancelledException("cancelled")

    monkeypatch.setattr("workers.runtime.JobStateMiddleware", _FakeStateMiddleware)
    monkeypatch.setattr("workers.runtime.JobHeartbeatMiddleware", _FakeHeartbeatMiddleware)

    asyncio.run(
        run_job_with_retry(
            uuid4(),
            JobType.TRANSPORT_SEARCH,
            stage="transport_search",
            execute_step=_execute_step,
        )
    )

    assert "cancelled_partial" in state_calls
    assert "failed" not in state_calls


def test_run_job_with_retry_marks_failed_after_max_retries(monkeypatch):
    state_calls = []
    sleep_calls = []

    class _FakeStateMiddleware:
        async def mark_running(self, job_id, stage=None):
            state_calls.append(("running", stage))

        async def mark_retrying(self, job_id, stage=None, retry_in_seconds=0):
            state_calls.append(("retrying", retry_in_seconds))

        async def mark_pending(self, job_id, stage=None):
            state_calls.append(("pending", stage))

        async def mark_completed(self, job_id, stage=None):
            state_calls.append(("completed", stage))

        async def mark_failed(self, job_id, stage=None, error_message=None):
            state_calls.append(("failed", error_message))

        async def mark_cancelled_partial(self, job_id, stage=None):
            state_calls.append(("cancelled_partial", stage))

    class _FakeHeartbeatMiddleware:
        def __init__(self, ttl_seconds=120):
            self.ttl_seconds = ttl_seconds

        async def beat(self, job_id):
            return None

        async def clear(self, job_id):
            return None

    async def _fake_sleep(seconds):
        sleep_calls.append(seconds)

    async def _execute_step():
        raise RuntimeError("always fails")

    monkeypatch.setattr("workers.runtime.JobStateMiddleware", _FakeStateMiddleware)
    monkeypatch.setattr("workers.runtime.JobHeartbeatMiddleware", _FakeHeartbeatMiddleware)
    monkeypatch.setattr("workers.runtime.asyncio.sleep", _fake_sleep)

    asyncio.run(
        run_job_with_retry(
            uuid4(),
            JobType.TRANSPORT_SEARCH,
            stage="transport_search",
            execute_step=_execute_step,
        )
    )

    assert [item[0] for item in state_calls].count("retrying") == 2
    assert [item[0] for item in state_calls].count("pending") == 2
    assert state_calls[-1][0] == "failed"
    assert sleep_calls == [5, 30]


def test_watchdog_marks_stale_running_jobs(monkeypatch):
    job_id = uuid4()
    updated = []
    published = []

    class _FakeResult:
        def mappings(self):
            return self

        def all(self):
            return [{"id": job_id}]

    class _FakeConn:
        async def execute(self, _query):
            return _FakeResult()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _FakeEngine:
        def connect(self):
            return _FakeConn()

    class _FakeRedis:
        async def exists(self, key):
            return 0

    async def _update(job_id, **kwargs):
        updated.append((job_id, kwargs))

    async def _publish(job_id, event_type, **kwargs):
        published.append((job_id, event_type, kwargs))

    monkeypatch.setattr("workers.watchdog.get_engine", lambda: _FakeEngine())
    monkeypatch.setattr("workers.watchdog.get_redis", lambda: _FakeRedis())
    monkeypatch.setattr("workers.watchdog.update_job_execution_state", _update)
    monkeypatch.setattr("workers.watchdog.publish_job_event", _publish)

    asyncio.run(sweep_stale_running_jobs())

    assert len(updated) == 1
    assert updated[0][1]["state"] == "cancelled_partial"
    assert len(published) == 1
    assert published[0][1] == "job.failed"


def test_watchdog_ignores_running_job_with_heartbeat(monkeypatch):
    job_id = uuid4()
    updated = []
    published = []

    class _FakeResult:
        def mappings(self):
            return self

        def all(self):
            return [{"id": job_id}]

    class _FakeConn:
        async def execute(self, _query):
            return _FakeResult()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _FakeEngine:
        def connect(self):
            return _FakeConn()

    class _FakeRedis:
        async def exists(self, key):
            return 1

    async def _update(job_id, **kwargs):
        updated.append((job_id, kwargs))

    async def _publish(job_id, event_type, **kwargs):
        published.append((job_id, event_type, kwargs))

    monkeypatch.setattr("workers.watchdog.get_engine", lambda: _FakeEngine())
    monkeypatch.setattr("workers.watchdog.get_redis", lambda: _FakeRedis())
    monkeypatch.setattr("workers.watchdog.update_job_execution_state", _update)
    monkeypatch.setattr("workers.watchdog.publish_job_event", _publish)

    asyncio.run(sweep_stale_running_jobs())

    assert updated == []
    assert published == []


def test_transport_stub_emits_progress_every_half_second(monkeypatch):
    progress_calls = []
    sleep_calls = []

    async def _check_cancellation(_job_id):
        return None

    async def _emit_stage_progress(job_id, *, stage, progress_percent, message):
        progress_calls.append((job_id, stage, progress_percent, message))

    async def _sleep(seconds):
        sleep_calls.append(seconds)

    monkeypatch.setattr("workers.handlers.transport.check_cancellation", _check_cancellation)
    monkeypatch.setattr("workers.handlers.transport.emit_stage_progress", _emit_stage_progress)
    monkeypatch.setattr("workers.handlers.transport.asyncio.sleep", _sleep)

    job_id = uuid4()
    asyncio.run(_transport_search_step(job_id))

    assert len(progress_calls) == 6
    assert [item[2] for item in progress_calls] == [16, 33, 50, 66, 83, 100]
    assert sleep_calls == [0.5, 0.5, 0.5, 0.5, 0.5, 0.5]
