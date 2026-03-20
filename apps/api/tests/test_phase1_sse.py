import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/find_ideal_estate")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("MAPBOX_ACCESS_TOKEN", "test")
os.environ.setdefault("MAPTILER_API_KEY", "test")
os.environ.setdefault("VALHALLA_URL", "http://localhost:8002")
os.environ.setdefault("OTP_URL", "http://localhost:8080")

from contracts import JobEventRead  # noqa: E402
from modules.jobs.events import _events_after_id, _format_sse_message, job_events_stream  # noqa: E402


class _FakeRequest:
    def __init__(self):
        self._checks = 0

    async def is_disconnected(self) -> bool:
        self._checks += 1
        return self._checks > 1


class _FakePubSub:
    def __init__(self, messages):
        self._messages = list(messages)
        self.subscribed_to = []
        self.unsubscribed_to = []
        self.closed = False

    async def subscribe(self, channel: str) -> None:
        self.subscribed_to.append(channel)

    async def get_message(self, ignore_subscribe_messages: bool = True, timeout: float = 1.0):
        if self._messages:
            return {"data": self._messages.pop(0)}
        return None

    async def unsubscribe(self, channel: str) -> None:
        self.unsubscribed_to.append(channel)

    async def aclose(self) -> None:
        self.closed = True


class _FakeRedis:
    def __init__(self, pubsub: _FakePubSub):
        self._pubsub = pubsub

    def pubsub(self) -> _FakePubSub:
        return self._pubsub


def test_events_after_id_skips_replayed_event():
    event_a = JobEventRead(
        id=uuid4(),
        job_id=uuid4(),
        event_type="job.started",
        stage=None,
        message=None,
        payload_json=None,
        created_at=datetime.now(tz=timezone.utc),
    )
    event_b = JobEventRead(
        id=uuid4(),
        job_id=event_a.job_id,
        event_type="job.completed",
        stage=None,
        message=None,
        payload_json=None,
        created_at=datetime.now(tz=timezone.utc),
    )

    remaining = _events_after_id([event_a, event_b], str(event_a.id))

    assert [event.id for event in remaining] == [event_b.id]


def test_format_sse_message_includes_id_and_event():
    payload = '{"id": "evt-1", "event_type": "job.started", "message": "started"}'

    formatted = _format_sse_message(payload)

    assert "id: evt-1" in formatted
    assert "event: job.started" in formatted
    assert '"message": "started"' in formatted


def test_job_events_stream_replays_and_streams_live(monkeypatch):
    async def _run() -> None:
        job_id = uuid4()
        replay_event = JobEventRead(
            id=uuid4(),
            job_id=job_id,
            event_type="job.started",
            stage="setup",
            message="Replay event",
            payload_json={"step": 1},
            created_at=datetime.now(tz=timezone.utc),
        )
        live_payload = '{"id": "live-1", "event_type": "job.stage.progress", "message": "Live event"}'
        fake_pubsub = _FakePubSub([live_payload])

        async def _list_job_events(requested_job_id):
            assert requested_job_id == job_id
            return [replay_event]

        monkeypatch.setattr("modules.jobs.events.list_job_events", _list_job_events)
        monkeypatch.setattr("modules.jobs.events.get_redis", lambda: _FakeRedis(fake_pubsub))

        request = _FakeRequest()
        stream = job_events_stream(job_id, request)

        replay_message = await anext(stream)
        live_message = await anext(stream)
        await stream.aclose()

        assert "event: job.started" in replay_message
        assert "Replay event" in replay_message
        assert "event: job.stage.progress" in live_message
        assert "Live event" in live_message
        assert fake_pubsub.subscribed_to == [f"job:{job_id}"]
        assert fake_pubsub.unsubscribed_to == [f"job:{job_id}"]
        assert fake_pubsub.closed is True

    asyncio.run(_run())