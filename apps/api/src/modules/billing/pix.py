from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from contracts import PaymentStatusRead, PixCheckoutResponse
from core.config import get_settings
from core.db import get_engine
from modules.billing.mercado_pago import (
    MercadoPagoConfigurationError,
    MercadoPagoError,
    MercadoPagoRequestError,
    cancel_payment as cancel_mercado_pago_payment,
    create_checkout_preference,
    get_payment as get_mercado_pago_payment,
    search_payments_by_external_reference,
    verify_webhook_signature as verify_mercado_pago_webhook_signature,
)
from modules.credits.service import grant_credits
from modules.plans.service import get_plan_by_slug, invalidate_entitlements_cache
from sqlalchemy import text


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


class PixError(Exception):
    pass


class PaymentNotFoundError(PixError):
    pass


class PaymentAlreadyProcessedError(PixError):
    pass


class PaymentExpiredError(PixError):
    pass


class PaymentNotPaidError(PixError):
    pass


def _json_dumps(payload: dict | None) -> str | None:
    if payload is None:
        return None
    return json.dumps(payload, ensure_ascii=False)


def _build_pix_copy_paste(*, pix_key: str, merchant_name: str, merchant_city: str, amount: Decimal, txid: str) -> str:
    settings = get_settings()
    if settings.pix_copy_paste_payload:
        return settings.pix_copy_paste_payload
    merchant_name_clean = merchant_name[:25].ljust(25)[:25]
    merchant_city_clean = merchant_city[:15].ljust(15)[:15]
    payload = (
        f"000201"
        f"26{_tlv('0014BR.GOV.BCB.PIX' + f'01{len(pix_key):02d}{pix_key}')}"
        f"52040000"
        f"5303986"
        f"54{len(f'{amount:.2f}'):02d}{amount:.2f}"
        f"5802BR"
        f"59{len(merchant_name_clean):02d}{merchant_name_clean}"
        f"60{len(merchant_city_clean):02d}{merchant_city_clean}"
        f"62{_tlv('05' + f'{len(txid):02d}{txid}')}"
        f"6304"
    )
    crc = _crc16(payload)
    return payload + crc


def _tlv(value: str) -> str:
    return f"{len(value):02d}{value}"


def _crc16(data: str) -> str:
    crc = 0xFFFF
    for char in data:
        crc ^= ord(char) << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return format(crc, "04X")


def _split_display_name(display_name: str | None) -> tuple[str | None, str | None]:
    if not display_name:
        return None, None
    parts = [part for part in display_name.strip().split() if part]
    if not parts:
        return None, None
    if len(parts) == 1:
        return parts[0], None
    return parts[0], " ".join(parts[1:])


def _build_qr_code_data_url(qr_code_base64: str | None) -> str | None:
    if not qr_code_base64:
        return None
    if qr_code_base64.startswith("iVBOR"):
        return f"data:image/png;base64,{qr_code_base64}"
    return f"data:image/jpeg;base64,{qr_code_base64}"


def _resolve_provider_status(external_status: str | None, *, expires_at: datetime | None) -> str | None:
    normalized = (external_status or "").strip().lower()
    if normalized == "approved":
        return "paid"
    if normalized in {"cancelled", "canceled", "rejected"}:
        return "cancelled"
    if normalized == "expired":
        return "expired"
    if expires_at is not None and expires_at < _utc_now():
        return "expired"
    return None


async def create_pix_checkout(
    *,
    user_id: UUID,
    plan_slug: str,
    payer_email: str,
    payer_display_name: str | None = None,
    payment_type: str = "plan_activation",
) -> PixCheckoutResponse:
    settings = get_settings()
    plan = await get_plan_by_slug(plan_slug)
    if plan is None or not plan.is_paid:
        raise PixError("Plano inválido ou não requer pagamento.")

    amount = plan.price_brl
    if amount is None or amount <= 0:
        raise PixError("Plano sem valor definido.")

    expiration_minutes = settings.pix_payment_expiration_minutes
    expires_at = _utc_now() + timedelta(minutes=expiration_minutes)
    payment_provider = (settings.pix_provider or "mercado_pago").strip().lower()
    if payment_provider not in {"manual", "mercado_pago"}:
        raise PixError("PIX_PROVIDER inválido. Use 'manual' ou 'mercado_pago'.")

    engine = get_engine()
    async with engine.begin() as conn:
        payment_result = await conn.execute(
            text(
                """
                INSERT INTO payments (
                    user_id,
                    plan_id,
                    payment_provider,
                    payment_method,
                    payment_type,
                    amount_brl,
                    status,
                    external_reference,
                    expires_at
                )
                VALUES (
                    :user_id,
                    :plan_id,
                    :payment_provider,
                    :payment_method,
                    :payment_type,
                    :amount,
                    'pending',
                    :external_reference,
                    :expires_at
                )
                RETURNING id
                """
            ),
            {
                "user_id": user_id,
                "plan_id": plan.id,
                "payment_provider": payment_provider,
                "payment_method": "pix_qr_code" if payment_provider == "manual" else "mercado_pago_checkout",
                "payment_type": payment_type,
                "amount": float(amount),
                "external_reference": None,
                "expires_at": expires_at,
            },
        )
        payment_id = payment_result.scalar_one()

    if payment_provider == "manual":
        return await _create_manual_pix_checkout(
            payment_id=payment_id,
            amount=amount,
            expires_at=expires_at,
        )

    payer_first_name, payer_last_name = _split_display_name(payer_display_name)
    external_reference = str(payment_id)

    try:
        provider_preference = await create_checkout_preference(
            amount=amount,
            title=f"Assinatura {plan.name}",
            description=f"Assinatura {plan.name} - Find Ideal Estate",
            payer_email=payer_email,
            external_reference=external_reference,
            expires_at=expires_at,
            payer_first_name=payer_first_name,
            payer_last_name=payer_last_name,
            back_url=settings.mercado_pago_checkout_back_url,
        )
    except (MercadoPagoConfigurationError, MercadoPagoRequestError) as exc:
        await _cleanup_failed_payment(payment_id)
        raise PixError(str(exc)) from exc
    except MercadoPagoError as exc:
        await _cleanup_failed_payment(payment_id)
        raise PixError("Falha ao criar checkout no Mercado Pago.") from exc

    checkout_url_raw = provider_preference.get("init_point") or provider_preference.get("sandbox_init_point")
    checkout_url = checkout_url_raw.strip() if isinstance(checkout_url_raw, str) else ""
    if not checkout_url:
        await _cleanup_failed_payment(payment_id)
        raise PixError("Mercado Pago não retornou a URL do painel de pagamento.")

    provider_expires_at = _parse_provider_expiration(provider_preference.get("expiration_date_to")) or expires_at

    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    UPDATE payments
                    SET external_reference = :external_reference,
                        expires_at = :expires_at
                    WHERE id = :payment_id
                    """
                ),
                {
                    "payment_id": payment_id,
                    "external_reference": external_reference,
                    "expires_at": provider_expires_at,
                },
            )
            await _upsert_pix_payment_data(
                conn,
                payment_id=payment_id,
                pix_key=None,
                merchant_name="Mercado Pago",
                merchant_city=None,
                qr_code_payload=None,
                pix_copy_paste=None,
                qr_code_image_url=None,
                provider_payload=provider_preference,
            )
    except Exception:
        await _cleanup_failed_payment(payment_id)
        raise

    return PixCheckoutResponse(
        payment_id=payment_id,
        checkout_flow="hosted_checkout",
        checkout_url=checkout_url,
        pix_copy_paste=None,
        qr_code_payload=None,
        qr_code_image_url=None,
        ticket_url=checkout_url,
        amount_brl=amount,
        expires_at=provider_expires_at,
        status="pending",
    )


async def _create_manual_pix_checkout(
    *,
    payment_id: UUID,
    amount: Decimal,
    expires_at: datetime,
) -> PixCheckoutResponse:
    settings = get_settings()
    pix_key = settings.pix_key or ""
    merchant_name = settings.pix_merchant_name or "Find Ideal Estate"
    merchant_city = settings.pix_merchant_city or "Sao Paulo"
    txid = str(payment_id).replace("-", "")[:25]
    copy_paste = _build_pix_copy_paste(
        pix_key=pix_key,
        merchant_name=merchant_name,
        merchant_city=merchant_city,
        amount=amount,
        txid=txid,
    )
    qr_code_image_url = settings.pix_static_qr_code_url

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                UPDATE payments
                SET external_reference = :external_reference
                WHERE id = :payment_id
                """
            ),
            {"payment_id": payment_id, "external_reference": str(payment_id)},
        )
        await _upsert_pix_payment_data(
            conn,
            payment_id=payment_id,
            pix_key=pix_key,
            merchant_name=merchant_name,
            merchant_city=merchant_city,
            qr_code_payload=copy_paste,
            pix_copy_paste=copy_paste,
            qr_code_image_url=qr_code_image_url,
            provider_payload=None,
        )

    return PixCheckoutResponse(
        payment_id=payment_id,
        checkout_flow="pix_qr",
        checkout_url=None,
        pix_copy_paste=copy_paste,
        qr_code_payload=copy_paste,
        qr_code_image_url=qr_code_image_url,
        ticket_url=None,
        amount_brl=amount,
        expires_at=expires_at,
        status="pending",
    )


async def get_payment_status(payment_id: UUID, *, user_id: UUID | None = None) -> PaymentStatusRead:
    row = await _fetch_payment_row(payment_id)
    if row is None:
        raise PaymentNotFoundError("Pagamento não encontrado.")
    if user_id is not None and row["user_id"] != user_id:
        raise PaymentNotFoundError("Pagamento não encontrado.")

    if row["status"] == "pending":
        payment_provider = (row["payment_provider"] or "").strip().lower()
        if payment_provider == "mercado_pago" and row["external_payment_id"]:
            await synchronize_mercado_pago_payment(payment_id)
            row = await _fetch_payment_row(payment_id)
            if row is None:
                raise PaymentNotFoundError("Pagamento não encontrado.")
        elif payment_provider == "mercado_pago" and row["external_reference"]:
            await reconcile_mercado_pago_payment_by_reference(payment_id)
            row = await _fetch_payment_row(payment_id)
            if row is None:
                raise PaymentNotFoundError("Pagamento não encontrado.")
        elif row["expires_at"] and row["expires_at"] < _utc_now():
            await _set_payment_status(payment_id, "expired")
            row = await _fetch_payment_row(payment_id)
            if row is None:
                raise PaymentNotFoundError("Pagamento não encontrado.")

    return _map_payment_status(row)


async def cancel_payment(payment_id: UUID, *, user_id: UUID) -> PaymentStatusRead:
    row = await _fetch_payment_row(payment_id)
    if row is None or row["user_id"] != user_id or row["status"] != "pending":
        raise PaymentNotFoundError("Pagamento não encontrado ou não pode ser cancelado.")

    payment_provider = (row["payment_provider"] or "").strip().lower()
    if payment_provider == "mercado_pago" and row["external_payment_id"]:
        try:
            provider_payment = await cancel_mercado_pago_payment(
                str(row["external_payment_id"]),
                idempotency_key=f"{payment_id}-cancel",
            )
        except MercadoPagoRequestError as exc:
            raise PixError(f"Não foi possível cancelar no Mercado Pago: {exc}") from exc
        except MercadoPagoError as exc:
            raise PixError("Falha ao cancelar pagamento no Mercado Pago.") from exc

        resolved_status = _resolve_provider_status(
            provider_payment.get("status") if isinstance(provider_payment, dict) else None,
            expires_at=row["expires_at"],
        ) or "cancelled"
        await _set_payment_status(payment_id, resolved_status, provider_payload=provider_payment)
    else:
        await _set_payment_status(payment_id, "cancelled")

    updated_row = await _fetch_payment_row(payment_id)
    if updated_row is None:
        raise PaymentNotFoundError("Pagamento não encontrado.")
    return _map_payment_status(updated_row)


async def activate_plan_from_pix(
    payment_id: UUID,
    *,
    verified_externally: bool = False,
    provider_payload: dict | None = None,
) -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                SELECT id, user_id, plan_id, status, expires_at, payment_type, payment_provider
                FROM payments
                WHERE id = :id
                FOR UPDATE
                """
            ),
            {"id": payment_id},
        )
        row = result.mappings().first()
        if row is None:
            raise PaymentNotFoundError("Pagamento não encontrado.")
        if row["status"] == "paid":
            raise PaymentAlreadyProcessedError("Pagamento já processado.")
        if row["payment_provider"] == "mercado_pago" and not verified_externally:
            raise PixError("Pagamento do Mercado Pago precisa ser conciliado antes da ativação.")
        if row["status"] != "pending":
            raise PixError(f"Pagamento em estado inválido: {row['status']}")
        if row["expires_at"] and row["expires_at"] < _utc_now():
            raise PaymentExpiredError("Pagamento expirado.")

        user_id = row["user_id"]
        plan_id = row["plan_id"]

        await conn.execute(
            text("UPDATE payments SET status = 'paid', paid_at = now() WHERE id = :id"),
            {"id": payment_id},
        )
        if provider_payload is not None:
            await _upsert_provider_payload(conn, payment_id=payment_id, provider_payload=provider_payload)

        await conn.execute(
            text(
                """
                UPDATE plan_activations
                SET status = 'replaced', updated_at = now()
                WHERE user_id = :user_id AND status = 'active'
                """
            ),
            {"user_id": user_id},
        )

        await conn.execute(
            text(
                """
                INSERT INTO plan_activations (user_id, plan_id, source_payment_id, status, started_at, ends_at)
                VALUES (:user_id, :plan_id, :payment_id, 'active', now(), now() + interval '30 days')
                """
            ),
            {"user_id": user_id, "plan_id": plan_id, "payment_id": payment_id},
        )

        plan_result = await conn.execute(
            text("SELECT monthly_credits FROM plans WHERE id = :plan_id"),
            {"plan_id": plan_id},
        )
        monthly_credits = plan_result.scalar_one()
        reason = "pix_plan_renewal" if row["payment_type"] == "plan_renewal" else "pix_plan_activation"

        await conn.execute(
            text(
                """
                INSERT INTO user_credits (user_id, plan_id, cycle_credits, monthly_quota, cycle_started_at, cycle_ends_at)
                VALUES (:user_id, :plan_id, :credits, :credits, now(), now() + interval '30 days')
                ON CONFLICT (user_id) DO UPDATE
                SET plan_id = :plan_id,
                    cycle_credits = :credits,
                    monthly_quota = :credits,
                    cycle_started_at = now(),
                    cycle_ends_at = now() + interval '30 days',
                    updated_at = now()
                """
            ),
            {"user_id": user_id, "plan_id": plan_id, "credits": monthly_credits},
        )

        await grant_credits(
            conn,
            user_id=user_id,
            bucket="cycle",
            amount=0,
            reason=reason,
            reference_id=payment_id,
        )

    await invalidate_entitlements_cache(user_id)


async def synchronize_mercado_pago_payment(payment_id: UUID) -> None:
    row = await _fetch_payment_row(payment_id)
    if row is None:
        raise PaymentNotFoundError("Pagamento não encontrado.")
    if row["payment_provider"] != "mercado_pago" or not row["external_payment_id"] or row["status"] == "paid":
        return

    try:
        provider_payment = await get_mercado_pago_payment(str(row["external_payment_id"]))
    except MercadoPagoRequestError as exc:
        raise PixError(f"Não foi possível consultar pagamento no Mercado Pago: {exc}") from exc
    except MercadoPagoError as exc:
        raise PixError("Falha ao consultar pagamento no Mercado Pago.") from exc

    resolved_status = _resolve_provider_status(provider_payment.get("status"), expires_at=row["expires_at"])
    if resolved_status == "paid":
        try:
            await activate_plan_from_pix(
                payment_id,
                verified_externally=True,
                provider_payload=provider_payment,
            )
        except PaymentAlreadyProcessedError:
            return
        return

    if resolved_status in {"cancelled", "expired"}:
        await _set_payment_status(payment_id, resolved_status, provider_payload=provider_payment)
        return

    await _upsert_provider_payload_for_payment(payment_id, provider_payload=provider_payment)


async def reconcile_mercado_pago_payment_by_reference(payment_id: UUID) -> None:
    row = await _fetch_payment_row(payment_id)
    if row is None:
        raise PaymentNotFoundError("Pagamento não encontrado.")
    if row["payment_provider"] != "mercado_pago" or row["status"] == "paid":
        return

    external_reference = str(row["external_reference"] or "").strip()
    if not external_reference:
        return

    try:
        payments = await search_payments_by_external_reference(external_reference)
    except MercadoPagoRequestError as exc:
        raise PixError(f"Não foi possível consultar pagamentos no Mercado Pago: {exc}") from exc
    except MercadoPagoError as exc:
        raise PixError("Falha ao consultar pagamentos no Mercado Pago.") from exc

    for provider_payment in payments:
        provider_reference = str(provider_payment.get("external_reference") or "").strip()
        provider_payment_id = provider_payment.get("id")
        if provider_reference != external_reference or provider_payment_id is None:
            continue

        await _link_external_payment_to_internal_payment(
            payment_id=payment_id,
            external_payment_id=str(provider_payment_id),
            provider_payload=provider_payment,
        )
        await synchronize_mercado_pago_payment(payment_id)
        return


async def process_mercado_pago_webhook_notification(
    *,
    notification: dict,
    query_data_id: str | None,
) -> None:
    event_id_raw = notification.get("id")
    event_id = str(event_id_raw) if event_id_raw is not None else None
    event_type = str(notification.get("action") or notification.get("type") or "payment.updated")
    external_payment_id = query_data_id
    if not external_payment_id:
        data = notification.get("data")
        if isinstance(data, dict) and data.get("id") is not None:
            external_payment_id = str(data["id"])

    webhook_event_id, already_processed = await _begin_webhook_event(
        provider="mercado_pago",
        event_id=event_id,
        event_type=event_type,
        payload=notification,
    )
    if already_processed:
        return

    try:
        if str(notification.get("type") or "").lower() != "payment" or not external_payment_id:
            await _complete_webhook_event(webhook_event_id)
            return

        payment_row = await _fetch_payment_row_by_external_id(external_payment_id)
        if payment_row is None:
            provider_payment = await get_mercado_pago_payment(external_payment_id)
            external_reference = str(provider_payment.get("external_reference") or "")
            payment_row = await _fetch_payment_row_by_reference(external_reference)
            if payment_row is not None:
                await _link_external_payment_to_internal_payment(
                    payment_id=payment_row["id"],
                    external_payment_id=external_payment_id,
                    provider_payload=provider_payment,
                )

        if payment_row is None:
            await _complete_webhook_event(webhook_event_id)
            return

        await synchronize_mercado_pago_payment(payment_row["id"])
        await _complete_webhook_event(webhook_event_id)
    except Exception as exc:
        await _fail_webhook_event(webhook_event_id, str(exc))
        raise


def verify_pix_callback_signature(body: bytes, signature: str, *, data_id: str | None, request_id: str | None) -> bool:
    settings = get_settings()
    provider = (settings.pix_provider or "mercado_pago").strip().lower()
    if provider == "mercado_pago":
        return verify_mercado_pago_webhook_signature(
            data_id=data_id,
            x_signature=signature,
            x_request_id=request_id,
        )

    secret = settings.pix_callback_secret
    if not secret:
        return False

    import hashlib
    import hmac

    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _parse_provider_expiration(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _map_payment_status(row) -> PaymentStatusRead:
    return PaymentStatusRead(
        id=row["id"],
        status=row["status"],
        payment_provider=row["payment_provider"],
        payment_type=row["payment_type"],
        amount_brl=Decimal(str(row["amount_brl"])),
        plan_id=row["plan_id"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
        paid_at=row["paid_at"],
    )


async def _fetch_payment_row(payment_id: UUID):
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                """
                SELECT id, user_id, plan_id, payment_provider, payment_method, payment_type,
                       amount_brl, status, external_reference, external_payment_id,
                       created_at, expires_at, paid_at, cancelled_at
                FROM payments
                WHERE id = :payment_id
                """
            ),
            {"payment_id": payment_id},
        )
        return result.mappings().first()


async def _fetch_payment_row_by_external_id(external_payment_id: str):
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                """
                SELECT id, user_id, plan_id, payment_provider, payment_method, payment_type,
                       amount_brl, status, external_reference, external_payment_id,
                       created_at, expires_at, paid_at, cancelled_at
                FROM payments
                WHERE external_payment_id = :external_payment_id
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"external_payment_id": external_payment_id},
        )
        return result.mappings().first()


async def _fetch_payment_row_by_reference(external_reference: str):
    if not external_reference:
        return None
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                """
                SELECT id, user_id, plan_id, payment_provider, payment_method, payment_type,
                       amount_brl, status, external_reference, external_payment_id,
                       created_at, expires_at, paid_at, cancelled_at
                FROM payments
                WHERE external_reference = :external_reference
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"external_reference": external_reference},
        )
        return result.mappings().first()


async def _cleanup_failed_payment(payment_id: UUID) -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM payments WHERE id = :payment_id"), {"payment_id": payment_id})


async def _set_payment_status(payment_id: UUID, status_value: str, *, provider_payload: dict | None = None) -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                UPDATE payments
                SET status = :status,
                    cancelled_at = CASE WHEN :status = 'cancelled' THEN now() ELSE cancelled_at END
                WHERE id = :payment_id
                """
            ),
            {"payment_id": payment_id, "status": status_value},
        )
        if provider_payload is not None:
            await _upsert_provider_payload(conn, payment_id=payment_id, provider_payload=provider_payload)


async def _upsert_pix_payment_data(
    conn,
    *,
    payment_id: UUID,
    pix_key: str | None,
    merchant_name: str | None,
    merchant_city: str | None,
    qr_code_payload: str | None,
    pix_copy_paste: str | None,
    qr_code_image_url: str | None,
    provider_payload: dict | None,
) -> None:
    update_result = await conn.execute(
        text(
            """
            UPDATE pix_payment_data
            SET pix_key = :pix_key,
                merchant_name = :merchant_name,
                merchant_city = :merchant_city,
                qr_code_payload = :qr_code_payload,
                pix_copy_paste = :pix_copy_paste,
                qr_code_image_url = :qr_code_image_url,
                provider_payload = CAST(:provider_payload AS JSONB)
            WHERE payment_id = :payment_id
            """
        ),
        {
            "payment_id": payment_id,
            "pix_key": pix_key,
            "merchant_name": merchant_name,
            "merchant_city": merchant_city,
            "qr_code_payload": qr_code_payload,
            "pix_copy_paste": pix_copy_paste,
            "qr_code_image_url": qr_code_image_url,
            "provider_payload": _json_dumps(provider_payload),
        },
    )
    if update_result.rowcount:
        return

    await conn.execute(
        text(
            """
            INSERT INTO pix_payment_data (
                payment_id,
                pix_key,
                merchant_name,
                merchant_city,
                qr_code_payload,
                pix_copy_paste,
                qr_code_image_url,
                provider_payload
            )
            VALUES (
                :payment_id,
                :pix_key,
                :merchant_name,
                :merchant_city,
                :qr_code_payload,
                :pix_copy_paste,
                :qr_code_image_url,
                CAST(:provider_payload AS JSONB)
            )
            """
        ),
        {
            "payment_id": payment_id,
            "pix_key": pix_key,
            "merchant_name": merchant_name,
            "merchant_city": merchant_city,
            "qr_code_payload": qr_code_payload,
            "pix_copy_paste": pix_copy_paste,
            "qr_code_image_url": qr_code_image_url,
            "provider_payload": _json_dumps(provider_payload),
        },
    )


async def _upsert_provider_payload(conn, *, payment_id: UUID, provider_payload: dict) -> None:
    qr_data = ((provider_payload.get("point_of_interaction") or {}).get("transaction_data") or {})
    await _upsert_pix_payment_data(
        conn,
        payment_id=payment_id,
        pix_key=None,
        merchant_name="Mercado Pago",
        merchant_city=None,
        qr_code_payload=qr_data.get("qr_code"),
        pix_copy_paste=qr_data.get("qr_code"),
        qr_code_image_url=_build_qr_code_data_url(qr_data.get("qr_code_base64")),
        provider_payload=provider_payload,
    )


async def _upsert_provider_payload_for_payment(payment_id: UUID, *, provider_payload: dict) -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await _upsert_provider_payload(conn, payment_id=payment_id, provider_payload=provider_payload)


async def _link_external_payment_to_internal_payment(
    *,
    payment_id: UUID,
    external_payment_id: str,
    provider_payload: dict,
) -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                UPDATE payments
                SET external_payment_id = :external_payment_id
                WHERE id = :payment_id
                """
            ),
            {
                "payment_id": payment_id,
                "external_payment_id": external_payment_id,
            },
        )
        await _upsert_provider_payload(conn, payment_id=payment_id, provider_payload=provider_payload)


async def _begin_webhook_event(*, provider: str, event_id: str | None, event_type: str, payload: dict) -> tuple[UUID, bool]:
    engine = get_engine()
    async with engine.begin() as conn:
        insert_result = await conn.execute(
            text(
                """
                INSERT INTO webhook_events (provider, event_id, event_type, payload, processed)
                VALUES (:provider, :event_id, :event_type, CAST(:payload AS JSONB), false)
                ON CONFLICT (provider, event_id) DO NOTHING
                RETURNING id
                """
            ),
            {
                "provider": provider,
                "event_id": event_id,
                "event_type": event_type,
                "payload": _json_dumps(payload),
            },
        )
        inserted_id = insert_result.scalar_one_or_none()
        if inserted_id is not None:
            return inserted_id, False

        existing_result = await conn.execute(
            text(
                """
                SELECT id, processed
                FROM webhook_events
                WHERE provider = :provider AND event_id = :event_id
                LIMIT 1
                """
            ),
            {"provider": provider, "event_id": event_id},
        )
        existing_row = existing_result.mappings().one()
        return existing_row["id"], bool(existing_row["processed"])


async def _complete_webhook_event(webhook_event_id: UUID) -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                UPDATE webhook_events
                SET processed = true,
                    processed_at = now(),
                    error = NULL
                WHERE id = :id
                """
            ),
            {"id": webhook_event_id},
        )


async def _fail_webhook_event(webhook_event_id: UUID, error_message: str) -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                UPDATE webhook_events
                SET error = :error
                WHERE id = :id
                """
            ),
            {"id": webhook_event_id, "error": error_message[:1000]},
        )
