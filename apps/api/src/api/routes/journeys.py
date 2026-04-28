from __future__ import annotations
from math import isfinite
from typing import Any
from uuid import UUID

from contracts import (
    JourneyCreate,
    JourneyRead,
    JourneyUpdate,
    TransportPointRead,
    ZoneDashboardAnalyticsRead,
    ZoneFavoriteAnalyticsRead,
    ZoneListResponse,
    ZoneSafetyIncidentCollectionRead,
)
from core.container import get_container
from core.db import get_engine
from fastapi import APIRouter, Depends, HTTPException, Response, status
from api.routes.auth import get_optional_auth_context
from modules.journeys.service import (
    ANONYMOUS_SESSION_COOKIE,
    create_journey,
    expire_journey,
    generate_anonymous_session_id,
    get_journey_for_access,
    get_journey,
    update_journey,
)
from modules.plans.service import resolve_entitlements
from modules.public_safety import classify_public_safety_group
from modules.dashboard.analytics import fetch_zone_dashboard_analytics, fetch_zone_favorite_analytics
from modules.public_safety import public_safety_group_case_sql
from modules.zones.badges import build_metric_badge
from modules.zones.vegetation import (
    extract_green_preferences,
    get_green_vegetation_label,
    green_vegetation_case_sql,
    green_vegetation_inclusion_sql,
)
from sqlalchemy import text

router = APIRouter(prefix="/journeys", tags=["journeys"])

# Default parameter values used when the plan has locked customization.
_DEFAULT_ZONE_RADIUS_M = 400
_DEFAULT_TRANSPORT_RADIUS_M = 400
_DEFAULT_MAX_TRAVEL_MINUTES = 30


async def _enforce_snapshot_customization(snapshot: dict[str, Any], auth_context) -> None:
    """Silently overrides locked/capped parameters — UI already blocks invalid values."""
    if auth_context.user is None:
        _clamp_locked_value(snapshot, "zone_radius_meters", _DEFAULT_ZONE_RADIUS_M)
        _clamp_locked_value(snapshot, "transport_search_radius_meters", _DEFAULT_TRANSPORT_RADIUS_M)
        _clamp_locked_value(snapshot, "max_travel_minutes", _DEFAULT_MAX_TRAVEL_MINUTES)
        return

    resolved = await resolve_entitlements(auth_context.user.id)
    ent = resolved.entitlements

    if not ent.can_customize_radius:
        _clamp_locked_value(snapshot, "zone_radius_meters", _DEFAULT_ZONE_RADIUS_M)
    elif ent.max_zone_radius_m_cap is not None:
        _clamp_cap_value(snapshot, "zone_radius_meters", ent.max_zone_radius_m_cap)

    if not ent.can_customize_distance:
        _clamp_locked_value(snapshot, "transport_search_radius_meters", _DEFAULT_TRANSPORT_RADIUS_M)

    if not ent.can_customize_max_time:
        _clamp_locked_value(snapshot, "max_travel_minutes", _DEFAULT_MAX_TRAVEL_MINUTES)
    else:
        mode = snapshot.get("transport_mode", "transit")
        cap = (
            ent.max_walk_minutes_cap if mode == "walk"
            else ent.max_car_minutes_cap if mode == "car"
            else ent.max_transit_minutes_cap
        )
        if cap is not None:
            _clamp_cap_value(snapshot, "max_travel_minutes", cap)


def _clamp_locked_value(snapshot: dict[str, Any], field: str, default: int | float) -> None:
    if snapshot.get(field) is not None:
        snapshot[field] = default


def _clamp_cap_value(snapshot: dict[str, Any], field: str, cap: int | float) -> None:
    val = snapshot.get(field)
    if val is not None and val > cap:
        snapshot[field] = cap



async def _enforce_zone_selection_policy(journey_id: UUID, zone_id: UUID, auth_context) -> None:
    return


async def _get_accessible_journey_or_404(journey_id: UUID, auth_context) -> JourneyRead:
    journey = await get_journey_for_access(
        journey_id,
        user_id=auth_context.user.id if auth_context.user is not None else None,
        anonymous_session_id=auth_context.anonymous_session_id,
    )
    if journey is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Journey not found")
    return journey


def _normalize_badges_payload(raw_badges: Any) -> dict[str, dict[str, Any]] | None:
    if not isinstance(raw_badges, dict):
        return None

    normalized: dict[str, dict[str, Any]] = {}
    key_map = {
        "green": "green_badge",
        "flood": "flood_badge",
        "safety": "safety_badge",
        "poi": "poi_badge",
        "green_badge": "green_badge",
        "flood_badge": "flood_badge",
        "safety_badge": "safety_badge",
        "poi_badge": "poi_badge",
    }

    for source_key, target_key in key_map.items():
        payload = raw_badges.get(source_key)
        if not isinstance(payload, dict):
            continue

        percentile = payload.get("percentile")
        if percentile is None:
            percentile = payload.get("rank_percentile")

        if percentile is None:
            continue

        normalized[target_key] = {
            "value": payload.get("value", 0),
            "percentile": percentile,
            "tier": payload.get("tier", "fair"),
        }

    return normalized or None


def _safe_float(value: Any) -> float | None:
    try:
        numeric_value = float(value) if value is not None else None
    except (TypeError, ValueError):
        numeric_value = None
    if numeric_value is None or not isfinite(numeric_value):
        return None
    return numeric_value


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def _build_rank_map(values_by_key: dict[str, float | None], *, higher_is_better: bool) -> dict[str, dict[str, Any] | None]:
    sortable_items = [
        (key, value)
        for key, value in values_by_key.items()
        if value is not None and isfinite(value)
    ]
    sortable_items.sort(
        key=lambda item: ((-item[1]) if higher_is_better else item[1], item[0])
    )

    total = len(sortable_items)
    ranks: dict[str, dict[str, Any] | None] = {key: None for key in values_by_key}
    if total == 0:
        return ranks

    previous_value: float | None = None
    current_position = 0
    for index, (key, value) in enumerate(sortable_items, start=1):
        if previous_value is None or value != previous_value:
            current_position = index
            previous_value = value
        ranks[key] = {
            "position": current_position,
            "total": total,
            "percentile": round(((total - current_position + 1) / total) * 100.0, 2),
        }

    return ranks


async def list_transport_points_for_journey(journey_id: UUID) -> list[TransportPointRead]:
    transport_service = get_container().transport_service()
    return await transport_service.list_transport_points_for_journey(journey_id)


async def list_zones_for_journey(journey_id: UUID) -> ZoneListResponse:
    engine = get_engine()
    async with engine.connect() as conn:
        snapshot_result = await conn.execute(
            text(
                """
                SELECT input_snapshot
                FROM journeys
                WHERE id = :journey_id
                """
            ),
            {"journey_id": journey_id},
        )
        snapshot_row = snapshot_result.mappings().first()

        green_enabled, green_vegetation_level = extract_green_preferences(
            snapshot_row["input_snapshot"] if snapshot_row else None
        )
        input_snapshot = snapshot_row["input_snapshot"] if snapshot_row else None
        search_type = str(input_snapshot.get("search_type") or "rent") if isinstance(input_snapshot, dict) else "rent"
        if search_type not in {"rent", "sale"}:
            search_type = "rent"
        property_usage_type = (
            str(input_snapshot.get("property_usage_type") or "all")
            if isinstance(input_snapshot, dict)
            else "all"
        )
        if property_usage_type not in {"all", "residential", "commercial"}:
            property_usage_type = "all"
        green_vegetation_label = (
            get_green_vegetation_label(green_vegetation_level) if green_enabled else None
        )
        green_area_sql = "NULL::DOUBLE PRECISION"
        if green_enabled and green_vegetation_level:
            classification_sql = green_vegetation_case_sql("gv.ves_categ")
            green_area_sql = f"""
                COALESCE((
                    SELECT
                        SUM(
                            ST_Area(
                                ST_Intersection(z.isochrone_geom, gv.geometry)::geography
                            )
                        )
                    FROM geosampa_vegetacao_significativa gv
                    WHERE z.isochrone_geom IS NOT NULL
                      AND ST_Intersects(z.isochrone_geom, gv.geometry)
                      AND {green_vegetation_inclusion_sql(classification_sql, green_vegetation_level)}
                ), 0)::DOUBLE PRECISION
            """
        elif green_enabled:
            green_area_sql = "z.green_area_m2::DOUBLE PRECISION"

        result = await conn.execute(
            text(
                f"""
                SELECT
                    z.id,
                    jz.journey_id,
                    z.transport_point_id,
                    z.fingerprint,
                    z.state,
                    z.is_circle_fallback,
                    z.max_time_minutes AS travel_time_minutes,
                    tp.walk_distance_m AS walk_distance_meters,
                    ST_AsGeoJSON(z.isochrone_geom)::JSONB AS isochrone_geom,
                    COALESCE(ST_Area(z.isochrone_geom::geography), 0)::DOUBLE PRECISION AS zone_area_m2,
                    {green_area_sql} AS green_area_m2,
                    z.flood_area_m2,
                    z.safety_incidents_count,
                    z.poi_counts,
                    z.poi_points,
                    z.badges,
                    z.badges_provisional,
                    z.created_at,
                    z.updated_at
                FROM zones z
                JOIN journey_zones jz ON jz.zone_id = z.id
                LEFT JOIN transport_points tp ON tp.id = jz.transport_point_id
                WHERE jz.journey_id = :journey_id
                ORDER BY z.max_time_minutes ASC, tp.walk_distance_m ASC, jz.created_at ASC, z.created_at ASC
                """
            ),
            {"journey_id": journey_id},
        )
        rows = result.mappings().all()

        price_summary_result = await conn.execute(
            text(
                """
                WITH journey_zone_base AS (
                    SELECT z.fingerprint, z.isochrone_geom
                    FROM journey_zones jz
                    JOIN zones z ON z.id = jz.zone_id
                    WHERE jz.journey_id = :journey_id
                      AND z.isochrone_geom IS NOT NULL
                ),
                latest_active_prices AS (
                    SELECT
                        la.property_id,
                                                MIN(COALESCE(snapshot.price, 0) + COALESCE(snapshot.condo_fee, 0) + COALESCE(snapshot.iptu, 0))::DOUBLE PRECISION AS current_total_price
                    FROM listing_ads la
                    JOIN LATERAL (
                                                SELECT ls.price, ls.condo_fee, ls.iptu
                        FROM listing_snapshots ls
                        WHERE ls.listing_ad_id = la.id
                          AND ls.price IS NOT NULL
                          AND (ls.availability_state = 'active' OR ls.availability_state IS NULL)
                        ORDER BY ls.observed_at DESC
                        LIMIT 1
                    ) snapshot ON TRUE
                    WHERE la.is_active = TRUE
                      AND la.advertised_usage_type = :search_type
                                            AND (:usage_type = 'all' OR la.usage_type IS NULL OR la.usage_type = :usage_type)
                    GROUP BY la.property_id
                ),
                zone_prices AS (
                    SELECT
                        jzb.fingerprint,
                        lap.current_total_price
                    FROM journey_zone_base jzb
                    JOIN properties p
                      ON p.location IS NOT NULL
                     AND ST_Within(p.location, jzb.isochrone_geom)
                    JOIN latest_active_prices lap ON lap.property_id = p.id
                )
                SELECT
                    fingerprint,
                    percentile_cont(0.5) WITHIN GROUP (ORDER BY current_total_price)::DOUBLE PRECISION AS p50_price,
                    COUNT(*)::INT AS active_listing_count
                FROM zone_prices
                GROUP BY fingerprint
                """
            ),
            {
                "journey_id": journey_id,
                "search_type": search_type,
                "usage_type": property_usage_type,
            },
        )
        price_summary_rows = {
            str(row["fingerprint"]): {
                "p50_price": _safe_float(row.get("p50_price")),
                "active_listing_count": int(row.get("active_listing_count") or 0),
            }
            for row in price_summary_result.mappings().all()
        }

        safety_group_sql = public_safety_group_case_sql("psi.category")
        journey_safety_result = await conn.execute(
            text(
                f"""
                WITH journey_zone_base AS (
                    SELECT
                        z.fingerprint,
                        z.isochrone_geom,
                        COALESCE(ST_Area(z.isochrone_geom::geography), 0)::DOUBLE PRECISION AS zone_area_m2
                    FROM journey_zones jz
                    JOIN zones z ON z.id = jz.zone_id
                    WHERE jz.journey_id = :journey_id
                ),
                zone_incidents AS (
                    SELECT
                        jzb.fingerprint,
                        COUNT(*) FILTER (
                            WHERE psi.occurred_at >= NOW() - INTERVAL '365 days'
                              AND ({safety_group_sql}) = 'robbery'
                        )::INT AS robbery_count_365d
                    FROM journey_zone_base jzb
                    LEFT JOIN public_safety_incidents psi
                      ON psi.location IS NOT NULL
                     AND jzb.isochrone_geom IS NOT NULL
                     AND ST_Within(psi.location, jzb.isochrone_geom)
                    GROUP BY jzb.fingerprint
                )
                SELECT
                    jzb.fingerprint,
                    jzb.zone_area_m2,
                    COALESCE(zi.robbery_count_365d, 0)::INT AS robbery_count_365d
                FROM journey_zone_base jzb
                LEFT JOIN zone_incidents zi ON zi.fingerprint = jzb.fingerprint
                ORDER BY jzb.fingerprint ASC
                """
            ),
            {"journey_id": journey_id},
        )
        safety_rows = [dict(row) for row in journey_safety_result.mappings().all()]

    zones = []
    completed_count = 0
    green_peers = [float(row["green_area_m2"] or 0.0) for row in rows if row["green_area_m2"] is not None]
    green_percentages_by_fingerprint = {
        str(row["fingerprint"]): _safe_ratio(
            (_safe_float(row.get("green_area_m2")) or 0.0) * 100.0,
            _safe_float(row.get("zone_area_m2")),
        )
        for row in rows
    }
    flood_percentages_by_fingerprint = {
        str(row["fingerprint"]): _safe_ratio(
            (_safe_float(row.get("flood_area_m2")) or 0.0) * 100.0,
            _safe_float(row.get("zone_area_m2")),
        )
        for row in rows
    }
    safety_density_by_fingerprint = {
        str(row["fingerprint"]): _safe_ratio(
            float(int(row.get("robbery_count_365d") or 0)),
            _safe_ratio(_safe_float(row.get("zone_area_m2")), 1_000_000.0),
        )
        for row in safety_rows
    }
    price_p50_by_fingerprint = {
        fingerprint: summary["p50_price"]
        for fingerprint, summary in price_summary_rows.items()
    }
    green_rank_map = _build_rank_map(green_percentages_by_fingerprint, higher_is_better=True)
    flood_rank_map = _build_rank_map(flood_percentages_by_fingerprint, higher_is_better=False)
    safety_rank_map = _build_rank_map(safety_density_by_fingerprint, higher_is_better=False)
    price_rank_map = _build_rank_map(price_p50_by_fingerprint, higher_is_better=False)
    for row in rows:
        state = str(row["state"])
        if state == "complete":
            completed_count += 1

        fingerprint = str(row["fingerprint"])
        badges = _normalize_badges_payload(row["badges"]) or {}
        if green_enabled and row["green_area_m2"] is not None:
            badges["green_badge"] = build_metric_badge(float(row["green_area_m2"] or 0.0), green_peers)
        else:
            badges.pop("green_badge", None)

        zones.append(
            {
                "id": row["id"],
                "journey_id": row["journey_id"],
                "transport_point_id": row["transport_point_id"],
                "fingerprint": fingerprint,
                "state": state,
                "is_circle_fallback": bool(row["is_circle_fallback"]),
                "travel_time_minutes": row["travel_time_minutes"],
                "walk_distance_meters": row["walk_distance_meters"],
                "isochrone_geom": row["isochrone_geom"],
                "green_area_m2": row["green_area_m2"],
                "green_vegetation_level": green_vegetation_level if green_enabled else None,
                "green_vegetation_label": green_vegetation_label,
                "flood_area_m2": row["flood_area_m2"],
                "safety_incidents_count": row["safety_incidents_count"],
                "poi_counts": row["poi_counts"],
                "poi_points": row["poi_points"],
                "badges": badges or None,
                "journey_rankings": {
                    "safety": safety_rank_map.get(fingerprint),
                    "green": green_rank_map.get(fingerprint),
                    "flood": flood_rank_map.get(fingerprint),
                    "price": price_rank_map.get(fingerprint),
                },
                "price_summary": {
                    "p50_price": price_summary_rows.get(fingerprint, {}).get("p50_price"),
                    "active_listing_count": int(price_summary_rows.get(fingerprint, {}).get("active_listing_count") or 0),
                },
                "badges_provisional": bool(row["badges_provisional"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )

    return ZoneListResponse(
        zones=zones,
        total_count=len(zones),
        completed_count=completed_count,
    )


async def list_zone_safety_incidents_for_journey(
    journey_id: UUID,
    zone_fingerprint: str,
) -> ZoneSafetyIncidentCollectionRead:
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                """
                SELECT
                    psi.id,
                    psi.occurred_at,
                    psi.category,
                    ST_X(psi.location) AS lon,
                    ST_Y(psi.location) AS lat,
                    z.fingerprint AS zone_fingerprint
                FROM journey_zones jz
                JOIN zones z ON z.id = jz.zone_id
                JOIN public_safety_incidents psi
                    ON z.isochrone_geom IS NOT NULL
                    AND psi.location IS NOT NULL
                    AND ST_Within(psi.location, z.isochrone_geom)
                WHERE jz.journey_id = :journey_id
                  AND z.fingerprint = :zone_fingerprint
                ORDER BY psi.occurred_at DESC NULLS LAST, psi.id ASC
                """
            ),
            {"journey_id": journey_id, "zone_fingerprint": zone_fingerprint},
        )
        rows = result.mappings().all()

    features = []
    for row in rows:
        crime_group, crime_group_label = classify_public_safety_group(row.get("category"))
        lon = row.get("lon")
        lat = row.get("lat")
        if lon is None or lat is None:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(lon), float(lat)],
                },
                "properties": {
                    "id": row["id"],
                    "zone_fingerprint": row["zone_fingerprint"],
                    "crime_group": crime_group,
                    "crime_group_label": crime_group_label,
                    "crime_type": row.get("category"),
                    "occurred_at": row.get("occurred_at"),
                },
            }
        )

    return ZoneSafetyIncidentCollectionRead(features=features)


@router.post("", response_model=JourneyRead, status_code=status.HTTP_201_CREATED)
async def create_journey_endpoint(
    payload: JourneyCreate,
    response: Response,
    auth_context=Depends(get_optional_auth_context),
) -> JourneyRead:
    if payload.input_snapshot:
        await _enforce_snapshot_customization(payload.input_snapshot, auth_context)
    session_id = auth_context.anonymous_session_id or generate_anonymous_session_id()
    if auth_context.user is not None:
        journey = await create_journey(payload, user_id=auth_context.user.id)
    else:
        journey = await create_journey(payload, anonymous_session_id=session_id)
    if auth_context.user is None and auth_context.anonymous_session_id is None:
        response.set_cookie(
            key=ANONYMOUS_SESSION_COOKIE,
            value=session_id,
            httponly=True,
            samesite="lax",
        )
    return journey


@router.get("/{journey_id}", response_model=JourneyRead)
async def get_journey_endpoint(journey_id: UUID, auth_context=Depends(get_optional_auth_context)) -> JourneyRead:
    return await _get_accessible_journey_or_404(journey_id, auth_context)


@router.patch("/{journey_id}", response_model=JourneyRead)
async def update_journey_endpoint(
    journey_id: UUID,
    payload: JourneyUpdate,
    auth_context=Depends(get_optional_auth_context),
) -> JourneyRead:
    await _get_accessible_journey_or_404(journey_id, auth_context)
    if payload.input_snapshot:
        await _enforce_snapshot_customization(payload.input_snapshot, auth_context)
    if payload.selected_zone_id is not None:
        await _enforce_zone_selection_policy(journey_id, payload.selected_zone_id, auth_context)
    journey = await update_journey(journey_id, payload)
    if journey is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Journey not found")
    return journey


@router.delete("/{journey_id}", response_model=JourneyRead)
async def delete_journey_endpoint(journey_id: UUID, auth_context=Depends(get_optional_auth_context)) -> JourneyRead:
    await _get_accessible_journey_or_404(journey_id, auth_context)
    journey = await expire_journey(journey_id)
    if journey is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Journey not found")
    return journey


@router.get("/{journey_id}/transport-points", response_model=list[TransportPointRead])
async def list_transport_points_endpoint(
    journey_id: UUID,
    auth_context=Depends(get_optional_auth_context),
) -> list[TransportPointRead]:
    await _get_accessible_journey_or_404(journey_id, auth_context)
    return await list_transport_points_for_journey(journey_id)


@router.get("/{journey_id}/zones", response_model=ZoneListResponse)
async def list_zones_endpoint(journey_id: UUID, auth_context=Depends(get_optional_auth_context)) -> ZoneListResponse:
    await _get_accessible_journey_or_404(journey_id, auth_context)
    return await list_zones_for_journey(journey_id)


@router.get(
    "/{journey_id}/zones/{zone_fingerprint}/safety-incidents",
    response_model=ZoneSafetyIncidentCollectionRead,
)
async def list_zone_safety_incidents_endpoint(
    journey_id: UUID,
    zone_fingerprint: str,
    auth_context=Depends(get_optional_auth_context),
) -> ZoneSafetyIncidentCollectionRead:
    await _get_accessible_journey_or_404(journey_id, auth_context)
    return await list_zone_safety_incidents_for_journey(journey_id, zone_fingerprint)


@router.get(
    "/{journey_id}/zones/{zone_fingerprint}/dashboard-analytics",
    response_model=ZoneDashboardAnalyticsRead,
)
async def get_zone_dashboard_analytics_endpoint(
    journey_id: UUID,
    zone_fingerprint: str,
    property_id: UUID | None = None,
    neighborhood_name: str | None = None,
    city_name: str | None = None,
    page: str | None = None,
    search_type: str = "rent",
    usage_type: str = "all",
    spatial_scope: str = "all",
    address_scope: str = "all_addresses",
    min_price: float | None = None,
    max_price: float | None = None,
    min_size: float | None = None,
    max_size: float | None = None,
    auth_context=Depends(get_optional_auth_context),
) -> ZoneDashboardAnalyticsRead:
    await _get_accessible_journey_or_404(journey_id, auth_context)

    if usage_type not in {"all", "residential", "commercial"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="usage_type deve ser 'all', 'residential' ou 'commercial'")
    if spatial_scope not in {"all", "inside_zone"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="spatial_scope deve ser 'all' ou 'inside_zone'")
    if address_scope not in {"all_addresses", "selected_address"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="address_scope deve ser 'all_addresses' ou 'selected_address'")
    if page is not None and page not in {"preco", "seguranca", "ambiente"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="page deve ser 'preco', 'seguranca' ou 'ambiente'")

    try:
        payload = await fetch_zone_dashboard_analytics(
            journey_id=journey_id,
            zone_fingerprint=zone_fingerprint,
            property_id=property_id,
            neighborhood_name=neighborhood_name,
            city_name=city_name,
            page=page,
            search_type=search_type,
            usage_type=usage_type,
            spatial_scope=spatial_scope,
            address_scope=address_scope,
            min_price=min_price,
            max_price=max_price,
            min_size=min_size,
            max_size=max_size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return ZoneDashboardAnalyticsRead.model_validate(payload)


@router.get(
    "/{journey_id}/zones/{zone_fingerprint}/favorite-analytics",
    response_model=ZoneFavoriteAnalyticsRead,
)
async def get_zone_favorite_analytics_endpoint(
    journey_id: UUID,
    zone_fingerprint: str,
    search_type: str = "rent",
    usage_type: str = "all",
    auth_context=Depends(get_optional_auth_context),
) -> ZoneFavoriteAnalyticsRead:
    await _get_accessible_journey_or_404(journey_id, auth_context)

    if usage_type not in {"all", "residential", "commercial"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="usage_type deve ser 'all', 'residential' ou 'commercial'")

    try:
        payload = await fetch_zone_favorite_analytics(
            journey_id=journey_id,
            zone_fingerprint=zone_fingerprint,
            search_type=search_type,
            usage_type=usage_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return ZoneFavoriteAnalyticsRead.model_validate(payload)
