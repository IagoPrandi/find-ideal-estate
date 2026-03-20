"""phase1 journey job transport zone schema"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260316_0002"
down_revision = "20260316_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("journeys", sa.Column("selected_transport_point_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("journeys", sa.Column("selected_zone_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("journeys", sa.Column("selected_property_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("journeys", sa.Column("secondary_reference_label", sa.Text(), nullable=True))
    op.add_column("journeys", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("ALTER TABLE journeys ADD COLUMN secondary_reference_point geometry(Point, 4326)")

    op.execute(
        """
        CREATE TABLE transport_points (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            journey_id UUID REFERENCES journeys(id),
            source TEXT NOT NULL,
            external_id TEXT,
            name TEXT,
            location geometry(Point, 4326),
            walk_time_sec INT,
            walk_distance_m INT,
            route_ids TEXT[],
            modal_types TEXT[],
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_transport_points_location ON transport_points USING GIST (location)")
    op.create_foreign_key(
        "fk_journeys_selected_transport_point_id",
        "journeys",
        "transport_points",
        ["selected_transport_point_id"],
        ["id"],
    )

    op.execute(
        """
        CREATE TABLE zones (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            journey_id UUID REFERENCES journeys(id),
            transport_point_id UUID REFERENCES transport_points(id),
            modal TEXT NOT NULL,
            max_time_minutes INT NOT NULL,
            radius_meters INT NOT NULL,
            fingerprint TEXT NOT NULL UNIQUE,
            isochrone_geom geometry(Polygon, 4326),
            dataset_version_id UUID,
            state TEXT NOT NULL DEFAULT 'pending',
            green_area_m2 DOUBLE PRECISION,
            flood_area_m2 DOUBLE PRECISION,
            safety_incidents_count INT,
            poi_counts JSONB,
            badges JSONB,
            badges_provisional BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_zones_isochrone_geom ON zones USING GIST (isochrone_geom)")
    op.create_foreign_key(
        "fk_journeys_selected_zone_id",
        "journeys",
        "zones",
        ["selected_zone_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_journeys_selected_zone_id", "journeys", type_="foreignkey")
    op.execute("DROP INDEX IF EXISTS ix_zones_isochrone_geom")
    op.execute("DROP TABLE IF EXISTS zones")

    op.drop_constraint("fk_journeys_selected_transport_point_id", "journeys", type_="foreignkey")
    op.execute("DROP INDEX IF EXISTS ix_transport_points_location")
    op.execute("DROP TABLE IF EXISTS transport_points")

    op.execute("ALTER TABLE journeys DROP COLUMN secondary_reference_point")
    op.drop_column("journeys", "expires_at")
    op.drop_column("journeys", "secondary_reference_label")
    op.drop_column("journeys", "selected_property_id")
    op.drop_column("journeys", "selected_zone_id")
    op.drop_column("journeys", "selected_transport_point_id")