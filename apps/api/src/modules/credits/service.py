from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from contracts import AccountCreditsRead
from core.db import get_engine
from core.redis import get_redis
from sqlalchemy import text

ANONYMOUS_CREDIT_KEY = "credit:session:{session_id}"
ANONYMOUS_CREDIT_DEFAULT = 350
ANONYMOUS_CREDIT_TTL = 7 * 24 * 3600  # 7 days in seconds

STEP_COSTS: dict[str, int] = {
    "zone_generation": 20,
    "zone_enrichment": 20,
    "listings_cache": 20,
    "listings_scrape": 20,
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
    async with engine.connect() as conn:
        result = await conn.execute(
            text("""
                SELECT cycle_credits, rollover_balance, legacy_balance, cycle_ends_at, monthly_quota
                FROM user_credits
                WHERE user_id = :user_id
            """),
            {"user_id": user_id},
        )
        row = result.mappings().first()
    if row is None:
        return AccountCreditsRead(cycle=0, rollover=0, legacy=0, total=0, cycle_ends_at=None, monthly_quota=None)
    cycle = row["cycle_credits"]
    rollover = row["rollover_balance"]
    legacy = row["legacy_balance"]
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
        result = await conn.execute(
            text("""
                SELECT cycle_credits, rollover_balance, legacy_balance,
                       cycle_ends_at, monthly_quota
                FROM user_credits
                WHERE user_id = :user_id
                FOR UPDATE
            """),
            {"user_id": user_id},
        )
        row = result.mappings().first()
        if row is None:
            raise InsufficientCreditsError(required=cost, balance=0)

        cycle = row["cycle_credits"]
        rollover = row["rollover_balance"]
        legacy = row["legacy_balance"]
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
