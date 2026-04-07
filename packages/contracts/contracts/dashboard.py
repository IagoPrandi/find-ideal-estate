from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class DashboardRankRead(BaseModel):
    position: int | None = None
    total: int = 0
    percentile: float | None = None
    scope_label: str | None = None
    direction: Literal["higher_better", "lower_better"] | None = None
    note: str | None = None


class DashboardDistributionBucketRead(BaseModel):
    label: str
    count: int


class DashboardRankingItemRead(BaseModel):
    position: int
    neighborhood_name: str
    city_name: str | None = None
    value: float | None = None
    yearly_change_pct: float | None = None
    is_selected: bool = False


class DashboardPriceHistoryPointRead(BaseModel):
    date: str
    property_price: float | None = None
    neighborhood_median_price: float | None = None


class DashboardSafetyHourBucketRead(BaseModel):
    hour: int
    total_count: int = 0
    homicide_count: int = 0
    violent_count: int = 0
    robbery_count: int = 0
    theft_count: int = 0


class ZoneDashboardContextRead(BaseModel):
    zone_fingerprint: str
    property_id: UUID | None = None
    property_address: str | None = None
    neighborhood_name: str | None = None
    city_name: str | None = None
    state_code: str | None = None
    selected_price: float | None = None
    selected_unit_price: float | None = None
    zone_area_m2: float | None = None


class ZoneDashboardPriceRead(BaseModel):
    neighborhood_median_unit_price: float | None = None
    selected_vs_neighborhood_pct: float | None = None
    neighborhood_unit_price_rank: DashboardRankRead | None = None
    neighborhood_unit_price_ranking: list[DashboardRankingItemRead] = []
    yearly_change_pct: float | None = None
    yearly_change_rank: DashboardRankRead | None = None
    history: list[DashboardPriceHistoryPointRead] = []
    price_distribution: list[DashboardDistributionBucketRead] = []
    note: str | None = None


class ZoneDashboardSafetyRead(BaseModel):
    city_options: list[str] = []
    selected_city: str | None = None
    ranking_scope_label: str | None = None
    ranking_scope_note: str | None = None
    rate_scale_base: int | None = None
    selected_neighborhood_name: str | None = None
    homicide_count_365d: int = 0
    homicide_density_per_km2: float | None = None
    homicide_rank: DashboardRankRead | None = None
    robbery_count_365d: int = 0
    robbery_density_per_km2: float | None = None
    robbery_rate_rank: DashboardRankRead | None = None
    robbery_rate_ranking: list[DashboardRankingItemRead] = []
    theft_count_365d: int = 0
    robbery_to_theft_ratio: float | None = None
    robbery_to_theft_rank: DashboardRankRead | None = None
    peak_hours: list[DashboardSafetyHourBucketRead] = []


class ZoneDashboardEnvironmentRead(BaseModel):
    ranking_scope_label: str | None = None
    ranking_scope_note: str | None = None
    green_area_m2: float | None = None
    green_percentage: float | None = None
    green_rank: DashboardRankRead | None = None
    flood_area_m2: float | None = None
    flood_percentage: float | None = None
    flood_risk_label: str | None = None
    flood_rank: DashboardRankRead | None = None


class ZoneDashboardAnalyticsRead(BaseModel):
    context: ZoneDashboardContextRead
    price: ZoneDashboardPriceRead
    safety: ZoneDashboardSafetyRead
    environment: ZoneDashboardEnvironmentRead