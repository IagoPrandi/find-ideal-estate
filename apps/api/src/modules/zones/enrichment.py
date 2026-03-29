"""Zone enrichment service for green, flood, safety and POI metrics."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

import httpx
from core.config import get_settings
from core.db import get_engine
from core.redis import get_redis
from sqlalchemy import text

_POI_CATEGORIES = ("school", "supermarket", "pharmacy", "park", "restaurant", "gym")
_POI_CACHE_TTL_SECONDS = 1800

_ZONE_POI_CONTEXT_SQL = text(
    """
    SELECT
        z.fingerprint AS zone_fingerprint,
        z.fingerprint AS poi_source_fingerprint,
        ST_X(ST_Centroid(z.isochrone_geom)) AS lon,
        ST_Y(ST_Centroid(z.isochrone_geom)) AS lat,
        ST_XMin(z.isochrone_geom)::DOUBLE PRECISION AS xmin,
        ST_YMin(z.isochrone_geom)::DOUBLE PRECISION AS ymin,
        ST_XMax(z.isochrone_geom)::DOUBLE PRECISION AS xmax,
        ST_YMax(z.isochrone_geom)::DOUBLE PRECISION AS ymax
    FROM zones z
    WHERE z.id = :zone_id
    """
)

_JOURNEY_ZONE_POI_CONTEXT_SQL = text(
    """
    WITH RECURSIVE current_zone AS (
        SELECT
            z.id,
            z.fingerprint,
            z.isochrone_geom,
            z.created_at,
            ST_Centroid(z.isochrone_geom) AS center_geom,
            ST_Area(z.isochrone_geom::geography) AS area_m2
        FROM zones z
        WHERE z.id = :zone_id
    ),
    journey_zone_scope AS (
        SELECT
            z.id,
            z.fingerprint,
            z.isochrone_geom,
            z.created_at,
            ST_Centroid(z.isochrone_geom) AS center_geom,
            ST_Area(z.isochrone_geom::geography) AS area_m2
        FROM journey_zones jz
        JOIN zones z ON z.id = jz.zone_id
        WHERE jz.journey_id = :journey_id
    ),
    parent_chain AS (
        SELECT
            cz.id,
            cz.fingerprint,
            cz.isochrone_geom,
            cz.center_geom,
            cz.created_at,
            cz.area_m2,
            0 AS depth,
            ARRAY[cz.id]::uuid[] AS path
        FROM current_zone cz

        UNION ALL

        SELECT
            parent.id,
            parent.fingerprint,
            parent.isochrone_geom,
            parent.center_geom,
            parent.created_at,
            parent.area_m2,
            chain.depth + 1 AS depth,
            chain.path || parent.id
        FROM parent_chain chain
        JOIN LATERAL (
            SELECT
                scope.id,
                scope.fingerprint,
                scope.isochrone_geom,
                scope.center_geom,
                scope.created_at,
                scope.area_m2
            FROM journey_zone_scope scope
            WHERE scope.id <> ALL(chain.path)
              AND chain.center_geom IS NOT NULL
              AND scope.center_geom IS NOT NULL
              AND ST_Within(chain.center_geom, scope.isochrone_geom)
            ORDER BY scope.area_m2 ASC, scope.created_at ASC, scope.id ASC
            LIMIT 1
        ) parent ON TRUE
        WHERE chain.depth < 32
    ),
    poi_source AS (
        SELECT *
        FROM parent_chain
        ORDER BY depth DESC
        LIMIT 1
    )
    SELECT
        current_zone.fingerprint AS zone_fingerprint,
        poi_source.fingerprint AS poi_source_fingerprint,
        ST_X(poi_source.center_geom) AS lon,
        ST_Y(poi_source.center_geom) AS lat,
        ST_XMin(poi_source.isochrone_geom)::DOUBLE PRECISION AS xmin,
        ST_YMin(poi_source.isochrone_geom)::DOUBLE PRECISION AS ymin,
        ST_XMax(poi_source.isochrone_geom)::DOUBLE PRECISION AS xmax,
        ST_YMax(poi_source.isochrone_geom)::DOUBLE PRECISION AS ymax
    FROM current_zone
    JOIN poi_source ON TRUE
    """
)


def _format_mapbox_float(value: float) -> str:
    return f"{float(value):.6f}"


def _format_bbox(bbox: tuple[float, float, float, float]) -> str:
    return ",".join(_format_mapbox_float(part) for part in bbox)


def _format_proximity(lon: float, lat: float) -> str:
    return f"{_format_mapbox_float(lon)},{_format_mapbox_float(lat)}"


def _mapbox_poi_params(
    *,
    category: str,
    access_token: str,
    bbox: tuple[float, float, float, float],
    lon: float,
    lat: float,
) -> dict[str, str | int]:
    return {
        "q": str(category).strip(),
        "access_token": access_token,
        "language": "pt",
        "country": "BR",
        "limit": 10,
        "types": "poi",
        "bbox": _format_bbox(bbox),
        "proximity": _format_proximity(lon, lat),
    }


def _extract_poi_point(feature: dict[str, Any], *, category: str) -> dict[str, Any] | None:
    geometry = feature.get("geometry") or {}
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        return None

    lon = coordinates[0]
    lat = coordinates[1]
    if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
        return None

    properties = feature.get("properties") or {}
    feature_name = properties.get("name")
    if not isinstance(feature_name, str) or not feature_name.strip():
        feature_name = feature.get("name")

    feature_id = feature.get("id")
    if not isinstance(feature_id, str) or not feature_id.strip():
        feature_id = properties.get("mapbox_id")

    address = properties.get("full_address")
    if not isinstance(address, str) or not address.strip():
        address = properties.get("place_formatted")

    return {
        "kind": "poi",
        "id": feature_id.strip() if isinstance(feature_id, str) and feature_id.strip() else None,
        "name": feature_name.strip() if isinstance(feature_name, str) and feature_name.strip() else None,
        "category": category,
        "address": address.strip() if isinstance(address, str) and address.strip() else None,
        "lat": float(lat),
        "lon": float(lon),
    }


def _poi_cache_key(
    *,
    zone_fingerprint: str,
    categories: tuple[str, ...],
    bbox: tuple[float, float, float, float],
) -> str:
    payload = {
        "f": zone_fingerprint,
        "cats": list(categories),
        "bbox": [round(v, 6) for v in bbox],
    }
    digest = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:20]
    return f"zone_pois:v3:{digest}"


async def enrich_zone_green(zone_id: UUID) -> dict[str, Any]:
    engine = get_engine()
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                SELECT COALESCE(
                    SUM(
                        ST_Area(
                            ST_Intersection(z.isochrone_geom, gv.geometry)::geography
                        )
                    ),
                    0
                ) AS green_area_m2
                FROM zones z
                LEFT JOIN geosampa_vegetacao_significativa gv
                    ON z.isochrone_geom IS NOT NULL
                    AND ST_Intersects(z.isochrone_geom, gv.geometry)
                WHERE z.id = :zone_id
                GROUP BY z.id
                """
            ),
            {"zone_id": zone_id},
        )
        row = result.mappings().first()
        green_area = float(row["green_area_m2"]) if row else 0.0

        await conn.execute(
            text(
                """
                UPDATE zones
                SET green_area_m2 = :green_area_m2, updated_at = now()
                WHERE id = :zone_id
                """
            ),
            {"zone_id": zone_id, "green_area_m2": green_area},
        )

    return {"zone_id": str(zone_id), "green_area_m2": green_area}


async def enrich_zone_flood(zone_id: UUID) -> dict[str, Any]:
    engine = get_engine()
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                SELECT COALESCE(
                    SUM(
                        ST_Area(
                            ST_Intersection(z.isochrone_geom, gf.geometry)::geography
                        )
                    ),
                    0
                ) AS flood_area_m2
                FROM zones z
                LEFT JOIN geosampa_mancha_inundacao gf
                    ON z.isochrone_geom IS NOT NULL
                    AND ST_Intersects(z.isochrone_geom, gf.geometry)
                WHERE z.id = :zone_id
                GROUP BY z.id
                """
            ),
            {"zone_id": zone_id},
        )
        row = result.mappings().first()
        flood_area = float(row["flood_area_m2"]) if row else 0.0

        await conn.execute(
            text(
                """
                UPDATE zones
                SET flood_area_m2 = :flood_area_m2, updated_at = now()
                WHERE id = :zone_id
                """
            ),
            {"zone_id": zone_id, "flood_area_m2": flood_area},
        )

    return {"zone_id": str(zone_id), "flood_area_m2": flood_area}


async def enrich_zone_safety(zone_id: UUID) -> dict[str, Any]:
    engine = get_engine()
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                SELECT COALESCE(COUNT(psi.id)::INT, 0) AS safety_incidents_count
                FROM zones z
                LEFT JOIN public_safety_incidents psi
                    ON z.isochrone_geom IS NOT NULL
                    AND ST_Within(psi.location, z.isochrone_geom)
                WHERE z.id = :zone_id
                GROUP BY z.id
                """
            ),
            {"zone_id": zone_id},
        )
        row = result.mappings().first()
        count = int(row["safety_incidents_count"]) if row else 0

        await conn.execute(
            text(
                """
                UPDATE zones
                SET safety_incidents_count = :count, updated_at = now()
                WHERE id = :zone_id
                """
            ),
            {"zone_id": zone_id, "count": count},
        )

    return {"zone_id": str(zone_id), "safety_incidents_count": count}


async def _load_zone_poi_context(
    zone_id: UUID,
    *,
    journey_id: UUID | None,
) -> dict[str, Any] | None:
    engine = get_engine()
    async with engine.begin() as conn:
        zone_result = await conn.execute(
            _JOURNEY_ZONE_POI_CONTEXT_SQL if journey_id is not None else _ZONE_POI_CONTEXT_SQL,
            {"zone_id": zone_id, "journey_id": journey_id},
        )
        return zone_result.mappings().first()


async def enrich_zone_pois(
    zone_id: UUID,
    *,
    journey_id: UUID | None = None,
) -> dict[str, Any]:
    zone = await _load_zone_poi_context(zone_id, journey_id=journey_id)

    if zone is None or zone["lon"] is None or zone["lat"] is None:
        return {"zone_id": str(zone_id), "poi_counts": {}}

    bbox = (float(zone["xmin"]), float(zone["ymin"]), float(zone["xmax"]), float(zone["ymax"]))
    zone_fingerprint = str(zone["poi_source_fingerprint"] or zone["zone_fingerprint"])
    cache_key = _poi_cache_key(
        zone_fingerprint=zone_fingerprint,
        categories=_POI_CATEGORIES,
        bbox=bbox,
    )

    redis = get_redis()
    cached = await redis.get(cache_key)
    if cached:
        cached_payload = json.loads(cached)
        poi_counts = cached_payload.get("poi_counts") or {}
        poi_points = cached_payload.get("poi_points") or []
    else:
        settings = get_settings()
        poi_counts: dict[str, int] = {k: 0 for k in _POI_CATEGORIES}
        poi_points: list[dict[str, Any]] = []
        zone_lon = float(zone["lon"])
        zone_lat = float(zone["lat"])
        async with httpx.AsyncClient(timeout=8.0) as client:
            for category in _POI_CATEGORIES:
                try:
                    response = await client.get(
                        "https://api.mapbox.com/search/searchbox/v1/forward",
                        params=_mapbox_poi_params(
                            category=category,
                            access_token=settings.mapbox_access_token,
                            bbox=bbox,
                            lon=zone_lon,
                            lat=zone_lat,
                        ),
                    )
                    response.raise_for_status()
                    payload = response.json()
                    features = payload.get("features", [])
                    poi_counts[category] = len(features)
                    for feature in features:
                        point = _extract_poi_point(feature, category=category)
                        if point is not None:
                            poi_points.append(point)
                except Exception:
                    poi_counts[category] = 0

            await redis.set(
                cache_key,
                json.dumps({"poi_counts": poi_counts, "poi_points": poi_points}, ensure_ascii=True),
                ex=_POI_CACHE_TTL_SECONDS,
            )

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                UPDATE zones
                SET poi_counts = CAST(:poi_counts AS JSONB),
                    poi_points = CAST(:poi_points AS JSONB),
                    updated_at = now()
                WHERE id = :zone_id
                """
            ),
            {
                "zone_id": zone_id,
                "poi_counts": json.dumps(poi_counts, ensure_ascii=True),
                "poi_points": json.dumps(poi_points, ensure_ascii=True),
            },
        )

    return {"zone_id": str(zone_id), "poi_counts": poi_counts, "poi_points": poi_points}

