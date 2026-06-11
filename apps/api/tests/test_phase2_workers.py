import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from contracts import JobRead, JobState, JobType
from modules.jobs.service import enqueue_job
from workers.cancellation import JobCancelledException
from workers.handlers.enrichment import enrich_zones_actor
from workers.handlers.transport import _transport_search_step, transport_search_actor
from workers.handlers.zones import zone_generation_actor
from workers.queue import QUEUE_CONCURRENCY, QUEUE_NAMES, Priority, configure_broker
from workers.retry_policy import JobRetryPolicy
from workers.runner import resolve_worker_plan, should_combine_worker_queues
from workers.runtime import run_job_with_retry
from workers.watchdog import (
    reenqueue_stale_pending_jobs,
    start_watchdog,
    stop_watchdog,
    sweep_stale_running_jobs,
)


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


def test_resolve_worker_plan_accepts_env_concurrency_override(monkeypatch):
    monkeypatch.setenv("WORKER_CONCURRENCY_DEFAULT", "1")
    monkeypatch.setenv("WORKER_CONCURRENCY_ENRICHMENT", "2")

    assert resolve_worker_plan(["transport", "enrichment"]) == [
        ("transport", 1),
        ("enrichment", 2),
    ]


def test_should_combine_worker_queues_reads_env(monkeypatch):
    monkeypatch.delenv("WORKER_COMBINED_QUEUES", raising=False)
    assert should_combine_worker_queues() is False

    monkeypatch.setenv("WORKER_COMBINED_QUEUES", "true")
    assert should_combine_worker_queues() is True


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


def test_run_job_with_retry_ignores_cancelled_heartbeat_shutdown(monkeypatch):
    warnings = []

    class _FakeStateMiddleware:
        async def mark_running(self, job_id, stage=None):
            return None

        async def mark_retrying(self, job_id, stage=None, retry_in_seconds=0):
            return None

        async def mark_pending(self, job_id, stage=None):
            return None

        async def mark_completed(self, job_id, stage=None):
            return None

        async def mark_failed(self, job_id, stage=None, error_message=None):
            return None

        async def mark_cancelled_partial(self, job_id, stage=None):
            return None

    class _FakeHeartbeatMiddleware:
        def __init__(self, ttl_seconds=120):
            self.ttl_seconds = ttl_seconds

        async def beat(self, job_id):
            await asyncio.sleep(10)

        async def clear(self, job_id):
            return None

    async def _execute_step():
        return None

    monkeypatch.setattr("workers.runtime.JobStateMiddleware", _FakeStateMiddleware)
    monkeypatch.setattr("workers.runtime.JobHeartbeatMiddleware", _FakeHeartbeatMiddleware)
    monkeypatch.setattr(
        "workers.runtime.logger.warning",
        lambda message, *args, **kwargs: warnings.append(message),
    )

    asyncio.run(
        run_job_with_retry(
            uuid4(),
            JobType.TRANSPORT_SEARCH,
            stage="transport_search",
            execute_step=_execute_step,
        )
    )

    assert "heartbeat loop finished with error" not in warnings


def test_transport_actor_uses_shared_worker_loop(monkeypatch):
    captured = []

    def _fake_run_worker_coroutine(awaitable):
        captured.append(awaitable)
        awaitable.close()

    monkeypatch.setattr("workers.runner.run_worker_coroutine", _fake_run_worker_coroutine)

    transport_search_actor(str(uuid4()))

    assert len(captured) == 1


def test_zone_actor_uses_shared_worker_loop(monkeypatch):
    captured = []

    def _fake_run_worker_coroutine(awaitable):
        captured.append(awaitable)
        awaitable.close()

    monkeypatch.setattr("workers.runner.run_worker_coroutine", _fake_run_worker_coroutine)

    zone_generation_actor(str(uuid4()))

    assert len(captured) == 1


def test_enrichment_actor_uses_shared_worker_loop(monkeypatch):
    captured = []

    def _fake_run_worker_coroutine(awaitable):
        captured.append(awaitable)
        awaitable.close()

    monkeypatch.setattr("workers.runner.run_worker_coroutine", _fake_run_worker_coroutine)

    enrich_zones_actor(str(uuid4()))

    assert len(captured) == 1


def _sample_job_for_enqueue(job_type: JobType) -> JobRead:
    return JobRead(
        id=uuid4(),
        journey_id=uuid4(),
        job_type=job_type,
        state=JobState.PENDING,
        progress_percent=0,
        current_stage=None,
        cancel_requested_at=None,
        started_at=None,
        finished_at=None,
        worker_id=None,
        result_ref={},
        error_code=None,
        error_message=None,
        created_at=datetime.now(tz=timezone.utc),
    )


def test_enqueue_job_runs_selected_types_inline_locally(monkeypatch):
    inline_jobs = []

    async def _fake_run_job_inline(job):
        inline_jobs.append(job.job_type)

    async def _exercise():
        await enqueue_job(_sample_job_for_enqueue(JobType.ZONE_GENERATION))
        await asyncio.sleep(0)

    monkeypatch.setattr("modules.jobs.service._uses_stub_broker", lambda: False)
    monkeypatch.setattr(
        "modules.jobs.service.get_settings",
        lambda: SimpleNamespace(local_inline_job_types="default"),
    )
    monkeypatch.setattr("modules.jobs.service._run_job_inline", _fake_run_job_inline)

    asyncio.run(_exercise())

    assert inline_jobs == [JobType.ZONE_GENERATION]


def test_enqueue_job_keeps_listings_scrape_external_when_local_inline_enabled(monkeypatch):
    sent_ids = []

    async def _exercise():
        await enqueue_job(_sample_job_for_enqueue(JobType.LISTINGS_SCRAPE))

    monkeypatch.setattr("modules.jobs.service._uses_stub_broker", lambda: False)
    monkeypatch.setattr(
        "modules.jobs.service.get_settings",
        lambda: SimpleNamespace(local_inline_job_types="default"),
    )
    monkeypatch.setattr(
        "workers.handlers.listings.listings_scrape_actor.send",
        lambda job_id: sent_ids.append(job_id),
    )

    asyncio.run(_exercise())

    assert len(sent_ids) == 1


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


def test_watchdog_reenqueues_stale_pending_jobs(monkeypatch):
    job = _sample_job_for_enqueue(JobType.ZONE_ENRICHMENT)
    enqueued = []
    published = []

    class _FakeResult:
        def mappings(self):
            return self

        def all(self):
            return [{"id": job.id, "job_type": JobType.ZONE_ENRICHMENT.value}]

    class _FakeConn:
        async def execute(self, _query, _params=None):
            return _FakeResult()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _FakeEngine:
        def connect(self):
            return _FakeConn()

    class _FakeRedis:
        async def set(self, key, value, *, ex=None, nx=False):
            return True

    async def _get_job(job_id):
        assert job_id == job.id
        return job

    async def _enqueue_job(job):
        enqueued.append(job.id)

    async def _publish(job_id, event_type, **kwargs):
        published.append((job_id, event_type, kwargs))

    monkeypatch.setattr("workers.watchdog.get_engine", lambda: _FakeEngine())
    monkeypatch.setattr("workers.watchdog.get_redis", lambda: _FakeRedis())
    monkeypatch.setattr("workers.watchdog.get_job", _get_job)
    monkeypatch.setattr("workers.watchdog.enqueue_job", _enqueue_job)
    monkeypatch.setattr("workers.watchdog.publish_job_event", _publish)

    asyncio.run(reenqueue_stale_pending_jobs())

    assert enqueued == [job.id]
    assert published[0][1] == "job.reenqueued"


def test_start_watchdog_uses_utc_timezone(monkeypatch):
    captured = {}

    class _FakeScheduler:
        def __init__(self, *args, **kwargs):
            captured["timezone"] = kwargs.get("timezone")
            self.jobs = []
            captured["jobs"] = self.jobs

        def add_job(self, func, trigger, **kwargs):
            self.jobs.append((func, trigger, kwargs))

        def start(self):
            captured["started"] = True

        def shutdown(self, wait=False):
            captured["shutdown_wait"] = wait

    monkeypatch.setattr(
        "workers.watchdog.get_settings",
        lambda: SimpleNamespace(
            enable_listings_prewarm_scheduler=True,
            listings_prewarm_cron_hour=3,
            listings_prewarm_cron_minute=0,
        ),
    )
    monkeypatch.setattr("workers.watchdog.AsyncIOScheduler", _FakeScheduler)

    stop_watchdog()
    start_watchdog()
    stop_watchdog()

    assert str(captured["timezone"]) == "UTC"
    assert captured["started"] is True
    assert len(captured["jobs"]) == 3


def test_transport_search_step_queries_and_emits_progress(monkeypatch):
    progress_calls = []
    searched_job_ids = []

    async def _check_cancellation(_job_id):
        return None

    async def _emit_stage_progress(job_id, *, stage, progress_percent, message):
        progress_calls.append((job_id, stage, progress_percent, message))

    async def _run_transport_search_for_job(job_id):
        searched_job_ids.append(job_id)
        return 2

    monkeypatch.setattr("workers.handlers.transport.check_cancellation", _check_cancellation)
    monkeypatch.setattr("workers.handlers.transport.emit_stage_progress", _emit_stage_progress)
    monkeypatch.setattr(
        "workers.handlers.transport.run_transport_search_for_job",
        _run_transport_search_for_job,
    )

    job_id = uuid4()
    asyncio.run(_transport_search_step(job_id))

    assert searched_job_ids == [job_id]
    assert [item[2] for item in progress_calls] == [10, 40, 100]
