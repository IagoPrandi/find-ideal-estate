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

from contracts import AuthUserRead  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from src.main import app  # noqa: E402


def _auth_user_payload():
    return {
        "id": str(uuid4()),
        "email": "ana@example.com",
        "display_name": "Ana",
        "is_active": True,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
    }


def test_me_without_session_returns_guest(monkeypatch):
    async def _context(*, session_token=None, anonymous_session_id=None):
        return type(
            "Ctx",
            (),
            {
                "user": None,
                "session_expires_at": None,
                "session_token": session_token,
                "anonymous_session_id": anonymous_session_id,
            },
        )()

    monkeypatch.setattr("api.routes.auth.build_request_auth_context", _context)

    with TestClient(app) as client:
        response = client.get("/auth/me")

    assert response.status_code == 200
    assert response.json() == {
        "is_authenticated": False,
        "user": None,
        "session_expires_at": None,
    }


def test_register_sets_auth_cookie(monkeypatch):
    user_payload = _auth_user_payload()
    expires_at = datetime(2026, 5, 1, tzinfo=timezone.utc)

    async def _context(*, session_token=None, anonymous_session_id=None):
        return type(
            "Ctx",
            (),
            {
                "user": None,
                "session_expires_at": None,
                "session_token": session_token,
                "anonymous_session_id": "anon-123",
            },
        )()

    async def _register(payload, *, anonymous_session_id=None):
        assert anonymous_session_id == "anon-123"
        assert payload.email == "ana@example.com"
        return AuthUserRead.model_validate(user_payload), "session-token-abc", expires_at

    monkeypatch.setattr("api.routes.auth.build_request_auth_context", _context)
    monkeypatch.setattr("api.routes.auth.register_user", _register)

    with TestClient(app) as client:
        response = client.post(
            "/auth/register",
            json={
                "email": "ana@example.com",
                "password": "senha-super-forte",
                "display_name": "Ana",
            },
        )

    assert response.status_code == 201
    assert response.json()["is_authenticated"] is True
    assert response.json()["user"]["email"] == "ana@example.com"
    assert "auth_session=session-token-abc" in response.headers["set-cookie"]


def test_job_route_requires_accessible_journey(monkeypatch):
    async def _context(*, session_token=None, anonymous_session_id=None):
        return type(
            "Ctx",
            (),
            {
                "user": None,
                "session_expires_at": None,
                "session_token": session_token,
                "anonymous_session_id": "anon-123",
            },
        )()

    async def _journey_access(journey_id, context):
        assert str(journey_id) == "00000000-0000-0000-0000-000000000123"
        return None

    monkeypatch.setattr("api.routes.auth.build_request_auth_context", _context)
    monkeypatch.setattr("api.routes.jobs.get_accessible_journey", _journey_access)

    with TestClient(app) as client:
        response = client.post(
            "/jobs",
            json={
                "journey_id": "00000000-0000-0000-0000-000000000123",
                "job_type": "zone_generation",
            },
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Journey not found"