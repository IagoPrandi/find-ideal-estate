from __future__ import annotations

import asyncio
import os
import sys
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

from src.modules.zones.service import (  # noqa: E402
    ZoneGenerationOutcome,
    ZoneService,
    compute_zone_fingerprint,
)
from src.workers.handlers.zones import _zone_generation_step  # noqa: E402


class _FakeMappings:
    def __init__(self, *, first_row=None, one_row=None):
        self._first_row = first_row
        self._one_row = one_row

    def first(self):
        return self._first_row

    def one(self):
        if self._one_row is None:
            raise RuntimeError("Expected one row")
        return self._one_row


class _FakeResult:
    def __init__(self, *, first_row=None, one_row=None):
        self._mappings = _FakeMappings(first_row=first_row, one_row=one_row)

    def mappings(self):
        return self._mappings


class _FakeConn:
    def __init__(self, *, context_row, existing_zone_row):
        self.context_row = context_row
        self.existing_zone_row = existing_zone_row
        self.insert_called = False
        self.association_called = False

    async def execute(self, statement, params):
        sql = str(statement)
        if "FROM jobs jb" in sql:
            return _FakeResult(first_row=self.context_row)
        if "FROM zones" in sql and "fingerprint = :fingerprint" in sql:
            return _FakeResult(first_row=self.existing_zone_row)
        if "INSERT INTO journey_zones" in sql:
            self.association_called = True
            return _FakeResult()
        if "INSERT INTO zones" in sql:
            self.insert_called = True
            return _FakeResult(one_row={"id": uuid4()})
        raise AssertionError(f"Unexpected SQL executed: {sql}")


class _FakeBeginCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeEngine:
    def __init__(self, conn):
        self._conn = conn

    def begin(self):
        return _FakeBeginCtx(self._conn)


def test_compute_zone_fingerprint_rounds_lat_lon_to_5_decimals() -> None:
    first = compute_zone_fingerprint(-23.550521, -46.633309, "walking", 30, 1200, "v1")
    second = compute_zone_fingerprint(-23.550524, -46.633306, "walking", 30, 1200, "v1")
    assert first == second


def test_zone_service_reuses_existing_zone_before_calling_valhalla(monkeypatch) -> None:
    class _FakeValhalla:
        def __init__(self):
            self.called = False

        async def isochrone(self, origin, costing, contours_minutes):
            self.called = True
            raise AssertionError("Valhalla should not be called when zone is reused")

    fake_valhalla = _FakeValhalla()
    service = ZoneService(valhalla_adapter=fake_valhalla, otp_adapter=object())

    context_row = {
        "journey_id": uuid4(),
        "input_snapshot": {
            "travel_mode": "walking",
            "max_travel_time_min": 25,
            "zone_radius_meters": 900,
            "dataset_version_id": "11111111-1111-1111-1111-111111111111",
        },
        "transport_point_id": uuid4(),
        "lat": -23.55052,
        "lon": -46.63331,
    }
    existing_zone_id = uuid4()
    fake_conn = _FakeConn(context_row=context_row, existing_zone_row={"id": existing_zone_id})
    monkeypatch.setattr("src.modules.zones.service.get_engine", lambda: _FakeEngine(fake_conn))

    outcome = asyncio.run(service.ensure_zone_for_job(uuid4()))

    assert outcome.reused is True
    assert outcome.zone_id == existing_zone_id
    assert fake_valhalla.called is False
    assert fake_conn.insert_called is False
    assert fake_conn.association_called is True


def test_zone_generation_step_emits_reused_and_generated_events(monkeypatch) -> None:
    events: list[str] = []

    async def _check_cancellation(_job_id):
        return None

    async def _emit_stage_progress(*_args, **_kwargs):
        return None

    async def _publish_event(_job_id, event_type, **_kwargs):
        events.append(event_type)
        return None

    async def _run_reused(_job_id):
        return {
            "zones": [ZoneGenerationOutcome(zone_id=uuid4(), fingerprint="fp-reused", reused=True)],
            "total": 1,
            "completed": 0,
        }

    async def _run_generated(_job_id):
        return {
            "zones": [ZoneGenerationOutcome(zone_id=uuid4(), fingerprint="fp-generated", reused=False)],
            "total": 1,
            "completed": 1,
        }

    monkeypatch.setattr("src.workers.handlers.zones.check_cancellation", _check_cancellation)
    monkeypatch.setattr("src.workers.handlers.zones.emit_stage_progress", _emit_stage_progress)
    monkeypatch.setattr("src.workers.handlers.zones.publish_job_event", _publish_event)

    monkeypatch.setattr("src.workers.handlers.zones.run_zone_generation_for_job", _run_reused)
    asyncio.run(_zone_generation_step(uuid4()))

    monkeypatch.setattr("src.workers.handlers.zones.run_zone_generation_for_job", _run_generated)
    asyncio.run(_zone_generation_step(uuid4()))

    assert "zone.reused" in events
    assert "zone.generated" in events
    assert "job.partial_result.ready" in events
