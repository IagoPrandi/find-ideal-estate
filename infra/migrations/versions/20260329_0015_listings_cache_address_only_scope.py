"""Make listings cache unique by normalized search address only."""

from alembic import op


revision = "20260329_0015"
down_revision = "20260329_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY search_location_normalized
                       ORDER BY
                           CASE status
                               WHEN 'complete' THEN 0
                               WHEN 'partial' THEN 1
                               WHEN 'scraping' THEN 2
                               WHEN 'pending' THEN 3
                               WHEN 'cancelled_partial' THEN 4
                               ELSE 5
                           END,
                           COALESCE(scraped_at, created_at) DESC,
                           created_at DESC,
                           id DESC
                   ) AS rn
            FROM zone_listing_caches
        )
        DELETE FROM zone_listing_caches zlc
        USING ranked
        WHERE zlc.id = ranked.id
          AND ranked.rn > 1
        """
    )

    op.execute("DROP INDEX IF EXISTS ix_zone_listing_caches_scope")
    op.execute("DROP INDEX IF EXISTS uq_zone_listing_caches_scope")

    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_zone_listing_caches_search_location
        ON zone_listing_caches (search_location_normalized)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_zone_listing_caches_search_location")

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
