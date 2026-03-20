"""Phase 3 GeoSampa transport ingestion tables.

Revision ID: 20260318_0004
Revises: 20260318_0003
Create Date: 2026-03-18
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260318_0004"
down_revision = "20260318_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS geosampa_metro_stations (
            id BIGSERIAL PRIMARY KEY,
            geometry geometry(Geometry, 4326) NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS geosampa_trem_stations (
            id BIGSERIAL PRIMARY KEY,
            geometry geometry(Geometry, 4326) NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS geosampa_bus_stops (
            id BIGSERIAL PRIMARY KEY,
            geometry geometry(Geometry, 4326) NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS geosampa_bus_terminals (
            id BIGSERIAL PRIMARY KEY,
            geometry geometry(Geometry, 4326) NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS geosampa_bus_corridors (
            id BIGSERIAL PRIMARY KEY,
            geometry geometry(Geometry, 4326) NOT NULL
        )
        """
    )

    op.execute("CREATE INDEX IF NOT EXISTS ix_geosampa_metro_stations_geometry ON geosampa_metro_stations USING GIST (geometry)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_geosampa_trem_stations_geometry ON geosampa_trem_stations USING GIST (geometry)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_geosampa_bus_stops_geometry ON geosampa_bus_stops USING GIST (geometry)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_geosampa_bus_terminals_geometry ON geosampa_bus_terminals USING GIST (geometry)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_geosampa_bus_corridors_geometry ON geosampa_bus_corridors USING GIST (geometry)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_geosampa_bus_corridors_geometry")
    op.execute("DROP INDEX IF EXISTS ix_geosampa_bus_terminals_geometry")
    op.execute("DROP INDEX IF EXISTS ix_geosampa_bus_stops_geometry")
    op.execute("DROP INDEX IF EXISTS ix_geosampa_trem_stations_geometry")
    op.execute("DROP INDEX IF EXISTS ix_geosampa_metro_stations_geometry")

    op.execute("DROP TABLE IF EXISTS geosampa_bus_corridors")
    op.execute("DROP TABLE IF EXISTS geosampa_bus_terminals")
    op.execute("DROP TABLE IF EXISTS geosampa_bus_stops")
    op.execute("DROP TABLE IF EXISTS geosampa_trem_stations")
    op.execute("DROP TABLE IF EXISTS geosampa_metro_stations")
