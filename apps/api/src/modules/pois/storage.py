"""Persistent POI storage and cache helpers."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence
from uuid import UUID

from core.db import get_engine
from sqlalchemy import text

POI_PROVIDER_MAPBOX_SEARCHBOX = "mapbox_searchbox"
POI_CACHE_STATUS_PENDING = "pending"
POI_CACHE_STATUS_COMPLETE = "complete"
POI_CACHE_STATUS_FAILED = "failed"
POI_CACHE_TTL_HOURS = 24


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    nfkd = unicodedata.normalize("NFKD", value)
    ascii_only = nfkd.encode("ascii", "ignore").decode("ascii")
    lower = ascii_only.lower()
    return re.sub(r"\s+", " ", lower).strip()


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def compute_poi_fingerprint(
    *,
    name: str | None,
    address: str | None,
    category: str | None,
    lat: float | None,
    lon: float | None,
) -> str:
    canonical = {
        "address": _normalize_text(address),
        "category": _normalize_text(category),
        "lat": round(float(lat), 5) if lat is not None else None,
        "lon": round(float(lon), 5) if lon is not None else None,
        "name": _normalize_text(name),
    }
    payload = json.dumps(canonical, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_poi_cache_config_hash(
    *,
    categories: Sequence[str],
    provider: str = POI_PROVIDER_MAPBOX_SEARCHBOX,
    limit_per_category: int = 10,
    search_geometry_strategy: str = "zone_bbox",
) -> str:
    canonical = {
        "categories": sorted(str(category).strip() for category in categories if str(category).strip()),
        "limit_per_category": int(limit_per_category),
        "provider": provider,
        "search_geometry_strategy": str(search_geometry_strategy).strip() or "zone_bbox",
        "version": 2,
    }
    payload = json.dumps(canonical, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def poi_cache_is_usable(record: dict[str, Any] | None) -> bool:
    if record is None:
        return False
    if record.get("status") != POI_CACHE_STATUS_COMPLETE:
        return False
    expires_at = record.get("expires_at")
    if expires_at is None:
        return True
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at > _utcnow()


def _normalize_poi_counts(raw_counts: dict[str, Any] | None) -> dict[str, int]:
    if not isinstance(raw_counts, dict):
        return {}
    normalized: dict[str, int] = {}
    for key, value in raw_counts.items():
        if key is None:
            continue
        try:
            normalized[str(key)] = int(value)
        except (TypeError, ValueError):
            normalized[str(key)] = 0
    return normalized


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


async def get_persisted_poi_cache_payload(
    zone_fingerprint: str,
    config_hash: str,
) -> dict[str, Any] | None:
    engine = get_engine()
    async with engine.connect() as conn:
        cache_row = await conn.execute(
            text(
                """
                SELECT id, zone_fingerprint, config_hash, status, poi_counts,
                       point_count, scraped_at, expires_at, created_at, updated_at
                FROM zone_poi_caches
                WHERE zone_fingerprint = :zone_fingerprint
                  AND config_hash = :config_hash
                """
            ),
            {"zone_fingerprint": zone_fingerprint, "config_hash": config_hash},
        )
        record = cache_row.mappings().first()
        if record is None:
            return None

        cache = dict(record)
        if not poi_cache_is_usable(cache):
            return None

        items_row = await conn.execute(
            text(
                """
                SELECT
                    p.provider_poi_id,
                    p.name,
                    p.category,
                    p.address,
                    ST_Y(p.location) AS lat,
                    ST_X(p.location) AS lon,
                    ci.position
                FROM zone_poi_cache_items ci
                JOIN poi_places p ON p.id = ci.poi_place_id
                WHERE ci.zone_poi_cache_id = :cache_id
                ORDER BY ci.position ASC
                """
            ),
            {"cache_id": cache["id"]},
        )
        points = [
            {
                "kind": "poi",
                "id": row["provider_poi_id"] if row["provider_poi_id"] else None,
                "name": row["name"],
                "category": row["category"],
                "address": row["address"],
                "lat": float(row["lat"]),
                "lon": float(row["lon"]),
            }
            for row in items_row.mappings().all()
            if row["lat"] is not None and row["lon"] is not None
        ]

    return {
        "zone_fingerprint": cache["zone_fingerprint"],
        "config_hash": cache["config_hash"],
        "poi_counts": _normalize_poi_counts(cache.get("poi_counts")),
        "poi_points": points,
    }


async def mark_poi_cache_failed(
    zone_fingerprint: str,
    config_hash: str,
) -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO zone_poi_caches (
                    zone_fingerprint,
                    config_hash,
                    status,
                    point_count,
                    updated_at
                ) VALUES (
                    :zone_fingerprint,
                    :config_hash,
                    :status,
                    0,
                    now()
                )
                ON CONFLICT (zone_fingerprint, config_hash) DO UPDATE
                SET status = EXCLUDED.status,
                    updated_at = now()
                """
            ),
            {
                "zone_fingerprint": zone_fingerprint,
                "config_hash": config_hash,
                "status": POI_CACHE_STATUS_FAILED,
            },
        )


async def persist_poi_cache_payload(
    *,
    zone_fingerprint: str,
    config_hash: str,
    poi_counts: dict[str, Any],
    poi_points: Sequence[dict[str, Any]],
    poi_entries: Sequence[dict[str, Any]] | None = None,
    provider: str = POI_PROVIDER_MAPBOX_SEARCHBOX,
) -> None:
    engine = get_engine()
    normalized_counts = _normalize_poi_counts(poi_counts)
    normalized_points = _normalize_poi_points(list(poi_points))
    entries = list(poi_entries) if poi_entries is not None else []
    if not entries:
        entries = [{"point": point, "raw_payload": None} for point in normalized_points]

    expires_at = _utcnow() + timedelta(hours=POI_CACHE_TTL_HOURS)

    async with engine.begin() as conn:
        cache_row = await conn.execute(
            text(
                """
                INSERT INTO zone_poi_caches (
                    zone_fingerprint,
                    config_hash,
                    status,
                    poi_counts,
                    point_count,
                    scraped_at,
                    expires_at,
                    updated_at
                ) VALUES (
                    :zone_fingerprint,
                    :config_hash,
                    :status,
                    CAST(:poi_counts AS JSONB),
                    :point_count,
                    now(),
                    :expires_at,
                    now()
                )
                ON CONFLICT (zone_fingerprint, config_hash) DO UPDATE
                SET status = EXCLUDED.status,
                    poi_counts = EXCLUDED.poi_counts,
                    point_count = EXCLUDED.point_count,
                    scraped_at = now(),
                    expires_at = EXCLUDED.expires_at,
                    updated_at = now()
                RETURNING id
                """
            ),
            {
                "zone_fingerprint": zone_fingerprint,
                "config_hash": config_hash,
                "status": POI_CACHE_STATUS_COMPLETE,
                "poi_counts": json.dumps(normalized_counts, ensure_ascii=True),
                "point_count": len(normalized_points),
                "expires_at": expires_at,
            },
        )
        cache_id: UUID = cache_row.scalar_one()

        await conn.execute(
            text("DELETE FROM zone_poi_cache_items WHERE zone_poi_cache_id = :cache_id"),
            {"cache_id": cache_id},
        )

        for position, entry in enumerate(entries, start=1):
            point = entry.get("point") if isinstance(entry, dict) else None
            if not isinstance(point, dict):
                continue

            category = point.get("category")
            lat = point.get("lat")
            lon = point.get("lon")
            if not isinstance(category, str) or not category.strip():
                continue
            if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
                continue

            fingerprint = compute_poi_fingerprint(
                name=point.get("name"),
                address=point.get("address"),
                category=category,
                lat=float(lat),
                lon=float(lon),
            )

            place_result = await conn.execute(
                text(
                    """
                    INSERT INTO poi_places (
                        provider,
                        provider_poi_id,
                        name,
                        address,
                        location,
                        category,
                        fingerprint
                    ) VALUES (
                        :provider,
                        :provider_poi_id,
                        :name,
                        :address,
                        ST_SetSRID(
                            ST_MakePoint(
                                CAST(:lon AS DOUBLE PRECISION),
                                CAST(:lat AS DOUBLE PRECISION)
                            ),
                            4326
                        ),
                        :category,
                        :fingerprint
                    )
                    ON CONFLICT (fingerprint) DO UPDATE
                    SET provider_poi_id = COALESCE(EXCLUDED.provider_poi_id, poi_places.provider_poi_id),
                        name = COALESCE(EXCLUDED.name, poi_places.name),
                        address = COALESCE(EXCLUDED.address, poi_places.address),
                        location = COALESCE(EXCLUDED.location, poi_places.location),
                        category = EXCLUDED.category,
                        last_seen_at = now(),
                        is_active = true
                    RETURNING id
                    """
                ),
                {
                    "provider": provider,
                    "provider_poi_id": point.get("id"),
                    "name": point.get("name"),
                    "address": point.get("address"),
                    "lat": float(lat),
                    "lon": float(lon),
                    "category": category,
                    "fingerprint": fingerprint,
                },
            )
            poi_place_id: UUID = place_result.scalar_one()

            raw_payload = entry.get("raw_payload") if isinstance(entry, dict) else None
            if raw_payload is not None:
                await conn.execute(
                    text(
                        """
                        INSERT INTO poi_snapshots (
                            poi_place_id,
                            raw_payload
                        ) VALUES (
                            :poi_place_id,
                            CAST(:raw_payload AS JSONB)
                        )
                        """
                    ),
                    {
                        "poi_place_id": poi_place_id,
                        "raw_payload": json.dumps(raw_payload, ensure_ascii=True),
                    },
                )

            await conn.execute(
                text(
                    """
                    INSERT INTO zone_poi_cache_items (
                        zone_poi_cache_id,
                        poi_place_id,
                        position
                    ) VALUES (
                        :cache_id,
                        :poi_place_id,
                        :position
                    )
                    """
                ),
                {
                    "cache_id": cache_id,
                    "poi_place_id": poi_place_id,
                    "position": position,
                },
            )


async def project_poi_payload_to_zone(
    zone_id: UUID,
    *,
    poi_counts: dict[str, Any],
    poi_points: Sequence[dict[str, Any]],
) -> None:
    normalized_counts = _normalize_poi_counts(poi_counts)
    normalized_points = _normalize_poi_points(list(poi_points))

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
                "poi_counts": json.dumps(normalized_counts, ensure_ascii=True),
                "poi_points": json.dumps(normalized_points, ensure_ascii=True),
            },
        )
