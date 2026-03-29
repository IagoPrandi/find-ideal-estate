"""Badge computation for zone metrics with provisional/final medians."""

from __future__ import annotations

import json
import statistics
from typing import Any
from uuid import UUID

from core.db import get_engine
from sqlalchemy import text


class ZoneBadgeValue:
    """Represents a single badge value (e.g., green area percentile rank)."""

    def __init__(
        self,
        metric_name: str,
        value: float | int,
        peer_median: float,
        rank_percentile: float,
        tier: str,
    ):
        self.metric_name = metric_name
        self.value = value
        self.peer_median = peer_median
        self.rank_percentile = rank_percentile
        self.tier = tier  # "excellent", "good", "fair", "poor"

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "value": self.value,
            "peer_median": self.peer_median,
            "rank_percentile": self.rank_percentile,
            "tier": self.tier,
        }


def _compute_rank_percentile(value: float | int, peer_values: list[float | int]) -> float:
    """Compute percentile rank of value within peer_values (0-100)."""
    if not peer_values:
        return 50.0
    sorted_peers = sorted(peer_values)
    rank = sum(1 for v in sorted_peers if v <= value)
    return (rank / len(sorted_peers)) * 100.0


def _percentile_to_tier(percentile: float) -> str:
    """Map percentile rank to tier badge."""
    if percentile >= 75:
        return "excellent"
    if percentile >= 50:
        return "good"
    if percentile >= 25:
        return "fair"
    return "poor"


def build_metric_badge(
    value: float | int,
    peer_values: list[float | int],
    *,
    invert: bool = False,
) -> dict[str, Any]:
    """Build the compact badge payload used by journey zone responses."""
    percentile = _compute_rank_percentile(value, peer_values)
    if invert:
        percentile = 100 - percentile

    return {
        "value": value,
        "percentile": percentile,
        "tier": _percentile_to_tier(percentile),
    }


async def compute_zone_badges(
    zone_id: UUID, provisional: bool = True, based_on_count: int | None = None
) -> dict[str, Any]:
    """
    Compute badges for a zone based on current enrichment metrics.

    Args:
        zone_id: UUID of the zone
        provisional: If True, use provisional medians (zones completed so far).
                    If False, use final medians (all zones completed).
        based_on_count: For provisional badges, indicates X/Y zones completed.
                       If None, will query the database.

    Returns:
        Dictionary with badge data:
        {
            "green": {...},
            "flood": {...},
            "safety": {...},
            "provisional": bool,
            "based_on": "X/Y" if provisional else None,
        }
    """
    engine = get_engine()

    # Retrieve zone metrics
    async with engine.connect() as conn:
        zone_result = await conn.execute(
            text(
                """
                SELECT
                    green_area_m2,
                    flood_area_m2,
                    safety_incidents_count
                FROM zones
                WHERE id = :zone_id
                """
            ),
            {"zone_id": zone_id},
        )
        zone_row = zone_result.mappings().first()

    if zone_row is None:
        raise RuntimeError(f"Zone {zone_id} not found")

    green_value = float(zone_row["green_area_m2"] or 0.0)
    flood_value = float(zone_row["flood_area_m2"] or 0.0)
    safety_value = int(zone_row["safety_incidents_count"] or 0)

    # Determine peer set (all zones vs. zones completed so far)
    if provisional:
        # Provisional: use only zones that have completed enrichment (state = 'complete')
        query = """
            SELECT
                green_area_m2,
                flood_area_m2,
                safety_incidents_count
            FROM zones
            WHERE state = 'complete'
            ORDER BY updated_at ASC
        """
    else:
        # Final: use all zones in the journey
        query = """
            SELECT z.green_area_m2, z.flood_area_m2, z.safety_incidents_count
            FROM journey_zones jz
            JOIN zones z ON z.id = jz.zone_id
            INNER JOIN (
                SELECT jz2.journey_id
                FROM journey_zones jz2
                WHERE jz2.zone_id = :zone_id
                ORDER BY jz2.created_at ASC
                LIMIT 1
            ) target ON jz.journey_id = target.journey_id
            ORDER BY jz.created_at ASC, z.updated_at ASC
        """

    async with engine.connect() as conn:
        peer_result = await conn.execute(text(query), {"zone_id": zone_id})
        peer_rows = peer_result.mappings().fetchall()

    green_peers = [float(row["green_area_m2"] or 0.0) for row in peer_rows]
    flood_peers = [float(row["flood_area_m2"] or 0.0) for row in peer_rows]
    safety_peers = [int(row["safety_incidents_count"] or 0) for row in peer_rows]

    # Compute medians
    green_median = statistics.median(green_peers) if green_peers else 0.0
    flood_median = statistics.median(flood_peers) if flood_peers else 0.0
    safety_median = statistics.median(safety_peers) if safety_peers else 0.0

    # Compute percentile ranks (higher is better for green; higher is worse for flood/safety)
    green_percentile = _compute_rank_percentile(green_value, green_peers)
    flood_percentile = 100 - _compute_rank_percentile(flood_value, flood_peers)  # Invert
    safety_percentile = 100 - _compute_rank_percentile(safety_value, safety_peers)  # Invert

    badges = {
        "green": ZoneBadgeValue(
            metric_name="green_area_m2",
            value=green_value,
            peer_median=green_median,
            rank_percentile=green_percentile,
            tier=_percentile_to_tier(green_percentile),
        ).to_dict(),
        "flood": ZoneBadgeValue(
            metric_name="flood_area_m2",
            value=flood_value,
            peer_median=flood_median,
            rank_percentile=flood_percentile,
            tier=_percentile_to_tier(flood_percentile),
        ).to_dict(),
        "safety": ZoneBadgeValue(
            metric_name="safety_incidents_count",
            value=safety_value,
            peer_median=safety_median,
            rank_percentile=safety_percentile,
            tier=_percentile_to_tier(safety_percentile),
        ).to_dict(),
        "provisional": provisional,
    }

    if provisional and based_on_count is not None:
        badges["based_on"] = f"{based_on_count}/{len(green_peers)}"

    return badges


async def update_zone_badges(
    zone_id: UUID, badges_data: dict[str, Any], provisional: bool = True
) -> None:
    """Update zone badges in database and set provisional flag."""
    engine = get_engine()

    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                UPDATE zones
                SET badges = :badges, badges_provisional = :provisional, updated_at = now()
                WHERE id = :zone_id
                """
            ),
            {
                "zone_id": zone_id,
                "badges": json.dumps(badges_data, ensure_ascii=True),
                "provisional": provisional,
            },
        )
