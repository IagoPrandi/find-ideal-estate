"""Phase 3 M3.7 - external usage ledger for geocoding proxy.

Revision ID: 20260320_0005
Revises: 20260318_0004
Create Date: 2026-03-20
"""

from alembic import op

revision = "20260320_0005"
down_revision = "20260318_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS external_usage_ledger (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            provider       TEXT NOT NULL,
            operation_type TEXT NOT NULL,
            user_id        UUID,
            session_id     TEXT,
            journey_id     UUID,
            units          INT DEFAULT 1,
            estimated_cost NUMERIC(8,4),
            cache_hit      BOOLEAN DEFAULT false,
            status         TEXT,
            created_at     TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_external_usage_ledger_session_id ON external_usage_ledger (session_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_external_usage_ledger_created_at ON external_usage_ledger (created_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_external_usage_ledger_created_at")
    op.execute("DROP INDEX IF EXISTS ix_external_usage_ledger_session_id")
    op.execute("DROP TABLE IF EXISTS external_usage_ledger")
