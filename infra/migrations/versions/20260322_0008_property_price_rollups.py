"""M6.1 – property_price_rollups: daily price percentile snapshots per zone."""

from alembic import op

revision = "20260322_0008"
down_revision = "20260321_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE property_price_rollups (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            date             DATE NOT NULL,
            zone_fingerprint TEXT NOT NULL,
            search_type      TEXT NOT NULL,
            median_price     NUMERIC(12,2),
            p25_price        NUMERIC(12,2),
            p75_price        NUMERIC(12,2),
            sample_count     INT NOT NULL DEFAULT 0,
            computed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (date, zone_fingerprint, search_type)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_price_rollups_fingerprint "
        "ON property_price_rollups (zone_fingerprint, date DESC)"
    )
    op.execute(
        "CREATE INDEX ix_price_rollups_date ON property_price_rollups (date)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_price_rollups_date")
    op.execute("DROP INDEX IF EXISTS ix_price_rollups_fingerprint")
    op.execute("DROP TABLE IF EXISTS property_price_rollups")
