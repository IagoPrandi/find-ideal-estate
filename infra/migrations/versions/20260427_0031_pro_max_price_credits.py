"""Correct Pro Max price and credits

Revision ID: 20260427_0031
Revises: 20260427_0030
Create Date: 2026-04-27 13:00:00.000000
"""

from alembic import op


revision = "20260427_0031"
down_revision = "20260427_0030"
branch_labels = None
depends_on = None


def _set_pro_max_plan(price_brl: str, monthly_credits: int, reason: str) -> None:
    op.execute(f"""
        UPDATE plans
        SET price_brl = {price_brl},
            monthly_credits = {monthly_credits}
        WHERE slug = 'pro_max'
    """)

    op.execute(f"""
        WITH active_pro_max AS (
            SELECT DISTINCT ON (pa.user_id)
                pa.user_id,
                p.id AS plan_id
            FROM plan_activations pa
            JOIN plans p ON p.id = pa.plan_id
            WHERE p.slug = 'pro_max'
              AND pa.status = 'active'
              AND pa.ends_at > now()
            ORDER BY pa.user_id, pa.started_at DESC
        ),
        previous_balances AS (
            SELECT
                apm.user_id,
                COALESCE(uc.cycle_credits + uc.rollover_balance + uc.legacy_balance, 0) AS previous_total
            FROM active_pro_max apm
            LEFT JOIN user_credits uc ON uc.user_id = apm.user_id
        )
        INSERT INTO credit_ledger (user_id, bucket, delta, reason, reference_id, balance_after)
        SELECT
            user_id,
            'cycle',
            {monthly_credits} - previous_total,
            '{reason}',
            NULL,
            {monthly_credits}
        FROM previous_balances
    """)

    op.execute(f"""
        WITH active_pro_max AS (
            SELECT DISTINCT ON (pa.user_id)
                pa.user_id,
                p.id AS plan_id
            FROM plan_activations pa
            JOIN plans p ON p.id = pa.plan_id
            WHERE p.slug = 'pro_max'
              AND pa.status = 'active'
              AND pa.ends_at > now()
            ORDER BY pa.user_id, pa.started_at DESC
        )
        INSERT INTO user_credits (
            user_id,
            plan_id,
            cycle_credits,
            rollover_balance,
            legacy_balance,
            cycle_started_at,
            cycle_ends_at,
            monthly_quota,
            updated_at
        )
        SELECT
            user_id,
            plan_id,
            {monthly_credits},
            0,
            0,
            now(),
            now() + interval '30 days',
            {monthly_credits},
            now()
        FROM active_pro_max
        ON CONFLICT (user_id) DO UPDATE
        SET
            plan_id = EXCLUDED.plan_id,
            cycle_credits = EXCLUDED.cycle_credits,
            rollover_balance = 0,
            legacy_balance = 0,
            cycle_started_at = EXCLUDED.cycle_started_at,
            cycle_ends_at = EXCLUDED.cycle_ends_at,
            monthly_quota = EXCLUDED.monthly_quota,
            updated_at = now()
    """)


def upgrade() -> None:
    _set_pro_max_plan("149.90", 20000, "pro_max_price_credits_correction_20260427")


def downgrade() -> None:
    _set_pro_max_plan("149.90", 20000, "pro_max_price_credits_correction_rollback_20260427")
