from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from core.db import get_engine
from modules.transport import OTPAdapter, ValhallaAdapter
from modules.transport.valhalla_adapter import GeoPoint
from sqlalchemy import text


@dataclass(frozen=True)
class ZoneGenerationOutcome:
    zone_id: UUID
    fingerprint: str
    reused: bool


def compute_zone_fingerprint(
    lat: float,
    lon: float,
    modal: str,
    max_time_minutes: int,
    radius_meters: int,
    dataset_version: str | None,
) -> str:
    canonical = {
        "dataset_v": dataset_version,
        "lat": round(float(lat), 5),
        "lon": round(float(lon), 5),
        "max_time": int(max_time_minutes),
        "modal": str(modal).strip().lower(),
        "radius": int(radius_meters),
    }
    payload = json.dumps(canonical, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _extract_zone_config(input_snapshot: dict[str, Any] | None) -> tuple[str, int, int, str | None]:
    if not isinstance(input_snapshot, dict):
        return "walking", 30, 1500, None

    raw_modal = (
        input_snapshot.get("zone_modal")
        or input_snapshot.get("travel_mode")
        or input_snapshot.get("modal")
    )
    modal = str(raw_modal or "walking").strip().lower()
    if modal in {"walk", "pedestrian"}:
        modal = "walking"

    raw_max_time = (
        input_snapshot.get("max_time_minutes")
        or input_snapshot.get("max_travel_time_min")
        or input_snapshot.get("time_max_minutes")
    )
    if isinstance(raw_max_time, (int, float)) and raw_max_time > 0:
        max_time_minutes = int(raw_max_time)
    else:
        max_time_minutes = 30

    raw_radius = (
        input_snapshot.get("zone_radius_meters")
        or input_snapshot.get("radius_meters")
        or input_snapshot.get("radius")
    )
    if isinstance(raw_radius, (int, float)) and raw_radius > 0:
        radius_meters = int(raw_radius)
    else:
        radius_meters = 1500

    dataset_version = input_snapshot.get("dataset_version_id")
    dataset_version_id = str(dataset_version) if dataset_version is not None else None
    return modal, max_time_minutes, radius_meters, dataset_version_id


def _modal_to_valhalla_costing(modal: str) -> str:
    normalized = str(modal).strip().lower()
    if normalized == "car":
        return "auto"
    return "pedestrian"


def _extract_isochrone_geometry(isochrone_geojson: dict[str, Any]) -> dict[str, Any]:
    if isochrone_geojson.get("type") == "FeatureCollection":
        features = isochrone_geojson.get("features") or []
        if features:
            feature = features[0] or {}
            geometry = feature.get("geometry")
            if isinstance(geometry, dict) and geometry.get("type"):
                return geometry

    geometry = isochrone_geojson.get("geometry")
    if isinstance(geometry, dict) and geometry.get("type"):
        return geometry

    if isochrone_geojson.get("type") in {"Polygon", "MultiPolygon"}:
        return isochrone_geojson

    raise ValueError("Valhalla isochrone response has no valid geometry")


class ZoneService:
    """Zone orchestration service for generation and reuse flow."""

    def __init__(
        self,
        *,
        valhalla_adapter: ValhallaAdapter,
        otp_adapter: OTPAdapter,
    ) -> None:
        self._valhalla_adapter = valhalla_adapter
        self._otp_adapter = otp_adapter

    @property
    def valhalla_adapter(self) -> ValhallaAdapter:
        return self._valhalla_adapter

    @property
    def otp_adapter(self) -> OTPAdapter:
        return self._otp_adapter

    async def ensure_zones_for_job(self, job_id: UUID) -> dict[str, Any]:
        """Generate zones for all transport points in a journey, emitting partial results.

        Returns:
            dict with 'zones' list of ZoneGenerationOutcome, 'total' and 'completed' counts
        """
        engine = get_engine()
        async with engine.begin() as conn:
            # Load journey with all transport points
            context_result = await conn.execute(
                text(
                    """
                    SELECT
                        j.id AS journey_id,
                        j.input_snapshot
                    FROM jobs jb
                    JOIN journeys j ON j.id = jb.journey_id
                    WHERE jb.id = :job_id
                    """
                ),
                {"job_id": job_id},
            )
            context = context_result.mappings().first()
            if context is None:
                raise RuntimeError(f"Zone generation context not found for job {job_id}")

            journey_id = context["journey_id"]
            input_snapshot = context["input_snapshot"]

            # Fetch all transport points for this journey
            points_result = await conn.execute(
                text(
                    """
                    SELECT id, ST_Y(location) AS lat, ST_X(location) AS lon
                    FROM transport_points
                    WHERE journey_id = :journey_id
                    ORDER BY walk_distance_m ASC, created_at ASC
                    """
                ),
                {"journey_id": journey_id},
            )
            points = points_result.mappings().fetchall()
            if not points:
                raise RuntimeError(f"No transport points found for journey {journey_id}")

            modal, max_time_minutes, radius_meters, dataset_version_id = _extract_zone_config(
                input_snapshot
            )

            zones = []
            for idx, point in enumerate(points):
                transport_point_id = point["id"]
                lat = point["lat"]
                lon = point["lon"]

                # Compute fingerprint
                fingerprint = compute_zone_fingerprint(
                    float(lat),
                    float(lon),
                    modal,
                    max_time_minutes,
                    radius_meters,
                    dataset_version_id,
                )

                # Check for existing zone
                existing_result = await conn.execute(
                    text(
                        """
                        SELECT id
                        FROM zones
                        WHERE fingerprint = :fingerprint
                        LIMIT 1
                        """
                    ),
                    {"fingerprint": fingerprint},
                )
                existing = existing_result.mappings().first()
                if existing is not None:
                    await conn.execute(
                        text(
                            """
                            INSERT INTO journey_zones (journey_id, zone_id, transport_point_id)
                            VALUES (:journey_id, :zone_id, :transport_point_id)
                            ON CONFLICT (journey_id, zone_id) DO UPDATE
                            SET transport_point_id = EXCLUDED.transport_point_id
                            """
                        ),
                        {
                            "journey_id": journey_id,
                            "zone_id": existing["id"],
                            "transport_point_id": transport_point_id,
                        },
                    )
                    zones.append(
                        ZoneGenerationOutcome(
                            zone_id=existing["id"],
                            fingerprint=fingerprint,
                            reused=True,
                        )
                    )
                    continue

                # Update zone state to 'generating' before calling Valhalla
                await conn.execute(
                    text(
                        """
                        UPDATE zones
                        SET state = 'generating', updated_at = now()
                        WHERE fingerprint = :fingerprint AND state = 'pending'
                        """
                    ),
                    {"fingerprint": fingerprint},
                )

                # Generate isochrone from Valhalla
                isochrone_geojson = await self._valhalla_adapter.isochrone(
                    origin=GeoPoint(lat=float(lat), lon=float(lon)),
                    costing=_modal_to_valhalla_costing(modal),
                    contours_minutes=[max_time_minutes],
                )
                geometry = _extract_isochrone_geometry(isochrone_geojson)

                # Insert zone
                insert_result = await conn.execute(
                    text(
                        """
                        INSERT INTO zones (
                            journey_id,
                            transport_point_id,
                            modal,
                            max_time_minutes,
                            radius_meters,
                            fingerprint,
                            isochrone_geom,
                            dataset_version_id,
                            state,
                            updated_at
                        ) VALUES (
                            :journey_id,
                            :transport_point_id,
                            :modal,
                            :max_time_minutes,
                            :radius_meters,
                            :fingerprint,
                            ST_SetSRID(ST_GeomFromGeoJSON(:isochrone_geom), 4326),
                            CAST(:dataset_version_id AS UUID),
                            'enriching',
                            now()
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "journey_id": journey_id,
                        "transport_point_id": transport_point_id,
                        "modal": modal,
                        "max_time_minutes": max_time_minutes,
                        "radius_meters": radius_meters,
                        "fingerprint": fingerprint,
                        "isochrone_geom": json.dumps(geometry, ensure_ascii=True),
                        "dataset_version_id": dataset_version_id,
                    },
                )
                created = insert_result.mappings().one()
                await conn.execute(
                    text(
                        """
                        INSERT INTO journey_zones (journey_id, zone_id, transport_point_id)
                        VALUES (:journey_id, :zone_id, :transport_point_id)
                        ON CONFLICT (journey_id, zone_id) DO UPDATE
                        SET transport_point_id = EXCLUDED.transport_point_id
                        """
                    ),
                    {
                        "journey_id": journey_id,
                        "zone_id": created["id"],
                        "transport_point_id": transport_point_id,
                    },
                )
                zones.append(
                    ZoneGenerationOutcome(
                        zone_id=created["id"],
                        fingerprint=fingerprint,
                        reused=False,
                    )
                )

            return {
                "zones": zones,
                "total": len(zones),
                "completed": sum(1 for z in zones if not z.reused),
            }

    async def ensure_zone_for_job(self, job_id: UUID) -> ZoneGenerationOutcome:
        """Legacy method for backward compatibility - generates zone for first transport point."""
        engine = get_engine()
        async with engine.begin() as conn:
            context_result = await conn.execute(
                text(
                    """
                    SELECT
                        j.id AS journey_id,
                        j.input_snapshot,
                        tp.id AS transport_point_id,
                        ST_Y(tp.location) AS lat,
                        ST_X(tp.location) AS lon
                    FROM jobs jb
                    JOIN journeys j ON j.id = jb.journey_id
                    LEFT JOIN transport_points tp ON tp.id = COALESCE(
                        j.selected_transport_point_id,
                        (
                            SELECT id
                            FROM transport_points
                            WHERE journey_id = j.id
                            ORDER BY walk_distance_m ASC, created_at ASC
                            LIMIT 1
                        )
                    )
                    WHERE jb.id = :job_id
                    """
                ),
                {"job_id": job_id},
            )
            context = context_result.mappings().first()
            if context is None:
                raise RuntimeError(f"Zone generation context not found for job {job_id}")

            transport_point_id = context["transport_point_id"]
            lat = context["lat"]
            lon = context["lon"]
            if transport_point_id is None or lat is None or lon is None:
                raise RuntimeError("Zone generation requires at least one transport point")

            modal, max_time_minutes, radius_meters, dataset_version_id = _extract_zone_config(
                context["input_snapshot"]
            )
            fingerprint = compute_zone_fingerprint(
                float(lat),
                float(lon),
                modal,
                max_time_minutes,
                radius_meters,
                dataset_version_id,
            )

            existing_result = await conn.execute(
                text(
                    """
                    SELECT id
                    FROM zones
                    WHERE fingerprint = :fingerprint
                    LIMIT 1
                    """
                ),
                {"fingerprint": fingerprint},
            )
            existing = existing_result.mappings().first()
            if existing is not None:
                await conn.execute(
                    text(
                        """
                        INSERT INTO journey_zones (journey_id, zone_id, transport_point_id)
                        VALUES (:journey_id, :zone_id, :transport_point_id)
                        ON CONFLICT (journey_id, zone_id) DO UPDATE
                        SET transport_point_id = EXCLUDED.transport_point_id
                        """
                    ),
                    {
                        "journey_id": context["journey_id"],
                        "zone_id": existing["id"],
                        "transport_point_id": transport_point_id,
                    },
                )
                return ZoneGenerationOutcome(
                    zone_id=existing["id"],
                    fingerprint=fingerprint,
                    reused=True,
                )

            isochrone_geojson = await self._valhalla_adapter.isochrone(
                origin=GeoPoint(lat=float(lat), lon=float(lon)),
                costing=_modal_to_valhalla_costing(modal),
                contours_minutes=[max_time_minutes],
            )
            geometry = _extract_isochrone_geometry(isochrone_geojson)

            insert_result = await conn.execute(
                text(
                    """
                    INSERT INTO zones (
                        journey_id,
                        transport_point_id,
                        modal,
                        max_time_minutes,
                        radius_meters,
                        fingerprint,
                        isochrone_geom,
                        dataset_version_id,
                        state,
                        updated_at
                    ) VALUES (
                        :journey_id,
                        :transport_point_id,
                        :modal,
                        :max_time_minutes,
                        :radius_meters,
                        :fingerprint,
                        ST_SetSRID(ST_GeomFromGeoJSON(:isochrone_geom), 4326),
                        CAST(:dataset_version_id AS UUID),
                        'enriching',
                        now()
                    )
                    RETURNING id
                    """
                ),
                {
                    "journey_id": context["journey_id"],
                    "transport_point_id": transport_point_id,
                    "modal": modal,
                    "max_time_minutes": max_time_minutes,
                    "radius_meters": radius_meters,
                    "fingerprint": fingerprint,
                    "isochrone_geom": json.dumps(geometry, ensure_ascii=True),
                    "dataset_version_id": dataset_version_id,
                },
            )
            created = insert_result.mappings().one()
            await conn.execute(
                text(
                    """
                    INSERT INTO journey_zones (journey_id, zone_id, transport_point_id)
                    VALUES (:journey_id, :zone_id, :transport_point_id)
                    ON CONFLICT (journey_id, zone_id) DO UPDATE
                    SET transport_point_id = EXCLUDED.transport_point_id
                    """
                ),
                {
                    "journey_id": context["journey_id"],
                    "zone_id": created["id"],
                    "transport_point_id": transport_point_id,
                },
            )
            return ZoneGenerationOutcome(
                zone_id=created["id"],
                fingerprint=fingerprint,
                reused=False,
            )
