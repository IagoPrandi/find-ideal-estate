from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from contracts import JourneyCreate, JourneyRead, JourneyReferencePoint, JourneyState, JourneyUpdate
from core.db import get_engine
from sqlalchemy import text
from sqlalchemy.engine import RowMapping

ANONYMOUS_SESSION_COOKIE = "anonymous_session_id"
ANONYMOUS_SESSION_TTL_DAYS = 7

_JOURNEY_SELECT = """
SELECT
    id,
    user_id,
    anonymous_session_id,
    state,
    input_snapshot,
    selected_transport_point_id,
    selected_zone_id,
    selected_property_id,
    last_completed_step,
    secondary_reference_label,
    CASE
        WHEN secondary_reference_point IS NULL THEN NULL
        ELSE ST_Y(secondary_reference_point)
    END AS secondary_reference_lat,
    CASE
        WHEN secondary_reference_point IS NULL THEN NULL
        ELSE ST_X(secondary_reference_point)
    END AS secondary_reference_lon,
    created_at,
    updated_at,
    expires_at
FROM journeys
WHERE id = :journey_id
"""


def generate_anonymous_session_id() -> str:
    return secrets.token_urlsafe(32)


def default_expiration() -> datetime:
    return datetime.now(tz=timezone.utc) + timedelta(days=ANONYMOUS_SESSION_TTL_DAYS)


def _point_to_fields(row: RowMapping) -> JourneyReferencePoint | None:
    lat = row["secondary_reference_lat"]
    lon = row["secondary_reference_lon"]
    if lat is None or lon is None:
        return None
    return JourneyReferencePoint(lat=lat, lon=lon)


def _row_to_journey(row: RowMapping) -> JourneyRead:
    return JourneyRead(
        id=row["id"],
        user_id=row["user_id"],
        anonymous_session_id=row["anonymous_session_id"],
        state=row["state"],
        input_snapshot=row["input_snapshot"],
        selected_transport_point_id=row["selected_transport_point_id"],
        selected_zone_id=row["selected_zone_id"],
        selected_property_id=row["selected_property_id"],
        last_completed_step=row["last_completed_step"],
        secondary_reference_label=row["secondary_reference_label"],
        secondary_reference_point=_point_to_fields(row),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        expires_at=row["expires_at"],
    )


async def get_journey(journey_id: UUID) -> JourneyRead | None:
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(text(_JOURNEY_SELECT), {"journey_id": journey_id})
        row = result.mappings().first()
    if row is None:
        return None
    return _row_to_journey(row)


async def create_journey(payload: JourneyCreate, anonymous_session_id: str | None = None) -> JourneyRead:
    session_id = anonymous_session_id or generate_anonymous_session_id()
    reference_point = payload.secondary_reference_point
    params = {
        "anonymous_session_id": session_id,
        "input_snapshot": json.dumps(payload.input_snapshot) if payload.input_snapshot is not None else None,
        "secondary_reference_label": payload.secondary_reference_label,
        "expires_at": default_expiration(),
    }
    insert_sql = """
        INSERT INTO journeys (
            anonymous_session_id,
            state,
            input_snapshot,
            secondary_reference_label,
            expires_at
        )
        VALUES (
            :anonymous_session_id,
            :state,
            CAST(:input_snapshot AS JSONB),
            :secondary_reference_label,
            :expires_at
        )
        RETURNING id
    """
    if reference_point is not None:
        params["secondary_reference_lat"] = reference_point.lat
        params["secondary_reference_lon"] = reference_point.lon
        insert_sql = """
            INSERT INTO journeys (
                anonymous_session_id,
                state,
                input_snapshot,
                secondary_reference_label,
                secondary_reference_point,
                expires_at
            )
            VALUES (
                :anonymous_session_id,
                :state,
                CAST(:input_snapshot AS JSONB),
                :secondary_reference_label,
                ST_SetSRID(
                    ST_MakePoint(
                        CAST(:secondary_reference_lon AS DOUBLE PRECISION),
                        CAST(:secondary_reference_lat AS DOUBLE PRECISION)
                    ),
                    4326
                ),
                :expires_at
            )
            RETURNING id
        """
    engine = get_engine()
    async with engine.begin() as conn:
        result = await conn.execute(
            text(insert_sql),
            {**params, "state": JourneyState.DRAFT.value},
        )
        journey_id = result.scalar_one()
    journey = await get_journey(journey_id)
    if journey is None:
        raise RuntimeError("Journey creation did not persist")
    return journey


async def update_journey(journey_id: UUID, payload: JourneyUpdate) -> JourneyRead | None:
    updates = payload.model_dump(mode="python", exclude_unset=True)
    if not updates:
        return await get_journey(journey_id)

    set_clauses: list[str] = []
    params: dict[str, Any] = {"journey_id": journey_id}

    if "state" in updates:
        set_clauses.append("state = :state")
        params["state"] = updates["state"].value if hasattr(updates["state"], "value") else updates["state"]

    if "input_snapshot" in updates:
        set_clauses.append("input_snapshot = CAST(:input_snapshot AS JSONB)")
        params["input_snapshot"] = json.dumps(updates["input_snapshot"]) if updates["input_snapshot"] is not None else None

    for field in ("selected_transport_point_id", "selected_zone_id", "selected_property_id", "last_completed_step", "secondary_reference_label"):
        if field in updates:
            set_clauses.append(f"{field} = :{field}")
            params[field] = updates[field]

    if "secondary_reference_point" in updates:
        point = updates["secondary_reference_point"]
        if point is None:
            set_clauses.append("secondary_reference_point = NULL")
        else:
            set_clauses.append(
                "secondary_reference_point = ST_SetSRID("
                "ST_MakePoint(CAST(:secondary_reference_lon AS DOUBLE PRECISION), CAST(:secondary_reference_lat AS DOUBLE PRECISION)), "
                "4326)"
            )
            params["secondary_reference_lat"] = point.lat
            params["secondary_reference_lon"] = point.lon

    set_clauses.append("updated_at = now()")
    engine = get_engine()
    async with engine.begin() as conn:
        result = await conn.execute(
            text(f"UPDATE journeys SET {', '.join(set_clauses)} WHERE id = :journey_id RETURNING id"),
            params,
        )
        row = result.first()
    if row is None:
        return None
    return await get_journey(journey_id)


async def expire_journey(journey_id: UUID) -> JourneyRead | None:
    engine = get_engine()
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                UPDATE journeys
                SET state = :state, updated_at = now(), expires_at = now()
                WHERE id = :journey_id
                RETURNING id
                """
            ),
            {"journey_id": journey_id, "state": JourneyState.EXPIRED.value},
        )
        row = result.first()
    if row is None:
        return None
    return await get_journey(journey_id)