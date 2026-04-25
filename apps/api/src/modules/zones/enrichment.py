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
    compute_poi_fingerprint,
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
    "gym": "fitness_center",
}
_POI_CACHE_TTL_SECONDS = 1800
_POI_FETCH_LIMIT = 30
_POI_REUSE_MIN_COVERAGE_RATIO = 0.98
_POI_REUSE_MAX_SOURCE_ZONES = 12

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

_JOURNEY_ZONE_POI_CONTEXT_SQL = _ZONE_POI_CONTEXT_SQL

_FILTER_ZONE_POI_POINTS_SQL = text(
    """
    WITH zone_geom AS (
        SELECT z.isochrone_geom
        FROM zones z
        WHERE z.id = :zone_id
    ),
    candidate_points AS (
        SELECT
            candidate.point AS point,
            candidate.ordinality AS ordinality,
            CAST(candidate.point ->> 'lon' AS DOUBLE PRECISION) AS lon,
            CAST(candidate.point ->> 'lat' AS DOUBLE PRECISION) AS lat
        FROM jsonb_array_elements(CAST(:poi_points AS JSONB)) WITH ORDINALITY AS candidate(point, ordinality)
    )
    SELECT candidate_points.point AS point
    FROM candidate_points
    JOIN zone_geom ON zone_geom.isochrone_geom IS NOT NULL
    WHERE ST_Covers(
        zone_geom.isochrone_geom,
        ST_SetSRID(
            ST_MakePoint(candidate_points.lon, candidate_points.lat),
            4326
        )
    )
    ORDER BY candidate_points.ordinality ASC
    """
)

_REUSABLE_ZONE_POI_SOURCES_SQL = text(
    """
    WITH current_zone AS (
        SELECT
            z.id,
            z.isochrone_geom,
            ST_Area(z.isochrone_geom::geography) AS target_area_m2
        FROM zones z
        WHERE z.id = :zone_id
    ),
    candidate_sources AS (
        SELECT
            source.id AS source_zone_id,
            source.fingerprint AS source_zone_fingerprint,
            source.isochrone_geom AS source_geom,
            ST_Area(source.isochrone_geom::geography) AS source_area_m2,
            ST_Covers(source.isochrone_geom, current_zone.isochrone_geom) AS source_covers_target,
            COALESCE(
                ST_Area(ST_Intersection(source.isochrone_geom, current_zone.isochrone_geom)::geography)
                / NULLIF(current_zone.target_area_m2, 0),
                0
            ) AS target_overlap_ratio,
            cache.scraped_at
        FROM current_zone
        JOIN journey_zones jz ON jz.journey_id = :journey_id
        JOIN zones source ON source.id = jz.zone_id
        JOIN zone_poi_caches cache
            ON cache.zone_fingerprint = source.fingerprint
           AND cache.config_hash = :config_hash
        WHERE source.id <> current_zone.id
          AND current_zone.isochrone_geom IS NOT NULL
          AND source.isochrone_geom IS NOT NULL
          AND cache.status = 'complete'
          AND (cache.expires_at IS NULL OR cache.expires_at > now())
          AND ST_Intersects(source.isochrone_geom, current_zone.isochrone_geom)
    ),
    candidate_coverage AS (
        SELECT COALESCE(
            ST_Area(
                ST_Intersection(
                    current_zone.isochrone_geom,
                    ST_UnaryUnion(ST_Collect(candidate_sources.source_geom))
                )::geography
            ) / NULLIF(current_zone.target_area_m2, 0),
            0
        ) AS coverage_ratio
        FROM current_zone
        JOIN candidate_sources ON TRUE
        GROUP BY current_zone.isochrone_geom, current_zone.target_area_m2
    )
    SELECT
        candidate_sources.source_zone_fingerprint,
        candidate_sources.source_covers_target,
        candidate_sources.target_overlap_ratio,
        COALESCE(candidate_coverage.coverage_ratio, 0) AS coverage_ratio
    FROM candidate_sources
    CROSS JOIN candidate_coverage
    ORDER BY candidate_sources.source_covers_target DESC,
             candidate_sources.target_overlap_ratio DESC,
             candidate_sources.source_area_m2 ASC,
             candidate_sources.scraped_at DESC NULLS LAST,
             candidate_sources.source_zone_id ASC
    LIMIT :max_sources
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
        "strategy": ISOCHRONE_PROXY_SEARCH_STRATEGY,
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


def _normalize_poi_points(raw_points: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_points, list):
        return []

    normalized: list[dict[str, Any]] = []
    for item in raw_points:
        if not isinstance(item, dict):
            continue
        lat = item.get("lat")
        lon = item.get("lon")
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            continue
        normalized.append(
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
    return normalized


def _count_poi_points_by_category(poi_points: list[dict[str, Any]]) -> dict[str, int]:
    counts = {category: 0 for category in _POI_CATEGORIES}
    for point in poi_points:
        category = point.get("category")
        if category in counts:
            counts[category] += 1
    return counts


def _merge_poi_points(*point_groups: Any) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen_fingerprints: set[str] = set()

    for point_group in point_groups:
        for point in _normalize_poi_points(point_group):
            fingerprint = compute_poi_fingerprint(
                name=point.get("name"),
                address=point.get("address"),
                category=point.get("category"),
                lat=point.get("lat"),
                lon=point.get("lon"),
            )
            if fingerprint in seen_fingerprints:
                continue
            seen_fingerprints.add(fingerprint)
            merged.append(point)

    return merged


async def _load_reusable_poi_source_points(
    zone_id: UUID,
    *,
    journey_id: UUID | None,
    config_hash: str,
) -> tuple[list[dict[str, Any]], float]:
    if journey_id is None:
        return [], 0.0

    engine = get_engine()
    async with engine.begin() as conn:
        result = await conn.execute(
            _REUSABLE_ZONE_POI_SOURCES_SQL,
            {
                "zone_id": zone_id,
                "journey_id": journey_id,
                "config_hash": config_hash,
                "max_sources": _POI_REUSE_MAX_SOURCE_ZONES,
            },
        )
        rows = result.mappings().all()

    if not rows:
        return [], 0.0

    coverage_ratio = float(rows[0].get("coverage_ratio") or 0.0)
    merged_points: list[dict[str, Any]] = []
    missing_payload = False
    for row in rows:
        source_zone_fingerprint = row.get("source_zone_fingerprint")
        if not source_zone_fingerprint:
            continue
        payload = await get_persisted_poi_cache_payload(str(source_zone_fingerprint), config_hash)
        if payload is None:
            missing_payload = True
            continue
        merged_points = _merge_poi_points(merged_points, payload.get("poi_points") or [])

    if missing_payload:
        coverage_ratio = 0.0

    return merged_points, coverage_ratio


async def _filter_poi_points_to_zone(
    zone_id: UUID,
    poi_points: Any,
) -> list[dict[str, Any]]:
    normalized_points = _normalize_poi_points(poi_points)
    if not normalized_points:
        return []

    engine = get_engine()
    async with engine.begin() as conn:
        result = await conn.execute(
            _FILTER_ZONE_POI_POINTS_SQL,
            {
                "zone_id": zone_id,
                "poi_points": json.dumps(normalized_points, ensure_ascii=True),
            },
        )
        rows = result.mappings().all()

    filtered_points: list[dict[str, Any]] = []
    for row in rows:
        point = row.get("point")
        if isinstance(point, str):
            try:
                point = json.loads(point)
            except json.JSONDecodeError:
                continue
        if isinstance(point, dict):
            filtered_points.append(point)

    return _normalize_poi_points(filtered_points)


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
                    ST_Area(
                        (
                            ST_UnaryUnion(
                                ST_Collect(
                                    ST_Intersection(z.isochrone_geom, gv.geometry)
                                )
                            )
                        )::geography
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
                    ST_Area(
                        (
                            ST_UnaryUnion(
                                ST_Collect(
                                    ST_Intersection(z.isochrone_geom, gf.geometry)
                                )
                            )
                        )::geography
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
    zone_fingerprint = str(zone["zone_fingerprint"])
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
        poi_points = await _filter_poi_points_to_zone(zone_id, persisted_payload.get("poi_points") or [])
        poi_counts = _count_poi_points_by_category(poi_points)
        await redis.set(
            cache_key,
            json.dumps({"poi_counts": poi_counts, "poi_points": poi_points}, ensure_ascii=True),
            ex=_POI_CACHE_TTL_SECONDS,
        )
    else:
        cached = await redis.get(cache_key)
        if cached:
            cached_payload = json.loads(cached)
            poi_points = await _filter_poi_points_to_zone(zone_id, cached_payload.get("poi_points") or [])
            poi_counts = _count_poi_points_by_category(poi_points)
        else:
            reusable_proxy_points, reusable_coverage_ratio = await _load_reusable_poi_source_points(
                zone_id,
                journey_id=journey_id,
                config_hash=config_hash,
            )
            legacy_payload = _legacy_zone_payload_from_context(zone)
            if reusable_proxy_points and reusable_coverage_ratio >= _POI_REUSE_MIN_COVERAGE_RATIO:
                poi_points = await _filter_poi_points_to_zone(zone_id, reusable_proxy_points)
                poi_counts = _count_poi_points_by_category(poi_points)
                await redis.set(
                    cache_key,
                    json.dumps({"poi_counts": poi_counts, "poi_points": poi_points}, ensure_ascii=True),
                    ex=_POI_CACHE_TTL_SECONDS,
                )
            elif legacy_payload is not None and not reusable_proxy_points:
                poi_points = await _filter_poi_points_to_zone(zone_id, legacy_payload["poi_points"])
                poi_counts = _count_poi_points_by_category(poi_points)
                await redis.set(
                    cache_key,
                    json.dumps({"poi_counts": poi_counts, "poi_points": poi_points}, ensure_ascii=True),
                    ex=_POI_CACHE_TTL_SECONDS,
                )
            else:
                settings = get_settings()
                fetched_proxy_points: list[dict[str, Any]] = []
                fetched_proxy_entries: list[dict[str, Any]] = []
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
                            for feature in features:
                                point = _extract_poi_point(feature, category=category)
                                if point is not None:
                                    fetched_proxy_points.append(point)
                                    fetched_proxy_entries.append({"point": point, "raw_payload": feature})
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

                proxy_points_for_zone = _merge_poi_points(reusable_proxy_points, fetched_proxy_points)
                poi_points = await _filter_poi_points_to_zone(zone_id, proxy_points_for_zone)
                poi_counts = _count_poi_points_by_category(poi_points)

                await persist_poi_cache_payload(
                    zone_fingerprint=zone_fingerprint,
                    config_hash=config_hash,
                    poi_counts=_count_poi_points_by_category(fetched_proxy_points),
                    poi_points=fetched_proxy_points,
                    poi_entries=fetched_proxy_entries,
                )
                await redis.set(
                    cache_key,
                    json.dumps({"poi_counts": poi_counts, "poi_points": poi_points}, ensure_ascii=True),
                    ex=_POI_CACHE_TTL_SECONDS,
                )

    await project_poi_payload_to_zone(zone_id, poi_counts=poi_counts, poi_points=poi_points)

    return {"zone_id": str(zone_id), "poi_counts": poi_counts, "poi_points": poi_points}

