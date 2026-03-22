"""journey zones association for reused fingerprints"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260321_0006"
down_revision = "20260320_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE journey_zones (
            journey_id UUID NOT NULL REFERENCES journeys(id) ON DELETE CASCADE,
            zone_id UUID NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
            transport_point_id UUID REFERENCES transport_points(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (journey_id, zone_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_journey_zones_journey_id ON journey_zones (journey_id, created_at ASC)"
    )
    op.execute(
        "CREATE INDEX ix_journey_zones_zone_id ON journey_zones (zone_id)"
    )
    op.execute(
        """
        INSERT INTO journey_zones (journey_id, zone_id, transport_point_id)
        SELECT z.journey_id, z.id, z.transport_point_id
        FROM zones z
        WHERE z.journey_id IS NOT NULL
        ON CONFLICT (journey_id, zone_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_journey_zones_zone_id")
    op.execute("DROP INDEX IF EXISTS ix_journey_zones_journey_id")
    op.execute("DROP TABLE IF EXISTS journey_zones")