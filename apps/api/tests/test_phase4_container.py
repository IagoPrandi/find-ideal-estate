from __future__ import annotations

import os
import sys
from pathlib import Path

from dependency_injector import providers

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/find_ideal_estate")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("MAPBOX_ACCESS_TOKEN", "test")
os.environ.setdefault("MAPTILER_API_KEY", "test")
os.environ.setdefault("VALHALLA_URL", "http://localhost:8002")
os.environ.setdefault("OTP_URL", "http://localhost:8080")

from src.core.container import AppContainer  # noqa: E402


def test_container_zone_service_supports_mocked_providers() -> None:
    container = AppContainer()
    container.config.from_dict(
        {
            "valhalla_url": "http://valhalla.test",
            "otp_url": "http://otp.test",
            "http_timeout_seconds": 5.0,
        }
    )
    container.redis_client.override(object())

    fake_valhalla = object()
    fake_otp = object()

    with container.valhalla_adapter.override(providers.Object(fake_valhalla)):
        with container.otp_adapter.override(providers.Object(fake_otp)):
            zone_service = container.zone_service()

    assert zone_service.valhalla_adapter is fake_valhalla
    assert zone_service.otp_adapter is fake_otp


def test_container_transport_service_is_singleton() -> None:
    container = AppContainer()
    first = container.transport_service()
    second = container.transport_service()

    assert first.__class__.__name__ == "TransportService"
    assert first is second
