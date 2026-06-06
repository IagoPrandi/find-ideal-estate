"""Add GEO content layer: slug, metric tables, scores, coverage, urban_metrics_by_district view.

Revision ID: 20260606_0042
Revises: 20260605_0041
Create Date: 2026-06-06
"""

from alembic import op

revision = "20260606_0042"
down_revision = "20260605_0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Add slug to neighborhood_boundaries for URL-safe routing
    # ------------------------------------------------------------------
    op.execute(
        """
        ALTER TABLE neighborhood_boundaries
        ADD COLUMN IF NOT EXISTS slug TEXT
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_neighborhood_boundaries_slug
        ON neighborhood_boundaries (city_code, slug)
        WHERE slug IS NOT NULL
        """
    )

    # ------------------------------------------------------------------
    # 2. Green area metrics per neighborhood
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS neighborhood_green_area_metrics (
            neighborhood_code TEXT PRIMARY KEY
                REFERENCES neighborhood_boundaries(neighborhood_code) ON DELETE CASCADE,
            city_code         TEXT NOT NULL,
            green_area_m2     DOUBLE PRECISION NOT NULL DEFAULT 0,
            green_area_pct    DOUBLE PRECISION NOT NULL DEFAULT 0,
            data_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            inputs_hash       TEXT NOT NULL DEFAULT ''
        )
        """
    )

    # ------------------------------------------------------------------
    # 3. Flood risk metrics per neighborhood
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS neighborhood_flood_risk_metrics (
            neighborhood_code TEXT PRIMARY KEY
                REFERENCES neighborhood_boundaries(neighborhood_code) ON DELETE CASCADE,
            city_code         TEXT NOT NULL,
            flood_area_m2     DOUBLE PRECISION NOT NULL DEFAULT 0,
            flood_area_pct    DOUBLE PRECISION NOT NULL DEFAULT 0,
            data_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            inputs_hash       TEXT NOT NULL DEFAULT ''
        )
        """
    )

    # ------------------------------------------------------------------
    # 4. Transport metrics per neighborhood (from GeoSampa)
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS neighborhood_transport_metrics (
            neighborhood_code     TEXT PRIMARY KEY
                REFERENCES neighborhood_boundaries(neighborhood_code) ON DELETE CASCADE,
            city_code             TEXT NOT NULL,
            metro_station_count   INTEGER NOT NULL DEFAULT 0,
            trem_station_count    INTEGER NOT NULL DEFAULT 0,
            bus_stop_count        INTEGER NOT NULL DEFAULT 0,
            bus_terminal_count    INTEGER NOT NULL DEFAULT 0,
            bus_corridor_count    INTEGER NOT NULL DEFAULT 0,
            transit_density_per_km2 DOUBLE PRECISION,
            data_at               TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    # ------------------------------------------------------------------
    # 5. POI access metrics per neighborhood
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS neighborhood_poi_metrics (
            neighborhood_code      TEXT PRIMARY KEY
                REFERENCES neighborhood_boundaries(neighborhood_code) ON DELETE CASCADE,
            city_code              TEXT NOT NULL,
            bus_stop_density_per_km2 DOUBLE PRECISION NOT NULL DEFAULT 0,
            poi_proxy_score        DOUBLE PRECISION,
            data_at                TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    # ------------------------------------------------------------------
    # 6. Normalized scores (0–100) per metric per neighborhood
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS neighborhood_metric_scores (
            neighborhood_code TEXT NOT NULL
                REFERENCES neighborhood_boundaries(neighborhood_code) ON DELETE CASCADE,
            city_code         TEXT NOT NULL,
            metric_name       TEXT NOT NULL,
            raw_value         DOUBLE PRECISION,
            normalized_score  DOUBLE PRECISION CHECK (normalized_score BETWEEN 0 AND 100),
            rank_asc          INTEGER,
            percentile        DOUBLE PRECISION,
            computed_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (neighborhood_code, metric_name)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_neighborhood_metric_scores_city_metric
        ON neighborhood_metric_scores (city_code, metric_name)
        """
    )

    # ------------------------------------------------------------------
    # 7. Coverage flags per metric per neighborhood
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS neighborhood_metric_coverage (
            neighborhood_code TEXT NOT NULL
                REFERENCES neighborhood_boundaries(neighborhood_code) ON DELETE CASCADE,
            city_code         TEXT NOT NULL,
            metric_name       TEXT NOT NULL,
            coverage_level    TEXT NOT NULL DEFAULT 'insufficient'
                CHECK (coverage_level IN ('complete', 'partial', 'insufficient')),
            has_data          BOOLEAN NOT NULL DEFAULT FALSE,
            last_updated_at   TIMESTAMPTZ,
            notes             TEXT,
            PRIMARY KEY (neighborhood_code, metric_name)
        )
        """
    )

    # ------------------------------------------------------------------
    # 8. Materialized view: urban_metrics_by_district
    #    Joins all metric tables; is_publishable = TRUE when >= 4 metrics
    #    have data. This is the read surface for the GEO content layer.
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE MATERIALIZED VIEW IF NOT EXISTS urban_metrics_by_district AS
        SELECT
            nb.neighborhood_code,
            nb.city_code,
            nb.city_name,
            nb.district_code,
            nb.district_name,
            nb.neighborhood_name,
            nb.slug,
            nb.area_km2,
            nb.geometry,

            -- Per-metric normalized scores (NULL when data unavailable)
            (SELECT nms.normalized_score
             FROM neighborhood_metric_scores nms
             WHERE nms.neighborhood_code = nb.neighborhood_code
               AND nms.metric_name = 'transport')        AS transport_score,

            (SELECT nms.normalized_score
             FROM neighborhood_metric_scores nms
             WHERE nms.neighborhood_code = nb.neighborhood_code
               AND nms.metric_name = 'green_area')       AS green_area_score,

            (SELECT nms.normalized_score
             FROM neighborhood_metric_scores nms
             WHERE nms.neighborhood_code = nb.neighborhood_code
               AND nms.metric_name = 'flood_risk')       AS flood_risk_score,

            (SELECT nms.normalized_score
             FROM neighborhood_metric_scores nms
             WHERE nms.neighborhood_code = nb.neighborhood_code
               AND nms.metric_name = 'safety')           AS safety_score,

            (SELECT nms.normalized_score
             FROM neighborhood_metric_scores nms
             WHERE nms.neighborhood_code = nb.neighborhood_code
               AND nms.metric_name = 'poi_access')       AS poi_access_score,

            -- Coverage map as JSON  { metric_name: coverage_level }
            (SELECT COALESCE(jsonb_object_agg(nmc.metric_name, nmc.coverage_level), '{}'::jsonb)
             FROM neighborhood_metric_coverage nmc
             WHERE nmc.neighborhood_code = nb.neighborhood_code) AS coverage,

            -- Publishable when >= 4 of 5 metrics have data
            (SELECT COUNT(*) >= 4
             FROM neighborhood_metric_coverage nmc
             WHERE nmc.neighborhood_code = nb.neighborhood_code
               AND nmc.has_data = TRUE)                  AS is_publishable,

            now()                                        AS refreshed_at
        FROM neighborhood_boundaries nb
        WITH DATA
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_urban_metrics_by_district_code
        ON urban_metrics_by_district (neighborhood_code)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_urban_metrics_by_district_city_slug
        ON urban_metrics_by_district (city_code, slug)
        WHERE slug IS NOT NULL AND is_publishable = TRUE
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_urban_metrics_by_district_geometry
        ON urban_metrics_by_district USING GIST (geometry)
        """
    )

    # ------------------------------------------------------------------
    # 9. Helper function: refresh the materialized view
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION refresh_urban_metrics_by_district()
        RETURNS VOID LANGUAGE plpgsql AS $$
        BEGIN
            REFRESH MATERIALIZED VIEW CONCURRENTLY urban_metrics_by_district;
        END;
        $$
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS refresh_urban_metrics_by_district()")
    op.execute("DROP INDEX IF EXISTS ix_urban_metrics_by_district_geometry")
    op.execute("DROP INDEX IF EXISTS ix_urban_metrics_by_district_city_slug")
    op.execute("DROP INDEX IF EXISTS ux_urban_metrics_by_district_code")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS urban_metrics_by_district")
    op.execute("DROP TABLE IF EXISTS neighborhood_metric_coverage")
    op.execute("DROP TABLE IF EXISTS neighborhood_metric_scores")
    op.execute("DROP TABLE IF EXISTS neighborhood_poi_metrics")
    op.execute("DROP TABLE IF EXISTS neighborhood_transport_metrics")
    op.execute("DROP TABLE IF EXISTS neighborhood_flood_risk_metrics")
    op.execute("DROP TABLE IF EXISTS neighborhood_green_area_metrics")
    op.execute("DROP INDEX IF EXISTS ux_neighborhood_boundaries_slug")
    op.execute("ALTER TABLE neighborhood_boundaries DROP COLUMN IF EXISTS slug")
