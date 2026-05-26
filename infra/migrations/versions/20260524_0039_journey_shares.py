"""Add journey sharing tokens.

Revision ID: 20260524_0039
Revises: 20260523_0038
Create Date: 2026-05-24 00:39:00.000000
"""

from alembic import op


revision = "20260524_0039"
down_revision = "20260523_0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS journey_shares (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            journey_id UUID NOT NULL REFERENCES journeys(id) ON DELETE CASCADE,
            created_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            created_by_anonymous_session_id TEXT,
            token_hash TEXT NOT NULL UNIQUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            revoked_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_journey_shares_journey_id
        ON journey_shares (journey_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_journey_shares_active_token_hash
        ON journey_shares (token_hash)
        WHERE revoked_at IS NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_journey_shares_active_token_hash")
    op.execute("DROP INDEX IF EXISTS idx_journey_shares_journey_id")
    op.execute("DROP TABLE IF EXISTS journey_shares")
