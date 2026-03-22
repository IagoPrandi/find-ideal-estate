from __future__ import annotations

from uuid import UUID

from contracts import ZoneListResponse, ZoneRead, PriceRollupRead
from core.container import get_container
from core.db import get_engine as _get_engine
from fastapi import APIRouter, HTTPException, Query, status
from modules.listings.price_rollups import fetch_rollups_for_zone
from sqlalchemy import text

router = APIRouter(prefix="/journeys", tags=["zones"])


@router.get("/{journey_id}/zones", response_model=ZoneListResponse)
async def list_zones_endpoint(journey_id: UUID) -> ZoneListResponse:
    """List all zones for a journey, ordered by travel_time_minutes."""
    zone_service = get_container().zone_service()
    
    try:
        zones = await zone_service.list_zones_for_journey(journey_id)
        completed_count = sum(1 for z in zones if z.get("state") == "complete")
        
        return ZoneListResponse(
            zones=zones,  # type: ignore
            total_count=len(zones),
            completed_count=completed_count,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Falha ao carregar zonas: {str(e)}",
        )


@router.get(
    "/{journey_id}/zones/{zone_fingerprint}/price-rollups",
    response_model=list[PriceRollupRead],
)
async def get_price_rollups(
    journey_id: UUID,
    zone_fingerprint: str,
    search_type: str = Query(default="rent", pattern="^(rent|sale)$"),
    days: int = Query(default=30, ge=1, le=365),
) -> list[PriceRollupRead]:
    """M6.1: Return daily price-percentile rollups for a zone (up to *days* entries)."""
    engine = _get_engine()
    async with engine.connect() as conn:
        rows = await fetch_rollups_for_zone(
            conn, zone_fingerprint, search_type, days=days
        )

    results: list[PriceRollupRead] = []
    for row in rows:
        raw_date = row.get("date")
        results.append(
            PriceRollupRead(
                id=row["id"],
                date=raw_date.isoformat() if hasattr(raw_date, "isoformat") else str(raw_date),
                zone_fingerprint=row["zone_fingerprint"],
                search_type=row["search_type"],
                median_price=row.get("median_price"),
                p25_price=row.get("p25_price"),
                p75_price=row.get("p75_price"),
                sample_count=int(row.get("sample_count") or 0),
                computed_at=row["computed_at"],
            )
        )
    return results
