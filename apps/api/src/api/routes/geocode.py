from __future__ import annotations

from typing import Any

from core.config import get_settings
from fastapi import APIRouter, Cookie, HTTPException, Response, status
from modules.geocoding.geocoding_service import geocode
from modules.journeys.service import ANONYMOUS_SESSION_COOKIE, generate_anonymous_session_id
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api", tags=["geocoding"])


class GeocodeRequest(BaseModel):
    q: str = Field(..., min_length=1, max_length=300)


class GeocodeResponse(BaseModel):
    suggestions: list[dict[str, Any]]
    cache_hit: bool


@router.post("/geocode", response_model=GeocodeResponse)
async def geocode_endpoint(
    payload: GeocodeRequest,
    response: Response,
    anonymous_session_id: str | None = Cookie(default=None),
) -> GeocodeResponse:
    session_id = anonymous_session_id or generate_anonymous_session_id()
    if anonymous_session_id is None:
        response.set_cookie(
            key=ANONYMOUS_SESSION_COOKIE,
            value=session_id,
            httponly=True,
            samesite="lax",
        )
    settings = get_settings()
    try:
        result = await geocode(
            q=payload.q,
            session_id=session_id,
            mapbox_token=settings.mapbox_access_token,
        )
    except ValueError as exc:
        if "rate_limit" in str(exc):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded: 30 geocode requests per minute per session.",
            ) from exc
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Geocoding service temporarily unavailable.",
        ) from exc

    return GeocodeResponse(
        suggestions=result["suggestions"],
        cache_hit=result["cache_hit"],
    )
