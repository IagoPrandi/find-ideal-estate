"""Add canonical neighborhood boundaries and cached public safety metrics."""

from alembic import op

revision = "20260405_0017"
down_revision = "20260403_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS neighborhood_boundaries (
            neighborhood_code TEXT PRIMARY KEY,
            city_code TEXT NOT NULL,
            city_name TEXT NOT NULL,
            state_code TEXT,
            state_name TEXT,
            district_code TEXT,
            district_name TEXT,
            neighborhood_name TEXT NOT NULL,
            area_km2 DOUBLE PRECISION NOT NULL DEFAULT 0,
            geometry geometry(MultiPolygon, 4326) NOT NULL,
            source_dataset_type TEXT NOT NULL,
            source_dataset_hash TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS location_name_aliases (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            location_type TEXT NOT NULL,
            source_system TEXT NOT NULL,
            raw_name TEXT NOT NULL,
            raw_match_key TEXT NOT NULL,
            canonical_city_code TEXT,
            canonical_city_name TEXT,
            canonical_neighborhood_code TEXT,
            canonical_name TEXT NOT NULL,
            confidence DOUBLE PRECISION NOT NULL DEFAULT 1,
            resolution_reason TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public_safety_neighborhood_metrics (
            neighborhood_code TEXT PRIMARY KEY REFERENCES neighborhood_boundaries(neighborhood_code) ON DELETE CASCADE,
            city_code TEXT NOT NULL,
            city_name TEXT NOT NULL,
            neighborhood_name TEXT NOT NULL,
            area_km2 DOUBLE PRECISION NOT NULL DEFAULT 0,
            incident_count_365d INTEGER NOT NULL DEFAULT 0,
            homicide_count_365d INTEGER NOT NULL DEFAULT 0,
            robbery_count_365d INTEGER NOT NULL DEFAULT 0,
            theft_count_365d INTEGER NOT NULL DEFAULT 0,
            homicide_density_per_km2 DOUBLE PRECISION,
            robbery_density_per_km2 DOUBLE PRECISION,
            theft_density_per_km2 DOUBLE PRECISION,
            robbery_to_theft_ratio DOUBLE PRECISION,
            inputs_hash TEXT NOT NULL,
            computed_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_neighborhood_boundaries_geometry "
        "ON neighborhood_boundaries USING GIST (geometry)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_neighborhood_boundaries_city_name "
        "ON neighborhood_boundaries (city_name, neighborhood_name)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_location_name_aliases_source_raw "
        "ON location_name_aliases (location_type, source_system, raw_match_key, COALESCE(canonical_city_code, ''), COALESCE(canonical_neighborhood_code, ''))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_location_name_aliases_match_key "
        "ON location_name_aliases (location_type, raw_match_key)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_public_safety_neighborhood_metrics_city_name "
        "ON public_safety_neighborhood_metrics (city_name, neighborhood_name)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_public_safety_neighborhood_metrics_robbery_density "
        "ON public_safety_neighborhood_metrics (city_name, robbery_density_per_km2 DESC NULLS LAST)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_public_safety_neighborhood_metrics_robbery_density")
    op.execute("DROP INDEX IF EXISTS ix_public_safety_neighborhood_metrics_city_name")
    op.execute("DROP INDEX IF EXISTS ix_location_name_aliases_match_key")
    op.execute("DROP INDEX IF EXISTS ux_location_name_aliases_source_raw")
    op.execute("DROP INDEX IF EXISTS ix_neighborhood_boundaries_city_name")
    op.execute("DROP INDEX IF EXISTS ix_neighborhood_boundaries_geometry")
    op.execute("DROP TABLE IF EXISTS public_safety_neighborhood_metrics")
    op.execute("DROP TABLE IF EXISTS location_name_aliases")
    op.execute("DROP TABLE IF EXISTS neighborhood_boundaries")