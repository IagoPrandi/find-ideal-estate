from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from .jobs import JobRead


class AdminScrapingQueueItemRead(BaseModel):
    search_location_normalized: str
    search_location_label: str
    search_location_type: str
    search_type: str
    usage_type: str
    demand_count: int
    last_requested_at: datetime | None = None
    zone_fingerprint: str | None = None
    cache_status: str | None = None
    cache_age_hours: float | None = None
    last_prewarmed_at: datetime | None = None
    scraped_at: datetime | None = None


class AdminScrapingQueueRead(BaseModel):
    items: list[AdminScrapingQueueItemRead]
    total_count: int
    limit: int
    lookback_hours: int


class AdminScrapingQueueAddRequest(BaseModel):
    addresses: list[str] = Field(min_length=1, max_length=100)
    search_type: str = "rent"
    usage_type: str = "residential"
    search_location_type: str = "address"


class AdminScrapingQueueMutationRead(BaseModel):
    status: str
    affected_count: int


class AdminScrapingOverviewRead(BaseModel):
    scheduler_enabled: bool
    cron_hour: int
    cron_minute: int
    timezone: str
    next_run_at: datetime | None = None
    seconds_until_next_run: int | None = None
    lookback_hours: int
    limit: int
    active_job: JobRead | None = None
    latest_job: JobRead | None = None
    queue_count: int


class AdminScrapingBatchRead(BaseModel):
    job: JobRead
    trigger: str | None = None
    status: str | None = None
    target_count: int
    processed_count: int
    skipped_count: int
    failed_count: int
    duration_ms: int | None = None
    target_statuses: dict[str, Any] = Field(default_factory=dict)


class AdminScrapingBatchesRead(BaseModel):
    items: list[AdminScrapingBatchRead]
    total_count: int
    limit: int
    offset: int


class AdminRunNowResponse(BaseModel):
    job: JobRead
    target_count: int
    status: str


class AdminUserRead(BaseModel):
    id: UUID
    email: str
    display_name: str | None = None
    is_active: bool
    is_superuser: bool
    role: str
    created_at: datetime


class AdminUsersRead(BaseModel):
    items: list[AdminUserRead]
    total_count: int
    limit: int
    offset: int


class AdminUserRoleUpdateRequest(BaseModel):
    role: str
