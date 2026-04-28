"""Enforce plan hierarchy, disable plan scraping, reset user credits

Revision ID: 20260427_0030
Revises: 20260427_0029
Create Date: 2026-04-27 12:00:00.000000
"""

from alembic import op


revision = "20260427_0030"
down_revision = "20260427_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE plans
        SET
            price_brl = CASE slug
                WHEN 'anonymous' THEN NULL
                WHEN 'free' THEN 0.00
                WHEN 'basico' THEN 21.99
                WHEN 'pro' THEN 90.99
                WHEN 'pro_max' THEN 312.99
                ELSE price_brl
            END,
            monthly_credits = CASE slug
                WHEN 'anonymous' THEN 300
                WHEN 'free' THEN 350
                WHEN 'basico' THEN 800
                WHEN 'pro' THEN 4000
                WHEN 'pro_max' THEN 20000
                ELSE monthly_credits
            END
        WHERE slug IN ('anonymous', 'free', 'basico', 'pro', 'pro_max')
    """)

    op.execute("""
        UPDATE plan_entitlements pe
        SET
            max_active_metrics = CASE p.slug
                WHEN 'anonymous' THEN 4
                WHEN 'free' THEN 4
                WHEN 'basico' THEN 4
                ELSE NULL
            END,
            auto_refresh_policy = 'none',
            pro_max_refresh_max_zones = NULL,
            pro_max_refresh_max_listings = NULL,
            pro_max_refresh_cadence_days = NULL,
            pro_max_refresh_eligibility_days = NULL
        FROM plans p
        WHERE pe.plan_id = p.id
          AND p.slug IN ('anonymous', 'free', 'basico', 'pro', 'pro_max')
    """)

    op.execute("""
        WITH free_plan AS (
            SELECT id, monthly_credits
            FROM plans
            WHERE slug = 'free'
            LIMIT 1
        )
        INSERT INTO plan_activations (user_id, plan_id, source_payment_id, status, started_at, ends_at)
        SELECT u.id, fp.id, NULL, 'active', now(), now() + interval '30 days'
        FROM users u
        CROSS JOIN free_plan fp
        WHERE NOT EXISTS (
            SELECT 1
            FROM plan_activations pa
            WHERE pa.user_id = u.id
              AND pa.status = 'active'
              AND pa.ends_at > now()
        )
    """)

    op.execute("""
        WITH active_plans AS (
            SELECT DISTINCT ON (pa.user_id)
                pa.user_id,
                p.id AS plan_id,
                p.monthly_credits
            FROM plan_activations pa
            JOIN plans p ON p.id = pa.plan_id
            WHERE pa.status = 'active'
              AND pa.ends_at > now()
            ORDER BY pa.user_id, p.display_order DESC, pa.started_at DESC
        ),
        target_users AS (
            SELECT u.id AS user_id, ap.plan_id, ap.monthly_credits
            FROM users u
            JOIN active_plans ap ON ap.user_id = u.id
        ),
        previous_balances AS (
            SELECT
                tu.user_id,
                tu.monthly_credits,
                COALESCE(uc.cycle_credits + uc.rollover_balance + uc.legacy_balance, 0) AS previous_total
            FROM target_users tu
            LEFT JOIN user_credits uc ON uc.user_id = tu.user_id
        )
        INSERT INTO credit_ledger (user_id, bucket, delta, reason, reference_id, balance_after)
        SELECT
            user_id,
            'cycle',
            monthly_credits - previous_total,
            'admin_reset_plan_credits_20260427',
            NULL,
            monthly_credits
        FROM previous_balances
    """)

    op.execute("""
        WITH active_plans AS (
            SELECT DISTINCT ON (pa.user_id)
                pa.user_id,
                p.id AS plan_id,
                p.monthly_credits
            FROM plan_activations pa
            JOIN plans p ON p.id = pa.plan_id
            WHERE pa.status = 'active'
              AND pa.ends_at > now()
            ORDER BY pa.user_id, p.display_order DESC, pa.started_at DESC
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
            monthly_credits,
            0,
            0,
            now(),
            now() + interval '30 days',
            monthly_credits,
            now()
        FROM active_plans
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


def downgrade() -> None:
    op.execute("""
        UPDATE plans
        SET
            price_brl = CASE slug
                WHEN 'pro_max' THEN 312.99
                ELSE price_brl
            END,
            monthly_credits = CASE slug
                WHEN 'anonymous' THEN 300
                WHEN 'pro_max' THEN 20000
                ELSE monthly_credits
            END
        WHERE slug IN ('anonymous', 'pro_max')
    """)

    op.execute("""
        UPDATE plan_entitlements pe
        SET
            max_active_metrics = CASE p.slug
                WHEN 'anonymous' THEN NULL
                WHEN 'free' THEN NULL
                WHEN 'basico' THEN 4
                ELSE NULL
            END,
            auto_refresh_policy = CASE p.slug
                WHEN 'pro_max' THEN 'managed_queue'
                ELSE 'none'
            END,
            pro_max_refresh_max_zones = CASE p.slug WHEN 'pro_max' THEN 10 ELSE NULL END,
            pro_max_refresh_max_listings = CASE p.slug WHEN 'pro_max' THEN 30 ELSE NULL END,
            pro_max_refresh_cadence_days = CASE p.slug WHEN 'pro_max' THEN 7 ELSE NULL END,
            pro_max_refresh_eligibility_days = CASE p.slug WHEN 'pro_max' THEN 30 ELSE NULL END
        FROM plans p
        WHERE pe.plan_id = p.id
          AND p.slug IN ('anonymous', 'free', 'basico', 'pro', 'pro_max')
    """)
