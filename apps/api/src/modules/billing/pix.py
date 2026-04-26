from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from contracts import PaymentStatusRead, PixCheckoutResponse
from core.config import get_settings
from core.db import get_engine
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


def _build_pix_copy_paste(*, pix_key: str, merchant_name: str, merchant_city: str, amount: Decimal, txid: str) -> str:
    settings = get_settings()
    if settings.pix_copy_paste_payload:
        return settings.pix_copy_paste_payload
    # EMV Pix payload (simplified static format for manual provider)
    # Real dynamic QR would be generated via the PSP API
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


async def create_pix_checkout(
    *,
    user_id: UUID,
    plan_slug: str,
    payment_type: str = "plan_activation",
) -> PixCheckoutResponse:
    settings = get_settings()
    plan = await get_plan_by_slug(plan_slug)
    if plan is None or not plan.is_paid:
        raise PixError("Plano inválido ou não requer pagamento.")

    amount = plan.price_brl
    if amount is None or amount <= 0:
        raise PixError("Plano sem valor definido.")

    pix_key = settings.pix_key or ""
    merchant_name = settings.pix_merchant_name or "Find Ideal Estate"
    merchant_city = settings.pix_merchant_city or "Sao Paulo"
    expiration_minutes = settings.pix_payment_expiration_minutes
    expires_at = _utc_now() + timedelta(minutes=expiration_minutes)

    engine = get_engine()
    async with engine.begin() as conn:
        payment_result = await conn.execute(
            text("""
                INSERT INTO payments (user_id, plan_id, payment_provider, payment_method, payment_type, amount_brl, status, expires_at)
                VALUES (:user_id, :plan_id, 'pix', 'pix_qr_code', :payment_type, :amount, 'pending', :expires_at)
                RETURNING id
            """),
            {
                "user_id": user_id,
                "plan_id": plan.id,
                "payment_type": payment_type,
                "amount": float(amount),
                "expires_at": expires_at,
            },
        )
        payment_id = payment_result.scalar_one()

        txid = str(payment_id).replace("-", "")[:25]
        copy_paste = _build_pix_copy_paste(
            pix_key=pix_key,
            merchant_name=merchant_name,
            merchant_city=merchant_city,
            amount=amount,
            txid=txid,
        )
        qr_code_image_url = settings.pix_static_qr_code_url

        await conn.execute(
            text("""
                INSERT INTO pix_payment_data (payment_id, pix_key, merchant_name, merchant_city, qr_code_payload, pix_copy_paste, qr_code_image_url)
                VALUES (:payment_id, :pix_key, :merchant_name, :merchant_city, :qr_code_payload, :pix_copy_paste, :qr_code_image_url)
            """),
            {
                "payment_id": payment_id,
                "pix_key": pix_key,
                "merchant_name": merchant_name,
                "merchant_city": merchant_city,
                "qr_code_payload": copy_paste,
                "pix_copy_paste": copy_paste,
                "qr_code_image_url": qr_code_image_url,
            },
        )

    return PixCheckoutResponse(
        payment_id=payment_id,
        pix_copy_paste=copy_paste,
        qr_code_payload=copy_paste,
        qr_code_image_url=qr_code_image_url,
        amount_brl=amount,
        expires_at=expires_at,
        status="pending",
    )


async def get_payment_status(payment_id: UUID, *, user_id: UUID | None = None) -> PaymentStatusRead:
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text("""
                SELECT id, user_id, plan_id, payment_provider, payment_method, payment_type,
                       amount_brl, status, created_at, expires_at, paid_at
                FROM payments
                WHERE id = :payment_id
            """),
            {"payment_id": payment_id},
        )
        row = result.mappings().first()
    if row is None:
        raise PaymentNotFoundError("Pagamento não encontrado.")
    if user_id is not None and row["user_id"] != user_id:
        raise PaymentNotFoundError("Pagamento não encontrado.")

    # auto-expire
    if row["status"] == "pending" and row["expires_at"] and row["expires_at"] < _utc_now():
        engine2 = get_engine()
        async with engine2.begin() as conn2:
            await conn2.execute(
                text("UPDATE payments SET status = 'expired' WHERE id = :id AND status = 'pending'"),
                {"id": payment_id},
            )
        return PaymentStatusRead(
            id=payment_id,
            status="expired",
            payment_provider=row["payment_provider"],
            payment_type=row["payment_type"],
            amount_brl=Decimal(str(row["amount_brl"])),
            plan_id=row["plan_id"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            paid_at=None,
        )

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


async def cancel_payment(payment_id: UUID, *, user_id: UUID) -> PaymentStatusRead:
    engine = get_engine()
    async with engine.begin() as conn:
        result = await conn.execute(
            text("""
                UPDATE payments
                SET status = 'cancelled', cancelled_at = now()
                WHERE id = :id AND user_id = :user_id AND status = 'pending'
                RETURNING id, plan_id, payment_provider, payment_type, amount_brl, status, created_at, expires_at, paid_at
            """),
            {"id": payment_id, "user_id": user_id},
        )
        row = result.mappings().first()
    if row is None:
        raise PaymentNotFoundError("Pagamento não encontrado ou não pode ser cancelado.")
    return PaymentStatusRead(
        id=row["id"],
        status=row["status"],
        payment_provider=row["payment_provider"],
        payment_type=row["payment_type"],
        amount_brl=Decimal(str(row["amount_brl"])),
        plan_id=row["plan_id"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
        paid_at=None,
    )


async def activate_plan_from_pix(payment_id: UUID) -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        result = await conn.execute(
            text("""
                SELECT id, user_id, plan_id, status, expires_at, payment_type
                FROM payments
                WHERE id = :id
                FOR UPDATE
            """),
            {"id": payment_id},
        )
        row = result.mappings().first()
        if row is None:
            raise PaymentNotFoundError("Pagamento não encontrado.")
        if row["status"] == "paid":
            raise PaymentAlreadyProcessedError("Pagamento já processado.")
        if row["status"] != "pending":
            raise PixError(f"Pagamento em estado inválido: {row['status']}")
        if row["expires_at"] and row["expires_at"] < _utc_now():
            raise PaymentExpiredError("Pagamento expirado.")

        user_id = row["user_id"]
        plan_id = row["plan_id"]

        # Mark payment as paid
        await conn.execute(
            text("UPDATE payments SET status = 'paid', paid_at = now() WHERE id = :id"),
            {"id": payment_id},
        )

        # Expire any existing active activations
        await conn.execute(
            text("""
                UPDATE plan_activations
                SET status = 'replaced', updated_at = now()
                WHERE user_id = :user_id AND status = 'active'
            """),
            {"user_id": user_id},
        )

        # Create new activation
        await conn.execute(
            text("""
                INSERT INTO plan_activations (user_id, plan_id, source_payment_id, status, started_at, ends_at)
                VALUES (:user_id, :plan_id, :payment_id, 'active', now(), now() + interval '30 days')
            """),
            {"user_id": user_id, "plan_id": plan_id, "payment_id": payment_id},
        )

        # Get plan monthly credits
        plan_result = await conn.execute(
            text("SELECT monthly_credits FROM plans WHERE id = :plan_id"),
            {"plan_id": plan_id},
        )
        monthly_credits = plan_result.scalar_one()

        reason = "pix_plan_renewal" if row["payment_type"] == "plan_renewal" else "pix_plan_activation"

        # Upsert user_credits
        await conn.execute(
            text("""
                INSERT INTO user_credits (user_id, plan_id, cycle_credits, monthly_quota, cycle_started_at, cycle_ends_at)
                VALUES (:user_id, :plan_id, :credits, :credits, now(), now() + interval '30 days')
                ON CONFLICT (user_id) DO UPDATE
                SET plan_id = :plan_id,
                    cycle_credits = :credits,
                    monthly_quota = :credits,
                    cycle_started_at = now(),
                    cycle_ends_at = now() + interval '30 days',
                    updated_at = now()
            """),
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


def verify_pix_callback_signature(body: bytes, signature: str) -> bool:
    settings = get_settings()
    secret = settings.pix_callback_secret
    if not secret:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()  # type: ignore[attr-defined]
    return hmac.compare_digest(expected, signature)
