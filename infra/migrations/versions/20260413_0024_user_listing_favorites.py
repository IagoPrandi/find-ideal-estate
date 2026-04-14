"""user listing favorites by account

Revision ID: 20260413_0024
Revises: 20260412_0023
Create Date: 2026-04-13 15:40:00.000000
"""

from alembic import op


revision = "20260413_0024"
down_revision = "20260412_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE user_listing_favorites (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            listing_key      TEXT NOT NULL,
            journey_id       UUID NOT NULL,
            zone_fingerprint TEXT NOT NULL,
            search_type      TEXT NOT NULL,
            usage_type       TEXT NOT NULL,
            listing_payload  JSONB NOT NULL,
            saved_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_user_listing_favorites_user_key UNIQUE (user_id, listing_key)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_user_listing_favorites_user_saved_at "
        "ON user_listing_favorites (user_id, saved_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_listing_favorites")