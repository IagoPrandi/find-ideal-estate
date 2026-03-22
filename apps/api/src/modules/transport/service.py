from __future__ import annotations

from uuid import UUID

from contracts import TransportPointRead

from .points_service import list_transport_points_for_journey, run_transport_search_for_job


class TransportService:
    """Facade service kept thin while transport domain grows in Phase 4+."""

    async def run_transport_search_for_job(self, job_id: UUID) -> int:
        return await run_transport_search_for_job(job_id)

    async def list_transport_points_for_journey(self, journey_id: UUID) -> list[TransportPointRead]:
        return await list_transport_points_for_journey(journey_id)
