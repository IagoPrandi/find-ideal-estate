from __future__ import annotations

from uuid import UUID

from contracts import JourneyCreate, JourneyRead, JourneyUpdate
from fastapi import APIRouter, Cookie, HTTPException, Response, status
from modules.journeys.service import ANONYMOUS_SESSION_COOKIE, create_journey, expire_journey, generate_anonymous_session_id, get_journey, update_journey

router = APIRouter(prefix="/journeys", tags=["journeys"])


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