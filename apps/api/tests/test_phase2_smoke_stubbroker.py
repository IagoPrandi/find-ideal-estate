import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from uuid import uuid4

# ruff: noqa: E402

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/find_ideal_estate")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("MAPBOX_ACCESS_TOKEN", "test")
os.environ.setdefault("MAPTILER_API_KEY", "test")
os.environ.setdefault("VALHALLA_URL", "http://localhost:8002")
os.environ.setdefault("OTP_URL", "http://localhost:8080")

from contracts import JobCancelAccepted, JobEventRead
from dramatiq.worker import Worker
from httpx import ASGITransport, AsyncClient
from modules.jobs.events import job_channel, job_events_stream
from src.main import app
from workers.queue import configure_broker


class _FakeRequest:
    def __init__(self) -> None:
        self._disconnected = False

    def disconnect(self) -> None:
        self._disconnected = True

    async def is_disconnected(self) -> bool:
        return self._disconnected


class _FakePubSub:
    def __init__(self, redis: "_FakeRedis") -> None:
        self._redis = redis
        self._channels: set[str] = set()

    async def subscribe(self, channel: str) -> None:
        self._channels.add(channel)

    async def get_message(self, ignore_subscribe_messages: bool = True, timeout: float = 1.0):
        _ = ignore_subscribe_messages
        deadline = monotonic() + timeout
        while monotonic() < deadline:
            for channel in list(self._channels):
                queue = self._redis.channels.setdefault(channel, asyncio.Queue())
                if not queue.empty():
                    return {"data": queue.get_nowait()}
            await asyncio.sleep(0.01)
        return None

    async def unsubscribe(self, channel: str) -> None:
        self._channels.discard(channel)

    async def aclose(self) -> None:
        self._channels.clear()


class _FakeRedis:
    def __init__(self) -> None:
        self.channels: dict[str, asyncio.Queue[str]] = {}

    def pubsub(self) -> _FakePubSub:
        return _FakePubSub(self)

    async def publish(self, channel: str, payload: str) -> None:
        queue = self.channels.setdefault(channel, asyncio.Queue())
        queue.put_nowait(payload)


def test_phase2_smoke_enqueue_and_wait_sse_completed(monkeypatch):
    async def _run() -> None:
        broker = configure_broker("stub", "redis://localhost:6379/0")
        from workers.handlers.transport import transport_search_actor

        # Force this actor to use the test StubBroker instance.
        transport_search_actor.broker = broker
        broker.declare_actor(transport_search_actor)

        events: list[JobEventRead] = []
        fake_redis = _FakeRedis()
        job_id = uuid4()

        class _Job:
            cancel_requested_at = None

        async def _publish_job_event(
            event_job_id,
            event_type,
            *,
            stage=None,
            message=None,
            payload_json=None,
        ):
            event = JobEventRead(
                id=uuid4(),
                job_id=event_job_id,
                event_type=event_type,
                stage=stage,
                message=message,
                payload_json=payload_json,
                created_at=datetime.now(tz=timezone.utc),
            )
            events.append(event)
            await fake_redis.publish(job_channel(event_job_id), event.model_dump_json())
            return event

        async def _list_job_events(_job_id):
            return list(events)

        async def _get_job(_job_id):
            return _Job()

        async def _update_job_execution_state(_job_id, **_kwargs):
            return None

        class _FakeHeartbeatMiddleware:
            def __init__(self, ttl_seconds=120):
                self.ttl_seconds = ttl_seconds

            @staticmethod
            def heartbeat_key(_job_id):
                return "job_heartbeat:fake"

            async def beat(self, _job_id):
                return None

            async def clear(self, _job_id):
                return None

        monkeypatch.setattr("workers.middleware.publish_job_event", _publish_job_event)
        monkeypatch.setattr(
            "workers.middleware.update_job_execution_state",
            _update_job_execution_state,
        )
        monkeypatch.setattr("workers.handlers.transport.run_transport_search_for_job", lambda _job_id: asyncio.sleep(0))
        monkeypatch.setattr("workers.cancellation.get_job", _get_job)
        monkeypatch.setattr("workers.runtime.JobHeartbeatMiddleware", _FakeHeartbeatMiddleware)
        monkeypatch.setattr("modules.jobs.events.list_job_events", _list_job_events)
        monkeypatch.setattr("modules.jobs.events.get_redis", lambda: fake_redis)

        worker = Worker(broker, worker_threads=1)
        request = _FakeRequest()
        stream = job_events_stream(job_id, request)

        worker.start()
        transport_search_actor.send(str(job_id))

        completed_seen = False
        deadline = monotonic() + 10.0

        try:
            while monotonic() < deadline:
                try:
                    message = await asyncio.wait_for(anext(stream), timeout=1.5)
                except TimeoutError:
                    continue
                except StopAsyncIteration:
                    break

                if "event: job.completed" in message:
                    completed_seen = True
                    request.disconnect()
                    break
        finally:
            await stream.aclose()
            worker.stop()
            worker.join()

        assert completed_seen is True

    asyncio.run(_run())


def test_phase2_smoke_cancel_endpoint_emits_cancelled_under_2s(monkeypatch):
    async def _run() -> None:
        broker = configure_broker("stub", "redis://localhost:6379/0")
        from workers.handlers.transport import transport_search_actor

        # Force this actor to use the test StubBroker instance.
        transport_search_actor.broker = broker
        broker.declare_actor(transport_search_actor)

        events: list[JobEventRead] = []
        fake_redis = _FakeRedis()
        job_id = uuid4()
        cancel_state = {"requested_at": None}

        class _Job:
            @property
            def cancel_requested_at(self):
                return cancel_state["requested_at"]

        async def _publish_job_event(
            event_job_id,
            event_type,
            *,
            stage=None,
            message=None,
            payload_json=None,
        ):
            event = JobEventRead(
                id=uuid4(),
                job_id=event_job_id,
                event_type=event_type,
                stage=stage,
                message=message,
                payload_json=payload_json,
                created_at=datetime.now(tz=timezone.utc),
            )
            events.append(event)
            await fake_redis.publish(job_channel(event_job_id), event.model_dump_json())
            return event

        async def _list_job_events(_job_id):
            return list(events)

        async def _get_job(_job_id):
            return _Job()

        async def _update_job_execution_state(_job_id, **_kwargs):
            return None

        async def _request_job_cancellation(requested_job_id):
            cancel_state["requested_at"] = datetime.now(tz=timezone.utc)
            return JobCancelAccepted(
                job_id=requested_job_id,
                status="accepted",
                cancel_requested_at=cancel_state["requested_at"],
            )

        class _FakeHeartbeatMiddleware:
            def __init__(self, ttl_seconds=120):
                self.ttl_seconds = ttl_seconds

            @staticmethod
            def heartbeat_key(_job_id):
                return "job_heartbeat:fake"

            async def beat(self, _job_id):
                return None

            async def clear(self, _job_id):
                return None

        monkeypatch.setattr("workers.middleware.publish_job_event", _publish_job_event)
        monkeypatch.setattr(
            "workers.middleware.update_job_execution_state",
            _update_job_execution_state,
        )
        monkeypatch.setattr("workers.handlers.transport.run_transport_search_for_job", lambda _job_id: asyncio.sleep(0))
        monkeypatch.setattr("workers.cancellation.get_job", _get_job)
        monkeypatch.setattr("workers.runtime.JobHeartbeatMiddleware", _FakeHeartbeatMiddleware)
        monkeypatch.setattr("modules.jobs.events.list_job_events", _list_job_events)
        monkeypatch.setattr("modules.jobs.events.get_redis", lambda: fake_redis)
        monkeypatch.setattr("api.routes.jobs.request_job_cancellation", _request_job_cancellation)

        worker = Worker(broker, worker_threads=1)
        request = _FakeRequest()
        stream = job_events_stream(job_id, request)
        cancel_triggered_at = 0.0

        worker.start()
        transport_search_actor.send(str(job_id))

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            deadline = monotonic() + 10.0
            cancelled_seen = False
            cancel_requested = False

            try:
                while monotonic() < deadline:
                    try:
                        message = await asyncio.wait_for(anext(stream), timeout=1.0)
                    except TimeoutError:
                        continue
                    except StopAsyncIteration:
                        break

                    if (not cancel_requested) and "event: job.stage.progress" in message:
                        response = await client.post(f"/jobs/{job_id}/cancel")
                        assert response.status_code == 202
                        cancel_triggered_at = monotonic()
                        cancel_requested = True

                    if "event: job.cancelled" in message:
                        cancelled_seen = True
                        elapsed = monotonic() - cancel_triggered_at
                        assert elapsed < 2.0
                        request.disconnect()
                        break
            finally:
                await stream.aclose()
                worker.stop()
                worker.join()

            assert cancelled_seen is True

    asyncio.run(_run())
