from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

import httpx

from core.config import get_settings

MERCADO_PAGO_API_BASE_URL = "https://api.mercadopago.com"
_WEBHOOK_TOLERANCE_MS = 5 * 60 * 1000


class MercadoPagoError(Exception):
    pass


class MercadoPagoConfigurationError(MercadoPagoError):
    pass


class MercadoPagoRequestError(MercadoPagoError):
    def __init__(self, message: str, *, status_code: int | None = None, payload: dict | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}


@dataclass(frozen=True)
class MercadoPagoCredentials:
    environment: str
    access_token: str
    public_key: str | None
    webhook_secret: str | None
    webhook_url: str | None
    timeout_seconds: float


def get_mercado_pago_credentials() -> MercadoPagoCredentials:
    settings = get_settings()
    environment = (settings.mercado_pago_environment or "test").strip().lower()
    if environment not in {"test", "live"}:
        raise MercadoPagoConfigurationError("MERCADO_PAGO_ENVIRONMENT deve ser 'test' ou 'live'.")

    if environment == "live":
        access_token = settings.mercado_pago_access_token_live
        public_key = settings.mercado_pago_public_key_live
    else:
        access_token = settings.mercado_pago_access_token_test
        public_key = settings.mercado_pago_public_key_test

    if not access_token:
        raise MercadoPagoConfigurationError(
            f"Access token do Mercado Pago nÃ£o configurado para o ambiente '{environment}'."
        )

    return MercadoPagoCredentials(
        environment=environment,
        access_token=access_token,
        public_key=public_key,
        webhook_secret=settings.mercado_pago_webhook_secret,
        webhook_url=settings.mercado_pago_webhook_url,
        timeout_seconds=settings.mercado_pago_timeout_seconds,
    )


def _should_prefill_checkout_payer(*, environment: str, payer_email: str | None) -> bool:
    normalized_email = (payer_email or "").strip().lower()
    if not normalized_email:
        return False

    # No sandbox, evitar conflito entre o e-mail real do app e a conta buyer
    # autenticada no Checkout Pro durante os testes.
    if environment == "test" and not normalized_email.endswith("@testuser.com"):
        return False

    return True


async def create_pix_payment(
    *,
    amount: Decimal,
    description: str,
    payer_email: str,
    external_reference: str,
    expires_at: datetime,
    payer_first_name: str | None = None,
    payer_last_name: str | None = None,
) -> dict:
    credentials = get_mercado_pago_credentials()
    payload: dict[str, object] = {
        "transaction_amount": float(amount),
        "description": description,
        "payment_method_id": "pix",
        "external_reference": external_reference,
        "date_of_expiration": expires_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "payer": {
            "email": payer_email,
        },
    }

    payer = payload["payer"]
    if isinstance(payer, dict):
        if payer_first_name:
            payer["first_name"] = payer_first_name
        if payer_last_name:
            payer["last_name"] = payer_last_name

    if credentials.webhook_url:
        payload["notification_url"] = credentials.webhook_url

    return await _request(
        "POST",
        "/v1/payments",
        json_body=payload,
        idempotency_key=external_reference,
    )


async def create_checkout_preference(
    *,
    amount: Decimal,
    title: str,
    description: str,
    payer_email: str,
    external_reference: str,
    expires_at: datetime,
    payer_first_name: str | None = None,
    payer_last_name: str | None = None,
    back_url: str | None = None,
) -> dict:
    credentials = get_mercado_pago_credentials()
    payload: dict[str, object] = {
        "items": [
            {
                "id": external_reference,
                "title": title,
                "description": description,
                "quantity": 1,
                "currency_id": "BRL",
                "unit_price": float(amount),
            }
        ],
        "external_reference": external_reference,
        "payment_methods": {
            # Remove apenas os meios offline clássicos, preservando cartão e Pix.
            "excluded_payment_types": [{"id": "ticket"}],
        },
        "expires": True,
        "expiration_date_to": expires_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
    }

    payer = None
    if _should_prefill_checkout_payer(environment=credentials.environment, payer_email=payer_email):
        payload["payer"] = {"email": payer_email}
        payer = payload["payer"]

    if isinstance(payer, dict):
        if payer_first_name:
            payer["name"] = payer_first_name
        if payer_last_name:
            payer["surname"] = payer_last_name

    if credentials.webhook_url:
        payload["notification_url"] = credentials.webhook_url

    if back_url:
        payload["back_urls"] = {
            "success": back_url,
            "pending": back_url,
            "failure": back_url,
        }
        payload["auto_return"] = "approved"

    return await _request(
        "POST",
        "/checkout/preferences",
        json_body=payload,
        idempotency_key=external_reference,
    )


async def get_payment(payment_id: str) -> dict:
    return await _request("GET", f"/v1/payments/{payment_id}")


async def search_payments_by_external_reference(external_reference: str) -> list[dict]:
    payload = await _request(
        "GET",
        "/v1/payments/search",
        query_params={
            "sort": "date_created",
            "criteria": "desc",
            "range": "date_created",
            "begin_date": "NOW-30DAYS",
            "end_date": "NOW",
            "external_reference": external_reference,
        },
    )
    results = payload.get("results")
    if not isinstance(results, list):
        return []
    return [item for item in results if isinstance(item, dict)]


async def cancel_payment(payment_id: str, *, idempotency_key: str) -> dict:
    return await _request(
        "PUT",
        f"/v1/payments/{payment_id}",
        json_body={"status": "cancelled"},
        idempotency_key=idempotency_key,
    )


def verify_webhook_signature(
    *,
    data_id: str | None,
    x_signature: str,
    x_request_id: str | None,
) -> bool:
    credentials = get_mercado_pago_credentials()
    secret = credentials.webhook_secret
    if not secret or not x_signature:
        return False

    ts = None
    signature_hash = None
    for part in x_signature.split(","):
        key, _, value = part.partition("=")
        normalized_key = key.strip().lower()
        normalized_value = value.strip()
        if normalized_key == "ts":
            ts = normalized_value
        elif normalized_key == "v1":
            signature_hash = normalized_value

    if not ts or not signature_hash:
        return False

    try:
        ts_value = int(ts)
    except ValueError:
        return False

    now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    if abs(now_ms - ts_value) > _WEBHOOK_TOLERANCE_MS:
        return False

    template_parts = []
    if data_id:
        template_parts.append(f"id:{data_id}")
    if x_request_id:
        template_parts.append(f"request-id:{x_request_id}")
    template_parts.append(f"ts:{ts}")
    signature_template = ";".join(template_parts) + ";"
    expected = hmac.new(
        secret.encode("utf-8"),
        signature_template.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature_hash)


async def _request(
    method: str,
    path: str,
    *,
    json_body: dict | None = None,
    query_params: dict[str, str] | None = None,
    idempotency_key: str | None = None,
) -> dict:
    credentials = get_mercado_pago_credentials()
    headers = {
        "Authorization": f"Bearer {credentials.access_token}",
        "Accept": "application/json",
    }
    if json_body is not None:
        headers["Content-Type"] = "application/json"
    if idempotency_key:
        headers["X-Idempotency-Key"] = idempotency_key

    async with httpx.AsyncClient(
        base_url=MERCADO_PAGO_API_BASE_URL,
        timeout=httpx.Timeout(credentials.timeout_seconds),
    ) as client:
        response = await client.request(method, path, headers=headers, json=json_body, params=query_params)

    try:
        payload = response.json()
    except ValueError:
        payload = None

    if response.status_code >= 400:
        message = _extract_error_message(payload) or f"Mercado Pago respondeu com HTTP {response.status_code}."
        raise MercadoPagoRequestError(message, status_code=response.status_code, payload=payload or {})

    if not isinstance(payload, dict):
        raise MercadoPagoRequestError("Mercado Pago respondeu com payload invÃ¡lido.", status_code=response.status_code)

    return payload


def _extract_error_message(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None

    for key in ("message", "error_description", "error", "status_detail"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    cause = payload.get("cause")
    if isinstance(cause, list):
        messages = []
        for item in cause:
            if not isinstance(item, dict):
                continue
            description = item.get("description")
            if isinstance(description, str) and description.strip():
                messages.append(description.strip())
        if messages:
            return "; ".join(messages)

    return None
