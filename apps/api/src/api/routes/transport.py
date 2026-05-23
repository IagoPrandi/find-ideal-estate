"""Transport endpoints for GeoJSON helpers and vector tiles consumed by MapLibre."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException, Path, Query, Response
from core.db import get_engine
from modules.public_safety import (
    public_safety_group_case_sql,
    public_safety_group_label_case_sql,
)
from modules.zones.vegetation import green_vegetation_case_sql
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError

router = APIRouter(prefix="/transport", tags=["transport"])
logger = logging.getLogger(__name__)

MVT_MEDIA_TYPE = "application/vnd.mapbox-vector-tile"
_VECTOR_TILE_CACHE_VERSION = "20260521_v1"
_VECTOR_TILE_CACHE_CONTROL = "public, max-age=86400, stale-while-revalidate=604800"
_METERS_PER_DEGREE = 111_320.0
_GTFS_STOP_TILE_BUFFER_METERS = 250.0
_GEOSAMPA_BUS_STOP_MATCH_METERS = 45.0
_GEOSAMPA_BUS_TERMINAL_MATCH_METERS = 180.0
_GREEN_TILE_MIN_ZOOM = 12
_FLOOD_TILE_MIN_ZOOM = 14
_SAFETY_TILE_MIN_ZOOM = 10
_SLOW_TILE_QUERY_SECONDS = 2.0
_VECTOR_TILE_STATEMENT_TIMEOUT_MS = 25_000
_TRANSPORT_LINES_MIN_ZOOM = 13.4
_TRANSPORT_LINES_GTFS_MIN_ZOOM = 13.4
_TRANSPORT_STOPS_MIN_ZOOM = 13.1


def _meters_to_degree_buffer(meters: float) -> float:
    return meters / _METERS_PER_DEGREE


def _green_tile_simplify_tolerance(zoom: int) -> float:
    if zoom <= 10:
        return 0.0015
    if zoom <= 12:
        return 0.0006
    if zoom == 13:
        return 0.00045
    if zoom <= 14:
        return 0.0003
    return 0.00005


def _green_tile_min_area_m2(zoom: int) -> float:
    if zoom <= 12:
        return 100000.0
    if zoom == 13:
        return 50000.0
    if zoom == 14:
        return 20000.0
    if zoom == 15:
        return 500.0
    if zoom == 16:
        return 100.0
    return 0.0

_BUS_DESCRIPTOR_SQL = (
    "COALESCE(NULLIF(gr.route_short_name, ''), gr.route_id)"
)


def _tile_response(tile: bytes, *, cache_status: str | None = None) -> Response:
    headers = {"Cache-Control": _VECTOR_TILE_CACHE_CONTROL}
    if cache_status:
        headers["X-Vector-Tile-Cache"] = cache_status
    return Response(content=tile, media_type=MVT_MEDIA_TYPE, headers=headers)


async def _execute_vector_tile_query(conn, sql: str, params: dict, *, layer_name: str) -> bytes:
    started_at = time.perf_counter()
    try:
        await conn.execute(text("SET LOCAL jit = off"))
        await conn.execute(text(f"SET LOCAL statement_timeout = {_VECTOR_TILE_STATEMENT_TIMEOUT_MS}"))
        result = await conn.execute(text(sql), params)
        tile = result.scalar()
        tile_bytes = bytes(tile or b"")
        elapsed_seconds = time.perf_counter() - started_at
        if elapsed_seconds >= _SLOW_TILE_QUERY_SECONDS:
            logger.warning(
                "slow vector tile query for %s z=%s x=%s y=%s elapsed_ms=%.1f bytes=%s",
                layer_name,
                params.get("z"),
                params.get("x"),
                params.get("y"),
                elapsed_seconds * 1000,
                len(tile_bytes),
            )
        return tile_bytes
    except ProgrammingError as exc:
        elapsed_seconds = time.perf_counter() - started_at
        logger.exception(
            "vector tile query failed for %s z=%s x=%s y=%s elapsed_ms=%.1f",
            layer_name,
            params.get("z"),
            params.get("x"),
            params.get("y"),
            elapsed_seconds * 1000,
        )
        raise HTTPException(status_code=500, detail=f"Falha ao gerar vector tile de {layer_name}.") from exc
    except DBAPIError as exc:
        elapsed_seconds = time.perf_counter() - started_at
        logger.exception(
            "vector tile query aborted for %s z=%s x=%s y=%s elapsed_ms=%.1f",
            layer_name,
            params.get("z"),
            params.get("x"),
            params.get("y"),
            elapsed_seconds * 1000,
        )
        raise HTTPException(status_code=503, detail=f"Vector tile de {layer_name} excedeu o tempo limite.") from exc


async def _query_vector_tile(engine, sql: str, params: dict, *, layer_name: str) -> tuple[bytes, str]:
    async with engine.begin() as conn:
        tile = await _execute_vector_tile_query(conn, sql, params, layer_name=layer_name)
    return tile, "MISS"


async def _query_cached_vector_tile(engine, sql: str, params: dict, *, layer_name: str) -> tuple[bytes, str]:
    z = int(params["z"])
    x = int(params["x"])
    y = int(params["y"])

    async with engine.begin() as conn:
        cached = await conn.execute(
            text(
                """
                SELECT tile
                FROM vector_tile_cache
                WHERE layer_name = :layer_name
                  AND z = :z
                  AND x = :x
                  AND y = :y
                  AND cache_version = :cache_version
                  AND (expires_at IS NULL OR expires_at > now())
                """
            ),
            {
                "layer_name": layer_name,
                "z": z,
                "x": x,
                "y": y,
                "cache_version": _VECTOR_TILE_CACHE_VERSION,
            },
        )
        cached_tile = cached.scalar_one_or_none()
        if cached_tile is not None:
            return bytes(cached_tile), "HIT"

        started_at = time.perf_counter()
        tile = await _execute_vector_tile_query(conn, sql, params, layer_name=layer_name)
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        await conn.execute(
            text(
                """
                INSERT INTO vector_tile_cache (
                    layer_name,
                    z,
                    x,
                    y,
                    cache_version,
                    tile,
                    byte_size,
                    generated_at,
                    expires_at,
                    duration_ms
                )
                VALUES (
                    :layer_name,
                    :z,
                    :x,
                    :y,
                    :cache_version,
                    :tile,
                    :byte_size,
                    now(),
                    NULL,
                    :duration_ms
                )
                ON CONFLICT (layer_name, z, x, y, cache_version)
                DO UPDATE SET
                    tile = EXCLUDED.tile,
                    byte_size = EXCLUDED.byte_size,
                    generated_at = now(),
                    expires_at = EXCLUDED.expires_at,
                    duration_ms = EXCLUDED.duration_ms
                """
            ),
            {
                "layer_name": layer_name,
                "z": z,
                "x": x,
                "y": y,
                "cache_version": _VECTOR_TILE_CACHE_VERSION,
                "tile": tile,
                "byte_size": len(tile),
                "duration_ms": duration_ms,
            },
        )
    return tile, "MISS"


_TRANSPORT_LINES_TILE_ROWS_SQL = f"""
WITH bounds AS (
    SELECT
        ST_TileEnvelope(:z, :x, :y) AS env_3857,
        ST_Transform(ST_TileEnvelope(:z, :x, :y), 4326) AS env_4326
), candidate_gtfs_shapes AS (
    SELECT DISTINCT gs.shape_id::text AS shape_id
    FROM gtfs_shapes gs
    CROSS JOIN bounds b
    WHERE gs.location && b.env_4326
), gtfs_line_meta AS (
    SELECT
        gt.shape_id::text AS shape_id,
        COALESCE(
            MIN(NULLIF(gr.route_long_name, '')),
            MIN(NULLIF(gr.route_short_name, '')),
            gt.shape_id::text
        ) AS name,
        COUNT(DISTINCT {_BUS_DESCRIPTOR_SQL}) FILTER (WHERE gr.route_type = 3) AS bus_count,
        COALESCE(
            STRING_AGG(DISTINCT {_BUS_DESCRIPTOR_SQL}, '||' ORDER BY {_BUS_DESCRIPTOR_SQL}) FILTER (WHERE gr.route_type = 3),
            ''::text
        ) AS bus_list,
        CASE
            WHEN MIN(gr.route_type) = 1 THEN 'metro'
            WHEN MIN(gr.route_type) = 2 THEN 'train'
            ELSE 'bus'
        END AS mode
    FROM gtfs_trips gt
    JOIN gtfs_routes gr ON gr.route_id = gt.route_id
    JOIN candidate_gtfs_shapes cgs ON cgs.shape_id = gt.shape_id::text
    GROUP BY gt.shape_id
), gtfs_lines AS (
    SELECT
        cgs.shape_id AS id,
        COALESCE(glm.name, cgs.shape_id) AS name,
        COALESCE(glm.mode, 'bus') AS mode,
        'gtfs_shape'::text AS source_kind,
        COALESCE(glm.bus_count, 0)::bigint AS bus_count,
        COALESCE(glm.bus_list, ''::text) AS bus_list,
        ST_MakeLine(gs.location ORDER BY gs.shape_pt_sequence) AS geom_4326
    FROM gtfs_shapes gs
    JOIN candidate_gtfs_shapes cgs ON cgs.shape_id = gs.shape_id::text
    LEFT JOIN gtfs_line_meta glm ON glm.shape_id = cgs.shape_id
    GROUP BY cgs.shape_id, glm.name, glm.mode, glm.bus_count, glm.bus_list
), corridor_lines AS (
    SELECT
        md5(ST_AsEWKB(g.geometry)::text) AS id,
        COALESCE(NULLIF(g.nm_corredor, ''), 'Corredor de ônibus') AS name,
        'bus'::text AS mode,
        'geosampa_bus_corridor'::text AS source_kind,
        0::bigint AS bus_count,
        ''::text AS bus_list,
        ST_LineMerge(g.geometry) AS geom_4326
    FROM geosampa_bus_corridors g
    CROSS JOIN bounds b
    WHERE g.geometry && b.env_4326
), geosampa_lines AS (
    SELECT
        md5(ST_AsEWKB(g.geometry)::text) AS id,
        COALESCE(NULLIF(g.nm_linha_metro_trem, ''), NULLIF(g.nr_nome_linha, ''), 'Linha de metrô') AS name,
        'metro'::text AS mode,
        'geosampa_metro_line'::text AS source_kind,
        0::bigint AS bus_count,
        ''::text AS bus_list,
        ST_LineMerge(g.geometry) AS geom_4326
    FROM geosampa_metro_lines g
    CROSS JOIN bounds b
    WHERE g.geometry && b.env_4326
    UNION ALL
    SELECT
        md5(ST_AsEWKB(g.geometry)::text) AS id,
        COALESCE(NULLIF(g.nm_linha_metro_trem, ''), 'Linha de trem') AS name,
        'train'::text AS mode,
        'geosampa_train_line'::text AS source_kind,
        0::bigint AS bus_count,
        ''::text AS bus_list,
        ST_LineMerge(g.geometry) AS geom_4326
    FROM geosampa_trem_lines g
    CROSS JOIN bounds b
    WHERE g.geometry && b.env_4326
    UNION ALL
    SELECT
        md5(ST_AsEWKB(g.geometry)::text) AS id,
        COALESCE(NULLIF(g.ln_nome, ''), 'Linha de ônibus') AS name,
        'bus'::text AS mode,
        'geosampa_bus_line'::text AS source_kind,
        0::bigint AS bus_count,
        ''::text AS bus_list,
        ST_LineMerge(g.geometry) AS geom_4326
    FROM geosampa_bus_lines g
    CROSS JOIN bounds b
    WHERE g.geometry && b.env_4326
), merged AS (
    SELECT id, name, mode, source_kind, bus_count, bus_list, geom_4326
    FROM gtfs_lines, bounds
    WHERE geom_4326 IS NOT NULL AND ST_Intersects(geom_4326, env_4326)
    UNION ALL
    SELECT id, name, mode, source_kind, bus_count, bus_list, geom_4326
    FROM corridor_lines, bounds
    WHERE geom_4326 IS NOT NULL AND ST_Intersects(geom_4326, env_4326)
    UNION ALL
    SELECT id, name, mode, source_kind, bus_count, bus_list, geom_4326
    FROM geosampa_lines, bounds
    WHERE geom_4326 IS NOT NULL AND ST_Intersects(geom_4326, env_4326)
), mvtgeom AS (
    SELECT
        id,
        name,
        mode,
        source_kind,
        COALESCE(bus_count, 0)::int AS bus_count,
        COALESCE(bus_list, '') AS bus_list,
        geom_4326,
        env_3857,
        128 AS mvt_buffer
    FROM merged
    CROSS JOIN bounds
)
SELECT
    id,
    name,
    mode,
    source_kind,
    bus_count,
    bus_list,
    geom_4326,
    env_3857,
    mvt_buffer
FROM mvtgeom
"""


_TRANSPORT_LINES_TILE_SQL = f"""
WITH layer_rows AS (
    {_TRANSPORT_LINES_TILE_ROWS_SQL}
), mvtgeom AS (
    SELECT
        id,
        name,
        mode,
        source_kind,
        bus_count,
        bus_list,
        ST_AsMVTGeom(
            ST_Transform(geom_4326, 3857),
            env_3857,
            4096,
            mvt_buffer,
            true
        ) AS geom
    FROM layer_rows
)
SELECT ST_AsMVT(mvtgeom, 'transport_lines', 4096, 'geom')
FROM mvtgeom
WHERE geom IS NOT NULL
"""


def _transport_lines_overview_simplify_tolerance(zoom: int) -> float:
    if zoom <= 10:
        return 0.001
    if zoom <= 12:
        return 0.0005
    if zoom <= 14:
        return 0.0002
    return 0.00008


def _build_transport_lines_overview_tile_sql(zoom: int) -> str:
    simplify_tolerance = _transport_lines_overview_simplify_tolerance(zoom)
    bus_lines_sql = ""
    if zoom >= _TRANSPORT_LINES_GTFS_MIN_ZOOM:
        bus_lines_sql = f"""
    UNION ALL
    SELECT
        md5(ST_AsEWKB(g.geometry)::text) AS id,
        COALESCE(NULLIF(g.ln_nome, ''), 'Linha de ônibus') AS name,
        'bus'::text AS mode,
        'geosampa_bus_line'::text AS source_kind,
        0::bigint AS bus_count,
        ''::text AS bus_list,
        ST_Simplify(ST_LineMerge(g.geometry), {simplify_tolerance}, true) AS geom_4326
    FROM geosampa_bus_lines g
    CROSS JOIN bounds b
    WHERE g.geometry && b.env_4326
"""

    return f"""
WITH bounds AS (
    SELECT
        ST_TileEnvelope(:z, :x, :y) AS env_3857,
        ST_Transform(ST_TileEnvelope(:z, :x, :y), 4326) AS env_4326
), overview_lines AS (
    SELECT
        md5(ST_AsEWKB(g.geometry)::text) AS id,
        COALESCE(NULLIF(g.nm_corredor, ''), 'Corredor de ônibus') AS name,
        'bus'::text AS mode,
        'geosampa_bus_corridor'::text AS source_kind,
        0::bigint AS bus_count,
        ''::text AS bus_list,
        ST_Simplify(ST_LineMerge(g.geometry), {simplify_tolerance}, true) AS geom_4326
    FROM geosampa_bus_corridors g
    CROSS JOIN bounds b
    WHERE g.geometry && b.env_4326
    UNION ALL
    SELECT
        md5(ST_AsEWKB(g.geometry)::text) AS id,
        COALESCE(NULLIF(g.nm_linha_metro_trem, ''), NULLIF(g.nr_nome_linha, ''), 'Linha de metrô') AS name,
        'metro'::text AS mode,
        'geosampa_metro_line'::text AS source_kind,
        0::bigint AS bus_count,
        ''::text AS bus_list,
        ST_Simplify(ST_LineMerge(g.geometry), {simplify_tolerance}, true) AS geom_4326
    FROM geosampa_metro_lines g
    CROSS JOIN bounds b
    WHERE g.geometry && b.env_4326
    UNION ALL
    SELECT
        md5(ST_AsEWKB(g.geometry)::text) AS id,
        COALESCE(NULLIF(g.nm_linha_metro_trem, ''), 'Linha de trem') AS name,
        'train'::text AS mode,
        'geosampa_train_line'::text AS source_kind,
        0::bigint AS bus_count,
        ''::text AS bus_list,
        ST_Simplify(ST_LineMerge(g.geometry), {simplify_tolerance}, true) AS geom_4326
    FROM geosampa_trem_lines g
    CROSS JOIN bounds b
    WHERE g.geometry && b.env_4326
    {bus_lines_sql}
), mvtgeom AS (
    SELECT
        id,
        name,
        mode,
        source_kind,
        COALESCE(bus_count, 0)::int AS bus_count,
        COALESCE(bus_list, '') AS bus_list,
        ST_AsMVTGeom(
            ST_Transform(geom_4326, 3857),
            env_3857,
            4096,
            64,
            true
        ) AS geom
    FROM overview_lines
    CROSS JOIN bounds
    WHERE geom_4326 IS NOT NULL AND ST_Intersects(geom_4326, env_4326)
)
SELECT ST_AsMVT(mvtgeom, 'transport_lines', 4096, 'geom')
FROM mvtgeom
WHERE geom IS NOT NULL
"""


def _build_transport_lines_tile_sql(zoom: int) -> str:
    if zoom < _TRANSPORT_LINES_MIN_ZOOM:
        return "SELECT ''::bytea"
    if zoom >= _TRANSPORT_LINES_GTFS_MIN_ZOOM:
        return _TRANSPORT_LINES_TILE_SQL
    return _build_transport_lines_overview_tile_sql(zoom)


_TRANSPORT_STOPS_TILE_ROWS_SQL = f"""
WITH bounds AS (
    SELECT
        ST_TileEnvelope(:z, :x, :y) AS env_3857,
        ST_Transform(ST_TileEnvelope(:z, :x, :y), 4326) AS env_4326
), geosampa_bus_stop_points AS (
    SELECT
        md5(ST_AsEWKB(g.geometry)::text) AS id,
        COALESCE(NULLIF(g.nm_ponto_onibus, ''), 'Ponto de ônibus') AS name,
        ST_PointOnSurface(g.geometry) AS geom_4326
    FROM geosampa_bus_stops g
    CROSS JOIN bounds b
    WHERE g.geometry && b.env_4326
), geosampa_bus_terminal_points AS (
    SELECT
        md5(ST_AsEWKB(g.geometry)::text) AS id,
        COALESCE(NULLIF(g.nm_terminal, ''), 'Terminal de ônibus') AS name,
        ST_PointOnSurface(g.geometry) AS geom_4326
    FROM geosampa_bus_terminals g
    CROSS JOIN bounds b
    WHERE g.geometry && b.env_4326
), stop_points AS (
    SELECT
        md5(ST_AsEWKB(g.geometry)::text) AS id,
        COALESCE(NULLIF(g.nm_estacao_metro_trem, ''), 'Estação de metrô') AS name,
        'metro_station'::text AS kind,
        'geosampa_metro_station'::text AS source_kind,
        0::int AS bus_count,
        ''::text AS bus_list,
        ST_PointOnSurface(g.geometry) AS geom_4326
    FROM geosampa_metro_stations g
    CROSS JOIN bounds b
    WHERE g.geometry && b.env_4326
    UNION ALL
    SELECT
        md5(ST_AsEWKB(g.geometry)::text) AS id,
        COALESCE(NULLIF(g.nm_estacao_metro_trem, ''), 'Estação de trem') AS name,
        'train_station'::text AS kind,
        'geosampa_train_station'::text AS source_kind,
        0::int AS bus_count,
        ''::text AS bus_list,
        ST_PointOnSurface(g.geometry) AS geom_4326
    FROM geosampa_trem_stations g
    CROSS JOIN bounds b
    WHERE g.geometry && b.env_4326
    UNION ALL
    SELECT
        gbsp.id AS id,
        gbsp.name AS name,
        'bus_stop'::text AS kind,
        'geosampa_bus_stop'::text AS source_kind,
        0::int AS bus_count,
        ''::text AS bus_list,
        gbsp.geom_4326
    FROM geosampa_bus_stop_points gbsp
    UNION ALL
    SELECT
        gbtp.id AS id,
        gbtp.name AS name,
        'bus_terminal'::text AS kind,
        'geosampa_bus_terminal'::text AS source_kind,
        0::int AS bus_count,
        ''::text AS bus_list,
        gbtp.geom_4326
    FROM geosampa_bus_terminal_points gbtp
), mvtgeom AS (
    SELECT
        id,
        name,
        kind,
        source_kind,
        bus_count,
        bus_list,
        geom_4326,
        env_3857,
        64 AS mvt_buffer
    FROM stop_points
    CROSS JOIN bounds
    WHERE geom_4326 IS NOT NULL AND ST_Intersects(geom_4326, env_4326)
)
SELECT
    id,
    name,
    kind,
    source_kind,
    bus_count,
    bus_list,
    geom_4326,
    env_3857,
    mvt_buffer
FROM mvtgeom
"""


_TRANSPORT_STOPS_TILE_SQL = f"""
WITH layer_rows AS (
    {_TRANSPORT_STOPS_TILE_ROWS_SQL}
), mvtgeom AS (
    SELECT
        id,
        name,
        kind,
        source_kind,
        bus_count,
        bus_list,
        ST_AsMVTGeom(
            ST_Transform(geom_4326, 3857),
            env_3857,
            4096,
            mvt_buffer,
            true
        ) AS geom
    FROM layer_rows
)
SELECT ST_AsMVT(mvtgeom, 'transport_stops', 4096, 'geom')
FROM mvtgeom
WHERE geom IS NOT NULL
"""


_TRANSPORT_STOPS_OVERVIEW_TILE_SQL = """
WITH bounds AS (
    SELECT
        ST_TileEnvelope(:z, :x, :y) AS env_3857,
        ST_Transform(ST_TileEnvelope(:z, :x, :y), 4326) AS env_4326
), stop_points AS (
    SELECT
        md5(ST_AsEWKB(g.geometry)::text) AS id,
        COALESCE(NULLIF(g.nm_estacao_metro_trem, ''), 'Estacao de metro') AS name,
        'metro_station'::text AS kind,
        'geosampa_metro_station'::text AS source_kind,
        0::int AS bus_count,
        ''::text AS bus_list,
        ST_PointOnSurface(g.geometry) AS geom_4326
    FROM geosampa_metro_stations g
    CROSS JOIN bounds b
    WHERE g.geometry && b.env_4326
    UNION ALL
    SELECT
        md5(ST_AsEWKB(g.geometry)::text) AS id,
        COALESCE(NULLIF(g.nm_estacao_metro_trem, ''), 'Estacao de trem') AS name,
        'train_station'::text AS kind,
        'geosampa_train_station'::text AS source_kind,
        0::int AS bus_count,
        ''::text AS bus_list,
        ST_PointOnSurface(g.geometry) AS geom_4326
    FROM geosampa_trem_stations g
    CROSS JOIN bounds b
    WHERE g.geometry && b.env_4326
    UNION ALL
    SELECT
        md5(ST_AsEWKB(g.geometry)::text) AS id,
        COALESCE(NULLIF(g.nm_terminal, ''), 'Terminal de onibus') AS name,
        'bus_terminal'::text AS kind,
        'geosampa_bus_terminal'::text AS source_kind,
        0::int AS bus_count,
        ''::text AS bus_list,
        ST_PointOnSurface(g.geometry) AS geom_4326
    FROM geosampa_bus_terminals g
    CROSS JOIN bounds b
    WHERE g.geometry && b.env_4326
), mvtgeom AS (
    SELECT
        id,
        name,
        kind,
        source_kind,
        bus_count,
        bus_list,
        ST_AsMVTGeom(
            ST_Transform(geom_4326, 3857),
            env_3857,
            4096,
            64,
            true
        ) AS geom
    FROM stop_points
    CROSS JOIN bounds
    WHERE geom_4326 IS NOT NULL AND ST_Intersects(geom_4326, env_4326)
)
SELECT ST_AsMVT(mvtgeom, 'transport_stops', 4096, 'geom')
FROM mvtgeom
WHERE geom IS NOT NULL
"""


def _build_transport_stops_tile_sql(zoom: int) -> str:
    if zoom >= 16:
        return _TRANSPORT_STOPS_TILE_SQL
    return _TRANSPORT_STOPS_OVERVIEW_TILE_SQL


_BUS_LINE_DETAIL_SQL = """
SELECT
    COALESCE(NULLIF(gr.route_short_name, ''), gr.route_id) AS route_number
FROM gtfs_trips gt
JOIN gtfs_routes gr ON gr.route_id = gt.route_id
WHERE gt.shape_id::text = :line_id
    AND gr.route_type = 3
GROUP BY route_number
ORDER BY route_number
"""


_BUS_STOP_DETAIL_SQL = """
SELECT
    COALESCE(NULLIF(gr.route_short_name, ''), gr.route_id) AS route_number
FROM gtfs_stop_times gst
JOIN gtfs_trips gt ON gt.trip_id = gst.trip_id
JOIN gtfs_routes gr ON gr.route_id = gt.route_id
WHERE gst.stop_id::text = :stop_id
    AND gr.route_type = 3
GROUP BY route_number
ORDER BY route_number
"""


_GEOSAMPA_BUS_STOP_DETAIL_SQL = f"""
WITH target AS (
    SELECT ST_PointOnSurface(g.geometry) AS geom_4326
    FROM geosampa_bus_stops g
    WHERE md5(ST_AsEWKB(g.geometry)::text) = :stop_id
), nearby_gtfs_stops AS (
    SELECT s.stop_id::text AS stop_id
    FROM gtfs_stops s
    JOIN target t
      ON s.location && ST_Expand(t.geom_4326, {_meters_to_degree_buffer(_GEOSAMPA_BUS_STOP_MATCH_METERS)})
     AND ST_DWithin(s.location::geography, t.geom_4326::geography, {_GEOSAMPA_BUS_STOP_MATCH_METERS})
)
SELECT
    COALESCE(NULLIF(gr.route_short_name, ''), gr.route_id) AS route_number
FROM nearby_gtfs_stops ngs
JOIN gtfs_stop_times gst ON gst.stop_id::text = ngs.stop_id
JOIN gtfs_trips gt ON gt.trip_id = gst.trip_id
JOIN gtfs_routes gr ON gr.route_id = gt.route_id
WHERE gr.route_type = 3
GROUP BY route_number
ORDER BY route_number
"""


_GEOSAMPA_BUS_TERMINAL_DETAIL_SQL = f"""
WITH target AS (
    SELECT ST_PointOnSurface(g.geometry) AS geom_4326
    FROM geosampa_bus_terminals g
    WHERE md5(ST_AsEWKB(g.geometry)::text) = :stop_id
), nearby_gtfs_stops AS (
    SELECT s.stop_id::text AS stop_id
    FROM gtfs_stops s
    JOIN target t
      ON s.location && ST_Expand(t.geom_4326, {_meters_to_degree_buffer(_GEOSAMPA_BUS_TERMINAL_MATCH_METERS)})
     AND ST_DWithin(s.location::geography, t.geom_4326::geography, {_GEOSAMPA_BUS_TERMINAL_MATCH_METERS})
)
SELECT
    COALESCE(NULLIF(gr.route_short_name, ''), gr.route_id) AS route_number
FROM nearby_gtfs_stops ngs
JOIN gtfs_stop_times gst ON gst.stop_id::text = ngs.stop_id
JOIN gtfs_trips gt ON gt.trip_id = gst.trip_id
JOIN gtfs_routes gr ON gr.route_id = gt.route_id
WHERE gr.route_type = 3
GROUP BY route_number
ORDER BY route_number
"""


_SELECTED_GTFS_STOP_TRACE_SQL = """
WITH selected_stop AS (
    SELECT s.stop_id::text AS stop_id
    FROM gtfs_stops s
    WHERE s.stop_id::text = :external_id
), candidate_shapes AS (
    SELECT DISTINCT
        gt.shape_id::text AS shape_id,
        gt.route_id::text AS route_id
    FROM selected_stop ss
    JOIN gtfs_stop_times gst ON gst.stop_id::text = ss.stop_id
    JOIN gtfs_trips gt ON gt.trip_id = gst.trip_id
    JOIN gtfs_routes gr ON gr.route_id = gt.route_id
    WHERE gr.route_type = 3
      AND gt.shape_id IS NOT NULL
      AND (
          COALESCE(array_length(CAST(:route_ids AS TEXT[]), 1), 0) = 0
          OR gt.route_id::text = ANY(CAST(:route_ids AS TEXT[]))
      )
), traced_shapes AS (
    SELECT
        cs.shape_id AS id,
        COALESCE(NULLIF(gr.route_short_name, ''), NULLIF(gr.route_long_name, ''), cs.route_id) AS name,
        'bus'::text AS mode,
        'gtfs_shape'::text AS source_kind,
        ST_AsGeoJSON(ST_MakeLine(gs.location ORDER BY gs.shape_pt_sequence))::JSONB AS geometry
    FROM candidate_shapes cs
    JOIN gtfs_shapes gs ON gs.shape_id::text = cs.shape_id
    JOIN gtfs_routes gr ON gr.route_id::text = cs.route_id
    GROUP BY cs.shape_id, name
)
SELECT id, name, mode, source_kind, geometry
FROM traced_shapes
WHERE geometry IS NOT NULL
LIMIT 80
"""


_SELECTED_GEOSAMPA_BUS_STOP_TRACE_SQL = f"""
WITH anchor AS (
    SELECT ST_PointOnSurface(g.geometry) AS geom_4326
    FROM geosampa_bus_stops g
    WHERE md5(ST_AsEWKB(g.geometry)::text) = :external_id
), nearby_gtfs_stops AS (
    SELECT s.stop_id::text AS stop_id
    FROM gtfs_stops s
    JOIN anchor a
      ON s.location && ST_Expand(a.geom_4326, {_meters_to_degree_buffer(_GEOSAMPA_BUS_STOP_MATCH_METERS)})
     AND ST_DWithin(s.location::geography, a.geom_4326::geography, {_GEOSAMPA_BUS_STOP_MATCH_METERS})
), candidate_shapes AS (
    SELECT DISTINCT
        gt.shape_id::text AS shape_id,
        gt.route_id::text AS route_id
    FROM nearby_gtfs_stops ngs
    JOIN gtfs_stop_times gst ON gst.stop_id::text = ngs.stop_id
    JOIN gtfs_trips gt ON gt.trip_id = gst.trip_id
    JOIN gtfs_routes gr ON gr.route_id = gt.route_id
    WHERE gr.route_type = 3
      AND gt.shape_id IS NOT NULL
      AND (
          COALESCE(array_length(CAST(:route_ids AS TEXT[]), 1), 0) = 0
          OR gt.route_id::text = ANY(CAST(:route_ids AS TEXT[]))
      )
), traced_shapes AS (
    SELECT
        cs.shape_id AS id,
        COALESCE(NULLIF(gr.route_short_name, ''), NULLIF(gr.route_long_name, ''), cs.route_id) AS name,
        'bus'::text AS mode,
        'gtfs_shape'::text AS source_kind,
        ST_AsGeoJSON(ST_MakeLine(gs.location ORDER BY gs.shape_pt_sequence))::JSONB AS geometry
    FROM candidate_shapes cs
    JOIN gtfs_shapes gs ON gs.shape_id::text = cs.shape_id
    JOIN gtfs_routes gr ON gr.route_id::text = cs.route_id
    GROUP BY cs.shape_id, name
)
SELECT id, name, mode, source_kind, geometry
FROM traced_shapes
WHERE geometry IS NOT NULL
LIMIT 80
"""


_SELECTED_GEOSAMPA_BUS_TERMINAL_TRACE_SQL = f"""
WITH anchor AS (
    SELECT ST_PointOnSurface(g.geometry) AS geom_4326
    FROM geosampa_bus_terminals g
    WHERE md5(ST_AsEWKB(g.geometry)::text) = :external_id
), nearby_gtfs_stops AS (
    SELECT s.stop_id::text AS stop_id
    FROM gtfs_stops s
    JOIN anchor a
      ON s.location && ST_Expand(a.geom_4326, {_meters_to_degree_buffer(_GEOSAMPA_BUS_TERMINAL_MATCH_METERS)})
     AND ST_DWithin(s.location::geography, a.geom_4326::geography, {_GEOSAMPA_BUS_TERMINAL_MATCH_METERS})
), candidate_shapes AS (
    SELECT DISTINCT
        gt.shape_id::text AS shape_id,
        gt.route_id::text AS route_id
    FROM nearby_gtfs_stops ngs
    JOIN gtfs_stop_times gst ON gst.stop_id::text = ngs.stop_id
    JOIN gtfs_trips gt ON gt.trip_id = gst.trip_id
    JOIN gtfs_routes gr ON gr.route_id = gt.route_id
    WHERE gr.route_type = 3
      AND gt.shape_id IS NOT NULL
      AND (
          COALESCE(array_length(CAST(:route_ids AS TEXT[]), 1), 0) = 0
          OR gt.route_id::text = ANY(CAST(:route_ids AS TEXT[]))
      )
), traced_shapes AS (
    SELECT
        cs.shape_id AS id,
        COALESCE(NULLIF(gr.route_short_name, ''), NULLIF(gr.route_long_name, ''), cs.route_id) AS name,
        'bus'::text AS mode,
        'gtfs_shape'::text AS source_kind,
        ST_AsGeoJSON(ST_MakeLine(gs.location ORDER BY gs.shape_pt_sequence))::JSONB AS geometry
    FROM candidate_shapes cs
    JOIN gtfs_shapes gs ON gs.shape_id::text = cs.shape_id
    JOIN gtfs_routes gr ON gr.route_id::text = cs.route_id
    GROUP BY cs.shape_id, name
)
SELECT id, name, mode, source_kind, geometry
FROM traced_shapes
WHERE geometry IS NOT NULL
LIMIT 80
"""


_SELECTED_GEOSAMPA_METRO_STATION_TRACE_SQL = """
WITH selected_station AS (
    SELECT ST_PointOnSurface(g.geometry) AS point_geom
    FROM geosampa_metro_stations g
    WHERE md5(ST_AsEWKB(g.geometry)::text) = :external_id
)
SELECT
    md5(ST_AsEWKB(g.geometry)::text) AS id,
    COALESCE(NULLIF(g.nm_linha_metro_trem, ''), NULLIF(g.nr_nome_linha, ''), 'Linha de metrô') AS name,
    'metro'::text AS mode,
    'geosampa_metro_line'::text AS source_kind,
    ST_AsGeoJSON(ST_LineMerge(g.geometry))::JSONB AS geometry
FROM geosampa_metro_lines g
CROSS JOIN selected_station s
WHERE g.geometry IS NOT NULL
  AND ST_DWithin(g.geometry::geography, s.point_geom::geography, 160)
LIMIT 12
"""


_SELECTED_GEOSAMPA_TREM_STATION_TRACE_SQL = """
WITH selected_station AS (
    SELECT ST_PointOnSurface(g.geometry) AS point_geom
    FROM geosampa_trem_stations g
    WHERE md5(ST_AsEWKB(g.geometry)::text) = :external_id
)
SELECT
    md5(ST_AsEWKB(g.geometry)::text) AS id,
    COALESCE(NULLIF(g.nm_linha_metro_trem, ''), 'Linha de trem') AS name,
    'train'::text AS mode,
    'geosampa_train_line'::text AS source_kind,
    ST_AsGeoJSON(ST_LineMerge(g.geometry))::JSONB AS geometry
FROM geosampa_trem_lines g
CROSS JOIN selected_station s
WHERE g.geometry IS NOT NULL
  AND ST_DWithin(g.geometry::geography, s.point_geom::geography, 160)
LIMIT 12
"""


async def _query_transport_stop_detail_rows(conn, stop_id: str, source_kind: str) -> list[dict]:
    sql_by_source_kind = {
        "gtfs_stop": _BUS_STOP_DETAIL_SQL,
        "geosampa_bus_stop": _GEOSAMPA_BUS_STOP_DETAIL_SQL,
        "geosampa_bus_terminal": _GEOSAMPA_BUS_TERMINAL_DETAIL_SQL,
    }
    sql = sql_by_source_kind.get(source_kind)
    if sql is None:
        raise HTTPException(status_code=400, detail="source_kind de parada não suportado")

    return (await conn.execute(text(sql), {"stop_id": stop_id})).mappings().all()


def _build_green_tile_sql(zoom: int) -> str:
    simplify_tolerance = _green_tile_simplify_tolerance(zoom)
    min_area_m2 = _green_tile_min_area_m2(zoom)
    area_filter_sql = ""
    if min_area_m2 > 0:
        if zoom <= 14:
            area_filter_sql = f"""
      AND g.ves_area ~ '^[0-9]+(\\.[0-9]+)?$'
      AND g.ves_area::double precision >= {min_area_m2}
"""
        else:
            area_filter_sql = f"""
      AND COALESCE(
            CASE
                WHEN g.ves_area ~ '^[0-9]+(\\.[0-9]+)?$' THEN g.ves_area::double precision
            END,
            ST_Area(g.geometry::geography)
        ) >= {min_area_m2}
"""
    tile_geometry_sql = (
        "g.geometry"
        if zoom >= 17
        else f"ST_Simplify(g.geometry, {simplify_tolerance}, true)"
    )
    return """
WITH bounds AS (
    SELECT
        ST_TileEnvelope(:z, :x, :y) AS env_3857,
        ST_Transform(ST_TileEnvelope(:z, :x, :y), 4326) AS env_4326
), candidate_rows AS (
    SELECT
        COALESCE(NULLIF(g.primaryindex, ''), 'green_area') AS id,
        COALESCE(NULLIF(g.ves_categ, ''), NULLIF(g.ves_bairro, ''), 'Área verde') AS source_name,
        {green_case_sql} AS vegetation_level,
        {tile_geometry_sql} AS geom_4326,
        env_3857
    FROM geosampa_vegetacao_significativa g
    CROSS JOIN bounds
    WHERE g.geometry && ST_Expand(env_4326, {simplify_tolerance})
      {area_filter_sql}
    ORDER BY
        CASE
            WHEN g.ves_area ~ '^[0-9]+(\\.[0-9]+)?$' THEN g.ves_area::double precision
            ELSE 0
        END DESC
    LIMIT 180
), layer_rows AS (
    SELECT
        id,
        source_name,
        vegetation_level,
        ST_AsMVTGeom(
            ST_Transform(geom_4326, 3857),
            env_3857,
            4096,
            64,
            true
        ) AS geom
    FROM candidate_rows
)
SELECT ST_AsMVT(layer_rows, 'green_areas', 4096, 'geom')
FROM layer_rows
WHERE geom IS NOT NULL
""".format(
        green_case_sql=green_vegetation_case_sql("g.ves_categ"),
        simplify_tolerance=simplify_tolerance,
        tile_geometry_sql=tile_geometry_sql,
        area_filter_sql=area_filter_sql,
    )


_FLOOD_TILE_SQL = """
WITH bounds AS (
    SELECT
        ST_TileEnvelope(:z, :x, :y) AS env_3857,
        ST_Transform(ST_TileEnvelope(:z, :x, :y), 4326) AS env_4326
), layer_rows AS (
    SELECT
        md5(ST_AsEWKB(g.geometry)::text) AS id,
        COALESCE(NULLIF(g.nm_bacia_hidrografica, ''), NULLIF(g.cd_identificador, ''), 'Área alagável') AS source_name,
        ST_AsMVTGeom(
            ST_Transform(ST_SimplifyPreserveTopology(g.geometry, 0.00008), 3857),
            env_3857,
            4096,
            256,
            true
        ) AS geom
    FROM geosampa_mancha_inundacao g
    CROSS JOIN bounds
    WHERE g.geometry && env_4326
      AND ST_Intersects(g.geometry, env_4326)
)
SELECT ST_AsMVT(layer_rows, 'flood_areas', 4096, 'geom')
FROM layer_rows
WHERE geom IS NOT NULL
"""


_PUBLIC_SAFETY_TILE_ROWS_SQL = """
WITH bounds AS (
    SELECT
        ST_TileEnvelope(:z, :x, :y) AS env_3857,
        ST_Transform(ST_TileEnvelope(:z, :x, :y), 4326) AS env_4326
), layer_rows AS (
    SELECT
        psi.id::text AS id,
        {crime_group_sql} AS crime_group,
        {crime_group_label_sql} AS crime_group_label,
        COALESCE(NULLIF(psi.category, ''), 'Ocorrencia sem tipo') AS crime_type,
        CASE
            WHEN psi.occurred_at IS NULL THEN NULL
            ELSE to_char(psi.occurred_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
        END AS occurred_at,
        psi.location AS geom_4326,
        env_3857,
        64 AS mvt_buffer
    FROM public_safety_incidents psi
    CROSS JOIN bounds
    WHERE psi.location IS NOT NULL
      AND psi.location && env_4326
      AND ST_Intersects(psi.location, env_4326)
)
SELECT
    id,
    crime_group,
    crime_group_label,
    crime_type,
    occurred_at,
    geom_4326,
    env_3857,
    mvt_buffer
FROM layer_rows
""".format(
    crime_group_sql=public_safety_group_case_sql("psi.category"),
    crime_group_label_sql=public_safety_group_label_case_sql("psi.category"),
)


_PUBLIC_SAFETY_TILE_SQL = f"""
WITH layer_rows AS (
    {_PUBLIC_SAFETY_TILE_ROWS_SQL}
), mvtgeom AS (
    SELECT
        id,
        crime_group,
        crime_group_label,
        crime_type,
        occurred_at,
        ST_AsMVTGeom(
            ST_Transform(geom_4326, 3857),
            env_3857,
            4096,
            mvt_buffer,
            true
        ) AS geom
    FROM layer_rows
)
SELECT ST_AsMVT(mvtgeom, 'safety_incidents', 4096, 'geom')
FROM mvtgeom
WHERE geom IS NOT NULL
"""


def _public_safety_cluster_grid_size(zoom: int) -> float:
    if zoom <= 10:
        return 0.008
    if zoom == 11:
        return 0.005
    if zoom == 12:
        return 0.0025
    if zoom == 13:
        return 0.0012
    return 0.0


def _public_safety_count_label(count: int) -> str:
    if count < 1000:
        return str(count)
    value = count / 1000.0
    if count % 1000 == 0:
        return f"{int(value)}k"
    return f"{value:.1f}k"


async def _query_public_safety_feature_collection(
    engine,
    *,
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
    zoom: int,
    groups: tuple[str, ...] | None = None,
) -> dict:
    if zoom < _SAFETY_TILE_MIN_ZOOM:
        return {"type": "FeatureCollection", "features": []}

    min_lon_sql = f"{min_lon:.8f}"
    min_lat_sql = f"{min_lat:.8f}"
    max_lon_sql = f"{max_lon:.8f}"
    max_lat_sql = f"{max_lat:.8f}"
    bbox_sql = f"ST_MakeEnvelope({min_lon_sql}, {min_lat_sql}, {max_lon_sql}, {max_lat_sql}, 4326)"
    group_filter_clause = ""
    group_filter_params: dict[str, object] = {}

    if groups:
        group_filter_clause = "\n  AND {crime_group_sql} = ANY(:groups)".format(
            crime_group_sql=public_safety_group_case_sql("psi.category").strip(),
        )
        group_filter_params["groups"] = list(groups)

    raw_incidents_sql = """
WITH bounds AS (
    SELECT {bbox_sql} AS env_4326
)
SELECT
    psi.id::text AS id,
    {crime_group_sql} AS crime_group,
    {crime_group_label_sql} AS crime_group_label,
    COALESCE(NULLIF(psi.category, ''), 'Ocorrencia sem tipo') AS crime_type,
    CASE
        WHEN psi.occurred_at IS NULL THEN NULL
        ELSE to_char(psi.occurred_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
    END AS occurred_at,
    ST_X(psi.location) AS lon,
    ST_Y(psi.location) AS lat
FROM public_safety_incidents psi
CROSS JOIN bounds b
WHERE psi.location IS NOT NULL
  AND psi.location && b.env_4326
  AND ST_Intersects(psi.location, b.env_4326)
    {group_filter_clause}
ORDER BY psi.occurred_at DESC NULLS LAST, psi.id ASC
""".format(
        bbox_sql=bbox_sql,
        crime_group_sql=public_safety_group_case_sql("psi.category"),
        crime_group_label_sql=public_safety_group_label_case_sql("psi.category"),
                group_filter_clause=group_filter_clause,
    )

    clustered_incidents_sql = """
WITH bounds AS (
    SELECT {bbox_sql} AS env_4326
), incidents AS (
    SELECT
        psi.id::text AS id,
        ST_X(psi.location) AS lon,
        ST_Y(psi.location) AS lat,
        FLOOR(ST_X(psi.location) / {grid_size_sql})::bigint AS grid_x,
        FLOOR(ST_Y(psi.location) / {grid_size_sql})::bigint AS grid_y
    FROM public_safety_incidents psi
    CROSS JOIN bounds b
    WHERE psi.location IS NOT NULL
      AND psi.location && b.env_4326
      AND ST_Intersects(psi.location, b.env_4326)
            {group_filter_clause}
), aggregated AS (
    SELECT
        grid_x,
        grid_y,
        COUNT(*)::int AS point_count,
        AVG(lon)::double precision AS centroid_lon,
        AVG(lat)::double precision AS centroid_lat,
        MIN(id) AS incident_id
    FROM incidents
    GROUP BY grid_x, grid_y
)
SELECT
    grid_x,
    grid_y,
    point_count,
    centroid_lon,
    centroid_lat,
    incident_id
FROM aggregated
ORDER BY point_count DESC, grid_x ASC, grid_y ASC
""".format(
        bbox_sql=bbox_sql,
        grid_size_sql=f"{_public_safety_cluster_grid_size(zoom):.8f}",
    group_filter_clause=group_filter_clause,
    )

    singleton_details_sql = """
SELECT
    psi.id::text AS id,
    {crime_group_sql} AS crime_group,
    {crime_group_label_sql} AS crime_group_label,
    COALESCE(NULLIF(psi.category, ''), 'Ocorrencia sem tipo') AS crime_type,
    CASE
        WHEN psi.occurred_at IS NULL THEN NULL
        ELSE to_char(psi.occurred_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
    END AS occurred_at
FROM public_safety_incidents psi
WHERE psi.id::text = ANY(:incident_ids)
""".format(
        crime_group_sql=public_safety_group_case_sql("psi.category"),
        crime_group_label_sql=public_safety_group_label_case_sql("psi.category"),
    )

    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL jit = off"))
        if zoom > 13:
            rows = (await conn.execute(text(raw_incidents_sql), group_filter_params)).mappings().all()
        else:
            rows = (await conn.execute(text(clustered_incidents_sql), group_filter_params)).mappings().all()
            singleton_ids = [str(row.get("incident_id")) for row in rows if int(row.get("point_count") or 0) <= 1 and row.get("incident_id")]
            singleton_details = {}
            if singleton_ids:
                singleton_detail_rows = (await conn.execute(
                    text(singleton_details_sql),
                    {"incident_ids": singleton_ids},
                )).mappings().all()
                singleton_details = {
                    str(row["id"]): row
                    for row in singleton_detail_rows
                }

    if zoom > 13:
        features = []
        for row in rows:
            lon = row.get("lon")
            lat = row.get("lat")
            if lon is None or lat is None:
                continue
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
                    "properties": {
                        "id": str(row["id"]),
                        "crime_group": row.get("crime_group"),
                        "crime_group_label": row.get("crime_group_label"),
                        "crime_type": row.get("crime_type"),
                        "occurred_at": row.get("occurred_at"),
                    },
                }
            )
        return {"type": "FeatureCollection", "features": features}

    features = []
    for row in rows:
        point_count = int(row.get("point_count") or 0)
        centroid_lon = row.get("centroid_lon")
        centroid_lat = row.get("centroid_lat")
        if centroid_lon is None or centroid_lat is None:
            continue

        if point_count <= 1:
            incident_id = str(row.get("incident_id") or "")
            detail_row = singleton_details.get(incident_id, {})
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [float(centroid_lon), float(centroid_lat)]},
                    "properties": {
                        "id": incident_id,
                        "crime_group": detail_row.get("crime_group"),
                        "crime_group_label": detail_row.get("crime_group_label"),
                        "crime_type": detail_row.get("crime_type"),
                        "occurred_at": detail_row.get("occurred_at"),
                    },
                }
            )
            continue

        grid_x = int(row.get("grid_x") or 0)
        grid_y = int(row.get("grid_y") or 0)
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [centroid_lon, centroid_lat]},
                "properties": {
                    "id": f"cluster:{zoom}:{grid_x}:{grid_y}",
                    "point_count": point_count,
                    "point_count_abbreviated": _public_safety_count_label(point_count),
                },
            }
        )

    return {"type": "FeatureCollection", "features": features}


@router.get("/tiles/lines/{z}/{x}/{y}.pbf")
async def get_transport_lines_tile(
    z: int = Path(..., ge=0, le=22),
    x: int = Path(..., ge=0),
    y: int = Path(..., ge=0),
) -> Response:
    engine = get_engine()
    tile, cache_status = await _query_cached_vector_tile(
        engine,
        _build_transport_lines_tile_sql(z),
        {"z": z, "x": x, "y": y},
        layer_name="transport_lines",
    )
    return _tile_response(tile, cache_status=cache_status)


@router.get("/tiles/stops/{z}/{x}/{y}.pbf")
async def get_transport_stops_tile(
    z: int = Path(..., ge=0, le=22),
    x: int = Path(..., ge=0),
    y: int = Path(..., ge=0),
) -> Response:
    if z < _TRANSPORT_STOPS_MIN_ZOOM:
        return _tile_response(b"", cache_status="BYPASS")

    engine = get_engine()
    tile, cache_status = await _query_cached_vector_tile(
        engine,
        _build_transport_stops_tile_sql(z),
        {"z": z, "x": x, "y": y},
        layer_name="transport_stops",
    )
    return _tile_response(tile, cache_status=cache_status)


@router.get("/tiles/environment/green/{z}/{x}/{y}.pbf")
async def get_green_areas_tile(
    z: int = Path(..., ge=0, le=22),
    x: int = Path(..., ge=0),
    y: int = Path(..., ge=0),
) -> Response:
    if z < _GREEN_TILE_MIN_ZOOM:
        return _tile_response(b"", cache_status="BYPASS")

    engine = get_engine()
    tile, cache_status = await _query_cached_vector_tile(
        engine,
        _build_green_tile_sql(z),
        {"z": z, "x": x, "y": y},
        layer_name="green_areas",
    )
    return _tile_response(tile, cache_status=cache_status)


@router.get("/tiles/environment/flood/{z}/{x}/{y}.pbf")
async def get_flood_areas_tile(
    z: int = Path(..., ge=0, le=22),
    x: int = Path(..., ge=0),
    y: int = Path(..., ge=0),
) -> Response:
    if z < _FLOOD_TILE_MIN_ZOOM:
        return _tile_response(b"", cache_status="BYPASS")

    engine = get_engine()
    tile, cache_status = await _query_cached_vector_tile(
        engine,
        _FLOOD_TILE_SQL,
        {"z": z, "x": x, "y": y},
        layer_name="flood_areas",
    )
    return _tile_response(tile, cache_status=cache_status)


@router.get("/tiles/environment/safety/{z}/{x}/{y}.pbf")
async def get_public_safety_tile(
    z: int = Path(..., ge=0, le=22),
    x: int = Path(..., ge=0),
    y: int = Path(..., ge=0),
) -> Response:
    if z < _SAFETY_TILE_MIN_ZOOM:
        return _tile_response(b"", cache_status="BYPASS")

    engine = get_engine()
    tile, cache_status = await _query_cached_vector_tile(
        engine,
        _PUBLIC_SAFETY_TILE_SQL,
        {"z": z, "x": x, "y": y},
        layer_name="safety_incidents",
    )
    return _tile_response(tile, cache_status=cache_status)


@router.get("/safety-incidents")
async def get_public_safety_incidents(
    bbox: str = Query(..., min_length=7),
    zoom: int = Query(..., ge=0, le=22),
    groups: str | None = Query(default=None),
) -> dict:
    raw_parts = bbox.split(",")
    if len(raw_parts) != 4:
        raise HTTPException(status_code=400, detail="bbox invalido. Use minLon,minLat,maxLon,maxLat")

    try:
        min_lon, min_lat, max_lon, max_lat = (float(part.strip()) for part in raw_parts)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="bbox invalido. Coordenadas devem ser numericas") from exc

    if min_lon >= max_lon or min_lat >= max_lat:
        raise HTTPException(status_code=400, detail="bbox invalido. Envelope deve ter min < max")

    allowed_groups = {"theft", "robbery", "violence", "sexual", "drugs", "other"}
    parsed_groups: tuple[str, ...] | None = None
    if groups is not None:
        parsed_group_values = tuple(part.strip() for part in groups.split(",") if part.strip())
        invalid_groups = sorted({group for group in parsed_group_values if group not in allowed_groups})
        if invalid_groups:
            raise HTTPException(status_code=400, detail="groups invalido. Use theft,robbery,violence,sexual,drugs,other")
        parsed_groups = tuple(dict.fromkeys(parsed_group_values))

    engine = get_engine()
    return await _query_public_safety_feature_collection(
        engine,
        min_lon=min_lon,
        min_lat=min_lat,
        max_lon=max_lon,
        max_lat=max_lat,
        zoom=zoom,
        groups=parsed_groups,
    )


@router.get("/details/bus-line")
async def get_bus_line_details(
    line_id: str = Query(..., min_length=1),
) -> dict:
    engine = get_engine()
    async with engine.connect() as conn:
        rows = (await conn.execute(text(_BUS_LINE_DETAIL_SQL), {"line_id": line_id})).mappings().all()

    buses = [str(row["route_number"]) for row in rows]
    return {
        "count": len(buses),
        "buses": buses,
        "source": "gtfs",
    }


@router.get("/details/bus-stop")
async def get_bus_stop_details(
    stop_id: str = Query(..., min_length=1),
) -> dict:
    engine = get_engine()
    async with engine.connect() as conn:
        rows = await _query_transport_stop_detail_rows(conn, stop_id, "gtfs_stop")

    buses = [str(row["route_number"]) for row in rows]
    return {
        "count": len(buses),
        "buses": buses,
        "source": "gtfs",
    }


@router.get("/details/transport-stop")
async def get_transport_stop_details(
    stop_id: str = Query(..., min_length=1),
    source_kind: str = Query(..., min_length=1),
) -> dict:
    engine = get_engine()
    async with engine.connect() as conn:
        rows = await _query_transport_stop_detail_rows(conn, stop_id, source_kind)

    buses = [str(row["route_number"]) for row in rows]
    return {
        "count": len(buses),
        "buses": buses,
        "source": source_kind,
    }


@router.get("/selected-trace")
async def get_selected_transport_trace(
    source_kind: str = Query(..., min_length=1),
    external_id: str = Query(..., min_length=1),
    route_ids: list[str] = Query(default=[]),
) -> dict:
    sql_by_source_kind = {
        "gtfs_stop": _SELECTED_GTFS_STOP_TRACE_SQL,
        "geosampa_bus_stop": _SELECTED_GEOSAMPA_BUS_STOP_TRACE_SQL,
        "geosampa_bus_terminal": _SELECTED_GEOSAMPA_BUS_TERMINAL_TRACE_SQL,
        "geosampa_metro_station": _SELECTED_GEOSAMPA_METRO_STATION_TRACE_SQL,
        "geosampa_trem_station": _SELECTED_GEOSAMPA_TREM_STATION_TRACE_SQL,
    }
    sql = sql_by_source_kind.get(source_kind)
    if sql is None:
        raise HTTPException(status_code=400, detail="source_kind de trajeto selecionado não suportado")

    features = await _safe_query_lines(
        get_engine(),
        sql,
        {
            "external_id": external_id,
            "route_ids": route_ids,
        },
    )
    return {"type": "FeatureCollection", "features": features}


async def _safe_query_features(engine, sql: str, params: dict) -> list[dict]:
    """Execute spatial query and return GeoJSON features; returns [] on any table/query error."""
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text(sql), params)
            rows = result.mappings().all()
        features = []
        for row in rows:
            lat = row.get("lat")
            lon = row.get("lon")
            if lat is None or lon is None:
                continue
            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [float(lon), float(lat)],
                    },
                    "properties": {
                        "id": str(row.get("id") or ""),
                        "name": str(row.get("name") or ""),
                        "kind": str(row.get("kind") or "stop"),
                    },
                }
            )
        return features
    except (ProgrammingError, Exception):
        return []


async def _safe_query_lines(engine, sql: str, params: dict) -> list[dict]:
    """Execute line query and map rows to GeoJSON features."""
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text(sql), params)
            rows = result.mappings().all()
        features = []
        for row in rows:
            geom = row.get("geometry")
            if not geom:
                continue
            features.append(
                {
                    "type": "Feature",
                    "geometry": geom,
                    "properties": {
                        "id": str(row.get("id") or ""),
                        "name": str(row.get("name") or ""),
                        "mode": str(row.get("mode") or "bus"),
                        "source_kind": str(row.get("source_kind") or ""),
                    },
                }
            )
        return features
    except (ProgrammingError, Exception):
        return []


@router.get("/stops")
async def get_transport_stops(
    lon: float = Query(default=0.0),
    lat: float = Query(default=0.0),
    radius_m: int = Query(default=2500, ge=100, le=30000),
    bbox: str | None = Query(default=None),
) -> dict:
    """Return GeoJSON stops: GTFS bus stops + GeoSampa metro & trem stations.

    Accepts either bbox=minLon,minLat,maxLon,maxLat (viewport query)
    or lon+lat+radius_m (proximity query).  Unknown/missing tables return empty features
    and never raise 500 errors.
    """
    engine = get_engine()
    features: list[dict] = []

    if bbox:
        raw_parts = bbox.split(",")
        if len(raw_parts) != 4:
            return {"type": "FeatureCollection", "features": []}
        try:
            x1, y1, x2, y2 = (float(p.strip()) for p in raw_parts)
        except ValueError:
            return {"type": "FeatureCollection", "features": []}

        sp: dict = {"x1": x1, "y1": y1, "x2": x2, "y2": y2}

        gtfs_filter = (
            "ST_DWithin(s.location, ST_MakeEnvelope(:x1, :y1, :x2, :y2, 4326), 0)"
        )
        geom_filter = (
            "ST_DWithin(ST_PointOnSurface(g.geometry), ST_MakeEnvelope(:x1, :y1, :x2, :y2, 4326), 0)"
        )
    else:
        sp = {"cx": float(lon), "cy": float(lat), "rm": float(radius_m)}
        gtfs_filter = (
            "ST_DWithin(s.location::geography, ST_SetSRID(ST_MakePoint(:cx, :cy), 4326)::geography, :rm)"
        )
        geom_filter = (
            "ST_DWithin(ST_PointOnSurface(g.geometry)::geography, "
            "ST_SetSRID(ST_MakePoint(:cx, :cy), 4326)::geography, :rm)"
        )

    # --- GTFS bus stops ---
    features += await _safe_query_features(
        engine,
        f"""
        SELECT
            s.stop_id::text          AS id,
            s.stop_name::text        AS name,
            ST_Y(s.location)         AS lat,
            ST_X(s.location)         AS lon,
            'bus_stop'::text         AS kind
        FROM gtfs_stops s
        WHERE {gtfs_filter}
        ORDER BY s.stop_name
        LIMIT 600
        """,
        sp,
    )

    # --- GeoSampa metro stations ---
    features += await _safe_query_features(
        engine,
        f"""
        SELECT
            md5(ST_AsEWKB(g.geometry)::text)         AS id,
            NULL::text                               AS name,
            ST_Y(ST_PointOnSurface(g.geometry))      AS lat,
            ST_X(ST_PointOnSurface(g.geometry))      AS lon,
            'metro_station'::text                    AS kind
        FROM geosampa_metro_stations g
        WHERE {geom_filter}
        LIMIT 150
        """,
        sp,
    )

    # --- GeoSampa trem stations ---
    features += await _safe_query_features(
        engine,
        f"""
        SELECT
            md5(ST_AsEWKB(g.geometry)::text)         AS id,
            NULL::text                               AS name,
            ST_Y(ST_PointOnSurface(g.geometry))      AS lat,
            ST_X(ST_PointOnSurface(g.geometry))      AS lon,
            'train_station'::text                    AS kind
        FROM geosampa_trem_stations g
        WHERE {geom_filter}
        LIMIT 150
        """,
        sp,
    )

    # --- GeoSampa bus stops (geoportal_ponto_onibus) ---
    features += await _safe_query_features(
        engine,
        f"""
        SELECT
            md5(ST_AsEWKB(g.geometry)::text)         AS id,
            NULL::text                               AS name,
            ST_Y(ST_PointOnSurface(g.geometry))      AS lat,
            ST_X(ST_PointOnSurface(g.geometry))      AS lon,
            'bus_stop'::text                         AS kind
        FROM geosampa_bus_stops g
        WHERE {geom_filter}
        LIMIT 400
        """,
        sp,
    )

    return {"type": "FeatureCollection", "features": features}


@router.get("/layers")
async def get_transport_layers(
    bbox: str = Query(..., description="minLon,minLat,maxLon,maxLat"),
) -> dict:
    """Return route and stop FeatureCollections for current viewport."""
    parts = bbox.split(",")
    if len(parts) != 4:
        return {
            "routes": {"type": "FeatureCollection", "features": []},
            "stops": {"type": "FeatureCollection", "features": []},
        }

    try:
        x1, y1, x2, y2 = (float(p.strip()) for p in parts)
    except ValueError:
        return {
            "routes": {"type": "FeatureCollection", "features": []},
            "stops": {"type": "FeatureCollection", "features": []},
        }

    engine = get_engine()
    params = {"x1": x1, "y1": y1, "x2": x2, "y2": y2}

    # GTFS shapes classified by route_type (2=rail as train; others as bus for visualization)
    route_features = await _safe_query_lines(
        engine,
        """
        WITH viewport AS (
            SELECT ST_MakeEnvelope(:x1, :y1, :x2, :y2, 4326) AS env
        ), candidate_gtfs_shapes AS (
            SELECT DISTINCT gs.shape_id::text AS shape_id
            FROM gtfs_shapes gs
            CROSS JOIN viewport v
            WHERE ST_Intersects(gs.location, v.env)
        ), lines AS (
            SELECT
                cgs.shape_id AS id,
                MIN(gr.route_long_name)::text AS name,
                CASE WHEN MIN(gr.route_type) = 2 THEN 'train' ELSE 'bus' END AS mode,
                ST_AsGeoJSON(ST_MakeLine(gs.location ORDER BY gs.shape_pt_sequence))::JSONB AS geometry
            FROM gtfs_shapes gs
            JOIN candidate_gtfs_shapes cgs ON cgs.shape_id = gs.shape_id::text
            JOIN gtfs_trips gt ON gt.shape_id = gs.shape_id
            JOIN gtfs_routes gr ON gr.route_id = gt.route_id
            GROUP BY gs.shape_id
        )
        SELECT id, name, mode, geometry
        FROM lines
        WHERE geometry IS NOT NULL
        LIMIT 500
        """,
        params,
    )

    # GeoSampa bus corridors as bus lines overlay.
    route_features += await _safe_query_lines(
        engine,
        """
        SELECT
            md5(ST_AsEWKB(g.geometry)::text) AS id,
            NULL::text AS name,
            'bus'::text AS mode,
            ST_AsGeoJSON(ST_LineMerge(g.geometry))::JSONB AS geometry
        FROM geosampa_bus_corridors g
        WHERE ST_Intersects(g.geometry, ST_MakeEnvelope(:x1, :y1, :x2, :y2, 4326))
        LIMIT 300
        """,
        params,
    )

    stops_payload = await get_transport_stops(bbox=bbox)
    return {
        "routes": {"type": "FeatureCollection", "features": route_features},
        "stops": stops_payload,
    }
