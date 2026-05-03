from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from contracts import AccountCreditsRead
from core.db import get_engine
from core.redis import get_redis
from sqlalchemy import text

ANONYMOUS_CREDIT_KEY = "credit:session:{session_id}"
ANONYMOUS_CREDIT_DEFAULT = 300
ANONYMOUS_CREDIT_TTL = 7 * 24 * 3600  # 7 days in seconds

STEP_COSTS: dict[str, int] = {
    "zone_generation": 20,
    "zone_enrichment": 20,
    "listings_cache": 20,
    "report": 20,
}


class InsufficientCreditsError(Exception):
    def __init__(self, required: int, balance: int, upgrade_reason: str = "upgrade_required") -> None:
        self.required = required
        self.balance = balance
        self.upgrade_reason = upgrade_reason
        super().__init__(f"Créditos insuficientes: necessário={required}, saldo={balance}")


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


async def _resolve_effective_credit_plan(conn, *, user_id: UUID) -> dict | None:
    active_plan_result = await conn.execute(
        text("""
            SELECT p.id, p.monthly_credits, pe.cycle_length_days
            FROM plan_activations pa
            JOIN plans p ON p.id = pa.plan_id
            JOIN plan_entitlements pe ON pe.plan_id = p.id
            WHERE pa.user_id = :user_id
              AND pa.status = 'active'
              AND pa.ends_at > now()
            ORDER BY p.display_order DESC
            LIMIT 1
        """),
        {"user_id": user_id},
    )
    active_plan = active_plan_result.mappings().first()
    if active_plan is not None:
        return active_plan

    fallback_plan_result = await conn.execute(
        text("""
            SELECT p.id, p.monthly_credits, pe.cycle_length_days
            FROM plans p
            JOIN plan_entitlements pe ON pe.plan_id = p.id
            WHERE p.slug = 'free'
            LIMIT 1
        """)
    )
    return fallback_plan_result.mappings().first()


async def _refresh_credit_cycle_if_needed(conn, *, user_id: UUID, lock_row: bool) -> dict | None:
    lock_sql = "FOR UPDATE" if lock_row else ""
    result = await conn.execute(
        text(f"""
            SELECT plan_id, cycle_credits, rollover_balance, legacy_balance,
                   cycle_started_at, cycle_ends_at, monthly_quota
            FROM user_credits
            WHERE user_id = :user_id
            {lock_sql}
        """),
        {"user_id": user_id},
    )
    row = result.mappings().first()
    if row is None:
        return None

    now = _utc_now()
    cycle_ends_at = row["cycle_ends_at"]
    if cycle_ends_at is None or cycle_ends_at > now:
        return dict(row)

    effective_plan = await _resolve_effective_credit_plan(conn, user_id=user_id)
    monthly_quota = (
        int(effective_plan["monthly_credits"])
        if effective_plan is not None and effective_plan["monthly_credits"] is not None
        else int(row["monthly_quota"] or 0)
    )
    cycle_length_days = (
        int(effective_plan["cycle_length_days"])
        if effective_plan is not None and effective_plan["cycle_length_days"] is not None
        else 30
    )
    new_plan_id = effective_plan["id"] if effective_plan is not None else row["plan_id"]
    new_cycle_ends_at = now + timedelta(days=cycle_length_days)
    legacy_balance = int(row["legacy_balance"] or 0)
    final_balance = monthly_quota + legacy_balance
    cycle_delta = monthly_quota - int(row["cycle_credits"] or 0)
    rollover_balance = int(row["rollover_balance"] or 0)

    await conn.execute(
        text("""
            UPDATE user_credits
            SET plan_id = :plan_id,
                cycle_credits = :cycle_credits,
                rollover_balance = 0,
                monthly_quota = :monthly_quota,
                cycle_started_at = :cycle_started_at,
                cycle_ends_at = :cycle_ends_at,
                updated_at = now()
            WHERE user_id = :user_id
        """),
        {
            "user_id": user_id,
            "plan_id": new_plan_id,
            "cycle_credits": monthly_quota,
            "monthly_quota": monthly_quota,
            "cycle_started_at": now,
            "cycle_ends_at": new_cycle_ends_at,
        },
    )

    if cycle_delta != 0:
        await conn.execute(
            text("""
                INSERT INTO credit_ledger (user_id, bucket, delta, reason, reference_id, balance_after)
                VALUES (:user_id, 'cycle', :delta, 'monthly_cycle_reset', NULL, :balance_after)
            """),
            {"user_id": user_id, "delta": cycle_delta, "balance_after": final_balance},
        )

    if rollover_balance != 0:
        await conn.execute(
            text("""
                INSERT INTO credit_ledger (user_id, bucket, delta, reason, reference_id, balance_after)
                VALUES (:user_id, 'rollover', :delta, 'monthly_cycle_reset', NULL, :balance_after)
            """),
            {"user_id": user_id, "delta": -rollover_balance, "balance_after": final_balance},
        )

    return {
        "plan_id": new_plan_id,
        "cycle_credits": monthly_quota,
        "rollover_balance": 0,
        "legacy_balance": legacy_balance,
        "cycle_started_at": now,
        "cycle_ends_at": new_cycle_ends_at,
        "monthly_quota": monthly_quota,
    }


async def get_or_init_anonymous_credits(session_id: str) -> int:
    redis = get_redis()
    key = ANONYMOUS_CREDIT_KEY.format(session_id=session_id)
    raw = await redis.get(key)
    if raw is None:
        await redis.set(key, ANONYMOUS_CREDIT_DEFAULT, ex=ANONYMOUS_CREDIT_TTL)
        return ANONYMOUS_CREDIT_DEFAULT
    return int(raw)


async def consume_anonymous_credits(session_id: str, amount: int) -> int:
    redis = get_redis()
    key = ANONYMOUS_CREDIT_KEY.format(session_id=session_id)
    current = await get_or_init_anonymous_credits(session_id)
    if current < amount:
        raise InsufficientCreditsError(required=amount, balance=current)
    new_balance = await redis.decrby(key, amount)
    return int(new_balance)


async def delete_anonymous_credits(session_id: str) -> None:
    redis = get_redis()
    key = ANONYMOUS_CREDIT_KEY.format(session_id=session_id)
    await redis.delete(key)


async def get_user_credits(user_id: UUID) -> AccountCreditsRead:
    engine = get_engine()
    async with engine.begin() as conn:
        row = await _refresh_credit_cycle_if_needed(conn, user_id=user_id, lock_row=True)
    if row is None:
        return AccountCreditsRead(cycle=0, rollover=0, legacy=0, total=0, cycle_ends_at=None, monthly_quota=None)
    cycle = int(row["cycle_credits"] or 0)
    rollover = int(row["rollover_balance"] or 0)
    legacy = int(row["legacy_balance"] or 0)
    return AccountCreditsRead(
        cycle=cycle,
        rollover=rollover,
        legacy=legacy,
        total=cycle + rollover + legacy,
        cycle_ends_at=row["cycle_ends_at"],
        monthly_quota=row["monthly_quota"],
    )


async def check_and_consume(user_id: UUID, step: str, *, reference_id: UUID | None = None, bypass: bool = False) -> AccountCreditsRead:
    if bypass:
        return AccountCreditsRead(
            cycle=999999,
            rollover=0,
            legacy=0,
            total=999999,
            cycle_ends_at=None,
            monthly_quota=999999,
        )
    cost = STEP_COSTS.get(step, 20)
    engine = get_engine()
    async with engine.begin() as conn:
        row = await _refresh_credit_cycle_if_needed(conn, user_id=user_id, lock_row=True)
        if row is None:
            raise InsufficientCreditsError(required=cost, balance=0)

        cycle = int(row["cycle_credits"] or 0)
        rollover = int(row["rollover_balance"] or 0)
        legacy = int(row["legacy_balance"] or 0)
        total = cycle + rollover + legacy

        if total < cost:
            raise InsufficientCreditsError(required=cost, balance=total)

        # FIFO: cycle → rollover → legacy
        remaining = cost
        new_cycle = cycle
        new_rollover = rollover
        new_legacy = legacy

        if remaining > 0 and new_cycle > 0:
            deduct = min(remaining, new_cycle)
            new_cycle -= deduct
            remaining -= deduct
            await conn.execute(
                text("""
                    INSERT INTO credit_ledger (user_id, bucket, delta, reason, reference_id, balance_after)
                    VALUES (:user_id, 'cycle', :delta, :reason, :ref_id,
                            (SELECT cycle_credits + rollover_balance + legacy_balance FROM user_credits WHERE user_id = :user_id) - :cost_total)
                """),
                {
                    "user_id": user_id,
                    "delta": -deduct,
                    "reason": f"step_{step}",
                    "ref_id": reference_id,
                    "cost_total": cost,
                },
            )

        if remaining > 0 and new_rollover > 0:
            deduct = min(remaining, new_rollover)
            new_rollover -= deduct
            remaining -= deduct
            await conn.execute(
                text("""
                    INSERT INTO credit_ledger (user_id, bucket, delta, reason, reference_id, balance_after)
                    VALUES (:user_id, 'rollover', :delta, :reason, :ref_id,
                            (SELECT cycle_credits + rollover_balance + legacy_balance FROM user_credits WHERE user_id = :user_id) - :cost_total)
                """),
                {
                    "user_id": user_id,
                    "delta": -deduct,
                    "reason": f"step_{step}",
                    "ref_id": reference_id,
                    "cost_total": cost,
                },
            )

        if remaining > 0 and new_legacy > 0:
            deduct = min(remaining, new_legacy)
            new_legacy -= deduct
            await conn.execute(
                text("""
                    INSERT INTO credit_ledger (user_id, bucket, delta, reason, reference_id, balance_after)
                    VALUES (:user_id, 'legacy', :delta, :reason, :ref_id,
                            (SELECT cycle_credits + rollover_balance + legacy_balance FROM user_credits WHERE user_id = :user_id) - :cost_total)
                """),
                {
                    "user_id": user_id,
                    "delta": -deduct,
                    "reason": f"step_{step}",
                    "ref_id": reference_id,
                    "cost_total": cost,
                },
            )

        new_total = new_cycle + new_rollover + new_legacy
        await conn.execute(
            text("""
                UPDATE user_credits
                SET cycle_credits = :cycle, rollover_balance = :rollover, legacy_balance = :legacy,
                    updated_at = now()
                WHERE user_id = :user_id
            """),
            {"cycle": new_cycle, "rollover": new_rollover, "legacy": new_legacy, "user_id": user_id},
        )

    return AccountCreditsRead(
        cycle=new_cycle,
        rollover=new_rollover,
        legacy=new_legacy,
        total=new_total,
        cycle_ends_at=row["cycle_ends_at"],
        monthly_quota=row["monthly_quota"],
    )


async def grant_credits(
    conn,
    *,
    user_id: UUID,
    bucket: str,
    amount: int,
    reason: str,
    reference_id: UUID | None = None,
) -> None:
    if bucket == "cycle":
        await conn.execute(
            text("UPDATE user_credits SET cycle_credits = cycle_credits + :amount, updated_at = now() WHERE user_id = :user_id"),
            {"amount": amount, "user_id": user_id},
        )
    elif bucket == "rollover":
        await conn.execute(
            text("UPDATE user_credits SET rollover_balance = rollover_balance + :amount, updated_at = now() WHERE user_id = :user_id"),
            {"amount": amount, "user_id": user_id},
        )
    else:
        await conn.execute(
            text("UPDATE user_credits SET legacy_balance = legacy_balance + :amount, updated_at = now() WHERE user_id = :user_id"),
            {"amount": amount, "user_id": user_id},
        )

    result = await conn.execute(
        text("SELECT cycle_credits + rollover_balance + legacy_balance AS total FROM user_credits WHERE user_id = :user_id"),
        {"user_id": user_id},
    )
    balance_after = result.scalar() or 0

    await conn.execute(
        text("""
            INSERT INTO credit_ledger (user_id, bucket, delta, reason, reference_id, balance_after)
            VALUES (:user_id, :bucket, :delta, :reason, :ref_id, :balance_after)
        """),
        {
            "user_id": user_id,
            "bucket": bucket,
            "delta": amount,
            "reason": reason,
            "ref_id": reference_id,
            "balance_after": balance_after,
        },
    )
