from __future__ import annotations

from api.routes.auth import get_optional_auth_context
from contracts import FavoriteZoneColorUpdate, FavoriteZoneCreate, FavoriteZoneNoteUpdate, FavoriteZoneRead, FavoriteZoneShareRead, FavoriteZoneShareSnapshotRead
from fastapi import APIRouter, Depends, HTTPException, Response, status
from modules.auth.service import get_accessible_journey
from modules.plans.service import assert_can_save_zone_with_plan, resolve_entitlements
from modules.zone_favorites.service import (
    build_zone_key,
    create_zone_favorite_share,
    delete_user_zone_favorite,
    get_zone_favorite_share_snapshot,
    list_user_zone_favorites,
    revoke_zone_favorite_shares,
    update_user_zone_favorite_color,
    update_user_zone_favorite_note,
    upsert_user_zone_favorite,
)

router = APIRouter(prefix="/zone-favorites", tags=["zone-favorites"])
alias_router = APIRouter(prefix="/favorites/zones", tags=["zone-favorites"])
public_router = APIRouter(prefix="/zone-shares", tags=["zone-shares"])


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
    resolved = await resolve_entitlements(user.id)
    retention_days = resolved.entitlements.retention_days
    return await list_user_zone_favorites(user.id, retention_days=retention_days)


@router.post("", response_model=FavoriteZoneRead)
async def save_zone_favorite_endpoint(
    payload: FavoriteZoneCreate,
    auth_context=Depends(get_optional_auth_context),
) -> FavoriteZoneRead:
    user = _require_authenticated_user(auth_context)
    journey = await get_accessible_journey(payload.journey_id, auth_context)
    if journey is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Journey not found")
    resolved = await resolve_entitlements(user.id)
    zone_key = build_zone_key(payload.journey_id, payload.zone_fingerprint)
    await assert_can_save_zone_with_plan(user.id, resolved, zone_key=zone_key)
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


@alias_router.patch("/{zone_key}/color", response_model=FavoriteZoneRead)
@router.patch("/{zone_key}/color", response_model=FavoriteZoneRead)
async def update_zone_favorite_color_endpoint(
    zone_key: str,
    payload: FavoriteZoneColorUpdate,
    auth_context=Depends(get_optional_auth_context),
) -> FavoriteZoneRead:
    user = _require_authenticated_user(auth_context)
    result = await update_user_zone_favorite_color(user.id, zone_key, payload)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zona salva não encontrada.")
    return result


@alias_router.post("/{zone_key}/share", response_model=FavoriteZoneShareRead)
@router.post("/{zone_key}/share", response_model=FavoriteZoneShareRead)
async def create_zone_favorite_share_endpoint(
    zone_key: str,
    auth_context=Depends(get_optional_auth_context),
) -> FavoriteZoneShareRead:
    user = _require_authenticated_user(auth_context)
    share = await create_zone_favorite_share(user.id, zone_key)
    if share is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zona salva não encontrada.")
    return share


@alias_router.delete("/{zone_key}/share", status_code=status.HTTP_204_NO_CONTENT)
@router.delete("/{zone_key}/share", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_zone_favorite_share_endpoint(
    zone_key: str,
    auth_context=Depends(get_optional_auth_context),
) -> Response:
    user = _require_authenticated_user(auth_context)
    await revoke_zone_favorite_shares(user.id, zone_key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{zone_key}")
async def delete_zone_favorite_endpoint(
    zone_key: str,
    auth_context=Depends(get_optional_auth_context),
) -> dict[str, str]:
    user = _require_authenticated_user(auth_context)
    await delete_user_zone_favorite(user.id, zone_key)
    return {"message": "ok"}


@public_router.get("/{token}", response_model=FavoriteZoneShareSnapshotRead)
async def get_zone_favorite_share_endpoint(token: str) -> FavoriteZoneShareSnapshotRead:
    snapshot = await get_zone_favorite_share_snapshot(token)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compartilhamento não encontrado.")
    return snapshot
