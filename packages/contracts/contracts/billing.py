from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class PlanRead(BaseModel):
    id: UUID
    slug: str
    name: str
    price_brl: Decimal | None
    monthly_credits: int
    is_paid: bool
    display_order: int


class PlanEntitlementsRead(BaseModel):
    max_listing_favorites: int | None
    max_zone_favorites: int | None
    retention_days: int
    can_customize_radius: bool
    can_customize_max_time: bool
    can_customize_distance: bool
    max_active_metrics: int | None
    transport_line_policy: str
    zone_selection_policy: str
    auto_refresh_policy: str
    pro_max_refresh_max_zones: int | None
    pro_max_refresh_max_listings: int | None
    pro_max_refresh_cadence_days: int | None
    pro_max_refresh_eligibility_days: int | None
    rollover_percent: int
    rollover_cycles: int
    cycle_length_days: int
    max_transit_minutes_cap: int | None = None
    max_walk_minutes_cap: int | None = None
    max_car_minutes_cap: int | None = None
    max_zone_radius_m_cap: int | None = None
    max_transport_radius_m_cap: int | None = None


class ResolvedEntitlements(BaseModel):
    plan: PlanRead
    entitlements: PlanEntitlementsRead


class AccountPlanRead(BaseModel):
    plan: PlanRead
    status: str
    started_at: datetime | None
    ends_at: datetime | None
    entitlements: PlanEntitlementsRead


class AccountCreditsRead(BaseModel):
    cycle: int
    rollover: int
    legacy: int
    total: int
    cycle_ends_at: datetime | None
    monthly_quota: int | None


class PixCheckoutRequest(BaseModel):
    plan_slug: str
    payment_type: str = "plan_activation"


class PixCheckoutResponse(BaseModel):
    payment_id: UUID
    pix_copy_paste: str
    qr_code_payload: str
    qr_code_image_url: str | None
    amount_brl: Decimal
    expires_at: datetime
    status: str


class PaymentStatusRead(BaseModel):
    id: UUID
    status: str
    payment_provider: str
    payment_type: str
    amount_brl: Decimal
    plan_id: UUID | None
    created_at: datetime
    expires_at: datetime | None
    paid_at: datetime | None


class PixConfirmRequest(BaseModel):
    payment_id: UUID
