from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from contracts import AccountPlanRead, PlanEntitlementsRead, PlanRead, ResolvedEntitlements
from core.db import get_engine
from core.redis import get_redis
from modules.plans.exceptions import EntitlementExceeded, ViewWindowExpired
from modules.usage_restrictions.service import get_global_usage_restrictions_disabled
from sqlalchemy import text

_ENTITLEMENTS_CACHE_TTL = 60
_ENTITLEMENTS_CACHE_KEY = "entitlements:user:{user_id}"
_FREE_PLAN_SLUG = "free"
_ANONYMOUS_PLAN_SLUG = "anonymous"
_PROPRIETARIO_ROLE = "proprietario"
_PROPRIETARIO_PLAN_ID = UUID("00000000-0000-0000-0000-000000000099")

_PLAN_CAPS: dict[str, dict] = {
    "anonymous": {
        "max_transit_minutes_cap": None,
        "max_walk_minutes_cap": None,
        "max_car_minutes_cap": None,
        "max_zone_radius_m_cap": 500,
        "max_transport_radius_m_cap": None,
    },
    "free": {
        "max_transit_minutes_cap": None,
        "max_walk_minutes_cap": None,
        "max_car_minutes_cap": None,
        "max_zone_radius_m_cap": 500,
        "max_transport_radius_m_cap": None,
    },
    "basico": {
        "max_transit_minutes_cap": 20,
        "max_walk_minutes_cap": 15,
        "max_car_minutes_cap": 10,
        "max_zone_radius_m_cap": 500,
        "max_transport_radius_m_cap": None,
    },
    "pro": {
        "max_transit_minutes_cap": None,
        "max_walk_minutes_cap": None,
        "max_car_minutes_cap": None,
        "max_zone_radius_m_cap": 500,
        "max_transport_radius_m_cap": None,
    },
    "pro_max": {
        "max_transit_minutes_cap": None,
        "max_walk_minutes_cap": None,
        "max_car_minutes_cap": None,
        "max_zone_radius_m_cap": 500,
        "max_transport_radius_m_cap": None,
    },
}


def _proprietario_resolved_entitlements() -> ResolvedEntitlements:
    plan = PlanRead(
        id=_PROPRIETARIO_PLAN_ID,
        slug="proprietario",
        name="Proprietário",
        price_brl=None,
        monthly_credits=999999,
        is_paid=False,
        display_order=99,
    )
    entitlements = PlanEntitlementsRead(
        max_listing_favorites=None,
        max_zone_favorites=None,
        retention_days=365,
        can_customize_radius=True,
        can_customize_max_time=True,
        can_customize_distance=True,
        max_active_metrics=None,
        transport_line_policy="unlocked",
        zone_selection_policy="any",
        auto_refresh_policy="none",
        pro_max_refresh_max_zones=None,
        pro_max_refresh_max_listings=None,
        pro_max_refresh_cadence_days=None,
        pro_max_refresh_eligibility_days=None,
        rollover_percent=100,
        rollover_cycles=12,
        cycle_length_days=30,
        max_transit_minutes_cap=None,
        max_walk_minutes_cap=None,
        max_car_minutes_cap=None,
        max_zone_radius_m_cap=None,
        max_transport_radius_m_cap=None,
    )
    return ResolvedEntitlements(plan=plan, entitlements=entitlements)


async def _get_user_usage_access(user_id: UUID) -> tuple[str, bool]:
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                """
                SELECT
                    role,
                    COALESCE(usage_restrictions_disabled, false) AS usage_restrictions_disabled
                FROM users
                WHERE id = :user_id
                LIMIT 1
                """
            ),
            {"user_id": user_id},
        )
        row = result.mappings().first()
    if row is None:
        return "user", False
    return (row["role"] or "user"), bool(row["usage_restrictions_disabled"])


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _row_to_plan(row) -> PlanRead:
    return PlanRead(
        id=row["id"],
        slug=row["slug"],
        name=row["name"],
        price_brl=Decimal(str(row["price_brl"])) if row["price_brl"] is not None else None,
        monthly_credits=row["monthly_credits"],
        is_paid=row["is_paid"],
        display_order=row["display_order"],
    )


def _row_to_entitlements(row) -> PlanEntitlementsRead:
    caps = _PLAN_CAPS.get(row["slug"], {})
    return PlanEntitlementsRead(
        max_listing_favorites=row["max_listing_favorites"],
        max_zone_favorites=row["max_zone_favorites"],
        retention_days=row["retention_days"],
        can_customize_radius=row["can_customize_radius"],
        can_customize_max_time=row["can_customize_max_time"],
        can_customize_distance=row["can_customize_distance"],
        max_active_metrics=row["max_active_metrics"],
        transport_line_policy=row["transport_line_policy"],
        zone_selection_policy=row["zone_selection_policy"],
        auto_refresh_policy=row["auto_refresh_policy"],
        pro_max_refresh_max_zones=row["pro_max_refresh_max_zones"],
        pro_max_refresh_max_listings=row["pro_max_refresh_max_listings"],
        pro_max_refresh_cadence_days=row["pro_max_refresh_cadence_days"],
        pro_max_refresh_eligibility_days=row["pro_max_refresh_eligibility_days"],
        rollover_percent=row["rollover_percent"],
        rollover_cycles=row["rollover_cycles"],
        cycle_length_days=row["cycle_length_days"],
        max_transit_minutes_cap=caps.get("max_transit_minutes_cap"),
        max_walk_minutes_cap=caps.get("max_walk_minutes_cap"),
        max_car_minutes_cap=caps.get("max_car_minutes_cap"),
        max_zone_radius_m_cap=caps.get("max_zone_radius_m_cap"),
        max_transport_radius_m_cap=caps.get("max_transport_radius_m_cap"),
    )


async def get_plan_by_slug(slug: str) -> PlanRead | None:
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT id, slug, name, price_brl, monthly_credits, is_paid, display_order FROM plans WHERE slug = :slug AND is_active = true LIMIT 1"),
            {"slug": slug},
        )
        row = result.mappings().first()
    if row is None:
        return None
    return _row_to_plan(row)


async def list_plans() -> list[PlanRead]:
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT id, slug, name, price_brl, monthly_credits, is_paid, display_order FROM plans WHERE is_active = true AND slug != 'anonymous' ORDER BY display_order")
        )
        rows = result.mappings().all()
    return [_row_to_plan(r) for r in rows]


async def resolve_entitlements(user_id: UUID) -> ResolvedEntitlements:
    if await get_global_usage_restrictions_disabled():
        return _proprietario_resolved_entitlements()

    role, usage_restrictions_disabled = await _get_user_usage_access(user_id)
    if role == _PROPRIETARIO_ROLE or usage_restrictions_disabled:
        return _proprietario_resolved_entitlements()

    cache_key = _ENTITLEMENTS_CACHE_KEY.format(user_id=str(user_id))
    redis = get_redis()
    cached = await redis.get(cache_key)
    if cached:
        data = json.loads(cached)
        return ResolvedEntitlements.model_validate(data)

    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text("""
                SELECT
                    p.id, p.slug, p.name, p.price_brl, p.monthly_credits, p.is_paid, p.display_order,
                    pe.max_listing_favorites, pe.max_zone_favorites, pe.retention_days,
                    pe.can_customize_radius, pe.can_customize_max_time, pe.can_customize_distance,
                    pe.max_active_metrics,
                    pe.transport_line_policy, pe.zone_selection_policy,
                    pe.auto_refresh_policy,
                    pe.pro_max_refresh_max_zones, pe.pro_max_refresh_max_listings,
                    pe.pro_max_refresh_cadence_days, pe.pro_max_refresh_eligibility_days,
                    pe.rollover_percent, pe.rollover_cycles, pe.cycle_length_days
                FROM plan_activations pa
                JOIN plans p ON p.id = pa.plan_id
                JOIN plan_entitlements pe ON pe.plan_id = p.id
                WHERE pa.user_id = :user_id
                  AND pa.status = 'active'
                  AND pa.ends_at > now()
                ORDER BY p.display_order DESC
                LIMIT 1
            """),
            {"user_id": user_id},
        )
        row = result.mappings().first()

    if row is None:
        # fallback to free plan if no active activation (edge case)
        result2_engine = get_engine()
        async with result2_engine.connect() as conn2:
            result2 = await conn2.execute(
                text("""
                    SELECT
                        p.id, p.slug, p.name, p.price_brl, p.monthly_credits, p.is_paid, p.display_order,
                        pe.max_listing_favorites, pe.max_zone_favorites, pe.retention_days,
                        pe.can_customize_radius, pe.can_customize_max_time, pe.can_customize_distance,
                        pe.max_active_metrics,
                        pe.transport_line_policy, pe.zone_selection_policy,
                        pe.auto_refresh_policy,
                        pe.pro_max_refresh_max_zones, pe.pro_max_refresh_max_listings,
                        pe.pro_max_refresh_cadence_days, pe.pro_max_refresh_eligibility_days,
                        pe.rollover_percent, pe.rollover_cycles, pe.cycle_length_days
                    FROM plans p
                    JOIN plan_entitlements pe ON pe.plan_id = p.id
                    WHERE p.slug = :slug
                    LIMIT 1
                """),
                {"slug": _FREE_PLAN_SLUG},
            )
            row = result2.mappings().first()

    plan = _row_to_plan(row)
    entitlements = _row_to_entitlements(row)
    resolved = ResolvedEntitlements(plan=plan, entitlements=entitlements)

    await redis.set(cache_key, resolved.model_dump_json(), ex=_ENTITLEMENTS_CACHE_TTL)
    return resolved


async def invalidate_entitlements_cache(user_id: UUID) -> None:
    redis = get_redis()
    await redis.delete(_ENTITLEMENTS_CACHE_KEY.format(user_id=str(user_id)))


async def activate_plan_direct(user_id: UUID, plan_slug: str) -> None:
    """Directly activate a plan for a user without payment. Proprietário-only operation."""
    engine = get_engine()
    async with engine.begin() as conn:
        plan_result = await conn.execute(
            text("SELECT id, monthly_credits FROM plans WHERE slug = :slug AND is_active = true LIMIT 1"),
            {"slug": plan_slug},
        )
        plan_row = plan_result.mappings().first()
        if plan_row is None:
            raise ValueError(f"Plano '{plan_slug}' não encontrado.")

        plan_id = plan_row["id"]
        monthly_credits = plan_row["monthly_credits"]

        await conn.execute(
            text("""
                UPDATE plan_activations
                SET status = 'replaced', updated_at = now()
                WHERE user_id = :user_id AND status = 'active'
            """),
            {"user_id": user_id},
        )

        await conn.execute(
            text("""
                INSERT INTO plan_activations (user_id, plan_id, source_payment_id, status, started_at, ends_at)
                VALUES (:user_id, :plan_id, NULL, 'active', now(), now() + interval '30 days')
            """),
            {"user_id": user_id, "plan_id": plan_id},
        )

        await conn.execute(
            text("""
                INSERT INTO user_credits (user_id, plan_id, cycle_credits, monthly_quota, cycle_started_at, cycle_ends_at)
                VALUES (:user_id, :plan_id, :credits, :credits, now(), now() + interval '30 days')
                ON CONFLICT (user_id) DO UPDATE
                SET plan_id = :plan_id,
                    cycle_credits = :credits,
                    monthly_quota = :credits,
                    cycle_started_at = now(),
                    cycle_ends_at = now() + interval '30 days',
                    updated_at = now()
            """),
            {"user_id": user_id, "plan_id": plan_id, "credits": monthly_credits},
        )

    await invalidate_entitlements_cache(user_id)


async def count_listing_favorites(user_id: UUID) -> int:
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT COUNT(*) FROM user_listing_favorites WHERE user_id = :user_id"),
            {"user_id": user_id},
        )
        return int(result.scalar() or 0)


async def count_zone_favorites(user_id: UUID) -> int:
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT COUNT(*) FROM user_zone_favorites WHERE user_id = :user_id"),
            {"user_id": user_id},
        )
        return int(result.scalar() or 0)


async def listing_favorite_exists(user_id: UUID, listing_key: str) -> bool:
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT 1 FROM user_listing_favorites WHERE user_id = :user_id AND listing_key = :listing_key LIMIT 1"),
            {"user_id": user_id, "listing_key": listing_key},
        )
        return result.first() is not None


async def zone_favorite_exists(user_id: UUID, zone_key: str) -> bool:
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT 1 FROM user_zone_favorites WHERE user_id = :user_id AND zone_key = :zone_key LIMIT 1"),
            {"user_id": user_id, "zone_key": zone_key},
        )
        return result.first() is not None


async def assert_can_save_listing(user_id: UUID, entitlements: PlanEntitlementsRead) -> None:
    limit = entitlements.max_listing_favorites
    if limit is None:
        return
    current = await count_listing_favorites(user_id)
    if current >= limit:
        raise EntitlementExceeded(
            kind="max_listing_favorites",
            plan=entitlements.transport_line_policy,
            current=current,
            limit=limit,
        )


async def assert_can_save_listing_with_plan(
    user_id: UUID,
    resolved: ResolvedEntitlements,
    *,
    listing_key: str | None = None,
) -> None:
    limit = resolved.entitlements.max_listing_favorites
    if limit is None:
        return
    if listing_key is not None and await listing_favorite_exists(user_id, listing_key):
        return  # upsert de item já salvo — não consome cota
    current = await count_listing_favorites(user_id)
    if current >= limit:
        raise EntitlementExceeded(
            kind="max_listing_favorites",
            plan=resolved.plan.slug,
            current=current,
            limit=limit,
        )


async def assert_can_save_zone_with_plan(
    user_id: UUID,
    resolved: ResolvedEntitlements,
    *,
    zone_key: str | None = None,
) -> None:
    limit = resolved.entitlements.max_zone_favorites
    if limit is None:
        return
    if zone_key is not None and await zone_favorite_exists(user_id, zone_key):
        return  # upsert de zona já salva — não consome cota
    current = await count_zone_favorites(user_id)
    if current >= limit:
        raise EntitlementExceeded(
            kind="max_zone_favorites",
            plan=resolved.plan.slug,
            current=current,
            limit=limit,
        )


def assert_can_customize(field: str, resolved: ResolvedEntitlements) -> None:
    flag_map = {
        "radius": resolved.entitlements.can_customize_radius,
        "max_time": resolved.entitlements.can_customize_max_time,
        "distance": resolved.entitlements.can_customize_distance,
    }
    if field not in flag_map:
        return
    if not flag_map[field]:
        raise EntitlementExceeded(kind=f"customize_{field}", plan=resolved.plan.slug)


def assert_view_window_valid(view_state: str, plan_slug: str) -> None:
    if view_state == "expired_for_view":
        raise ViewWindowExpired(plan=plan_slug)


async def get_active_plan_activation(user_id: UUID) -> AccountPlanRead | None:
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text("""
                SELECT
                    p.id, p.slug, p.name, p.price_brl, p.monthly_credits, p.is_paid, p.display_order,
                    pe.max_listing_favorites, pe.max_zone_favorites, pe.retention_days,
                    pe.can_customize_radius, pe.can_customize_max_time, pe.can_customize_distance,
                    pe.max_active_metrics,
                    pe.transport_line_policy, pe.zone_selection_policy,
                    pe.auto_refresh_policy,
                    pe.pro_max_refresh_max_zones, pe.pro_max_refresh_max_listings,
                    pe.pro_max_refresh_cadence_days, pe.pro_max_refresh_eligibility_days,
                    pe.rollover_percent, pe.rollover_cycles, pe.cycle_length_days,
                    pa.status AS activation_status,
                    pa.started_at,
                    pa.ends_at
                FROM plan_activations pa
                JOIN plans p ON p.id = pa.plan_id
                JOIN plan_entitlements pe ON pe.plan_id = p.id
                WHERE pa.user_id = :user_id
                  AND pa.status = 'active'
                  AND pa.ends_at > now()
                ORDER BY p.display_order DESC
                LIMIT 1
            """),
            {"user_id": user_id},
        )
        row = result.mappings().first()
    if row is None:
        return None
    return AccountPlanRead(
        plan=_row_to_plan(row),
        status=row["activation_status"],
        started_at=row["started_at"],
        ends_at=row["ends_at"],
        entitlements=_row_to_entitlements(row),
    )
