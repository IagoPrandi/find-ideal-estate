from __future__ import annotations

from api.routes.auth import get_optional_auth_context
from contracts import FavoriteListingCreate, FavoriteListingRead
from fastapi import APIRouter, Depends, HTTPException, status
from modules.auth.service import get_accessible_journey
from modules.favorites.service import delete_user_favorite, list_user_favorites, upsert_user_favorite

router = APIRouter(prefix="/favorites", tags=["favorites"])


def _require_authenticated_user(auth_context):
    if auth_context.user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Faça login para salvar imóveis na sua conta.",
        )
    return auth_context.user


@router.get("", response_model=list[FavoriteListingRead])
async def list_favorites_endpoint(auth_context=Depends(get_optional_auth_context)) -> list[FavoriteListingRead]:
    user = _require_authenticated_user(auth_context)
    return await list_user_favorites(user.id)


@router.post("", response_model=FavoriteListingRead)
async def save_favorite_endpoint(
    payload: FavoriteListingCreate,
    auth_context=Depends(get_optional_auth_context),
) -> FavoriteListingRead:
    user = _require_authenticated_user(auth_context)
    journey = await get_accessible_journey(payload.journey_id, auth_context)
    if journey is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Journey not found")
    return await upsert_user_favorite(user.id, payload)


@router.delete("/{listing_key}")
async def delete_favorite_endpoint(listing_key: str, auth_context=Depends(get_optional_auth_context)) -> dict[str, str]:
    user = _require_authenticated_user(auth_context)
    await delete_user_favorite(user.id, listing_key)
    return {"message": "ok"}