from __future__ import annotations

from collections.abc import Sequence
import json
from typing import Any
from uuid import UUID

from contracts import TransportPointRead
from core.db import get_engine
from sqlalchemy import text
from sqlalchemy.engine import RowMapping

_WALKING_SPEED_M_PER_SEC = 1.25

_JOB_JOURNEY_CONTEXT_SQL = text(
    """
    SELECT
        j.id AS journey_id,
        j.input_snapshot,
        CASE
            WHEN j.secondary_reference_point IS NULL THEN NULL
            ELSE ST_Y(j.secondary_reference_point)
        END AS secondary_reference_lat,
        CASE
            WHEN j.secondary_reference_point IS NULL THEN NULL
            ELSE ST_X(j.secondary_reference_point)
        END AS secondary_reference_lon
    FROM jobs jb
    JOIN journeys j ON j.id = jb.journey_id
    WHERE jb.id = :job_id
    """
)


class TransportSearchError(RuntimeError):
    """Raised when transport point search cannot run with current journey payload."""


def _source_filter_tokens(input_snapshot: dict[str, Any] | None) -> set[str]:
    if not isinstance(input_snapshot, dict):
        return {"gtfs", "metro", "trem"}

    raw_modal = (
        input_snapshot.get("transport_modal")
        or input_snapshot.get("modal")
        or input_snapshot.get("travel_mode")
    )
    modal = str(raw_modal or "transit").strip().lower()
    if modal in {"transit", "public", "public_transport", "bus+metro+trem"}:
        return {"gtfs", "metro", "trem"}
    if modal in {"bus", "onibus"}:
        return {"gtfs"}
    if modal in {"metro", "subway"}:
        return {"metro"}
    if modal in {"trem", "train", "rail"}:
        return {"trem"}

    # Non-transit selection keeps full set for now until FE step 2 introduces strict modal choices.
    return {"gtfs", "metro", "trem"}


def _extract_reference_point(
    input_snapshot: dict[str, Any] | None,
    *,
    secondary_lat: float | None,
    secondary_lon: float | None,
) -> tuple[float, float]:
    if isinstance(input_snapshot, dict):
        reference = input_snapshot.get("reference_point")
        if isinstance(reference, dict):
            lat = reference.get("lat")
            lon = reference.get("lon")
            if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                return float(lat), float(lon)

    if isinstance(secondary_lat, (int, float)) and isinstance(secondary_lon, (int, float)):
        return float(secondary_lat), float(secondary_lon)

    raise TransportSearchError("Journey has no valid reference point for transport search")


def _extract_radius_meters(input_snapshot: dict[str, Any] | None) -> int:
    if not isinstance(input_snapshot, dict):
        return 300

    for key in ("transport_search_radius_meters", "zone_radius_meters", "radius_meters", "radius"):
        raw_value = input_snapshot.get(key)
        if isinstance(raw_value, (int, float)) and raw_value > 0:
            return int(raw_value)
    return 300


def _build_transport_search_sql(source_tokens: set[str]) -> str:
    include_gtfs = "gtfs" in source_tokens
    include_metro = "metro" in source_tokens
    include_trem = "trem" in source_tokens

    selects: list[str] = []
    if include_gtfs:
        selects.append(
            """
            SELECT
                'gtfs_stop'::text AS source,
                s.stop_id::text AS external_id,
                s.stop_name::text AS name,
                ST_Y(s.location) AS lat,
                ST_X(s.location) AS lon,
                ST_Distance(s.location::geography, ref.ref_point::geography) AS walk_distance_m,
                COALESCE(route_agg.route_count, 0) AS route_count,
                COALESCE(route_agg.route_ids, ARRAY[]::text[]) AS route_ids,
                ARRAY['bus']::text[] AS modal_types
            FROM gtfs_stops s
            CROSS JOIN ref
            LEFT JOIN (
                SELECT
                    st.stop_id,
                    COUNT(DISTINCT t.route_id) AS route_count,
                    ARRAY_AGG(DISTINCT t.route_id) FILTER (WHERE t.route_id IS NOT NULL) AS route_ids
                FROM gtfs_stop_times st
                JOIN gtfs_trips t ON t.trip_id = st.trip_id
                GROUP BY st.stop_id
            ) route_agg ON route_agg.stop_id = s.stop_id
            WHERE ST_DWithin(s.location::geography, ref.ref_point::geography, ref.radius_m)
            """
        )
    if include_metro:
        selects.append(
            """
            SELECT
                'geosampa_metro_station'::text AS source,
                md5(ST_AsEWKB(g.geometry)::text) AS external_id,
                NULL::text AS name,
                ST_Y(ST_PointOnSurface(g.geometry)) AS lat,
                ST_X(ST_PointOnSurface(g.geometry)) AS lon,
                ST_Distance(ST_PointOnSurface(g.geometry)::geography, ref.ref_point::geography) AS walk_distance_m,
                0 AS route_count,
                ARRAY[]::text[] AS route_ids,
                ARRAY['metro']::text[] AS modal_types
            FROM geosampa_metro_stations g
            CROSS JOIN ref
            WHERE ST_DWithin(ST_PointOnSurface(g.geometry)::geography, ref.ref_point::geography, ref.radius_m)
            """
        )
    if include_trem:
        selects.append(
            """
            SELECT
                'geosampa_trem_station'::text AS source,
                md5(ST_AsEWKB(g.geometry)::text) AS external_id,
                NULL::text AS name,
                ST_Y(ST_PointOnSurface(g.geometry)) AS lat,
                ST_X(ST_PointOnSurface(g.geometry)) AS lon,
                ST_Distance(ST_PointOnSurface(g.geometry)::geography, ref.ref_point::geography) AS walk_distance_m,
                0 AS route_count,
                ARRAY[]::text[] AS route_ids,
                ARRAY['train']::text[] AS modal_types
            FROM geosampa_trem_stations g
            CROSS JOIN ref
            WHERE ST_DWithin(ST_PointOnSurface(g.geometry)::geography, ref.ref_point::geography, ref.radius_m)
            """
        )

    if not selects:
        return """
        WITH ref AS (
            SELECT
                ST_SetSRID(ST_MakePoint(CAST(:ref_lon AS DOUBLE PRECISION), CAST(:ref_lat AS DOUBLE PRECISION)), 4326) AS ref_point,
                CAST(:radius_m AS DOUBLE PRECISION) AS radius_m
        )
        SELECT
            NULL::text AS source,
            NULL::text AS external_id,
            NULL::text AS name,
            NULL::double precision AS lat,
            NULL::double precision AS lon,
            NULL::double precision AS walk_distance_m,
            NULL::int AS route_count,
            ARRAY[]::text[] AS route_ids,
            ARRAY[]::text[] AS modal_types
        WHERE FALSE
        """

    return f"""
    WITH ref AS (
        SELECT
            ST_SetSRID(ST_MakePoint(CAST(:ref_lon AS DOUBLE PRECISION), CAST(:ref_lat AS DOUBLE PRECISION)), 4326) AS ref_point,
            CAST(:radius_m AS DOUBLE PRECISION) AS radius_m
    )
    SELECT
        source,
        external_id,
        name,
        lat,
        lon,
        walk_distance_m,
        route_count,
        route_ids,
        modal_types
    FROM (
        {' UNION ALL '.join(selects)}
    ) ranked
    ORDER BY walk_distance_m ASC, route_count DESC
    """


def _row_to_transport_point(row: RowMapping) -> TransportPointRead:
    raw_route_ids = row["route_ids"] if isinstance(row["route_ids"], Sequence) else []
    raw_modal_types = row["modal_types"] if isinstance(row["modal_types"], Sequence) else []
    return TransportPointRead(
        id=row["id"],
        journey_id=row["journey_id"],
        source=str(row["source"]),
        external_id=row["external_id"],
        name=row["name"],
        lat=float(row["lat"]),
        lon=float(row["lon"]),
        walk_time_sec=int(row["walk_time_sec"]),
        walk_distance_m=int(row["walk_distance_m"]),
        route_ids=[str(item) for item in raw_route_ids if item],
        modal_types=[str(item) for item in raw_modal_types if item],
        route_count=int(row["route_count"]),
        created_at=row["created_at"],
    )


async def run_transport_search_for_job(job_id: UUID) -> int:
    engine = get_engine()
    async with engine.begin() as conn:
        context_result = await conn.execute(_JOB_JOURNEY_CONTEXT_SQL, {"job_id": job_id})
        context_row = context_result.mappings().first()
        if context_row is None:
            raise TransportSearchError(f"Job {job_id} not found")

        journey_id = context_row["journey_id"]
        input_snapshot = context_row["input_snapshot"]
        ref_lat, ref_lon = _extract_reference_point(
            input_snapshot,
            secondary_lat=context_row["secondary_reference_lat"],
            secondary_lon=context_row["secondary_reference_lon"],
        )
        radius_m = _extract_radius_meters(input_snapshot)
        source_tokens = _source_filter_tokens(input_snapshot)

        sql = _build_transport_search_sql(source_tokens)
        search_result = await conn.execute(
            text(sql),
            {
                "ref_lat": ref_lat,
                "ref_lon": ref_lon,
                "radius_m": radius_m,
            },
        )
        rows = search_result.mappings().all()

        await conn.execute(text("DELETE FROM transport_points WHERE journey_id = :journey_id"), {"journey_id": journey_id})

        if rows:
            payload: list[dict[str, Any]] = []
            for row in rows:
                walk_distance_m = max(0, int(round(float(row["walk_distance_m"] or 0.0))))
                walk_time_sec = max(0, int(round(walk_distance_m / _WALKING_SPEED_M_PER_SEC)))
                payload.append(
                    {
                        "journey_id": journey_id,
                        "source": row["source"],
                        "external_id": row["external_id"],
                        "name": row["name"],
                        "lat": float(row["lat"]),
                        "lon": float(row["lon"]),
                        "walk_time_sec": walk_time_sec,
                        "walk_distance_m": walk_distance_m,
                        "route_ids": list(row["route_ids"] or []),
                        "modal_types": list(row["modal_types"] or []),
                    }
                )
            await conn.execute(
                text(
                    """
                    INSERT INTO transport_points (
                        journey_id,
                        source,
                        external_id,
                        name,
                        location,
                        walk_time_sec,
                        walk_distance_m,
                        route_ids,
                        modal_types
                    ) VALUES (
                        :journey_id,
                        :source,
                        :external_id,
                        :name,
                        ST_SetSRID(ST_MakePoint(CAST(:lon AS DOUBLE PRECISION), CAST(:lat AS DOUBLE PRECISION)), 4326),
                        :walk_time_sec,
                        :walk_distance_m,
                        CAST(:route_ids AS TEXT[]),
                        CAST(:modal_types AS TEXT[])
                    )
                    """
                ),
                payload,
            )

        await conn.execute(
            text(
                """
                UPDATE jobs
                SET result_ref = CAST(:result_ref AS JSONB)
                WHERE id = :job_id
                """
            ),
            {
                "job_id": job_id,
                "result_ref": json.dumps(
                    {
                        "transport_points_count": len(rows),
                        "source_filter": sorted(source_tokens),
                    }
                ),
            },
        )

    return len(rows)


async def list_transport_points_for_journey(journey_id: UUID) -> list[TransportPointRead]:
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                """
                SELECT
                    tp.id,
                    tp.journey_id,
                    tp.source,
                    tp.external_id,
                    tp.name,
                    ST_Y(tp.location) AS lat,
                    ST_X(tp.location) AS lon,
                    COALESCE(tp.walk_time_sec, 0) AS walk_time_sec,
                    COALESCE(tp.walk_distance_m, 0) AS walk_distance_m,
                    COALESCE(tp.route_ids, ARRAY[]::text[]) AS route_ids,
                    COALESCE(tp.modal_types, ARRAY[]::text[]) AS modal_types,
                    COALESCE(array_length(tp.route_ids, 1), 0) AS route_count,
                    tp.created_at
                FROM transport_points tp
                WHERE tp.journey_id = :journey_id
                ORDER BY tp.walk_distance_m ASC, COALESCE(array_length(tp.route_ids, 1), 0) DESC, tp.created_at ASC
                """
            ),
            {"journey_id": journey_id},
        )
        rows = result.mappings().all()
    return [_row_to_transport_point(row) for row in rows]
