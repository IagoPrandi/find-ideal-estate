import asyncio
import hashlib
import hmac
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
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
from modules.billing.mercado_pago import (  # noqa: E402
    create_checkout_preference,
    search_payments_by_external_reference,
    verify_webhook_signature,
)
from modules.billing.pix import PixError, get_payment_status  # noqa: E402
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
            checkout_flow="hosted_checkout",
            checkout_url="https://www.mercadopago.com.br/checkout/teste",
            pix_copy_paste=None,
            qr_code_payload=None,
            qr_code_image_url=None,
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


def test_checkout_preference_omits_payer_in_test_for_non_testuser_email(monkeypatch):
    monkeypatch.setenv("MERCADO_PAGO_ENVIRONMENT", "test")
    monkeypatch.setenv("MERCADO_PAGO_ACCESS_TOKEN_TEST", "test-token")
    _reset_settings_cache()

    captured = {}

    async def _request(method, path, *, json_body=None, idempotency_key=None):
        captured["method"] = method
        captured["path"] = path
        captured["json_body"] = json_body
        captured["idempotency_key"] = idempotency_key
        return {"id": "pref-test", "sandbox_init_point": "https://sandbox.mercadopago.com/test"}

    monkeypatch.setattr("modules.billing.mercado_pago._request", _request)

    response = asyncio.run(
        create_checkout_preference(
            amount=Decimal("21.99"),
            title="Assinatura Básico",
            description="Assinatura Básico - Find Ideal Estate",
            payer_email="ana@example.com",
            external_reference="ref-123",
            expires_at=datetime.now(tz=timezone.utc),
            payer_first_name="Ana",
            payer_last_name="Silva",
        )
    )

    assert response["id"] == "pref-test"
    assert captured["method"] == "POST"
    assert captured["path"] == "/checkout/preferences"
    assert captured["idempotency_key"] == "ref-123"
    assert "payer" not in captured["json_body"]


def test_checkout_preference_keeps_payer_in_test_for_testuser_email(monkeypatch):
    monkeypatch.setenv("MERCADO_PAGO_ENVIRONMENT", "test")
    monkeypatch.setenv("MERCADO_PAGO_ACCESS_TOKEN_TEST", "test-token")
    _reset_settings_cache()

    captured = {}

    async def _request(method, path, *, json_body=None, idempotency_key=None):
        captured["json_body"] = json_body
        return {"id": "pref-test", "sandbox_init_point": "https://sandbox.mercadopago.com/test"}

    monkeypatch.setattr("modules.billing.mercado_pago._request", _request)

    asyncio.run(
        create_checkout_preference(
            amount=Decimal("21.99"),
            title="Assinatura Básico",
            description="Assinatura Básico - Find Ideal Estate",
            payer_email="test_user_br@testuser.com",
            external_reference="ref-456",
            expires_at=datetime.now(tz=timezone.utc),
            payer_first_name="Teste",
            payer_last_name="Comprador",
        )
    )

    assert captured["json_body"]["payer"] == {
        "email": "test_user_br@testuser.com",
        "name": "Teste",
        "surname": "Comprador",
    }


def test_search_payments_by_external_reference_uses_search_endpoint(monkeypatch):
    captured = {}

    async def _request(method, path, *, json_body=None, query_params=None, idempotency_key=None):
        captured["method"] = method
        captured["path"] = path
        captured["query_params"] = query_params
        return {"results": [{"id": 123, "external_reference": "ref-789"}]}

    monkeypatch.setattr("modules.billing.mercado_pago._request", _request)

    results = asyncio.run(search_payments_by_external_reference("ref-789"))

    assert results == [{"id": 123, "external_reference": "ref-789"}]
    assert captured["method"] == "GET"
    assert captured["path"] == "/v1/payments/search"
    assert captured["query_params"] == {
        "sort": "date_created",
        "criteria": "desc",
        "range": "date_created",
        "begin_date": "NOW-30DAYS",
        "end_date": "NOW",
        "external_reference": "ref-789",
    }


def test_get_payment_status_reconciles_mercado_pago_payment_by_reference(monkeypatch):
    payment_id = uuid4()
    pending_row = {
        "id": payment_id,
        "user_id": uuid4(),
        "plan_id": uuid4(),
        "payment_provider": "mercado_pago",
        "payment_method": "mercado_pago_checkout",
        "payment_type": "plan_activation",
        "amount_brl": Decimal("21.99"),
        "status": "pending",
        "external_reference": str(payment_id),
        "external_payment_id": None,
        "created_at": datetime.now(tz=timezone.utc),
        "expires_at": datetime.now(tz=timezone.utc),
        "paid_at": None,
        "cancelled_at": None,
    }
    paid_row = dict(pending_row)
    paid_row["status"] = "paid"
    paid_row["external_payment_id"] = "987654321"
    paid_row["paid_at"] = datetime.now(tz=timezone.utc)

    state = {"status": "pending", "linked": None, "synchronized": []}

    async def _fetch_payment_row(_payment_id):
        return pending_row if state["status"] == "pending" else paid_row

    async def _search(external_reference):
        assert external_reference == str(payment_id)
        return [{"id": 987654321, "external_reference": str(payment_id), "status": "approved"}]

    async def _link(*, payment_id, external_payment_id, provider_payload):
        state["linked"] = {
            "payment_id": payment_id,
            "external_payment_id": external_payment_id,
            "provider_payload": provider_payload,
        }

    async def _synchronize(_payment_id):
        state["synchronized"].append(_payment_id)
        state["status"] = "paid"

    monkeypatch.setattr("modules.billing.pix._fetch_payment_row", _fetch_payment_row)
    monkeypatch.setattr("modules.billing.pix.search_payments_by_external_reference", _search)
    monkeypatch.setattr("modules.billing.pix._link_external_payment_to_internal_payment", _link)
    monkeypatch.setattr("modules.billing.pix.synchronize_mercado_pago_payment", _synchronize)

    status = asyncio.run(get_payment_status(payment_id))

    assert status.status == "paid"
    assert state["linked"] == {
        "payment_id": payment_id,
        "external_payment_id": "987654321",
        "provider_payload": {"id": 987654321, "external_reference": str(payment_id), "status": "approved"},
    }
    assert state["synchronized"] == [payment_id]


def test_get_payment_returns_bad_request_for_pix_reconciliation_error(monkeypatch):
    _reset_settings_cache()
    user = AuthUserRead.model_validate(_auth_user_payload())

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

    async def _get_payment_status(payment_id, *, user_id=None):
        raise PixError("falha de conciliação")

    monkeypatch.setattr("api.routes.billing.build_request_auth_context", _context)
    monkeypatch.setattr("api.routes.billing.get_payment_status", _get_payment_status)

    with TestClient(app) as client:
        response = client.get(f"/billing/payments/{uuid4()}")

    assert response.status_code == 400
    assert response.json() == {"detail": "falha de conciliação"}
