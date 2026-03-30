"""Make listings cache key address-scoped (zone+config+search_location_normalized)."""

from alembic import op


revision = "20260329_0014"
down_revision = "20260329_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE zone_listing_caches
        ADD COLUMN IF NOT EXISTS search_location_normalized TEXT
        """
    )
    op.execute(
        """
        UPDATE zone_listing_caches
        SET search_location_normalized = ''
        WHERE search_location_normalized IS NULL
        """
    )
    op.execute(
        """
        ALTER TABLE zone_listing_caches
        ALTER COLUMN search_location_normalized SET NOT NULL
        """
    )
    op.execute(
        """
        ALTER TABLE zone_listing_caches
        ALTER COLUMN search_location_normalized SET DEFAULT ''
        """
    )

    op.execute("DROP INDEX IF EXISTS ix_zone_listing_caches_fingerprint")
    op.execute(
        """
        ALTER TABLE zone_listing_caches
        DROP CONSTRAINT IF EXISTS zone_listing_caches_zone_fingerprint_config_hash_key
        """
    )

    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_zone_listing_caches_scope
        ON zone_listing_caches (zone_fingerprint, config_hash, search_location_normalized)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_zone_listing_caches_scope
        ON zone_listing_caches (zone_fingerprint, config_hash, search_location_normalized)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_zone_listing_caches_scope")
    op.execute("DROP INDEX IF EXISTS uq_zone_listing_caches_scope")

    op.execute(
        """
        ALTER TABLE zone_listing_caches
        ADD CONSTRAINT zone_listing_caches_zone_fingerprint_config_hash_key
        UNIQUE (zone_fingerprint, config_hash)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_zone_listing_caches_fingerprint
        ON zone_listing_caches (zone_fingerprint, config_hash)
        """
    )

    op.execute(
        """
        ALTER TABLE zone_listing_caches
        DROP COLUMN IF EXISTS search_location_normalized
        """
    )
