from __future__ import annotations

from api.routes.auth import get_optional_auth_context
from contracts import FavoriteZoneCreate, FavoriteZoneNoteUpdate, FavoriteZoneRead
from fastapi import APIRouter, Depends, HTTPException, status
from modules.auth.service import get_accessible_journey
from modules.zone_favorites.service import (
    delete_user_zone_favorite,
    list_user_zone_favorites,
    update_user_zone_favorite_note,
    upsert_user_zone_favorite,
)

router = APIRouter(prefix="/zone-favorites", tags=["zone-favorites"])


def _require_authenticated_user(auth_context):
    if auth_context.user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Faça login para salvar zonas na sua conta.",
        )
    return auth_context.user


@router.get("", response_model=list[FavoriteZoneRead])
async def list_zone_favorites_endpoint(
    auth_context=Depends(get_optional_auth_context),
) -> list[FavoriteZoneRead]:
    user = _require_authenticated_user(auth_context)
    return await list_user_zone_favorites(user.id)


@router.post("", response_model=FavoriteZoneRead)
async def save_zone_favorite_endpoint(
    payload: FavoriteZoneCreate,
    auth_context=Depends(get_optional_auth_context),
) -> FavoriteZoneRead:
    user = _require_authenticated_user(auth_context)
    journey = await get_accessible_journey(payload.journey_id, auth_context)
    if journey is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Journey not found")
    return await upsert_user_zone_favorite(user.id, payload)


@router.patch("/{zone_key}/note", response_model=FavoriteZoneRead)
async def update_zone_favorite_note_endpoint(
    zone_key: str,
    payload: FavoriteZoneNoteUpdate,
    auth_context=Depends(get_optional_auth_context),
) -> FavoriteZoneRead:
    user = _require_authenticated_user(auth_context)
    result = await update_user_zone_favorite_note(user.id, zone_key, payload)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zona salva não encontrada.")
    return result


@router.delete("/{zone_key}")
async def delete_zone_favorite_endpoint(
    zone_key: str,
    auth_context=Depends(get_optional_auth_context),
) -> dict[str, str]:
    user = _require_authenticated_user(auth_context)
    await delete_user_zone_favorite(user.id, zone_key)
    return {"message": "ok"}
