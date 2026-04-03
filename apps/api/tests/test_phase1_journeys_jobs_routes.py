import os
import sys
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
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

from contracts import (  # noqa: E402
    JobCancelAccepted,
    JobCreate,
    JobRead,
    JobState,
    JobType,
    JourneyCreate,
    JourneyRead,
    JourneyState,
    JourneyUpdate,
)
from fastapi.testclient import TestClient  # noqa: E402
import pytest  # noqa: E402
from core.db import get_engine, init_db  # noqa: E402
from src.main import app  # noqa: E402
from modules.jobs.service import create_job  # noqa: E402
from sqlalchemy import text  # noqa: E402
from api.routes.journeys import _classify_public_safety_group  # noqa: E402


def _sample_transport_point(journey_id):
    return {
        "id": str(uuid4()),
        "journey_id": str(journey_id),
        "source": "gtfs_stop",
        "external_id": "123",
        "name": "Parada Teste",
        "lat": -23.55,
        "lon": -46.63,
        "walk_time_sec": 120,
        "walk_distance_m": 150,
        "route_ids": ["875A-10", "175T-10"],
        "modal_types": ["bus"],
        "route_count": 2,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
    }


def _sample_journey() -> JourneyRead:
    return JourneyRead(
        id=uuid4(),
        user_id=None,
        anonymous_session_id="session-123",
        state=JourneyState.DRAFT,
        input_snapshot={"radius": 500},
        selected_transport_point_id=None,
        selected_zone_id=None,
        selected_property_id=None,
        last_completed_step=1,
        secondary_reference_label="Office",
        secondary_reference_point=None,
        created_at=datetime.now(tz=timezone.utc),
        updated_at=datetime.now(tz=timezone.utc),
        expires_at=datetime.now(tz=timezone.utc),
    )


def _sample_job() -> JobRead:
    return JobRead(
        id=uuid4(),
        journey_id=uuid4(),
        job_type=JobType.ZONE_GENERATION,
        state=JobState.PENDING,
        progress_percent=0,
        current_stage="queued",
        cancel_requested_at=None,
        started_at=None,
        finished_at=None,
        worker_id=None,
        result_ref=None,
        error_code=None,
        error_message=None,
        created_at=datetime.now(tz=timezone.utc),
    )


def test_create_journey_sets_anonymous_cookie(monkeypatch):
    sample = _sample_journey()

    async def _create(payload: JourneyCreate, anonymous_session_id: str | None = None) -> JourneyRead:
        assert payload.input_snapshot == {"radius": 500}
        assert anonymous_session_id == "generated-session"
        return sample.model_copy(update={"anonymous_session_id": anonymous_session_id})

    monkeypatch.setattr("api.routes.journeys.generate_anonymous_session_id", lambda: "generated-session")
    monkeypatch.setattr("api.routes.journeys.create_journey", _create)

    with TestClient(app) as client:
        response = client.post("/journeys", json={"input_snapshot": {"radius": 500}})

    assert response.status_code == 201
    assert response.json()["state"] == JourneyState.DRAFT.value
    assert "anonymous_session_id=generated-session" in response.headers["set-cookie"]


def test_patch_journey_returns_updated_payload(monkeypatch):
    sample = _sample_journey()

    async def _update(journey_id, payload: JourneyUpdate) -> JourneyRead | None:
        assert journey_id == sample.id
        assert payload.last_completed_step == 4
        return sample.model_copy(update={"last_completed_step": 4, "state": JourneyState.ACTIVE})

    monkeypatch.setattr("api.routes.journeys.update_journey", _update)

    with TestClient(app) as client:
        response = client.patch(f"/journeys/{sample.id}", json={"last_completed_step": 4, "state": "active"})

    assert response.status_code == 200
    assert response.json()["last_completed_step"] == 4
    assert response.json()["state"] == JourneyState.ACTIVE.value


def test_create_job_returns_pending_job(monkeypatch):
    sample = _sample_job()

    async def _create(payload: JobCreate):
        assert payload.job_type == JobType.TRANSPORT_SEARCH
        return SimpleNamespace(
            job=sample.model_copy(update={"job_type": JobType.TRANSPORT_SEARCH}),
            created=True,
        )

    monkeypatch.setattr("api.routes.jobs.create_job", _create)

    with TestClient(app) as client:
        response = client.post(
            "/jobs",
            json={"journey_id": str(sample.journey_id), "job_type": JobType.TRANSPORT_SEARCH.value},
        )

    assert response.status_code == 201
    assert response.json()["job_type"] == JobType.TRANSPORT_SEARCH.value


def test_create_job_returns_existing_active_job_with_200(monkeypatch):
    sample = _sample_job()

    async def _create(payload: JobCreate):
        assert payload.job_type == JobType.ZONE_ENRICHMENT
        return SimpleNamespace(
            job=sample.model_copy(update={"job_type": JobType.ZONE_ENRICHMENT}),
            created=False,
        )

    monkeypatch.setattr("api.routes.jobs.create_job", _create)

    with TestClient(app) as client:
        response = client.post(
            "/jobs",
            json={"journey_id": str(sample.journey_id), "job_type": JobType.ZONE_ENRICHMENT.value},
        )

    assert response.status_code == 200
    assert response.json()["id"] == str(sample.id)
    assert response.json()["job_type"] == JobType.ZONE_ENRICHMENT.value


def test_cancel_job_returns_accepted(monkeypatch):
    sample = _sample_job()
    accepted = JobCancelAccepted(
        job_id=sample.id,
        status="accepted",
        cancel_requested_at=datetime.now(tz=timezone.utc),
    )

    async def _cancel(job_id):
        assert job_id == sample.id
        return accepted

    monkeypatch.setattr("api.routes.jobs.request_job_cancellation", _cancel)

    with TestClient(app) as client:
        response = client.post(f"/jobs/{sample.id}/cancel")

    assert response.status_code == 202
    assert response.json()["status"] == "accepted"


def test_get_journey_transport_points_returns_enriched_list(monkeypatch):
    sample = _sample_journey()
    sample_point = _sample_transport_point(sample.id)

    async def _get(journey_id):
        assert journey_id == sample.id
        return sample

    async def _list(journey_id):
        assert journey_id == sample.id
        return [sample_point]

    monkeypatch.setattr("api.routes.journeys.get_journey", _get)
    monkeypatch.setattr("api.routes.journeys.list_transport_points_for_journey", _list)

    with TestClient(app) as client:
        response = client.get(f"/journeys/{sample.id}/transport-points")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["source"] == "gtfs_stop"
    assert body[0]["walk_distance_m"] == 150
    assert body[0]["route_count"] == 2


def test_get_journey_zones_returns_list_response(monkeypatch):
    sample = _sample_journey()
    zone_id = str(uuid4())

    async def _get(journey_id):
        assert journey_id == sample.id
        return sample

    async def _list(journey_id):
        assert journey_id == sample.id
        return {
            "zones": [
                {
                    "id": zone_id,
                    "journey_id": str(sample.id),
                    "transport_point_id": None,
                    "fingerprint": "fp-1",
                    "state": "complete",
                    "is_circle_fallback": False,
                    "travel_time_minutes": 24,
                    "walk_distance_meters": 210,
                    "isochrone_geom": {
                        "type": "Polygon",
                        "coordinates": [[[-46.63, -23.55], [-46.62, -23.55], [-46.62, -23.54], [-46.63, -23.54], [-46.63, -23.55]]],
                    },
                    "green_area_m2": 1200.0,
                    "flood_area_m2": 50.0,
                    "safety_incidents_count": 3,
                    "poi_counts": {"school": 5},
                    "poi_points": [
                        {
                            "kind": "poi",
                            "id": "poi-1",
                            "name": "Colegio Centro",
                            "category": "school",
                            "address": "Rua A, 10",
                            "lat": -23.55,
                            "lon": -46.63,
                        }
                    ],
                    "badges": {
                        "green_badge": {"value": 1200.0, "percentile": 80.0, "tier": "excellent"}
                    },
                    "badges_provisional": False,
                    "created_at": datetime.now(tz=timezone.utc).isoformat(),
                    "updated_at": datetime.now(tz=timezone.utc).isoformat(),
                }
            ],
            "total_count": 1,
            "completed_count": 1,
        }

    monkeypatch.setattr("api.routes.journeys.get_journey", _get)
    monkeypatch.setattr("api.routes.journeys.list_zones_for_journey", _list)

    with TestClient(app) as client:
        response = client.get(f"/journeys/{sample.id}/zones")

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 1
    assert body["completed_count"] == 1
    assert len(body["zones"]) == 1
    assert body["zones"][0]["id"] == zone_id
    assert body["zones"][0]["transport_point_id"] is None
    assert body["zones"][0]["poi_points"][0]["name"] == "Colegio Centro"


def test_classify_public_safety_group_maps_canonical_groups():
    assert _classify_public_safety_group("Furto") == ("theft", "Furto")
    assert _classify_public_safety_group("Roubo") == ("robbery", "Roubo")
    assert _classify_public_safety_group("Agressao") == ("violence", "Violencia")
    assert _classify_public_safety_group("Estupro") == ("sexual", "Violencia sexual")
    assert _classify_public_safety_group("Trafico de drogas") == ("drugs", "Drogas")
    assert _classify_public_safety_group("Dano") == ("other", "Outros")


def test_get_journey_zone_safety_incidents_returns_feature_collection(monkeypatch):
    sample = _sample_journey()

    async def _get(journey_id):
        assert journey_id == sample.id
        return sample

    async def _list(journey_id, zone_fingerprint):
        assert journey_id == sample.id
        assert zone_fingerprint == "fp-1"
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [-46.63, -23.55],
                    },
                    "properties": {
                        "id": str(uuid4()),
                        "zone_fingerprint": "fp-1",
                        "crime_group": "theft",
                        "crime_group_label": "Furto",
                        "crime_type": "Furto",
                        "occurred_at": "2026-03-29T10:00:00+00:00",
                    },
                }
            ],
        }

    monkeypatch.setattr("api.routes.journeys.get_journey", _get)
    monkeypatch.setattr("api.routes.journeys.list_zone_safety_incidents_for_journey", _list)

    with TestClient(app) as client:
        response = client.get(f"/journeys/{sample.id}/zones/fp-1/safety-incidents")

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) == 1
    assert body["features"][0]["properties"]["crime_group"] == "theft"
    assert body["features"][0]["properties"]["crime_type"] == "Furto"


def test_get_price_rollups_returns_lat_lon(monkeypatch):
    journey_id = uuid4()

    class _FakeConn:
        pass

    class _FakeConnectCtx:
        async def __aenter__(self):
            return _FakeConn()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _FakeEngine:
        def connect(self):
            return _FakeConnectCtx()

    async def _fake_fetch_rollups_for_zone(_conn, zone_fingerprint, search_type, days=30):
        assert zone_fingerprint == "zone-fp-1"
        assert search_type == "rent"
        assert days == 30
        return [
            {
                "id": uuid4(),
                "date": datetime(2026, 3, 26, tzinfo=timezone.utc).date(),
                "zone_fingerprint": "zone-fp-1",
                "search_type": "rent",
                "median_price": 3500,
                "p25_price": 3000,
                "p75_price": 4200,
                "sample_count": 12,
                "computed_at": datetime.now(tz=timezone.utc),
                "lat": -23.55,
                "lon": -46.63,
            }
        ]

    monkeypatch.setattr("api.routes.zones._get_engine", lambda: _FakeEngine())
    monkeypatch.setattr("api.routes.zones.fetch_rollups_for_zone", _fake_fetch_rollups_for_zone)

    with TestClient(app) as client:
        response = client.get(
            f"/journeys/{journey_id}/zones/zone-fp-1/price-rollups?search_type=rent&days=30"
        )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["zone_fingerprint"] == "zone-fp-1"
    assert body[0]["lat"] == -23.55
    assert body[0]["lon"] == -46.63


@pytest.mark.anyio
async def test_create_job_reuses_existing_active_job_for_same_journey_and_type(monkeypatch):
    init_db(os.environ["DATABASE_URL"])
    engine = get_engine()
    journey_id = uuid4()
    enqueued: list[str] = []

    async def _fake_enqueue(job: JobRead) -> None:
        enqueued.append(str(job.id))

    monkeypatch.setattr("modules.jobs.service.enqueue_job", _fake_enqueue)

    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM jobs WHERE journey_id = :journey_id"), {"journey_id": journey_id})
        await conn.execute(text("DELETE FROM journeys WHERE id = :journey_id"), {"journey_id": journey_id})
        await conn.execute(text("INSERT INTO journeys (id) VALUES (:journey_id)"), {"journey_id": journey_id})

    try:
        payload = JobCreate(journey_id=journey_id, job_type=JobType.ZONE_ENRICHMENT)
        first, second = await asyncio.gather(create_job(payload), create_job(payload))

        assert sorted([first.created, second.created]) == [False, True]
        assert first.job.id == second.job.id
        assert enqueued == [str(first.job.id)] or enqueued == [str(second.job.id)]

        async with engine.connect() as conn:
            count_result = await conn.execute(
                text(
                    """
                    SELECT count(*)
                    FROM jobs
                    WHERE journey_id = :journey_id
                      AND job_type = 'zone_enrichment'
                      AND state IN ('pending', 'running', 'retrying')
                    """
                ),
                {"journey_id": journey_id},
            )
            assert int(count_result.scalar_one()) == 1
    finally:
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM jobs WHERE journey_id = :journey_id"), {"journey_id": journey_id})
            await conn.execute(text("DELETE FROM journeys WHERE id = :journey_id"), {"journey_id": journey_id})