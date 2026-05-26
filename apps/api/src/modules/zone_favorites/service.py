from __future__ import annotations

import hashlib
import json
import re
import secrets
from typing import Any
from uuid import UUID

from contracts import (
    FavoriteZoneCreate,
    FavoriteZoneColorUpdate,
    FavoriteZoneMetricsSnapshot,
    FavoriteZoneNoteUpdate,
    FavoriteZonePayload,
    FavoriteZoneRead,
    FavoriteZoneShareRead,
    FavoriteZoneShareSnapshotRead,
    FavoriteZoneTransportPoint,
    ListingCardRead,
    ZoneTransportSummaryRead,
    ZonePOIPointRead,
)
from core.db import get_engine
from modules.dashboard.analytics import fetch_zone_favorite_analytics
from modules.listings.dedup import fetch_listing_cards_for_zone
from modules.listings.platform_registry import PlatformRegistryError, get_platform_registry
from sqlalchemy import text

_DEFAULT_ZONE_COLOR = "#0ea5e9"
_ZONE_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def build_zone_key(journey_id: UUID, zone_fingerprint: str) -> str:
    return f"zone:{journey_id}:{zone_fingerprint}"


def _normalize_color(value: str | None) -> str:
    if isinstance(value, str) and _ZONE_COLOR_RE.fullmatch(value.strip()):
        return value.strip().lower()
    return _DEFAULT_ZONE_COLOR


def _default_color_for_zone_key(zone_key: str) -> str:
    palette = ["#0ea5e9", "#8b5cf6", "#10b981", "#f97316", "#ef4444", "#14b8a6", "#eab308", "#ec4899"]
    digest = hashlib.sha256(zone_key.encode("utf-8")).digest()
    return palette[digest[0] % len(palette)]


def generate_share_token() -> str:
    return secrets.token_urlsafe(32)


def _hash_share_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _row_to_favorite(row) -> FavoriteZoneRead:
    payload = FavoriteZonePayload.model_validate(row["zone_payload"])
    color = _normalize_color(row["color"] if "color" in row.keys() else payload.color)
    payload.color = color
    share = None
    if "share_created_at" in row.keys() and row["share_created_at"] is not None:
        share = FavoriteZoneShareRead(
            token=row["share_token"] if "share_token" in row.keys() else None,
            zone_key=row["zone_key"],
            created_at=row["share_created_at"],
            revoked_at=row["share_revoked_at"] if "share_revoked_at" in row.keys() else None,
        )
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
        color=color,
        share=share,
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


async def _build_transport_summary_from_db(*, journey_id: UUID, zone_fingerprint: str) -> ZoneTransportSummaryRead:
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                """
                WITH zone_base AS (
                    SELECT z.isochrone_geom
                    FROM journey_zones jz
                    JOIN zones z ON z.id = jz.zone_id
                    WHERE jz.journey_id = :journey_id
                      AND z.fingerprint = :zone_fingerprint
                      AND z.isochrone_geom IS NOT NULL
                    LIMIT 1
                ), bus_routes AS (
                    SELECT COUNT(DISTINCT COALESCE(NULLIF(gr.route_short_name, ''), gr.route_id))::INT AS count
                    FROM zone_base zb
                    JOIN gtfs_stops s ON ST_Within(s.location, zb.isochrone_geom)
                    JOIN gtfs_stop_times st ON st.stop_id = s.stop_id
                    JOIN gtfs_trips gt ON gt.trip_id = st.trip_id
                    JOIN gtfs_routes gr ON gr.route_id = gt.route_id
                    WHERE gr.route_type = 3
                ), rail_routes AS (
                    SELECT COUNT(DISTINCT COALESCE(NULLIF(gr.route_short_name, ''), gr.route_id))::INT AS count
                    FROM zone_base zb
                    JOIN gtfs_stops s ON ST_Within(s.location, zb.isochrone_geom)
                    JOIN gtfs_stop_times st ON st.stop_id = s.stop_id
                    JOIN gtfs_trips gt ON gt.trip_id = st.trip_id
                    JOIN gtfs_routes gr ON gr.route_id = gt.route_id
                    WHERE gr.route_type IN (1, 2)
                )
                SELECT
                    (
                        SELECT COUNT(DISTINCT s.stop_id)::INT
                        FROM zone_base zb, gtfs_stops s
                        WHERE ST_Within(s.location, zb.isochrone_geom)
                    ) + (
                        SELECT COUNT(DISTINCT md5(ST_AsEWKB(g.geometry)::text))::INT
                        FROM zone_base zb, geosampa_bus_stops g
                        WHERE ST_Within(ST_PointOnSurface(g.geometry), zb.isochrone_geom)
                    ) AS bus_stop_count,
                    COALESCE((SELECT count FROM bus_routes), 0) + (
                        SELECT COUNT(DISTINCT COALESCE(NULLIF(g.ln_nome, ''), md5(ST_AsEWKB(g.geometry)::text)))::INT
                        FROM zone_base zb, geosampa_bus_lines g
                        WHERE ST_Intersects(g.geometry, zb.isochrone_geom)
                    ) AS bus_line_count,
                    (
                        SELECT COUNT(DISTINCT md5(ST_AsEWKB(g.geometry)::text))::INT
                        FROM zone_base zb, geosampa_bus_terminals g
                        WHERE ST_Within(ST_PointOnSurface(g.geometry), zb.isochrone_geom)
                    ) AS bus_terminal_count,
                    (
                        SELECT COUNT(DISTINCT md5(ST_AsEWKB(g.geometry)::text))::INT
                        FROM zone_base zb, geosampa_metro_stations g
                        WHERE ST_Within(ST_PointOnSurface(g.geometry), zb.isochrone_geom)
                    ) + (
                        SELECT COUNT(DISTINCT md5(ST_AsEWKB(g.geometry)::text))::INT
                        FROM zone_base zb, geosampa_trem_stations g
                        WHERE ST_Within(ST_PointOnSurface(g.geometry), zb.isochrone_geom)
                    ) AS train_metro_platform_count,
                    COALESCE((SELECT count FROM rail_routes), 0) + (
                        SELECT COUNT(DISTINCT COALESCE(NULLIF(g.nm_linha_metro_trem, ''), NULLIF(g.nr_nome_linha, ''), md5(ST_AsEWKB(g.geometry)::text)))::INT
                        FROM zone_base zb, geosampa_metro_lines g
                        WHERE ST_Intersects(g.geometry, zb.isochrone_geom)
                    ) + (
                        SELECT COUNT(DISTINCT COALESCE(NULLIF(g.nm_linha_metro_trem, ''), md5(ST_AsEWKB(g.geometry)::text)))::INT
                        FROM zone_base zb, geosampa_trem_lines g
                        WHERE ST_Intersects(g.geometry, zb.isochrone_geom)
                    ) AS train_metro_line_count
                """
            ),
            {"journey_id": journey_id, "zone_fingerprint": zone_fingerprint},
        )
        row = result.mappings().first()
    if row is None:
        return ZoneTransportSummaryRead()
    return ZoneTransportSummaryRead(
        bus_stop_count=int(row.get("bus_stop_count") or 0),
        bus_line_count=int(row.get("bus_line_count") or 0),
        bus_terminal_count=int(row.get("bus_terminal_count") or 0),
        train_metro_platform_count=int(row.get("train_metro_platform_count") or 0),
        train_metro_line_count=int(row.get("train_metro_line_count") or 0),
    )


async def _build_property_type_counts_from_db(
    *,
    journey_id: UUID,
    zone_fingerprint: str,
    search_type: str,
    usage_type: str,
) -> dict[str, int]:
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                """
                WITH zone_base AS (
                    SELECT z.isochrone_geom
                    FROM journey_zones jz
                    JOIN zones z ON z.id = jz.zone_id
                    WHERE jz.journey_id = :journey_id
                      AND z.fingerprint = :zone_fingerprint
                      AND z.isochrone_geom IS NOT NULL
                    LIMIT 1
                ),
                latest_active_ads AS (
                    SELECT DISTINCT ON (la.property_id)
                        la.property_id,
                        la.usage_type AS ad_usage_type
                    FROM listing_ads la
                    JOIN LATERAL (
                        SELECT 1
                        FROM listing_snapshots ls
                        WHERE ls.listing_ad_id = la.id
                          AND (ls.availability_state = 'active' OR ls.availability_state IS NULL)
                        ORDER BY ls.observed_at DESC
                        LIMIT 1
                    ) snapshot ON TRUE
                    WHERE la.is_active = TRUE
                      AND la.advertised_usage_type = :search_type
                      AND (:usage_type = 'all' OR la.usage_type IS NULL OR la.usage_type = :usage_type)
                    ORDER BY la.property_id, la.last_seen_at DESC
                )
                SELECT COALESCE(p.usage_type, laa.ad_usage_type, 'unknown') AS property_type,
                       COUNT(DISTINCT p.id)::INT AS count
                FROM zone_base zb
                JOIN properties p ON p.location IS NOT NULL AND ST_Within(p.location, zb.isochrone_geom)
                JOIN latest_active_ads laa ON laa.property_id = p.id
                GROUP BY COALESCE(p.usage_type, laa.ad_usage_type, 'unknown')
                """
            ),
            {
                "journey_id": journey_id,
                "zone_fingerprint": zone_fingerprint,
                "search_type": search_type,
                "usage_type": usage_type,
            },
        )
        rows = result.mappings().all()
    return {str(row["property_type"]): int(row.get("count") or 0) for row in rows}


async def _build_listing_snapshot_from_db(
    *,
    journey_id: UUID,
    zone_fingerprint: str,
    search_type: str,
    usage_type: str,
) -> list[ListingCardRead]:
    try:
        platforms = get_platform_registry().available_platforms()
    except PlatformRegistryError:
        platforms = ["quintoandar", "zapimoveis", "vivareal"]
    cards = await fetch_listing_cards_for_zone(
        journey_id=journey_id,
        zone_fingerprint=zone_fingerprint,
        search_type=search_type,
        usage_type=usage_type,
        platforms=platforms,
        spatial_scope="inside_zone",
        address_scope="all_addresses",
        limit=80,
        offset=0,
    )
    return [ListingCardRead.model_validate(card) for card in cards]


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

    transport_summary = await _build_transport_summary_from_db(
        journey_id=journey_id,
        zone_fingerprint=zone_fingerprint,
    )
    property_type_counts = await _build_property_type_counts_from_db(
        journey_id=journey_id,
        zone_fingerprint=zone_fingerprint,
        search_type=search_type,
        usage_type=usage_type,
    )
    listings = await _build_listing_snapshot_from_db(
        journey_id=journey_id,
        zone_fingerprint=zone_fingerprint,
        search_type=search_type,
        usage_type=usage_type,
    )

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
        color=None,
        transport_point_id=tp_id,
        transport_point=transport_point,
        neighborhood_name=context.get("neighborhood_name"),
        city_name=context.get("city_name"),
        state_code=context.get("state_code"),
        isochrone_geom=zone_row.get("isochrone_geojson"),
        poi_counts=poi_counts,
        poi_points=poi_points,
        transport_summary=transport_summary,
        property_type_counts=property_type_counts,
        metrics=metrics,
        listings=listings,
    )


async def list_user_zone_favorites(user_id: UUID, *, retention_days: int | None = None) -> list[FavoriteZoneRead]:
    engine = get_engine()
    async with engine.connect() as conn:
        if retention_days is not None:
            result = await conn.execute(
                text(
                    """
                    SELECT
                        uzf.zone_key,
                        uzf.journey_id,
                        uzf.zone_fingerprint,
                        uzf.search_type,
                        uzf.usage_type,
                        uzf.saved_at,
                        uzf.zone_payload,
                        uzf.color,
                        uzf.note,
                        zfs.created_at AS share_created_at,
                        zfs.revoked_at AS share_revoked_at,
                        NULL::TEXT AS share_token
                    FROM user_zone_favorites uzf
                    LEFT JOIN LATERAL (
                        SELECT created_at, revoked_at
                        FROM zone_favorite_shares
                        WHERE zone_favorite_id = uzf.id
                          AND revoked_at IS NULL
                        ORDER BY created_at DESC
                        LIMIT 1
                    ) zfs ON TRUE
                    WHERE uzf.user_id = :user_id
                      AND uzf.saved_at > now() - (:retention_days * INTERVAL '1 day')
                    ORDER BY uzf.saved_at DESC
                    """
                ),
                {"user_id": user_id, "retention_days": retention_days},
            )
        else:
            result = await conn.execute(
                text(
                    """
                    SELECT
                        uzf.zone_key,
                        uzf.journey_id,
                        uzf.zone_fingerprint,
                        uzf.search_type,
                        uzf.usage_type,
                        uzf.saved_at,
                        uzf.zone_payload,
                        uzf.color,
                        uzf.note,
                        zfs.created_at AS share_created_at,
                        zfs.revoked_at AS share_revoked_at,
                        NULL::TEXT AS share_token
                    FROM user_zone_favorites uzf
                    LEFT JOIN LATERAL (
                        SELECT created_at, revoked_at
                        FROM zone_favorite_shares
                        WHERE zone_favorite_id = uzf.id
                          AND revoked_at IS NULL
                        ORDER BY created_at DESC
                        LIMIT 1
                    ) zfs ON TRUE
                    WHERE uzf.user_id = :user_id
                    ORDER BY uzf.saved_at DESC
                    """
                ),
                {"user_id": user_id},
            )
        rows = result.mappings().all()
    return [_row_to_favorite(row) for row in rows]


async def upsert_user_zone_favorite(user_id: UUID, create: FavoriteZoneCreate) -> FavoriteZoneRead:
    zone_key = build_zone_key(create.journey_id, create.zone_fingerprint)
    color = _default_color_for_zone_key(zone_key)
    payload = await _build_payload_from_db(
        journey_id=create.journey_id,
        zone_fingerprint=create.zone_fingerprint,
        search_type=create.search_type,
        usage_type=create.usage_type,
    )
    payload.color = color
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
                    color,
                    zone_payload
                )
                VALUES (
                    :user_id,
                    :zone_key,
                    :journey_id,
                    :zone_fingerprint,
                    :search_type,
                    :usage_type,
                    :color,
                    CAST(:zone_payload AS JSONB)
                )
                ON CONFLICT (user_id, zone_key)
                DO UPDATE SET
                    journey_id = EXCLUDED.journey_id,
                    zone_fingerprint = EXCLUDED.zone_fingerprint,
                    search_type = EXCLUDED.search_type,
                    usage_type = EXCLUDED.usage_type,
                    color = COALESCE(user_zone_favorites.color, EXCLUDED.color),
                    zone_payload = EXCLUDED.zone_payload,
                    saved_at = now(),
                    updated_at = now()
                RETURNING zone_key, journey_id, zone_fingerprint, search_type, usage_type, saved_at, zone_payload, color, note
                """
            ),
            {
                "user_id": user_id,
                "zone_key": zone_key,
                "journey_id": create.journey_id,
                "zone_fingerprint": create.zone_fingerprint,
                "search_type": create.search_type,
                "usage_type": create.usage_type,
                "color": color,
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
                RETURNING zone_key, journey_id, zone_fingerprint, search_type, usage_type, saved_at, zone_payload, color, note
                """
            ),
            {"user_id": user_id, "zone_key": zone_key, "note": payload.note},
        )
        row = result.mappings().first()
    if row is None:
        return None
    return _row_to_favorite(row)


async def update_user_zone_favorite_color(user_id: UUID, zone_key: str, payload: FavoriteZoneColorUpdate) -> FavoriteZoneRead | None:
    color = _normalize_color(payload.color)
    engine = get_engine()
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                UPDATE user_zone_favorites
                SET
                    color = :color,
                    zone_payload = jsonb_set(zone_payload, '{color}', to_jsonb(CAST(:color AS TEXT)), true),
                    updated_at = now()
                WHERE user_id = :user_id AND zone_key = :zone_key
                RETURNING zone_key, journey_id, zone_fingerprint, search_type, usage_type, saved_at, zone_payload, color, note
                """
            ),
            {"user_id": user_id, "zone_key": zone_key, "color": color},
        )
        row = result.mappings().first()
    if row is None:
        return None
    return _row_to_favorite(row)


async def create_zone_favorite_share(user_id: UUID, zone_key: str) -> FavoriteZoneShareRead | None:
    token = generate_share_token()
    token_hash = _hash_share_token(token)
    engine = get_engine()
    async with engine.begin() as conn:
        favorite_result = await conn.execute(
            text(
                """
                SELECT id
                FROM user_zone_favorites
                WHERE user_id = :user_id
                  AND zone_key = :zone_key
                LIMIT 1
                """
            ),
            {"user_id": user_id, "zone_key": zone_key},
        )
        favorite = favorite_result.mappings().first()
        if favorite is None:
            return None
        favorite_id = favorite["id"]
        await conn.execute(
            text(
                """
                UPDATE zone_favorite_shares
                SET revoked_at = now()
                WHERE zone_favorite_id = :zone_favorite_id
                  AND revoked_at IS NULL
                """
            ),
            {"zone_favorite_id": favorite_id},
        )
        result = await conn.execute(
            text(
                """
                INSERT INTO zone_favorite_shares (
                    zone_favorite_id,
                    created_by_user_id,
                    token_hash
                )
                VALUES (
                    :zone_favorite_id,
                    :user_id,
                    :token_hash
                )
                RETURNING created_at, revoked_at
                """
            ),
            {"zone_favorite_id": favorite_id, "user_id": user_id, "token_hash": token_hash},
        )
        row = result.mappings().one()
    return FavoriteZoneShareRead(token=token, zone_key=zone_key, created_at=row["created_at"], revoked_at=row["revoked_at"])


async def revoke_zone_favorite_shares(user_id: UUID, zone_key: str) -> bool:
    engine = get_engine()
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                UPDATE zone_favorite_shares zfs
                SET revoked_at = now()
                FROM user_zone_favorites uzf
                WHERE zfs.zone_favorite_id = uzf.id
                  AND uzf.user_id = :user_id
                  AND uzf.zone_key = :zone_key
                  AND zfs.revoked_at IS NULL
                """
            ),
            {"user_id": user_id, "zone_key": zone_key},
        )
    return bool(result.rowcount)


async def get_zone_favorite_share_snapshot(token: str) -> FavoriteZoneShareSnapshotRead | None:
    token_hash = _hash_share_token(token)
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                """
                SELECT
                    zfs.created_at AS share_created_at,
                    zfs.revoked_at AS share_revoked_at,
                    uzf.zone_key,
                    uzf.journey_id,
                    uzf.zone_fingerprint,
                    uzf.search_type,
                    uzf.usage_type,
                    uzf.saved_at,
                    uzf.zone_payload,
                    uzf.color,
                    uzf.note
                FROM zone_favorite_shares zfs
                JOIN user_zone_favorites uzf ON uzf.id = zfs.zone_favorite_id
                WHERE zfs.token_hash = :token_hash
                  AND zfs.revoked_at IS NULL
                LIMIT 1
                """
            ),
            {"token_hash": token_hash},
        )
        row = result.mappings().first()
    if row is None:
        return None
    zone = _row_to_favorite(row)
    share = FavoriteZoneShareRead(
        token=token,
        zone_key=row["zone_key"],
        created_at=row["share_created_at"],
        revoked_at=row["share_revoked_at"],
    )
    return FavoriteZoneShareSnapshotRead(share=share, zone=zone)


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
