from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from .classification import public_safety_group_case_sql
from .standardization import normalized_location_name_sql

_SQUARE_METERS_PER_KM2 = 1_000_000.0
_ANALYTICS_SOURCE_SYSTEM = "ssp"
_BOUNDARY_SOURCE_DATASET_TYPE = "ssp_point_hull_v1"
_ANALYTICS_FORMULA_VERSION = "ssp_point_hull_density_v2"
_MIN_BOUNDARY_AREA_KM2 = 0.01
_PUBLIC_SAFETY_TRANSLATE_SOURCE = "ÁÀÃÂÄáàãâäÉÈÊËéèêëÍÌÎÏíìîïÓÒÕÔÖóòõôöÚÙÛÜúùûüÇç"
_PUBLIC_SAFETY_TRANSLATE_TARGET = "AAAAAaaaaaEEEEeeeeIIIIiiiiOOOOOoooooUUUUuuuuCc"


@dataclass(frozen=True)
class PublicSafetyNeighborhoodAnalyticsResult:
    boundary_rows: int
    alias_rows: int
    metric_rows: int
    inputs_hash: str
    computed_at: datetime


def _normalized_public_safety_category_sql(column_name: str) -> str:
    return (
        "UPPER(TRANSLATE(COALESCE({column_name}, ''), '{source}', '{target}'))"
    ).format(
        column_name=column_name,
        source=_PUBLIC_SAFETY_TRANSLATE_SOURCE,
        target=_PUBLIC_SAFETY_TRANSLATE_TARGET,
    )


async def _ensure_public_safety_neighborhood_tables(conn: AsyncConnection) -> None:
    await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
    await conn.execute(
        text(
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
    )
    await conn.execute(
        text(
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
    )
    await conn.execute(
        text(
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
    )
    await conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_neighborhood_boundaries_geometry "
            "ON neighborhood_boundaries USING GIST (geometry)"
        )
    )
    await conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_neighborhood_boundaries_city_name "
            "ON neighborhood_boundaries (city_name, neighborhood_name)"
        )
    )
    await conn.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_location_name_aliases_source_raw "
            "ON location_name_aliases (location_type, source_system, raw_match_key, COALESCE(canonical_city_code, ''), COALESCE(canonical_neighborhood_code, ''))"
        )
    )
    await conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_location_name_aliases_match_key "
            "ON location_name_aliases (location_type, raw_match_key)"
        )
    )
    await conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_public_safety_neighborhood_metrics_city_name "
            "ON public_safety_neighborhood_metrics (city_name, neighborhood_name)"
        )
    )
    await conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_public_safety_neighborhood_metrics_robbery_density "
            "ON public_safety_neighborhood_metrics (city_name, robbery_density_per_km2 DESC NULLS LAST)"
        )
    )


async def _compute_public_safety_inputs_hash(conn: AsyncConnection) -> str:
    normalized_city_sql = normalized_location_name_sql("city_name")
    normalized_neighborhood_sql = normalized_location_name_sql("neighborhood_name")
    result = await conn.execute(
        text(
            f"""
            SELECT
                COUNT(*)::BIGINT AS total_rows,
                COUNT(*) FILTER (
                    WHERE location IS NOT NULL
                      AND {normalized_city_sql} IS NOT NULL
                      AND {normalized_neighborhood_sql} IS NOT NULL
                )::BIGINT AS geocoded_context_rows,
                COUNT(DISTINCT CONCAT_WS('|', {normalized_city_sql}, {normalized_neighborhood_sql}))::BIGINT AS distinct_pairs,
                MIN(occurred_at) AS min_occurred_at,
                MAX(occurred_at) AS max_occurred_at
            FROM public_safety_incidents
            """
        )
    )
    row = result.mappings().one()
    payload = "|".join(
        [
            _ANALYTICS_FORMULA_VERSION,
            str(row.get("total_rows") or 0),
            str(row.get("geocoded_context_rows") or 0),
            str(row.get("distinct_pairs") or 0),
            row.get("min_occurred_at").isoformat() if row.get("min_occurred_at") else "",
            row.get("max_occurred_at").isoformat() if row.get("max_occurred_at") else "",
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def refresh_public_safety_neighborhood_analytics(
    conn: AsyncConnection,
) -> PublicSafetyNeighborhoodAnalyticsResult:
    await _ensure_public_safety_neighborhood_tables(conn)
    computed_at = datetime.now(tz=timezone.utc)
    inputs_hash = await _compute_public_safety_inputs_hash(conn)
    normalized_city_sql = normalized_location_name_sql("psi.city_name")
    normalized_neighborhood_sql = normalized_location_name_sql("psi.neighborhood_name")
    normalized_category_sql = _normalized_public_safety_category_sql("psi.category")
    safety_group_sql = public_safety_group_case_sql("psi.category")

    await conn.execute(text("DELETE FROM public_safety_neighborhood_metrics"))
    await conn.execute(text("DELETE FROM location_name_aliases"))
    await conn.execute(text("DELETE FROM neighborhood_boundaries"))

    await conn.execute(
        text(
            f"""
            WITH normalized_incidents AS (
                SELECT
                    {normalized_city_sql} AS city_name,
                    {normalized_neighborhood_sql} AS neighborhood_name,
                    psi.location
                FROM public_safety_incidents psi
                WHERE psi.location IS NOT NULL
            ),
            grouped_points AS (
                SELECT
                    city_name,
                    neighborhood_name,
                    COUNT(DISTINCT ST_AsBinary(location))::INT AS distinct_point_count,
                    ST_Multi(
                        ST_CollectionExtract(
                            ST_MakeValid(ST_ConvexHull(ST_Collect(location))),
                            3
                        )
                    )::geometry(MultiPolygon, 4326) AS geometry
                FROM normalized_incidents
                WHERE city_name IS NOT NULL
                  AND neighborhood_name IS NOT NULL
                GROUP BY city_name, neighborhood_name
            ),
            valid_boundaries AS (
                SELECT
                    city_name,
                    neighborhood_name,
                    geometry,
                    (ST_Area(geometry::geography) / :square_meters_per_km2)::DOUBLE PRECISION AS area_km2
                FROM grouped_points
                WHERE distinct_point_count >= 3
                  AND geometry IS NOT NULL
                  AND NOT ST_IsEmpty(geometry)
                  AND ST_Dimension(geometry) = 2
                  AND ST_Area(geometry::geography) > 0
                                    AND (ST_Area(geometry::geography) / :square_meters_per_km2) >= :minimum_area_km2
            )
            INSERT INTO neighborhood_boundaries (
                neighborhood_code,
                city_code,
                city_name,
                neighborhood_name,
                area_km2,
                geometry,
                source_dataset_type,
                source_dataset_hash,
                created_at,
                updated_at
            )
            SELECT
                CONCAT('ssp-neighborhood-', md5(CONCAT(city_name, '|', neighborhood_name))) AS neighborhood_code,
                CONCAT('ssp-city-', md5(city_name)) AS city_code,
                city_name,
                neighborhood_name,
                area_km2,
                geometry,
                :source_dataset_type,
                :inputs_hash,
                :computed_at,
                :computed_at
            FROM valid_boundaries
            ORDER BY city_name ASC, neighborhood_name ASC
            """
        ),
        {
            "computed_at": computed_at,
            "inputs_hash": inputs_hash,
            "minimum_area_km2": _MIN_BOUNDARY_AREA_KM2,
            "source_dataset_type": _BOUNDARY_SOURCE_DATASET_TYPE,
            "square_meters_per_km2": _SQUARE_METERS_PER_KM2,
        },
    )

    await conn.execute(
        text(
            """
            INSERT INTO location_name_aliases (
                location_type,
                source_system,
                raw_name,
                raw_match_key,
                canonical_city_code,
                canonical_city_name,
                canonical_neighborhood_code,
                canonical_name,
                confidence,
                resolution_reason,
                created_at,
                updated_at
            )
            SELECT DISTINCT
                'city' AS location_type,
                :source_system AS source_system,
                nb.city_name AS raw_name,
                nb.city_name AS raw_match_key,
                nb.city_code AS canonical_city_code,
                nb.city_name AS canonical_city_name,
                NULL AS canonical_neighborhood_code,
                nb.city_name AS canonical_name,
                1.0 AS confidence,
                'normalized_from_ssp_point_hull' AS resolution_reason,
                CAST(:computed_at AS TIMESTAMPTZ) AS created_at,
                CAST(:computed_at AS TIMESTAMPTZ) AS updated_at
            FROM neighborhood_boundaries nb

            UNION ALL

            SELECT DISTINCT
                'neighborhood' AS location_type,
                :source_system AS source_system,
                nb.neighborhood_name AS raw_name,
                nb.neighborhood_name AS raw_match_key,
                nb.city_code AS canonical_city_code,
                nb.city_name AS canonical_city_name,
                nb.neighborhood_code AS canonical_neighborhood_code,
                nb.neighborhood_name AS canonical_name,
                1.0 AS confidence,
                'normalized_from_ssp_point_hull' AS resolution_reason,
                CAST(:computed_at AS TIMESTAMPTZ) AS created_at,
                CAST(:computed_at AS TIMESTAMPTZ) AS updated_at
            FROM neighborhood_boundaries nb
            """
        ),
        {"computed_at": computed_at, "source_system": _ANALYTICS_SOURCE_SYSTEM},
    )

    await conn.execute(
        text(
            f"""
            WITH normalized_recent_incidents AS (
                SELECT
                    {normalized_city_sql} AS city_name,
                    {normalized_neighborhood_sql} AS neighborhood_name,
                    {normalized_category_sql} AS normalized_category,
                    ({safety_group_sql}) AS safety_group
                FROM public_safety_incidents psi
                WHERE psi.location IS NOT NULL
                  AND psi.occurred_at >= NOW() - INTERVAL '365 days'
            ),
            aggregated_metrics AS (
                SELECT
                    nb.neighborhood_code,
                    nb.city_code,
                    nb.city_name,
                    nb.neighborhood_name,
                    nb.area_km2,
                    COUNT(nri.city_name)::INT AS incident_count_365d,
                    COUNT(*) FILTER (
                        WHERE nri.normalized_category LIKE '%HOMIC%'
                    )::INT AS homicide_count_365d,
                    COUNT(*) FILTER (
                        WHERE nri.safety_group = 'robbery'
                    )::INT AS robbery_count_365d,
                    COUNT(*) FILTER (
                        WHERE nri.safety_group = 'theft'
                    )::INT AS theft_count_365d
                FROM neighborhood_boundaries nb
                LEFT JOIN normalized_recent_incidents nri
                  ON nri.city_name = nb.city_name
                 AND nri.neighborhood_name = nb.neighborhood_name
                GROUP BY
                    nb.neighborhood_code,
                    nb.city_code,
                    nb.city_name,
                    nb.neighborhood_name,
                    nb.area_km2
            )
            INSERT INTO public_safety_neighborhood_metrics (
                neighborhood_code,
                city_code,
                city_name,
                neighborhood_name,
                area_km2,
                incident_count_365d,
                homicide_count_365d,
                robbery_count_365d,
                theft_count_365d,
                homicide_density_per_km2,
                robbery_density_per_km2,
                theft_density_per_km2,
                robbery_to_theft_ratio,
                inputs_hash,
                computed_at
            )
            SELECT
                neighborhood_code,
                city_code,
                city_name,
                neighborhood_name,
                area_km2,
                incident_count_365d,
                homicide_count_365d,
                robbery_count_365d,
                theft_count_365d,
                CASE WHEN area_km2 > 0 THEN homicide_count_365d::DOUBLE PRECISION / area_km2 ELSE NULL END AS homicide_density_per_km2,
                CASE WHEN area_km2 > 0 THEN robbery_count_365d::DOUBLE PRECISION / area_km2 ELSE NULL END AS robbery_density_per_km2,
                CASE WHEN area_km2 > 0 THEN theft_count_365d::DOUBLE PRECISION / area_km2 ELSE NULL END AS theft_density_per_km2,
                CASE WHEN theft_count_365d > 0 THEN robbery_count_365d::DOUBLE PRECISION / theft_count_365d ELSE NULL END AS robbery_to_theft_ratio,
                :inputs_hash,
                :computed_at
            FROM aggregated_metrics
            ORDER BY city_name ASC, neighborhood_name ASC
            """
        ),
        {"computed_at": computed_at, "inputs_hash": inputs_hash},
    )

    counts_result = await conn.execute(
        text(
            """
            SELECT
                (SELECT COUNT(*)::INT FROM neighborhood_boundaries) AS boundary_rows,
                (SELECT COUNT(*)::INT FROM location_name_aliases) AS alias_rows,
                (SELECT COUNT(*)::INT FROM public_safety_neighborhood_metrics) AS metric_rows
            """
        )
    )
    counts = counts_result.mappings().one()
    return PublicSafetyNeighborhoodAnalyticsResult(
        boundary_rows=int(counts.get("boundary_rows") or 0),
        alias_rows=int(counts.get("alias_rows") or 0),
        metric_rows=int(counts.get("metric_rows") or 0),
        inputs_hash=inputs_hash,
        computed_at=computed_at,
    )


__all__ = [
    "PublicSafetyNeighborhoodAnalyticsResult",
    "refresh_public_safety_neighborhood_analytics",
]