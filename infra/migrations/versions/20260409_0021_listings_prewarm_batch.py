"""Add last_prewarmed_at for nightly listings prewarm."""

from alembic import op


revision = "20260409_0021"
down_revision = "20260407_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE zone_listing_caches
        ADD COLUMN IF NOT EXISTS last_prewarmed_at TIMESTAMPTZ
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_zone_listing_caches_last_prewarmed_at
        ON zone_listing_caches (last_prewarmed_at DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_zone_listing_caches_last_prewarmed_at")
    op.execute(
        """
        ALTER TABLE zone_listing_caches
        DROP COLUMN IF EXISTS last_prewarmed_at
        """
    )