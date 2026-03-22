from __future__ import annotations

from uuid import UUID

from contracts import ZoneListResponse, ZoneRead
from core.container import get_container
from fastapi import APIRouter, HTTPException, status

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
