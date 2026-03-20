"""phase3 gtfs ingestion schema"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260318_0003"
down_revision = "20260316_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dataset_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("dataset_type", sa.Text(), nullable=False),
        sa.Column("version_hash", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_unique_constraint("uq_dataset_versions_type_hash", "dataset_versions", ["dataset_type", "version_hash"])
    op.execute(
        """
        CREATE UNIQUE INDEX uq_dataset_versions_current_per_type
        ON dataset_versions (dataset_type)
        WHERE is_current = true
        """
    )

    op.execute(
        """
        CREATE TABLE gtfs_stops (
            stop_id TEXT PRIMARY KEY,
            stop_name TEXT,
            stop_lat DOUBLE PRECISION NOT NULL,
            stop_lon DOUBLE PRECISION NOT NULL,
            location geometry(Point, 4326) NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX ix_gtfs_stops_location ON gtfs_stops USING GIST (location)")

    op.execute(
        """
        CREATE TABLE gtfs_routes (
            route_id TEXT PRIMARY KEY,
            route_short_name TEXT,
            route_long_name TEXT,
            route_type INT
        )
        """
    )

    op.execute(
        """
        CREATE TABLE gtfs_trips (
            trip_id TEXT PRIMARY KEY,
            route_id TEXT,
            shape_id TEXT
        )
        """
    )
    op.execute("CREATE INDEX ix_gtfs_trips_route_id ON gtfs_trips (route_id)")

    op.execute(
        """
        CREATE TABLE gtfs_stop_times (
            trip_id TEXT NOT NULL,
            stop_id TEXT NOT NULL,
            arrival_time TEXT,
            departure_time TEXT,
            stop_sequence INT NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX ix_gtfs_stop_times_trip_id ON gtfs_stop_times (trip_id)")
    op.execute("CREATE INDEX ix_gtfs_stop_times_stop_id ON gtfs_stop_times (stop_id)")

    op.execute(
        """
        CREATE TABLE gtfs_shapes (
            shape_id TEXT NOT NULL,
            shape_pt_sequence INT NOT NULL,
            location geometry(Point, 4326) NOT NULL,
            PRIMARY KEY (shape_id, shape_pt_sequence)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS gtfs_shapes")
    op.execute("DROP INDEX IF EXISTS ix_gtfs_stop_times_stop_id")
    op.execute("DROP INDEX IF EXISTS ix_gtfs_stop_times_trip_id")
    op.execute("DROP TABLE IF EXISTS gtfs_stop_times")
    op.execute("DROP INDEX IF EXISTS ix_gtfs_trips_route_id")
    op.execute("DROP TABLE IF EXISTS gtfs_trips")
    op.execute("DROP TABLE IF EXISTS gtfs_routes")
    op.execute("DROP INDEX IF EXISTS ix_gtfs_stops_location")
    op.execute("DROP TABLE IF EXISTS gtfs_stops")

    op.execute("DROP INDEX IF EXISTS uq_dataset_versions_current_per_type")
    op.drop_constraint("uq_dataset_versions_type_hash", "dataset_versions", type_="unique")
    op.drop_table("dataset_versions")