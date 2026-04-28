from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from contracts import (
    FavoriteZoneCreate,
    FavoriteZoneMetricsSnapshot,
    FavoriteZoneNoteUpdate,
    FavoriteZonePayload,
    FavoriteZoneRead,
    FavoriteZoneTransportPoint,
    ZonePOIPointRead,
)
from core.db import get_engine
from modules.dashboard.analytics import fetch_zone_favorite_analytics
from sqlalchemy import text


def build_zone_key(journey_id: UUID, zone_fingerprint: str) -> str:
    return f"zone:{journey_id}:{zone_fingerprint}"


def _row_to_favorite(row) -> FavoriteZoneRead:
    payload = FavoriteZonePayload.model_validate(row["zone_payload"])
    # Re-dedup ao ler para que rows antigos com POIs duplicados apareçam limpos
    # sem exigir re-save manual.
    payload.poi_points = _dedup_pois([poi.model_dump(mode="json") for poi in payload.poi_points])
    return FavoriteZoneRead(
        zone_key=row["zone_key"],
        journey_id=row["journey_id"],
        zone_fingerprint=row["zone_fingerprint"],
        search_type=row["search_type"],
        usage_type=row["usage_type"],
        saved_at=row["saved_at"],
        payload=payload,
        note=row["note"] if "note" in row.keys() else None,
    )


def _coerce_poi(raw: Any) -> ZonePOIPointRead | None:
    if not isinstance(raw, dict):
        return None
    lat = raw.get("lat")
    lon = raw.get("lon")
    if lat is None or lon is None:
        return None
    try:
        return ZonePOIPointRead(
            kind=str(raw.get("kind") or "poi"),
            id=str(raw["id"]) if raw.get("id") is not None else None,
            name=raw.get("name"),
            category=raw.get("category"),
            address=raw.get("address"),
            lat=float(lat),
            lon=float(lon),
        )
    except (TypeError, ValueError):
        return None


def _dedup_pois(raw_list: Any) -> list[ZonePOIPointRead]:
    if not isinstance(raw_list, list):
        return []
    seen: set[str] = set()
    out: list[ZonePOIPointRead] = []
    for item in raw_list:
        poi = _coerce_poi(item)
        if poi is None:
            continue
        name_key = (poi.name or "").strip().lower()
        address_key = (poi.address or "").strip().lower()
        category_key = (poi.category or "").strip().lower()
        # Categoria + nome + endereço bastam: ids variam entre rodadas de enriquecimento
        # e coordenadas podem oscilar em microajustes do mesmo POI.
        primary_key = f"{category_key}|{name_key}|{address_key}"
        if name_key and primary_key in seen:
            continue
        # Fallback: POI sem nome/endereço → dedup por coordenada arredondada.
        if not name_key:
            primary_key = f"{category_key}|@|{round(poi.lat, 4)}|{round(poi.lon, 4)}"
            if primary_key in seen:
                continue
        seen.add(primary_key)
        out.append(poi)
    return out


async def _build_payload_from_db(
    *,
    journey_id: UUID,
    zone_fingerprint: str,
    search_type: str,
    usage_type: str,
) -> FavoriteZonePayload:
    engine = get_engine()
    async with engine.connect() as conn:
        zone_result = await conn.execute(
            text(
                """
                SELECT
                    z.fingerprint,
                    z.transport_point_id,
                    z.max_time_minutes,
                    z.green_area_m2,
                    z.flood_area_m2,
                    z.safety_incidents_count,
                    z.poi_counts,
                    z.poi_points,
                    COALESCE(ST_Area(z.isochrone_geom::geography), 0)::DOUBLE PRECISION AS zone_area_m2,
                    ST_AsGeoJSON(z.isochrone_geom)::jsonb AS isochrone_geojson
                FROM journey_zones jz
                JOIN zones z ON z.id = jz.zone_id
                WHERE jz.journey_id = :journey_id
                  AND z.fingerprint = :zone_fingerprint
                LIMIT 1
                """
            ),
            {"journey_id": journey_id, "zone_fingerprint": zone_fingerprint},
        )
        zone_row = zone_result.mappings().first()
        if zone_row is None:
            raise ValueError("Zone not found for journey")

        transport_point: FavoriteZoneTransportPoint | None = None
        tp_id = zone_row.get("transport_point_id")
        if tp_id is not None:
            tp_result = await conn.execute(
                text(
                    """
                    SELECT
                        id,
                        name,
                        source,
                        external_id,
                        ST_Y(location) AS lat,
                        ST_X(location) AS lon,
                        walk_distance_m,
                        walk_time_sec,
                        modal_types
                    FROM transport_points
                    WHERE id = :id
                    LIMIT 1
                    """
                ),
                {"id": tp_id},
            )
            tp_row = tp_result.mappings().first()
            if tp_row is not None:
                transport_point = FavoriteZoneTransportPoint(
                    id=tp_row.get("id"),
                    name=tp_row.get("name"),
                    source=tp_row.get("source"),
                    external_id=tp_row.get("external_id"),
                    lat=float(tp_row["lat"]) if tp_row.get("lat") is not None else None,
                    lon=float(tp_row["lon"]) if tp_row.get("lon") is not None else None,
                    walk_distance_m=tp_row.get("walk_distance_m"),
                    walk_time_sec=tp_row.get("walk_time_sec"),
                    modal_types=list(tp_row.get("modal_types") or []),
                )

    poi_counts_raw = zone_row.get("poi_counts")
    poi_counts: dict[str, int] | None = None
    if isinstance(poi_counts_raw, dict):
        poi_counts = {str(k): int(v) for k, v in poi_counts_raw.items() if v is not None}

    raw_pois = zone_row.get("poi_points")
    if isinstance(raw_pois, str):
        try:
            raw_pois = json.loads(raw_pois)
        except ValueError:
            raw_pois = []
    poi_points = _dedup_pois(raw_pois)
    if poi_counts is None and poi_points:
        counts: dict[str, int] = {}
        for poi in poi_points:
            key = poi.category or "other"
            counts[key] = counts.get(key, 0) + 1
        poi_counts = counts

    context: dict[str, Any] = {}
    metrics_src: dict[str, Any] = {}
    try:
        analytics = await fetch_zone_favorite_analytics(
            journey_id=journey_id,
            zone_fingerprint=zone_fingerprint,
            search_type=search_type,
            usage_type=usage_type,
        )
        context = analytics.get("context") or {}
        metrics_src = analytics.get("metrics") or {}
    except Exception:
        # Analytics ausente não deve bloquear o save.
        pass

    zone_area_m2 = float(zone_row.get("zone_area_m2") or 0.0) or None
    green_area_m2 = zone_row.get("green_area_m2")
    flood_area_m2 = zone_row.get("flood_area_m2")

    def _pct(area: float | None) -> float | None:
        if area is None or not zone_area_m2 or zone_area_m2 <= 0:
            return None
        return round(float(area) * 100.0 / zone_area_m2, 2)

    metrics = FavoriteZoneMetricsSnapshot(
        zone_area_m2=zone_area_m2,
        green_area_m2=green_area_m2,
        green_percentage=metrics_src.get("green_percentage") or _pct(green_area_m2),
        flood_area_m2=flood_area_m2,
        flood_percentage=metrics_src.get("flood_percentage") or _pct(flood_area_m2),
        flood_risk_label=metrics_src.get("flood_risk_label"),
        safety_incidents_count=zone_row.get("safety_incidents_count"),
        homicide_density_per_km2=metrics_src.get("homicide_density_per_km2"),
        robbery_density_per_km2=metrics_src.get("robbery_density_per_km2"),
        theft_density_per_km2=metrics_src.get("theft_density_per_km2"),
        crime_density_per_km2=metrics_src.get("crime_density_per_km2"),
        zone_average_price=metrics_src.get("zone_average_price"),
        zone_average_unit_price=metrics_src.get("zone_average_unit_price"),
        travel_time_minutes=zone_row.get("max_time_minutes"),
    )

    return FavoriteZonePayload(
        fingerprint=zone_fingerprint,
        journey_id=journey_id,
        transport_point_id=tp_id,
        transport_point=transport_point,
        neighborhood_name=context.get("neighborhood_name"),
        city_name=context.get("city_name"),
        state_code=context.get("state_code"),
        isochrone_geom=zone_row.get("isochrone_geojson"),
        poi_counts=poi_counts,
        poi_points=poi_points,
        metrics=metrics,
        listings=[],
    )


async def list_user_zone_favorites(user_id: UUID, *, retention_days: int | None = None) -> list[FavoriteZoneRead]:
    engine = get_engine()
    async with engine.connect() as conn:
        if retention_days is not None:
            result = await conn.execute(
                text(
                    """
                    SELECT zone_key, journey_id, zone_fingerprint, search_type, usage_type, saved_at, zone_payload, note
                    FROM user_zone_favorites
                    WHERE user_id = :user_id
                      AND saved_at > now() - (:retention_days * INTERVAL '1 day')
                    ORDER BY saved_at DESC
                    """
                ),
                {"user_id": user_id, "retention_days": retention_days},
            )
        else:
            result = await conn.execute(
                text(
                    """
                    SELECT zone_key, journey_id, zone_fingerprint, search_type, usage_type, saved_at, zone_payload, note
                    FROM user_zone_favorites
                    WHERE user_id = :user_id
                    ORDER BY saved_at DESC
                    """
                ),
                {"user_id": user_id},
            )
        rows = result.mappings().all()
    return [_row_to_favorite(row) for row in rows]


async def upsert_user_zone_favorite(user_id: UUID, create: FavoriteZoneCreate) -> FavoriteZoneRead:
    zone_key = build_zone_key(create.journey_id, create.zone_fingerprint)
    payload = await _build_payload_from_db(
        journey_id=create.journey_id,
        zone_fingerprint=create.zone_fingerprint,
        search_type=create.search_type,
        usage_type=create.usage_type,
    )
    zone_payload_json = json.dumps(payload.model_dump(mode="json"), separators=(",", ":"))

    engine = get_engine()
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                INSERT INTO user_zone_favorites (
                    user_id,
                    zone_key,
                    journey_id,
                    zone_fingerprint,
                    search_type,
                    usage_type,
                    zone_payload
                )
                VALUES (
                    :user_id,
                    :zone_key,
                    :journey_id,
                    :zone_fingerprint,
                    :search_type,
                    :usage_type,
                    CAST(:zone_payload AS JSONB)
                )
                ON CONFLICT (user_id, zone_key)
                DO UPDATE SET
                    journey_id = EXCLUDED.journey_id,
                    zone_fingerprint = EXCLUDED.zone_fingerprint,
                    search_type = EXCLUDED.search_type,
                    usage_type = EXCLUDED.usage_type,
                    zone_payload = EXCLUDED.zone_payload,
                    saved_at = now(),
                    updated_at = now()
                RETURNING zone_key, journey_id, zone_fingerprint, search_type, usage_type, saved_at, zone_payload, note
                """
            ),
            {
                "user_id": user_id,
                "zone_key": zone_key,
                "journey_id": create.journey_id,
                "zone_fingerprint": create.zone_fingerprint,
                "search_type": create.search_type,
                "usage_type": create.usage_type,
                "zone_payload": zone_payload_json,
            },
        )
        row = result.mappings().one()
    return _row_to_favorite(row)


async def update_user_zone_favorite_note(user_id: UUID, zone_key: str, payload: FavoriteZoneNoteUpdate) -> FavoriteZoneRead | None:
    engine = get_engine()
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                UPDATE user_zone_favorites
                SET note = :note, updated_at = now()
                WHERE user_id = :user_id AND zone_key = :zone_key
                RETURNING zone_key, journey_id, zone_fingerprint, search_type, usage_type, saved_at, zone_payload, note
                """
            ),
            {"user_id": user_id, "zone_key": zone_key, "note": payload.note},
        )
        row = result.mappings().first()
    if row is None:
        return None
    return _row_to_favorite(row)


async def delete_user_zone_favorite(user_id: UUID, zone_key: str) -> bool:
    engine = get_engine()
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                DELETE FROM user_zone_favorites
                WHERE user_id = :user_id
                  AND zone_key = :zone_key
                """
            ),
            {
                "user_id": user_id,
                "zone_key": zone_key,
            },
        )
    return (result.rowcount or 0) > 0
