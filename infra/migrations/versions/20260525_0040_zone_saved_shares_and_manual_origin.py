"""Add saved-zone color, shares and manual zone origin.

Revision ID: 20260525_0040
Revises: 20260524_0039
Create Date: 2026-05-25 00:40:00.000000
"""

from alembic import op


revision = "20260525_0040"
down_revision = "20260524_0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE zones
        ADD COLUMN IF NOT EXISTS origin TEXT NOT NULL DEFAULT 'generated'
        """
    )
    op.execute(
        """
        ALTER TABLE zones
        ADD CONSTRAINT ck_zones_origin
        CHECK (origin IN ('generated', 'drawn'))
        """
    )
    op.execute(
        """
        ALTER TABLE user_zone_favorites
        ADD COLUMN IF NOT EXISTS color TEXT NOT NULL DEFAULT '#0ea5e9'
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS zone_favorite_shares (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            zone_favorite_id UUID NOT NULL REFERENCES user_zone_favorites(id) ON DELETE CASCADE,
            created_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            token_hash TEXT NOT NULL UNIQUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            revoked_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_zone_favorite_shares_zone_favorite_id
        ON zone_favorite_shares (zone_favorite_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_zone_favorite_shares_active_token_hash
        ON zone_favorite_shares (token_hash)
        WHERE revoked_at IS NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_zone_favorite_shares_active_token_hash")
    op.execute("DROP INDEX IF EXISTS idx_zone_favorite_shares_zone_favorite_id")
    op.execute("DROP TABLE IF EXISTS zone_favorite_shares")
    op.execute("ALTER TABLE user_zone_favorites DROP COLUMN IF EXISTS color")
    op.execute("ALTER TABLE zones DROP CONSTRAINT IF EXISTS ck_zones_origin")
    op.execute("ALTER TABLE zones DROP COLUMN IF EXISTS origin")
