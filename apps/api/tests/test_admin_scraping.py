import os
import sys
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

from contracts import AuthUserRead, JobRead, JobState, JobType  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from src.main import app  # noqa: E402


def _user(*, is_superuser: bool) -> AuthUserRead:
    return AuthUserRead(
        id=uuid4(),
        email="dev@example.com" if is_superuser else "user@example.com",
        display_name="Dev" if is_superuser else "User",
        is_active=True,
        is_superuser=is_superuser,
        created_at=datetime.now(tz=timezone.utc),
        role="user",
    )


def _job(state: JobState = JobState.PENDING) -> JobRead:
    return JobRead(
        id=uuid4(),
        journey_id=None,
        job_type=JobType.LISTINGS_PREWARM,
        state=state,
        progress_percent=0,
        current_stage="listings_prewarm",
        cancel_requested_at=None,
        started_at=None,
        finished_at=None,
        worker_id=None,
        result_ref={"trigger": "admin_run_now", "target_count_24h": 1},
        error_code=None,
        error_message=None,
        created_at=datetime.now(tz=timezone.utc),
    )


def _auth_context(user):
    async def _context(*, session_token=None, anonymous_session_id=None):
        return SimpleNamespace(
            user=user,
            session_expires_at=datetime.now(tz=timezone.utc),
            session_token=session_token,
            anonymous_session_id=anonymous_session_id,
        )

    return _context


def test_admin_scraping_requires_superuser(monkeypatch):
    monkeypatch.setattr("api.routes.admin_common.build_request_auth_context", _auth_context(_user(is_superuser=False)))

    with TestClient(app) as client:
        response = client.get("/admin/scraping/overview")

    assert response.status_code == 403
    assert response.json()["detail"] == "Acesso restrito ao desenvolvedor."


def test_admin_scraping_overview_returns_scheduler_state(monkeypatch):
    monkeypatch.setattr("api.routes.admin_common.build_request_auth_context", _auth_context(_user(is_superuser=True)))
    monkeypatch.setattr(
        "api.routes.admin_scraping.get_settings",
        lambda: SimpleNamespace(
            enable_listings_prewarm_scheduler=True,
            listings_prewarm_cron_hour=3,
            listings_prewarm_cron_minute=0,
            listings_prewarm_lookback_hours=24,
            listings_prewarm_limit=100,
        ),
    )
    async def _no_active_job():
        return None

    async def _no_jobs(**_kwargs):
        return [], 0

    async def _no_queue(**_kwargs):
        return []

    monkeypatch.setattr("api.routes.admin_scraping._get_active_prewarm_job", _no_active_job)
    monkeypatch.setattr("api.routes.admin_scraping._list_prewarm_jobs", _no_jobs)
    monkeypatch.setattr("api.routes.admin_scraping._queue_items", _no_queue)

    with TestClient(app) as client:
        response = client.get("/admin/scraping/overview")

    assert response.status_code == 200
    assert response.json()["scheduler_enabled"] is True
    assert response.json()["cron_hour"] == 3
    assert response.json()["queue_count"] == 0


def test_admin_run_now_rejects_active_batch(monkeypatch):
    monkeypatch.setattr("api.routes.admin_common.build_request_auth_context", _auth_context(_user(is_superuser=True)))

    async def _active_job():
        return _job(JobState.RUNNING)

    monkeypatch.setattr("api.routes.admin_scraping._get_active_prewarm_job", _active_job)

    with TestClient(app) as client:
        response = client.post("/admin/scraping/batches/run-now")

    assert response.status_code == 409
    assert response.json()["detail"] == "Já existe uma batelada em execução."


def test_admin_run_now_creates_prewarm_job(monkeypatch):
    sample_job = _job(JobState.PENDING)
    monkeypatch.setattr("api.routes.admin_common.build_request_auth_context", _auth_context(_user(is_superuser=True)))

    async def _no_active_job():
        return None

    monkeypatch.setattr("api.routes.admin_scraping._get_active_prewarm_job", _no_active_job)
    monkeypatch.setattr(
        "api.routes.admin_scraping.get_settings",
        lambda: SimpleNamespace(
            listings_prewarm_lookback_hours=24,
            listings_prewarm_limit=100,
            listings_prewarm_max_address_duration_seconds=60,
        ),
    )

    async def _targets(**_kwargs):
        return [
            {
                "search_location_normalized": "rua teste",
                "search_location_label": "Rua Teste",
                "search_location_type": "address",
                "search_type": "rent",
                "usage_type": "residential",
                "demand_count": 1,
            }
        ]

    async def _create_internal_job(**kwargs):
        assert kwargs["job_type"] == JobType.LISTINGS_PREWARM
        assert kwargs["result_ref"]["trigger"] == "admin_run_now"
        assert len(kwargs["result_ref"]["manual_targets"]) == 1
        return SimpleNamespace(job=sample_job, created=True)

    monkeypatch.setattr("api.routes.admin_scraping.get_prewarm_targets", _targets)
    monkeypatch.setattr("api.routes.admin_scraping.create_internal_job", _create_internal_job)

    with TestClient(app) as client:
        response = client.post("/admin/scraping/batches/run-now")

    assert response.status_code == 202
    body = response.json()
    assert body["job"]["id"] == str(sample_job.id)
    assert body["target_count"] == 1


def test_admin_user_scraping_permission_update(monkeypatch):
    developer = _user(is_superuser=True)
    target_user_id = uuid4()
    monkeypatch.setattr("api.routes.admin_common.build_request_auth_context", _auth_context(developer))

    class _Result:
        def mappings(self):
            return self

        def first(self):
            return {
                "id": target_user_id,
                "email": "morador@example.com",
                "display_name": "Morador",
                "is_active": True,
                "is_superuser": False,
                "can_start_immediate_scraping": True,
                "role": "user",
                "created_at": datetime.now(tz=timezone.utc),
            }

    class _Conn:
        async def execute(self, stmt, params):
            sql = str(stmt)
            assert "can_start_immediate_scraping" in sql
            assert params["user_id"] == target_user_id
            assert params["can_start_immediate_scraping"] is True
            return _Result()

    class _Begin:
        async def __aenter__(self):
            return _Conn()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _Engine:
        def begin(self):
            return _Begin()

    monkeypatch.setattr("api.routes.admin_users.get_engine", lambda: _Engine())

    with TestClient(app) as client:
        response = client.patch(
            f"/admin/users/{target_user_id}/scraping-permission",
            json={"can_start_immediate_scraping": True},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(target_user_id)
    assert body["can_start_immediate_scraping"] is True


def test_admin_user_role_update_rejects_invalid_role(monkeypatch):
    monkeypatch.setattr("api.routes.admin_common.build_request_auth_context", _auth_context(_user(is_superuser=True)))

    with TestClient(app) as client:
        response = client.patch(f"/admin/users/{uuid4()}/role", json={"role": "admin"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Função inválida."
