from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from contracts import FavoriteListingCreate, FavoriteListingRead, ListingCardRead, ManualFavoriteCreate
from core.db import get_engine
from modules.favorites.service import upsert_user_favorite
from sqlalchemy import text

_PLATFORM_HOST_MAP = (
    ("quintoandar", ("quintoandar.com.br",)),
    ("vivareal", ("vivareal.com.br", "vivareal.com",)),
    ("zapimoveis", ("zapimoveis.com.br", "zap.com.br",)),
)


def _detect_platform(host: str) -> str:
    host = host.lower().lstrip(".")
    host = host[4:] if host.startswith("www.") else host
    for canonical, patterns in _PLATFORM_HOST_MAP:
        for pattern in patterns:
            if host == pattern or host.endswith(f".{pattern}"):
                return canonical
    return "other"


_LISTING_ID_PATTERNS = {
    "quintoandar": re.compile(r"/imovel/(\d+)"),
    "vivareal": re.compile(r"-(\d{6,})(?:/|$)"),
    "zapimoveis": re.compile(r"-(\d{6,})(?:/|$)"),
}


def _extract_platform_listing_id(platform: str, parsed_path: str, full_url: str) -> str:
    pattern = _LISTING_ID_PATTERNS.get(platform)
    if pattern is not None:
        match = pattern.search(parsed_path)
        if match:
            return match.group(1)
    # Fallback: hash da URL estável para plataformas desconhecidas ou padrões novos.
    return "manual-" + hashlib.sha1(full_url.encode("utf-8")).hexdigest()[:16]


def _build_listing_card(
    *,
    platform: str,
    platform_listing_id: str,
    url: str,
    property_id: UUID,
    search_type: str,
    usage_type: str,
) -> ListingCardRead:
    return ListingCardRead.model_validate(
        {
            "property_id": str(property_id),
            "address_normalized": "Link enviado manualmente",
            "neighborhood_name": None,
            "city_name": None,
            "area_m2": None,
            "bedrooms": None,
            "bathrooms": None,
            "parking": None,
            "usage_type": usage_type,
            "platform": platform,
            "platform_listing_id": platform_listing_id,
            "url": url,
            "image_url": None,
            "lat": None,
            "lon": None,
            "has_coordinates": False,
            "inside_zone": False,
            "platforms_available": [platform],
            "platform_variants": [
                {
                    "platform": platform,
                    "platform_listing_id": platform_listing_id,
                    "url": url,
                    "image_url": None,
                    "current_best_price": None,
                    "condo_fee": None,
                    "iptu": None,
                    "observed_at": None,
                }
            ],
            "current_best_price": None,
            "current_unit_price": None,
            "neighborhood_median_unit_price": None,
            "current_vs_neighborhood_pct": None,
            "condo_fee": None,
            "iptu": None,
            "second_best_price": None,
            "duplication_badge": "manual",
            "observed_at": None,
            "price": None,
        }
    )


async def _persist_manual_listing(
    *,
    platform: str,
    platform_listing_id: str,
    url: str,
    search_type: str,
    usage_type: str,
) -> UUID:
    """Upsert property + listing_ad + snapshot for a manually submitted URL."""
    fingerprint = hashlib.sha256(f"manual|{platform}|{platform_listing_id}|{url}".encode("utf-8")).hexdigest()
    engine = get_engine()
    async with engine.begin() as conn:
        property_row = await conn.execute(
            text(
                """
                INSERT INTO properties (
                    address_normalized,
                    location,
                    usage_type,
                    usage_type_inferred,
                    fingerprint
                )
                VALUES (
                    :address_normalized,
                    NULL,
                    :usage_type,
                    TRUE,
                    :fingerprint
                )
                ON CONFLICT (fingerprint)
                DO UPDATE SET usage_type = COALESCE(properties.usage_type, EXCLUDED.usage_type)
                RETURNING id
                """
            ),
            {
                "address_normalized": "Link enviado manualmente",
                "usage_type": usage_type if usage_type in ("residential", "commercial") else "residential",
                "fingerprint": fingerprint,
            },
        )
        property_id = property_row.scalar_one()

        ad_row = await conn.execute(
            text(
                """
                INSERT INTO listing_ads (
                    property_id,
                    platform,
                    platform_listing_id,
                    url,
                    advertised_usage_type,
                    usage_type,
                    usage_type_inferred,
                    is_active,
                    last_seen_at
                )
                VALUES (
                    :property_id,
                    :platform,
                    :platform_listing_id,
                    :url,
                    :advertised_usage_type,
                    :usage_type,
                    TRUE,
                    TRUE,
                    now()
                )
                ON CONFLICT (platform, platform_listing_id)
                DO UPDATE SET
                    url = EXCLUDED.url,
                    is_active = TRUE,
                    last_seen_at = now(),
                    advertised_usage_type = COALESCE(listing_ads.advertised_usage_type, EXCLUDED.advertised_usage_type)
                RETURNING id
                """
            ),
            {
                "property_id": property_id,
                "platform": platform,
                "platform_listing_id": platform_listing_id,
                "url": url,
                "advertised_usage_type": search_type if search_type in ("rent", "sale") else "rent",
                "usage_type": usage_type if usage_type in ("residential", "commercial") else "residential",
            },
        )
        listing_ad_id = ad_row.scalar_one()

        await conn.execute(
            text(
                """
                INSERT INTO listing_snapshots (
                    listing_ad_id,
                    observed_at,
                    availability_state,
                    raw_payload
                )
                VALUES (
                    :listing_ad_id,
                    now(),
                    'active',
                    CAST(:raw_payload AS JSONB)
                )
                """
            ),
            {
                "listing_ad_id": listing_ad_id,
                "raw_payload": '{"source":"manual","url":' + _json_string(url) + "}",
            },
        )

    return property_id


def _json_string(value: str) -> str:
    import json

    return json.dumps(value)


async def upsert_manual_listing_favorite(
    user_id: UUID,
    payload: ManualFavoriteCreate,
) -> FavoriteListingRead:
    url = (payload.url or "").strip()
    if not url:
        raise ValueError("url vazia")

    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("URL inválida")

    platform = _detect_platform(parsed.netloc)
    platform_listing_id = _extract_platform_listing_id(platform, parsed.path or "", url)

    property_id = await _persist_manual_listing(
        platform=platform,
        platform_listing_id=platform_listing_id,
        url=url,
        search_type=payload.search_type,
        usage_type=payload.usage_type,
    )

    listing_card = _build_listing_card(
        platform=platform,
        platform_listing_id=platform_listing_id,
        url=url,
        property_id=property_id,
        search_type=payload.search_type,
        usage_type=payload.usage_type,
    )

    journey_id = payload.journey_id
    zone_fingerprint = payload.zone_fingerprint or ""

    if journey_id is None:
        # Associa o favorito a uma jornada qualquer do próprio usuário (mais recente),
        # evitando quebrar o schema que exige journey_id não-nulo.
        engine = get_engine()
        async with engine.connect() as conn:
            row = await conn.execute(
                text(
                    """
                    SELECT id FROM journeys
                    WHERE user_id = :user_id
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                ),
                {"user_id": user_id},
            )
            journey_id = row.scalar_one_or_none()
        if journey_id is None:
            raise ValueError("Sem jornada associada para anexar o favorito manual")

    favorite_create = FavoriteListingCreate(
        journey_id=journey_id,
        zone_fingerprint=zone_fingerprint,
        search_type=payload.search_type,
        usage_type=payload.usage_type,
        listing=listing_card,
    )
    return await upsert_user_favorite(user_id, favorite_create)
