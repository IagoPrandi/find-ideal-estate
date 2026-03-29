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
from modules.pois.storage import (
    compute_poi_cache_config_hash,
    get_persisted_poi_cache_payload,
    mark_poi_cache_failed,
    persist_poi_cache_payload,
    project_poi_payload_to_zone,
)
from modules.zones.isochrone_proxy import (
    ISOCHRONE_PROXY_SEARCH_STRATEGY,
    build_isochrone_proxy_circle,
)
from sqlalchemy import text

_POI_CATEGORIES = ("school", "supermarket", "pharmacy", "park", "restaurant", "gym")
_POI_CATEGORY_CANONICAL_IDS = {
    "school": "education",
    "supermarket": "supermarket",
    "pharmacy": "pharmacy",
    "park": "park",
    "restaurant": "restaurant",
    "gym": "fitness_centre",
}
_POI_CACHE_TTL_SECONDS = 1800
_POI_FETCH_LIMIT = 15

_ZONE_POI_CONTEXT_SQL = text(
    """
    SELECT
        z.fingerprint AS zone_fingerprint,
        z.fingerprint AS poi_source_fingerprint,
        ST_X(ST_Centroid(z.isochrone_geom)) AS lon,
        ST_Y(ST_Centroid(z.isochrone_geom)) AS lat,
        ST_Area(z.isochrone_geom::geography) AS area_m2,
        ST_XMin(z.isochrone_geom)::DOUBLE PRECISION AS xmin,
        ST_YMin(z.isochrone_geom)::DOUBLE PRECISION AS ymin,
        ST_XMax(z.isochrone_geom)::DOUBLE PRECISION AS xmax,
        ST_YMax(z.isochrone_geom)::DOUBLE PRECISION AS ymax,
        z.poi_counts AS existing_poi_counts,
        z.poi_points AS existing_poi_points
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
            ST_Area(z.isochrone_geom::geography) AS area_m2,
            z.poi_counts,
            z.poi_points
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
            ST_Area(z.isochrone_geom::geography) AS area_m2,
            z.poi_counts,
            z.poi_points
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
            cz.poi_counts,
            cz.poi_points,
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
            parent.poi_counts,
            parent.poi_points,
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
                scope.area_m2,
                scope.poi_counts,
                scope.poi_points
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
        poi_source.area_m2 AS area_m2,
        ST_XMin(poi_source.isochrone_geom)::DOUBLE PRECISION AS xmin,
        ST_YMin(poi_source.isochrone_geom)::DOUBLE PRECISION AS ymin,
        ST_XMax(poi_source.isochrone_geom)::DOUBLE PRECISION AS xmax,
        ST_YMax(poi_source.isochrone_geom)::DOUBLE PRECISION AS ymax,
        poi_source.poi_counts AS existing_poi_counts,
        poi_source.poi_points AS existing_poi_points
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
    canonical_category_id = _POI_CATEGORY_CANONICAL_IDS[category]
    return {
        "access_token": access_token,
        "language": "pt",
        "country": "BR",
        "limit": min(25, _POI_FETCH_LIMIT),
        "bbox": _format_bbox(bbox),
        "proximity": _format_proximity(lon, lat),
        "canonical_category_id": canonical_category_id,
    }


def _mapbox_poi_url(*, category: str) -> str:
    canonical_category_id = _POI_CATEGORY_CANONICAL_IDS[category]
    return f"https://api.mapbox.com/search/searchbox/v1/category/{canonical_category_id}"


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
    return f"zone_pois:v5:{digest}"


def _legacy_zone_payload_from_context(zone: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(zone, dict):
        return None

    raw_counts = zone.get("existing_poi_counts")
    raw_points = zone.get("existing_poi_points")
    if not isinstance(raw_counts, dict) or not isinstance(raw_points, list):
        return None
    if any(category not in raw_counts for category in _POI_CATEGORIES):
        return None

    normalized_counts: dict[str, int] = {}
    for category in _POI_CATEGORIES:
        try:
            normalized_counts[category] = int(raw_counts.get(category) or 0)
        except (TypeError, ValueError):
            return None

    normalized_points: list[dict[str, Any]] = []
    for item in raw_points:
        if not isinstance(item, dict):
            continue
        lat = item.get("lat")
        lon = item.get("lon")
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            continue
        normalized_points.append(
            {
                "kind": "poi",
                "id": str(item.get("id")).strip() if item.get("id") else None,
                "name": str(item.get("name")).strip() if item.get("name") else None,
                "category": str(item.get("category")).strip() if item.get("category") else None,
                "address": str(item.get("address")).strip() if item.get("address") else None,
                "lat": float(lat),
                "lon": float(lon),
            }
        )

    return {"poi_counts": normalized_counts, "poi_points": normalized_points}


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

    try:
        proxy_circle = build_isochrone_proxy_circle(
            lon=float(zone["lon"]),
            lat=float(zone["lat"]),
            area_m2=float(zone["area_m2"]),
        )
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Zone {zone_id} has invalid isochrone area for POI search proxy") from exc

    proxy_bbox = proxy_circle["bbox"]
    bbox = (
        float(proxy_bbox[0]),
        float(proxy_bbox[1]),
        float(proxy_bbox[2]),
        float(proxy_bbox[3]),
    )
    zone_fingerprint = str(zone["poi_source_fingerprint"] or zone["zone_fingerprint"])
    config_hash = compute_poi_cache_config_hash(
        categories=_POI_CATEGORIES,
        limit_per_category=_POI_FETCH_LIMIT,
        search_geometry_strategy=ISOCHRONE_PROXY_SEARCH_STRATEGY,
    )
    cache_key = _poi_cache_key(
        zone_fingerprint=zone_fingerprint,
        categories=_POI_CATEGORIES,
        bbox=bbox,
    )

    redis = get_redis()
    persisted_payload = await get_persisted_poi_cache_payload(zone_fingerprint, config_hash)
    if persisted_payload is not None:
        poi_counts = persisted_payload.get("poi_counts") or {}
        poi_points = persisted_payload.get("poi_points") or []
        await redis.set(
            cache_key,
            json.dumps({"poi_counts": poi_counts, "poi_points": poi_points}, ensure_ascii=True),
            ex=_POI_CACHE_TTL_SECONDS,
        )
    else:
        cached = await redis.get(cache_key)
        if cached:
            cached_payload = json.loads(cached)
            poi_counts = cached_payload.get("poi_counts") or {}
            poi_points = cached_payload.get("poi_points") or []
            await persist_poi_cache_payload(
                zone_fingerprint=zone_fingerprint,
                config_hash=config_hash,
                poi_counts=poi_counts,
                poi_points=poi_points,
            )
        else:
            legacy_payload = _legacy_zone_payload_from_context(zone)
            if legacy_payload is not None:
                poi_counts = legacy_payload["poi_counts"]
                poi_points = legacy_payload["poi_points"]
                await persist_poi_cache_payload(
                    zone_fingerprint=zone_fingerprint,
                    config_hash=config_hash,
                    poi_counts=poi_counts,
                    poi_points=poi_points,
                )
                await redis.set(
                    cache_key,
                    json.dumps({"poi_counts": poi_counts, "poi_points": poi_points}, ensure_ascii=True),
                    ex=_POI_CACHE_TTL_SECONDS,
                )
            else:
                settings = get_settings()
                poi_counts = {k: 0 for k in _POI_CATEGORIES}
                poi_points: list[dict[str, Any]] = []
                poi_entries: list[dict[str, Any]] = []
                zone_lon = float(zone["lon"])
                zone_lat = float(zone["lat"])
                current_category = None
                try:
                    async with httpx.AsyncClient(timeout=8.0) as client:
                        for category in _POI_CATEGORIES:
                            current_category = category
                            request_params = _mapbox_poi_params(
                                category=category,
                                access_token=settings.mapbox_access_token,
                                bbox=bbox,
                                lon=zone_lon,
                                lat=zone_lat,
                            )
                            canonical_category_id = str(request_params.pop("canonical_category_id"))
                            response = await client.get(
                                _mapbox_poi_url(category=category),
                                params=request_params,
                            )
                            response.raise_for_status()
                            payload = response.json()
                            features = payload.get("features", [])
                            poi_counts[category] = len(features)
                            for feature in features:
                                point = _extract_poi_point(feature, category=category)
                                if point is not None:
                                    poi_points.append(point)
                                    poi_entries.append({"point": point, "raw_payload": feature})
                except Exception as exc:
                    await mark_poi_cache_failed(zone_fingerprint, config_hash)
                    details = ""
                    if isinstance(exc, httpx.HTTPStatusError):
                        body = exc.response.text[:500].replace("\n", " ").strip()
                        details = (
                            f" [mapbox_status={exc.response.status_code} canonical_category="
                            f"{_POI_CATEGORY_CANONICAL_IDS.get(current_category or '', current_category or '')}"
                            f" body={body}]"
                        )
                    raise RuntimeError(
                        f"POI fetch failed for zone {zone_id} while loading category {current_category}{details}"
                    ) from exc

                await persist_poi_cache_payload(
                    zone_fingerprint=zone_fingerprint,
                    config_hash=config_hash,
                    poi_counts=poi_counts,
                    poi_points=poi_points,
                    poi_entries=poi_entries,
                )
                await redis.set(
                    cache_key,
                    json.dumps({"poi_counts": poi_counts, "poi_points": poi_points}, ensure_ascii=True),
                    ex=_POI_CACHE_TTL_SECONDS,
                )

    await project_poi_payload_to_zone(zone_id, poi_counts=poi_counts, poi_points=poi_points)

    return {"zone_id": str(zone_id), "poi_counts": poi_counts, "poi_points": poi_points}

