"""Transport endpoints for GeoJSON helpers and vector tiles consumed by MapLibre."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Path, Query, Response
from core.db import get_engine
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

router = APIRouter(prefix="/transport", tags=["transport"])
logger = logging.getLogger(__name__)

MVT_MEDIA_TYPE = "application/vnd.mapbox-vector-tile"


async def _query_vector_tile(engine, sql: str, params: dict, *, layer_name: str) -> bytes:
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text(sql), params)
            tile = result.scalar()
        return bytes(tile or b"")
    except ProgrammingError as exc:
        logger.exception("vector tile query failed for %s", layer_name)
        raise HTTPException(status_code=500, detail=f"Falha ao gerar vector tile de {layer_name}.") from exc


_TRANSPORT_LINES_TILE_SQL = """
WITH bounds AS (
    SELECT
        ST_TileEnvelope(:z, :x, :y) AS env_3857,
        ST_Transform(ST_TileEnvelope(:z, :x, :y), 4326) AS env_4326
), gtfs_lines AS (
    SELECT
        gs.shape_id::text AS id,
        COALESCE(
            MIN(NULLIF(gr.route_long_name, '')),
            MIN(NULLIF(gr.route_short_name, '')),
            gs.shape_id::text
        ) AS name,
        CASE
            WHEN MIN(gr.route_type) = 1 THEN 'metro'
            WHEN MIN(gr.route_type) = 2 THEN 'train'
            ELSE 'bus'
        END AS mode,
        ST_MakeLine(gs.location ORDER BY gs.shape_pt_sequence) AS geom_4326
    FROM gtfs_shapes gs
    JOIN gtfs_trips gt ON gt.shape_id = gs.shape_id
    JOIN gtfs_routes gr ON gr.route_id = gt.route_id
    CROSS JOIN bounds b
    WHERE gs.location && b.env_4326
    GROUP BY gs.shape_id
), corridor_lines AS (
    SELECT
        md5(ST_AsEWKB(g.geometry)::text) AS id,
        COALESCE(NULLIF(g.nm_corredor, ''), 'Corredor de ônibus') AS name,
        'bus'::text AS mode,
        ST_LineMerge(g.geometry) AS geom_4326
    FROM geosampa_bus_corridors g
    CROSS JOIN bounds b
    WHERE g.geometry && b.env_4326
), geosampa_lines AS (
    SELECT
        md5(ST_AsEWKB(g.geometry)::text) AS id,
        COALESCE(NULLIF(g.nm_linha_metro_trem, ''), NULLIF(g.nr_nome_linha, ''), 'Linha de metrô') AS name,
        'metro'::text AS mode,
        ST_LineMerge(g.geometry) AS geom_4326
    FROM geosampa_metro_lines g
    CROSS JOIN bounds b
    WHERE g.geometry && b.env_4326
    UNION ALL
    SELECT
        md5(ST_AsEWKB(g.geometry)::text) AS id,
        COALESCE(NULLIF(g.nm_linha_metro_trem, ''), 'Linha de trem') AS name,
        'train'::text AS mode,
        ST_LineMerge(g.geometry) AS geom_4326
    FROM geosampa_trem_lines g
    CROSS JOIN bounds b
    WHERE g.geometry && b.env_4326
    UNION ALL
    SELECT
        md5(ST_AsEWKB(g.geometry)::text) AS id,
        COALESCE(NULLIF(g.ln_nome, ''), 'Linha de ônibus') AS name,
        'bus'::text AS mode,
        ST_LineMerge(g.geometry) AS geom_4326
    FROM geosampa_bus_lines g
    CROSS JOIN bounds b
    WHERE g.geometry && b.env_4326
), merged AS (
    SELECT id, name, mode, geom_4326
    FROM gtfs_lines, bounds
    WHERE geom_4326 IS NOT NULL AND ST_Intersects(geom_4326, env_4326)
    UNION ALL
    SELECT id, name, mode, geom_4326
    FROM corridor_lines, bounds
    WHERE geom_4326 IS NOT NULL AND ST_Intersects(geom_4326, env_4326)
    UNION ALL
    SELECT id, name, mode, geom_4326
    FROM geosampa_lines, bounds
    WHERE geom_4326 IS NOT NULL AND ST_Intersects(geom_4326, env_4326)
), mvtgeom AS (
    SELECT
        id,
        name,
        mode,
        ST_AsMVTGeom(
            ST_Transform(geom_4326, 3857),
            env_3857,
            4096,
            128,
            true
        ) AS geom
    FROM merged
    CROSS JOIN bounds
)
SELECT ST_AsMVT(mvtgeom, 'transport_lines', 4096, 'geom')
FROM mvtgeom
WHERE geom IS NOT NULL
"""


_TRANSPORT_STOPS_TILE_SQL = """
WITH bounds AS (
    SELECT
        ST_TileEnvelope(:z, :x, :y) AS env_3857,
        ST_Transform(ST_TileEnvelope(:z, :x, :y), 4326) AS env_4326
), stop_points AS (
    SELECT
        s.stop_id::text AS id,
        COALESCE(NULLIF(s.stop_name, ''), s.stop_id::text) AS name,
        'bus_stop'::text AS kind,
        s.location AS geom_4326
    FROM gtfs_stops s
    CROSS JOIN bounds b
    WHERE s.location && b.env_4326
    UNION ALL
    SELECT
        md5(ST_AsEWKB(g.geometry)::text) AS id,
        COALESCE(NULLIF(g.nm_estacao_metro_trem, ''), 'Estação de metrô') AS name,
        'metro_station'::text AS kind,
        ST_PointOnSurface(g.geometry) AS geom_4326
    FROM geosampa_metro_stations g
    CROSS JOIN bounds b
    WHERE g.geometry && b.env_4326
    UNION ALL
    SELECT
        md5(ST_AsEWKB(g.geometry)::text) AS id,
        COALESCE(NULLIF(g.nm_estacao_metro_trem, ''), 'Estação de trem') AS name,
        'train_station'::text AS kind,
        ST_PointOnSurface(g.geometry) AS geom_4326
    FROM geosampa_trem_stations g
    CROSS JOIN bounds b
    WHERE g.geometry && b.env_4326
    UNION ALL
    SELECT
        md5(ST_AsEWKB(g.geometry)::text) AS id,
        COALESCE(NULLIF(g.nm_ponto_onibus, ''), 'Ponto de ônibus') AS name,
        'bus_stop'::text AS kind,
        ST_PointOnSurface(g.geometry) AS geom_4326
    FROM geosampa_bus_stops g
    CROSS JOIN bounds b
    WHERE g.geometry && b.env_4326
    UNION ALL
    SELECT
        md5(ST_AsEWKB(g.geometry)::text) AS id,
        COALESCE(NULLIF(g.nm_terminal, ''), 'Terminal de ônibus') AS name,
        'bus_terminal'::text AS kind,
        ST_PointOnSurface(g.geometry) AS geom_4326
    FROM geosampa_bus_terminals g
    CROSS JOIN bounds b
    WHERE g.geometry && b.env_4326
), mvtgeom AS (
    SELECT
        id,
        name,
        kind,
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


_GREEN_TILE_SQL = """
WITH bounds AS (
    SELECT
        ST_TileEnvelope(:z, :x, :y) AS env_3857,
        ST_Transform(ST_TileEnvelope(:z, :x, :y), 4326) AS env_4326
), layer_rows AS (
    SELECT
        md5(ST_AsEWKB(g.geometry)::text) AS id,
        COALESCE(NULLIF(g.ves_categ, ''), NULLIF(g.ves_bairro, ''), 'Área verde') AS source_name,
        ST_AsMVTGeom(
            ST_Transform(ST_SimplifyPreserveTopology(g.geometry, 0.00005), 3857),
            env_3857,
            4096,
            256,
            true
        ) AS geom
    FROM geosampa_vegetacao_significativa g
    CROSS JOIN bounds
    WHERE g.geometry && env_4326
      AND ST_Intersects(g.geometry, env_4326)
)
SELECT ST_AsMVT(layer_rows, 'green_areas', 4096, 'geom')
FROM layer_rows
WHERE geom IS NOT NULL
"""


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


@router.get("/tiles/lines/{z}/{x}/{y}.pbf")
async def get_transport_lines_tile(
    z: int = Path(..., ge=0, le=22),
    x: int = Path(..., ge=0),
    y: int = Path(..., ge=0),
) -> Response:
    engine = get_engine()
    tile = await _query_vector_tile(engine, _TRANSPORT_LINES_TILE_SQL, {"z": z, "x": x, "y": y}, layer_name="transport_lines")
    return Response(content=tile, media_type=MVT_MEDIA_TYPE)


@router.get("/tiles/stops/{z}/{x}/{y}.pbf")
async def get_transport_stops_tile(
    z: int = Path(..., ge=0, le=22),
    x: int = Path(..., ge=0),
    y: int = Path(..., ge=0),
) -> Response:
    engine = get_engine()
    tile = await _query_vector_tile(engine, _TRANSPORT_STOPS_TILE_SQL, {"z": z, "x": x, "y": y}, layer_name="transport_stops")
    return Response(content=tile, media_type=MVT_MEDIA_TYPE)


@router.get("/tiles/environment/green/{z}/{x}/{y}.pbf")
async def get_green_areas_tile(
    z: int = Path(..., ge=0, le=22),
    x: int = Path(..., ge=0),
    y: int = Path(..., ge=0),
) -> Response:
    engine = get_engine()
    tile = await _query_vector_tile(engine, _GREEN_TILE_SQL, {"z": z, "x": x, "y": y}, layer_name="green_areas")
    return Response(content=tile, media_type=MVT_MEDIA_TYPE)


@router.get("/tiles/environment/flood/{z}/{x}/{y}.pbf")
async def get_flood_areas_tile(
    z: int = Path(..., ge=0, le=22),
    x: int = Path(..., ge=0),
    y: int = Path(..., ge=0),
) -> Response:
    engine = get_engine()
    tile = await _query_vector_tile(engine, _FLOOD_TILE_SQL, {"z": z, "x": x, "y": y}, layer_name="flood_areas")
    return Response(content=tile, media_type=MVT_MEDIA_TYPE)


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
        ), lines AS (
            SELECT
                gs.shape_id::text AS id,
                MIN(gr.route_long_name)::text AS name,
                CASE WHEN MIN(gr.route_type) = 2 THEN 'train' ELSE 'bus' END AS mode,
                ST_AsGeoJSON(ST_MakeLine(gs.location ORDER BY gs.shape_pt_sequence))::JSONB AS geometry
            FROM gtfs_shapes gs
            JOIN gtfs_trips gt ON gt.shape_id = gs.shape_id
            JOIN gtfs_routes gr ON gr.route_id = gt.route_id
            CROSS JOIN viewport v
            WHERE ST_Intersects(gs.location, v.env)
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
