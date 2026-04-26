from __future__ import annotations

import json
from uuid import UUID

from contracts import FavoriteListingCreate, FavoriteListingRead, FavoriteNoteUpdate, ListingCardRead
from core.db import get_engine
from sqlalchemy import text


def build_listing_key(listing: ListingCardRead) -> str:
    if listing.property_id is not None:
        return f"property:{listing.property_id}"
    if listing.platform and listing.platform_listing_id:
        return f"platform:{listing.platform}:{listing.platform_listing_id}"
    if listing.platform_listing_id:
        return f"listing:{listing.platform_listing_id}"
    raise ValueError("Nao foi possivel identificar o imovel para salvar o favorito.")


def _row_to_favorite(row) -> FavoriteListingRead:
    return FavoriteListingRead(
        listing_key=row["listing_key"],
        journey_id=row["journey_id"],
        zone_fingerprint=row["zone_fingerprint"],
        search_type=row["search_type"],
        usage_type=row["usage_type"],
        saved_at=row["saved_at"],
        listing=ListingCardRead.model_validate(row["listing_payload"]),
        note=row["note"] if "note" in row.keys() else None,
    )


async def list_user_favorites(user_id: UUID) -> list[FavoriteListingRead]:
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                """
                SELECT listing_key, journey_id, zone_fingerprint, search_type, usage_type, saved_at, listing_payload, note
                FROM user_listing_favorites
                WHERE user_id = :user_id
                ORDER BY saved_at DESC
                """
            ),
            {"user_id": user_id},
        )
        rows = result.mappings().all()
    return [_row_to_favorite(row) for row in rows]


async def upsert_user_favorite(user_id: UUID, payload: FavoriteListingCreate) -> FavoriteListingRead:
    listing_key = build_listing_key(payload.listing)
    listing_payload = json.dumps(payload.listing.model_dump(mode="json"), separators=(",", ":"))

    engine = get_engine()
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                INSERT INTO user_listing_favorites (
                    user_id,
                    listing_key,
                    journey_id,
                    zone_fingerprint,
                    search_type,
                    usage_type,
                    listing_payload
                )
                VALUES (
                    :user_id,
                    :listing_key,
                    :journey_id,
                    :zone_fingerprint,
                    :search_type,
                    :usage_type,
                    CAST(:listing_payload AS JSONB)
                )
                ON CONFLICT (user_id, listing_key)
                DO UPDATE SET
                    journey_id = EXCLUDED.journey_id,
                    zone_fingerprint = EXCLUDED.zone_fingerprint,
                    search_type = EXCLUDED.search_type,
                    usage_type = EXCLUDED.usage_type,
                    listing_payload = EXCLUDED.listing_payload,
                    saved_at = now(),
                    updated_at = now()
                RETURNING listing_key, journey_id, zone_fingerprint, search_type, usage_type, saved_at, listing_payload, note
                """
            ),
            {
                "user_id": user_id,
                "listing_key": listing_key,
                "journey_id": payload.journey_id,
                "zone_fingerprint": payload.zone_fingerprint,
                "search_type": payload.search_type,
                "usage_type": payload.usage_type,
                "listing_payload": listing_payload,
            },
        )
        row = result.mappings().one()
    return _row_to_favorite(row)


async def update_user_favorite_note(user_id: UUID, listing_key: str, payload: FavoriteNoteUpdate) -> FavoriteListingRead | None:
    engine = get_engine()
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                UPDATE user_listing_favorites
                SET note = :note, updated_at = now()
                WHERE user_id = :user_id AND listing_key = :listing_key
                RETURNING listing_key, journey_id, zone_fingerprint, search_type, usage_type, saved_at, listing_payload, note
                """
            ),
            {"user_id": user_id, "listing_key": listing_key, "note": payload.note},
        )
        row = result.mappings().first()
    if row is None:
        return None
    return _row_to_favorite(row)


async def delete_user_favorite(user_id: UUID, listing_key: str) -> bool:
    engine = get_engine()
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                DELETE FROM user_listing_favorites
                WHERE user_id = :user_id
                  AND listing_key = :listing_key
                """
            ),
            {
                "user_id": user_id,
                "listing_key": listing_key,
            },
        )
    return (result.rowcount or 0) > 0