from __future__ import annotations

from typing import Any
from uuid import UUID

from contracts import (
    JourneyCreate,
    JourneyRead,
    JourneyUpdate,
    TransportPointRead,
    ZoneListResponse,
)
from core.container import get_container
from core.db import get_engine
from fastapi import APIRouter, Cookie, HTTPException, Response, status
from modules.journeys.service import (
    ANONYMOUS_SESSION_COOKIE,
    create_journey,
    expire_journey,
    generate_anonymous_session_id,
    get_journey,
    update_journey,
)
from sqlalchemy import text

router = APIRouter(prefix="/journeys", tags=["journeys"])


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


async def list_transport_points_for_journey(journey_id: UUID) -> list[TransportPointRead]:
    transport_service = get_container().transport_service()
    return await transport_service.list_transport_points_for_journey(journey_id)


async def list_zones_for_journey(journey_id: UUID) -> ZoneListResponse:
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                """
                SELECT
                    z.id,
                    jz.journey_id,
                    z.transport_point_id,
                    z.fingerprint,
                    z.state,
                    z.max_time_minutes AS travel_time_minutes,
                    tp.walk_distance_m AS walk_distance_meters,
                    ST_AsGeoJSON(z.isochrone_geom)::JSONB AS isochrone_geom,
                    z.green_area_m2,
                    z.flood_area_m2,
                    z.safety_incidents_count,
                    z.poi_counts,
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

    zones = []
    completed_count = 0
    for row in rows:
        state = str(row["state"])
        if state == "complete":
            completed_count += 1

        zones.append(
            {
                "id": row["id"],
                "journey_id": row["journey_id"],
                "transport_point_id": row["transport_point_id"],
                "fingerprint": row["fingerprint"],
                "state": state,
                "travel_time_minutes": row["travel_time_minutes"],
                "walk_distance_meters": row["walk_distance_meters"],
                "isochrone_geom": row["isochrone_geom"],
                "green_area_m2": row["green_area_m2"],
                "flood_area_m2": row["flood_area_m2"],
                "safety_incidents_count": row["safety_incidents_count"],
                "poi_counts": row["poi_counts"],
                "badges": _normalize_badges_payload(row["badges"]),
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


@router.post("", response_model=JourneyRead, status_code=status.HTTP_201_CREATED)
async def create_journey_endpoint(
    payload: JourneyCreate,
    response: Response,
    anonymous_session_id: str | None = Cookie(default=None),
) -> JourneyRead:
    session_id = anonymous_session_id or generate_anonymous_session_id()
    journey = await create_journey(payload, anonymous_session_id=session_id)
    response.set_cookie(
        key=ANONYMOUS_SESSION_COOKIE,
        value=session_id,
        httponly=True,
        samesite="lax",
    )
    return journey


@router.get("/{journey_id}", response_model=JourneyRead)
async def get_journey_endpoint(journey_id: UUID) -> JourneyRead:
    journey = await get_journey(journey_id)
    if journey is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Journey not found")
    return journey


@router.patch("/{journey_id}", response_model=JourneyRead)
async def update_journey_endpoint(journey_id: UUID, payload: JourneyUpdate) -> JourneyRead:
    journey = await update_journey(journey_id, payload)
    if journey is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Journey not found")
    return journey


@router.delete("/{journey_id}", response_model=JourneyRead)
async def delete_journey_endpoint(journey_id: UUID) -> JourneyRead:
    journey = await expire_journey(journey_id)
    if journey is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Journey not found")
    return journey


@router.get("/{journey_id}/transport-points", response_model=list[TransportPointRead])
async def list_transport_points_endpoint(journey_id: UUID) -> list[TransportPointRead]:
    journey = await get_journey(journey_id)
    if journey is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Journey not found")
    return await list_transport_points_for_journey(journey_id)


@router.get("/{journey_id}/zones", response_model=ZoneListResponse)
async def list_zones_endpoint(journey_id: UUID) -> ZoneListResponse:
    journey = await get_journey(journey_id)
    if journey is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Journey not found")
    return await list_zones_for_journey(journey_id)
