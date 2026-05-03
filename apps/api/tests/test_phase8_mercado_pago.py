import hashlib
import hmac
import json
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
os.environ.setdefault("PIX_PROVIDER", "mercado_pago")
os.environ.setdefault("MERCADO_PAGO_ENVIRONMENT", "test")
os.environ.setdefault("MERCADO_PAGO_ACCESS_TOKEN_TEST", "test-token")
os.environ.setdefault("MERCADO_PAGO_WEBHOOK_SECRET", "test-webhook-secret")

from contracts import AuthUserRead, PixCheckoutResponse  # noqa: E402
from core.config import get_settings  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from modules.billing.mercado_pago import verify_webhook_signature  # noqa: E402
from src.main import app  # noqa: E402


def _reset_settings_cache() -> None:
    get_settings.cache_clear()


def _auth_user_payload():
    return {
        "id": str(uuid4()),
        "email": "ana@example.com",
        "display_name": "Ana Silva",
        "is_active": True,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
        "role": "user",
    }


def _build_signature(*, secret: str, data_id: str, request_id: str, ts: int) -> str:
    template = f"id:{data_id};request-id:{request_id};ts:{ts};"
    digest = hmac.new(secret.encode("utf-8"), template.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"ts={ts},v1={digest}"


def test_verify_mercado_pago_webhook_signature_valid(monkeypatch):
    monkeypatch.setenv("PIX_PROVIDER", "mercado_pago")
    monkeypatch.setenv("MERCADO_PAGO_ENVIRONMENT", "test")
    monkeypatch.setenv("MERCADO_PAGO_ACCESS_TOKEN_TEST", "test-token")
    monkeypatch.setenv("MERCADO_PAGO_WEBHOOK_SECRET", "segredo-webhook")
    _reset_settings_cache()

    ts = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    signature = _build_signature(
        secret="segredo-webhook",
        data_id="123456",
        request_id="req-123",
        ts=ts,
    )

    assert verify_webhook_signature(
        data_id="123456",
        x_signature=signature,
        x_request_id="req-123",
    )


def test_pix_callback_processes_mercado_pago_notification(monkeypatch):
    monkeypatch.setenv("PIX_PROVIDER", "mercado_pago")
    monkeypatch.setenv("MERCADO_PAGO_ENVIRONMENT", "test")
    monkeypatch.setenv("MERCADO_PAGO_ACCESS_TOKEN_TEST", "test-token")
    monkeypatch.setenv("MERCADO_PAGO_WEBHOOK_SECRET", "segredo-webhook")
    _reset_settings_cache()

    captured = {}

    async def _process(*, notification, query_data_id):
        captured["notification"] = notification
        captured["query_data_id"] = query_data_id

    monkeypatch.setattr("api.routes.billing.process_mercado_pago_webhook_notification", _process)

    payload = {
        "id": "evento-1",
        "type": "payment",
        "action": "payment.updated",
        "data": {"id": "123456"},
    }
    body = json.dumps(payload).encode("utf-8")
    ts = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    signature = _build_signature(
        secret="segredo-webhook",
        data_id="123456",
        request_id="req-123",
        ts=ts,
    )

    with TestClient(app) as client:
        response = client.post(
            "/billing/pix/callback?data.id=123456&type=payment",
            data=body,
            headers={
                "content-type": "application/json",
                "x-signature": signature,
                "x-request-id": "req-123",
            },
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert captured["notification"] == payload
    assert captured["query_data_id"] == "123456"


def test_pix_checkout_passes_authenticated_user_to_service(monkeypatch):
    _reset_settings_cache()
    user = AuthUserRead.model_validate(_auth_user_payload())
    captured = {}

    async def _context(*, session_token=None, anonymous_session_id=None):
        return type(
            "Ctx",
            (),
            {
                "user": user,
                "session_expires_at": datetime.now(tz=timezone.utc),
                "session_token": session_token,
                "anonymous_session_id": anonymous_session_id,
            },
        )()

    async def _create_pix_checkout(*, user_id, plan_slug, payer_email, payer_display_name, payment_type):
        captured["user_id"] = user_id
        captured["plan_slug"] = plan_slug
        captured["payer_email"] = payer_email
        captured["payer_display_name"] = payer_display_name
        captured["payment_type"] = payment_type
        return PixCheckoutResponse(
            payment_id=uuid4(),
            pix_copy_paste="000201",
            qr_code_payload="000201",
            qr_code_image_url="data:image/png;base64,abc",
            ticket_url="https://www.mercadopago.com.br/payments/teste",
            amount_brl="21.99",
            expires_at=datetime.now(tz=timezone.utc),
            status="pending",
        )

    monkeypatch.setattr("api.routes.billing.build_request_auth_context", _context)
    monkeypatch.setattr("api.routes.billing.create_pix_checkout", _create_pix_checkout)

    with TestClient(app) as client:
        response = client.post(
            "/billing/pix/checkout",
            json={"plan_slug": "basico", "payment_type": "plan_activation"},
        )

    assert response.status_code == 201
    assert captured["user_id"] == user.id
    assert captured["plan_slug"] == "basico"
    assert captured["payer_email"] == "ana@example.com"
    assert captured["payer_display_name"] == "Ana Silva"
    assert captured["payment_type"] == "plan_activation"
