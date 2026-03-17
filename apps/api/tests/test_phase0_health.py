import os
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/find_ideal_estate")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("MAPBOX_ACCESS_TOKEN", "test")
os.environ.setdefault("MAPTILER_API_KEY", "test")
os.environ.setdefault("VALHALLA_URL", "http://localhost:8002")
os.environ.setdefault("OTP_URL", "http://localhost:8080")

from fastapi.testclient import TestClient  # noqa: E402
from src.main import app  # noqa: E402


def test_health_returns_ok_when_dependencies_are_healthy(monkeypatch):
    async def _db_ok() -> bool:
        return True

    async def _redis_ok() -> bool:
        return True

    monkeypatch.setattr("api.routes.health.db_healthcheck", _db_ok)
    monkeypatch.setattr("api.routes.health.redis_healthcheck", _redis_ok)

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok", "redis": "ok"}


def test_health_reports_degraded_when_one_dependency_fails(monkeypatch):
    async def _db_ok() -> bool:
        return True

    async def _redis_error() -> bool:
        return False

    monkeypatch.setattr("api.routes.health.db_healthcheck", _db_ok)
    monkeypatch.setattr("api.routes.health.redis_healthcheck", _redis_error)

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "degraded", "db": "ok", "redis": "error"}
