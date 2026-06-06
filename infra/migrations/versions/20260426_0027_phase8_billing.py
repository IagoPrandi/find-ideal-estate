"""Phase 8: plans, entitlements, credits, billing, Pix, plan_activations

Revision ID: 20260426_0027
Revises: 20260422_0026
Create Date: 2026-04-26 12:00:00.000000
"""

from alembic import op


revision = "20260426_0027"
down_revision = "20260422_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS plans (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            slug             TEXT UNIQUE NOT NULL,
            name             TEXT NOT NULL,
            price_brl        NUMERIC(8,2),
            monthly_credits  INT NOT NULL DEFAULT 0,
            is_paid          BOOLEAN NOT NULL DEFAULT false,
            stripe_price_id  TEXT,
            display_order    INT NOT NULL DEFAULT 0,
            is_active        BOOLEAN NOT NULL DEFAULT true,
            created_at       TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS plan_entitlements (
            plan_id                          UUID PRIMARY KEY REFERENCES plans(id) ON DELETE CASCADE,
            max_listing_favorites            INT,
            max_zone_favorites               INT,
            retention_days                   INT NOT NULL,
            can_customize_radius             BOOLEAN NOT NULL DEFAULT false,
            can_customize_max_time           BOOLEAN NOT NULL DEFAULT false,
            can_customize_distance           BOOLEAN NOT NULL DEFAULT false,
            max_active_metrics               INT,
            transport_line_policy            TEXT NOT NULL,
            zone_selection_policy            TEXT NOT NULL,
            auto_refresh_policy              TEXT NOT NULL,
            pro_max_refresh_max_zones        INT,
            pro_max_refresh_max_listings     INT,
            pro_max_refresh_cadence_days     INT,
            pro_max_refresh_eligibility_days INT,
            rollover_percent                 INT NOT NULL DEFAULT 0,
            rollover_cycles                  INT NOT NULL DEFAULT 0,
            cycle_length_days                INT NOT NULL DEFAULT 30
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id             UUID REFERENCES users(id) NOT NULL,
            plan_id             UUID REFERENCES plans(id),
            payment_provider    TEXT NOT NULL,
            payment_method      TEXT NOT NULL,
            payment_type        TEXT NOT NULL,
            amount_brl          NUMERIC(8,2) NOT NULL,
            status              TEXT NOT NULL DEFAULT 'pending',
            external_reference  TEXT,
            external_payment_id TEXT,
            created_at          TIMESTAMPTZ DEFAULT NOW(),
            expires_at          TIMESTAMPTZ,
            paid_at             TIMESTAMPTZ,
            cancelled_at        TIMESTAMPTZ,
            refunded_at         TIMESTAMPTZ
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS pix_payment_data (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            payment_id       UUID REFERENCES payments(id) ON DELETE CASCADE NOT NULL,
            pix_key          TEXT,
            merchant_name    TEXT,
            merchant_city    TEXT,
            qr_code_payload  TEXT,
            pix_copy_paste   TEXT,
            qr_code_image_url TEXT,
            provider_payload JSONB,
            created_at       TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS plan_activations (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id           UUID REFERENCES users(id) NOT NULL,
            plan_id           UUID REFERENCES plans(id) NOT NULL,
            source_payment_id UUID REFERENCES payments(id),
            status            TEXT NOT NULL DEFAULT 'active',
            started_at        TIMESTAMPTZ NOT NULL,
            ends_at           TIMESTAMPTZ NOT NULL,
            created_at        TIMESTAMPTZ DEFAULT NOW(),
            updated_at        TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_plan_activations_user_id ON plan_activations (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_plan_activations_ends_at ON plan_activations (ends_at) WHERE status = 'active'")

    op.execute("""
        CREATE TABLE IF NOT EXISTS user_credits (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id          UUID REFERENCES users(id) UNIQUE NOT NULL,
            plan_id          UUID REFERENCES plans(id),
            cycle_credits    INT NOT NULL DEFAULT 0,
            rollover_balance INT NOT NULL DEFAULT 0,
            legacy_balance   INT NOT NULL DEFAULT 0,
            cycle_started_at TIMESTAMPTZ,
            cycle_ends_at    TIMESTAMPTZ,
            monthly_quota    INT,
            updated_at       TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_credits_cycle_ends_at ON user_credits (cycle_ends_at)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS credit_ledger (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id      UUID REFERENCES users(id) NOT NULL,
            bucket       TEXT NOT NULL,
            delta        INT NOT NULL,
            reason       TEXT NOT NULL,
            reference_id UUID,
            balance_after INT NOT NULL,
            created_at   TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_credit_ledger_user_created ON credit_ledger (user_id, created_at DESC)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS pro_max_refresh_targets (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id             UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
            target_kind         TEXT NOT NULL,
            listing_favorite_id UUID REFERENCES user_listing_favorites(id) ON DELETE CASCADE,
            zone_favorite_id    UUID REFERENCES user_zone_favorites(id) ON DELETE CASCADE,
            is_active           BOOLEAN NOT NULL DEFAULT true,
            is_priority         BOOLEAN NOT NULL DEFAULT false,
            last_refreshed_at   TIMESTAMPTZ,
            next_refresh_due_at TIMESTAMPTZ NOT NULL,
            last_attempt_status TEXT,
            failure_count       INT NOT NULL DEFAULT 0,
            created_at          TIMESTAMPTZ DEFAULT NOW(),
            updated_at          TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT chk_target_xor CHECK (
                (target_kind = 'listing' AND listing_favorite_id IS NOT NULL AND zone_favorite_id IS NULL)
                OR (target_kind = 'zone' AND zone_favorite_id IS NOT NULL AND listing_favorite_id IS NULL)
            )
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS pro_max_refresh_runs (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            started_at   TIMESTAMPTZ NOT NULL,
            finished_at  TIMESTAMPTZ,
            total_items  INT,
            success_count INT,
            failure_count INT,
            skipped_count INT,
            status       TEXT NOT NULL DEFAULT 'running',
            created_at   TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS webhook_events (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            provider     TEXT NOT NULL,
            event_id     TEXT,
            event_type   TEXT NOT NULL,
            payload      JSONB,
            processed    BOOLEAN DEFAULT false,
            processed_at TIMESTAMPTZ,
            error        TEXT,
            created_at   TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (provider, event_id)
        )
    """)

    # Seed plans
    op.execute("""
        INSERT INTO plans (slug, name, price_brl, monthly_credits, is_paid, display_order)
        VALUES
            ('anonymous', 'Anônimo',        NULL,    300, false, 0),
            ('free',      'Free',           0.00,    350, false, 1),
            ('basico',    'Básico',        12.99,    800, true,  2),
            ('pro',       'Pro',           90.99,   4000, true,  3),
            ('pro_max',   'Pro Max',      312.99,  20000, true,  4)
        ON CONFLICT (slug) DO NOTHING
    """)

    # Seed plan_entitlements
    op.execute("""
        INSERT INTO plan_entitlements (
            plan_id,
            max_listing_favorites, max_zone_favorites, retention_days,
            can_customize_radius, can_customize_max_time, can_customize_distance,
            max_active_metrics,
            transport_line_policy, zone_selection_policy,
            auto_refresh_policy,
            pro_max_refresh_max_zones, pro_max_refresh_max_listings,
            pro_max_refresh_cadence_days, pro_max_refresh_eligibility_days,
            rollover_percent, rollover_cycles, cycle_length_days
        )
        SELECT
            p.id,
            e.max_listing_favorites::INT, e.max_zone_favorites::INT, e.retention_days::INT,
            e.can_customize_radius::BOOLEAN, e.can_customize_max_time::BOOLEAN, e.can_customize_distance::BOOLEAN,
            e.max_active_metrics::INT,
            e.transport_line_policy, e.zone_selection_policy,
            e.auto_refresh_policy,
            e.pro_max_refresh_max_zones::INT, e.pro_max_refresh_max_listings::INT,
            e.pro_max_refresh_cadence_days::INT, e.pro_max_refresh_eligibility_days::INT,
            e.rollover_percent::INT, e.rollover_cycles::INT, e.cycle_length_days::INT
        FROM plans p
        JOIN (VALUES
            ('anonymous', 0,   0,  7, true,  false, false, 4,    'locked_default', 'restricted', 'none', NULL, NULL, NULL, NULL, 0,  0, 30),
            ('free',      5,   2,  7, true,  false, false, 4,    'top_2_lines',    'restricted', 'none', NULL, NULL, NULL, NULL, 0,  0, 30),
            ('basico',    20,  4, 30, true,  true,  true,  4,    'unlocked',       'any',        'none', NULL, NULL, NULL, NULL, 25, 1, 30),
            ('pro',       100, 20,30, true,  true,  true,  NULL, 'unlocked',       'any',        'none', NULL, NULL, NULL, NULL, 25, 1, 30),
            ('pro_max',   100, 20,30, true,  true,  true,  NULL, 'unlocked',       'any',        'none', NULL, NULL, NULL, NULL, 25, 1, 30)
        ) AS e(
            slug,
            max_listing_favorites, max_zone_favorites, retention_days,
            can_customize_radius, can_customize_max_time, can_customize_distance,
            max_active_metrics,
            transport_line_policy, zone_selection_policy,
            auto_refresh_policy,
            pro_max_refresh_max_zones, pro_max_refresh_max_listings,
            pro_max_refresh_cadence_days, pro_max_refresh_eligibility_days,
            rollover_percent, rollover_cycles, cycle_length_days
        ) ON p.slug = e.slug
        ON CONFLICT (plan_id) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS webhook_events CASCADE")
    op.execute("DROP TABLE IF EXISTS pro_max_refresh_runs CASCADE")
    op.execute("DROP TABLE IF EXISTS pro_max_refresh_targets CASCADE")
    op.execute("DROP TABLE IF EXISTS credit_ledger CASCADE")
    op.execute("DROP TABLE IF EXISTS user_credits CASCADE")
    op.execute("DROP TABLE IF EXISTS plan_activations CASCADE")
    op.execute("DROP TABLE IF EXISTS pix_payment_data CASCADE")
    op.execute("DROP TABLE IF EXISTS payments CASCADE")
    op.execute("DROP TABLE IF EXISTS plan_entitlements CASCADE")
    op.execute("DROP TABLE IF EXISTS plans CASCADE")
