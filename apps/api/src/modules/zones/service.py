from __future__ import annotations

from collections.abc import Sequence
import hashlib
import json
from dataclasses import dataclass
import logging
import math
from typing import Any
from uuid import UUID

from core.db import get_engine
from modules.transport import OTPAdapter, ValhallaAdapter
from modules.transport.valhalla_adapter import GeoPoint
from modules.transport.valhalla_adapter import ValhallaCommunicationError
from modules.zones.candidate_generation import CandidateZone, CandidateZoneGenerationError, generate_candidate_zones_for_seed
from sqlalchemy import text

logger = logging.getLogger(__name__)
_ESTIMATED_WALKING_SPEED_METERS_PER_MINUTE = 80
_ESTIMATED_DRIVING_SPEED_METERS_PER_MINUTE = 500
_DIRECT_ISOCHRONE_MIN_AREA_RATIO_VS_CIRCLE = 0.05
_DIRECT_ISOCHRONE_MIN_BOUNDARY_RATIO_VS_RADIUS = 0.15
_DIRECT_ISOCHRONE_MIN_AREA_RATIO_FOR_EDGE_CASE = 0.25
_FIND_EXISTING_ZONES_BY_FINGERPRINT_SQL = text(
    """
    SELECT id, fingerprint
    FROM zones
    WHERE fingerprint = ANY(CAST(:fingerprints AS TEXT[]))
    """
)
_UPSERT_JOURNEY_ZONES_SQL = text(
    """
    INSERT INTO journey_zones (journey_id, zone_id, transport_point_id)
    VALUES (:journey_id, :zone_id, :transport_point_id)
    ON CONFLICT (journey_id, zone_id) DO UPDATE
    SET transport_point_id = EXCLUDED.transport_point_id
    """
)


def _is_direct_isochrone_modal(modal: str) -> bool:
    return str(modal).strip().lower() in {"walking", "car"}

@dataclass(frozen=True)
class ZoneGenerationOutcome:
    zone_id: UUID
    fingerprint: str
    reused: bool


@dataclass(frozen=True)
class DirectIsochroneMetrics:
    covers_origin: bool
    area_m2: float
    boundary_distance_m: float
    area_ratio_vs_circle: float
    boundary_ratio_vs_radius: float


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


def compute_candidate_zone_fingerprint(
    *,
    seed_lat: float,
    seed_lon: float,
    legacy_zone_id: str,
    mode: str,
    source_point_id: str,
    travel_time_minutes: float,
    radius_meters: int,
    max_time_minutes: int,
    dataset_version: str | None,
) -> str:
    canonical = {
        "source": "candidate_zones_from_cache_v10_fixed2",
        "dataset_v": dataset_version,
        "seed_lat": round(float(seed_lat), 5),
        "seed_lon": round(float(seed_lon), 5),
        "legacy_zone_id": str(legacy_zone_id),
        "mode": str(mode).strip().lower(),
        "source_point_id": str(source_point_id),
        "travel_time_minutes": round(float(travel_time_minutes), 2),
        "radius": int(radius_meters),
        "max_time": int(max_time_minutes),
    }
    payload = json.dumps(canonical, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _extract_zone_config(input_snapshot: dict[str, Any] | None) -> tuple[str, int, int, str | None]:
    if not isinstance(input_snapshot, dict):
        return "walking", 30, 1500, None

    raw_modal = (
        input_snapshot.get("zone_modal")
        or input_snapshot.get("transport_mode")
        or input_snapshot.get("travel_mode")
        or input_snapshot.get("modal")
    )
    modal = str(raw_modal or "walking").strip().lower()
    if modal in {"walk", "pedestrian"}:
        modal = "walking"
    elif modal in {"drive", "driving", "auto"}:
        modal = "car"

    raw_max_time = (
        input_snapshot.get("max_travel_time_minutes")
        or input_snapshot.get("max_travel_time_min")
        or input_snapshot.get("max_travel_minutes")
        or input_snapshot.get("max_time_minutes")
        or input_snapshot.get("time_max_minutes")
    )
    if isinstance(raw_max_time, (int, float)) and raw_max_time > 0:
        max_time_minutes = int(raw_max_time)
    else:
        max_time_minutes = 30

    raw_radius = (
        input_snapshot.get("zone_radius_meters")
        or input_snapshot.get("zone_radius_m")
        or input_snapshot.get("radius_meters")
        or input_snapshot.get("radius")
    )
    if isinstance(raw_radius, (int, float)) and raw_radius > 0:
        radius_meters = int(raw_radius)
    elif modal == "walking":
        radius_meters = max(300, max_time_minutes * _ESTIMATED_WALKING_SPEED_METERS_PER_MINUTE)
    elif modal == "car":
        radius_meters = max(500, max_time_minutes * _ESTIMATED_DRIVING_SPEED_METERS_PER_MINUTE)
    else:
        radius_meters = 1500

    dataset_version = input_snapshot.get("dataset_version_id")
    dataset_version_id = str(dataset_version) if dataset_version is not None else None
    return modal, max_time_minutes, radius_meters, dataset_version_id


def _extract_reference_point(input_snapshot: dict[str, Any] | None) -> tuple[float, float] | None:
    if not isinstance(input_snapshot, dict):
        return None

    raw_reference = input_snapshot.get("reference_point") or input_snapshot.get("primary_reference_point")
    if not isinstance(raw_reference, dict):
        return None

    lat = raw_reference.get("lat")
    lon = raw_reference.get("lon")
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return None
    return float(lat), float(lon)


def _extract_public_transport_mode(input_snapshot: dict[str, Any] | None) -> str | None:
    if not isinstance(input_snapshot, dict):
        return None

    raw_transport_mode = (
        input_snapshot.get("transport_mode")
        or input_snapshot.get("travel_mode")
        or input_snapshot.get("modal")
    )
    transport_mode = str(raw_transport_mode or "").strip().lower()
    if transport_mode not in {"transit", "public", "public_transport"}:
        return None

    raw_public_transport_mode = input_snapshot.get("public_transport_mode")
    if raw_public_transport_mode is None:
        return None
    return str(raw_public_transport_mode).strip().lower()


def _normalize_transport_point_modal_types(raw_modal_types: Sequence[Any] | None, source: str | None) -> set[str]:
    normalized = {str(item).strip().lower() for item in (raw_modal_types or []) if item}
    source_token = str(source or "").strip().lower()

    if source_token == "gtfs_stop" or "bus" in source_token:
        normalized.add("bus")
    if "metro" in source_token:
        normalized.add("metro")
    if "train" in source_token or "trem" in source_token or "rail" in source_token:
        normalized.add("train")

    return normalized


def _validate_public_transport_seed(
    public_transport_mode: str | None,
    *,
    transport_point_source: str | None,
    transport_point_modal_types: Sequence[Any] | None,
) -> None:
    normalized_mode = str(public_transport_mode or "").strip().lower()
    if normalized_mode not in {"bus", "rail"}:
        return

    seed_modal_types = _normalize_transport_point_modal_types(
        transport_point_modal_types,
        transport_point_source,
    )
    if normalized_mode == "bus" and "bus" not in seed_modal_types:
        raise RuntimeError(
            "Selected transport seed is not compatible with bus-only public transport mode"
        )
    if normalized_mode == "rail" and seed_modal_types.isdisjoint({"metro", "train", "trem", "rail"}):
        raise RuntimeError(
            "Selected transport seed is not compatible with rail-only public transport mode"
        )


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


def _circle_polygon(lat: float, lon: float, radius_m: float, n_points: int = 36) -> dict[str, Any]:
    """Approximate circle polygon when Valhalla is unavailable."""
    coords: list[list[float]] = []
    lat_r = math.radians(lat)
    for i in range(n_points + 1):
        angle = math.radians(i * 360 / n_points)
        d_lat = (radius_m / 111_320) * math.cos(angle)
        d_lon = (radius_m / (111_320 * max(math.cos(lat_r), 1e-6))) * math.sin(angle)
        coords.append([lon + d_lon, lat + d_lat])
    return {"type": "Polygon", "coordinates": [coords]}


def _iter_polygon_coordinate_sets(geometry: dict[str, Any]) -> list[list[list[list[float]]]]:
    geometry_type = str(geometry.get("type") or "").strip()
    coordinates = geometry.get("coordinates")
    if geometry_type == "Polygon" and isinstance(coordinates, list):
        return [coordinates]
    if geometry_type == "MultiPolygon" and isinstance(coordinates, list):
        return coordinates
    return []


def _project_lon_lat_to_local_meters(
    lon: float,
    lat: float,
    *,
    origin_lon: float,
    origin_lat: float,
) -> tuple[float, float]:
    meters_per_lat = 111_320.0
    meters_per_lon = meters_per_lat * max(math.cos(math.radians(origin_lat)), 1e-6)
    return (
        (lon - origin_lon) * meters_per_lon,
        (lat - origin_lat) * meters_per_lat,
    )


def _project_ring_to_local_meters(
    ring: list[Any],
    *,
    origin_lon: float,
    origin_lat: float,
) -> list[tuple[float, float]]:
    projected: list[tuple[float, float]] = []
    for point in ring:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        lon = point[0]
        lat = point[1]
        if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
            continue
        projected.append(
            _project_lon_lat_to_local_meters(
                float(lon),
                float(lat),
                origin_lon=origin_lon,
                origin_lat=origin_lat,
            )
        )
    return projected


def _point_in_ring(point: tuple[float, float], ring: list[tuple[float, float]]) -> bool:
    if len(ring) < 3:
        return False

    x, y = point
    inside = False
    previous_x, previous_y = ring[-1]
    for current_x, current_y in ring:
        intersects = ((current_y > y) != (previous_y > y)) and (
            x < (previous_x - current_x) * (y - current_y) / ((previous_y - current_y) or 1e-12) + current_x
        )
        if intersects:
            inside = not inside
        previous_x, previous_y = current_x, current_y
    return inside


def _distance_point_to_segment_m(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    point_x, point_y = point
    start_x, start_y = start
    end_x, end_y = end
    delta_x = end_x - start_x
    delta_y = end_y - start_y
    segment_length_sq = delta_x * delta_x + delta_y * delta_y
    if segment_length_sq <= 0:
        return math.hypot(point_x - start_x, point_y - start_y)

    projection = ((point_x - start_x) * delta_x + (point_y - start_y) * delta_y) / segment_length_sq
    projection = max(0.0, min(1.0, projection))
    closest_x = start_x + projection * delta_x
    closest_y = start_y + projection * delta_y
    return math.hypot(point_x - closest_x, point_y - closest_y)


def _ring_area_m2(ring: list[tuple[float, float]]) -> float:
    if len(ring) < 3:
        return 0.0
    area = 0.0
    previous_x, previous_y = ring[-1]
    for current_x, current_y in ring:
        area += previous_x * current_y - current_x * previous_y
        previous_x, previous_y = current_x, current_y
    return abs(area) / 2.0


def _measure_direct_isochrone_geometry(
    geometry: dict[str, Any],
    *,
    origin_lat: float,
    origin_lon: float,
    expected_radius_m: float,
) -> DirectIsochroneMetrics:
    polygons = _iter_polygon_coordinate_sets(geometry)
    if not polygons:
        return DirectIsochroneMetrics(
            covers_origin=False,
            area_m2=0.0,
            boundary_distance_m=0.0,
            area_ratio_vs_circle=0.0,
            boundary_ratio_vs_radius=0.0,
        )

    origin = (0.0, 0.0)
    covers_origin = False
    area_m2 = 0.0
    boundary_distance_m = math.inf

    for polygon in polygons:
        projected_rings = [
            _project_ring_to_local_meters(
                ring,
                origin_lon=origin_lon,
                origin_lat=origin_lat,
            )
            for ring in polygon
            if isinstance(ring, list)
        ]
        projected_rings = [ring for ring in projected_rings if len(ring) >= 3]
        if not projected_rings:
            continue

        exterior = projected_rings[0]
        holes = projected_rings[1:]
        polygon_area = _ring_area_m2(exterior) - sum(_ring_area_m2(hole) for hole in holes)
        area_m2 += max(0.0, polygon_area)

        if _point_in_ring(origin, exterior) and not any(_point_in_ring(origin, hole) for hole in holes):
            covers_origin = True

        for ring in projected_rings:
            previous = ring[-1]
            for current in ring:
                boundary_distance_m = min(
                    boundary_distance_m,
                    _distance_point_to_segment_m(origin, previous, current),
                )
                previous = current

    if not math.isfinite(boundary_distance_m):
        boundary_distance_m = 0.0

    ideal_circle_area_m2 = math.pi * max(expected_radius_m, 0.0) * max(expected_radius_m, 0.0)
    area_ratio_vs_circle = area_m2 / ideal_circle_area_m2 if ideal_circle_area_m2 > 0 else 0.0
    boundary_ratio_vs_radius = boundary_distance_m / expected_radius_m if expected_radius_m > 0 else 0.0
    return DirectIsochroneMetrics(
        covers_origin=covers_origin,
        area_m2=area_m2,
        boundary_distance_m=boundary_distance_m,
        area_ratio_vs_circle=area_ratio_vs_circle,
        boundary_ratio_vs_radius=boundary_ratio_vs_radius,
    )


def _direct_isochrone_validation_issue(metrics: DirectIsochroneMetrics) -> str | None:
    if not metrics.covers_origin:
        return "origin is outside returned geometry"
    if metrics.area_ratio_vs_circle < _DIRECT_ISOCHRONE_MIN_AREA_RATIO_VS_CIRCLE:
        return (
            "returned area is implausibly small for requested travel time "
            f"(area_ratio_vs_circle={metrics.area_ratio_vs_circle:.3f})"
        )
    if (
        metrics.boundary_ratio_vs_radius < _DIRECT_ISOCHRONE_MIN_BOUNDARY_RATIO_VS_RADIUS
        and metrics.area_ratio_vs_circle < _DIRECT_ISOCHRONE_MIN_AREA_RATIO_FOR_EDGE_CASE
    ):
        return (
            "origin is too close to the isochrone boundary for the requested travel time "
            f"(boundary_ratio_vs_radius={metrics.boundary_ratio_vs_radius:.3f}, "
            f"area_ratio_vs_circle={metrics.area_ratio_vs_circle:.3f})"
        )
    return None


async def _clear_journey_zone_links(conn, journey_id: UUID) -> None:
    await conn.execute(
        text(
            """
            DELETE FROM journey_zones
            WHERE journey_id = :journey_id
            """
        ),
        {"journey_id": journey_id},
    )

    await conn.execute(
        text(
            """
            UPDATE journeys
            SET selected_zone_id = NULL, updated_at = now()
            WHERE id = :journey_id
            """
        ),
        {"journey_id": journey_id},
    )


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

    async def _persist_single_isochrone_zone(
        self,
        conn,
        *,
        journey_id: UUID,
        transport_point_id: UUID | None,
        lat: float,
        lon: float,
        modal: str,
        max_time_minutes: int,
        radius_meters: int,
        dataset_version_id: str | None,
    ) -> ZoneGenerationOutcome:
        fingerprint = compute_zone_fingerprint(
            lat,
            lon,
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
                    "journey_id": journey_id,
                    "zone_id": existing["id"],
                    "transport_point_id": transport_point_id,
                },
            )
            return ZoneGenerationOutcome(
                zone_id=existing["id"],
                fingerprint=fingerprint,
                reused=True,
            )

        is_circle_fallback = False
        try:
            isochrone_geojson = await self._valhalla_adapter.isochrone(
                origin=GeoPoint(lat=float(lat), lon=float(lon)),
                costing=_modal_to_valhalla_costing(modal),
                contours_minutes=[max_time_minutes],
            )
            geometry = _extract_isochrone_geometry(isochrone_geojson)
        except (ValhallaCommunicationError, ValueError) as exc:
            logger.warning("Valhalla unavailable, using circle fallback: %s", exc)
            geometry = _circle_polygon(float(lat), float(lon), float(radius_meters))
            is_circle_fallback = True

        if not is_circle_fallback and _is_direct_isochrone_modal(modal):
            metrics = _measure_direct_isochrone_geometry(
                geometry,
                origin_lat=float(lat),
                origin_lon=float(lon),
                expected_radius_m=float(radius_meters),
            )
            validation_issue = _direct_isochrone_validation_issue(metrics)
            if validation_issue is not None:
                logger.warning(
                    "Valhalla returned implausible %s isochrone, using circle fallback: %s "
                    "(covers_origin=%s area_m2=%.1f boundary_distance_m=%.1f area_ratio_vs_circle=%.3f boundary_ratio_vs_radius=%.3f)",
                    modal,
                    validation_issue,
                    metrics.covers_origin,
                    metrics.area_m2,
                    metrics.boundary_distance_m,
                    metrics.area_ratio_vs_circle,
                    metrics.boundary_ratio_vs_radius,
                )
                geometry = _circle_polygon(float(lat), float(lon), float(radius_meters))
                is_circle_fallback = True

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
                    is_circle_fallback,
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
                    :is_circle_fallback,
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
                "is_circle_fallback": is_circle_fallback,
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
        return ZoneGenerationOutcome(
            zone_id=created["id"],
            fingerprint=fingerprint,
            reused=False,
        )

    async def ensure_zones_for_job(self, job_id: UUID) -> dict[str, Any]:
        """Generate candidate zones for the selected seed point, emitting partial results.

        Returns:
            dict with 'zones' list of ZoneGenerationOutcome, 'total' and 'completed' counts
        """
        engine = get_engine()
        async with engine.connect() as conn:
            context_result = await conn.execute(
                text(
                    """
                    SELECT
                        j.id AS journey_id,
                        j.input_snapshot,
                        tp.id AS transport_point_id,
                        tp.source AS transport_point_source,
                        COALESCE(tp.modal_types, ARRAY[]::text[]) AS transport_point_modal_types,
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

        journey_id = context["journey_id"]
        input_snapshot = context["input_snapshot"]
        modal, max_time_minutes, radius_meters, dataset_version_id = _extract_zone_config(
            input_snapshot
        )

        transport_point_id = context["transport_point_id"]
        lat = context["lat"]
        lon = context["lon"]
        if _is_direct_isochrone_modal(modal):
            reference_point = _extract_reference_point(input_snapshot)
            if reference_point is not None:
                lat, lon = reference_point
            if lat is None or lon is None:
                raise RuntimeError(f"No reference point found for direct isochrone zone generation in journey {journey_id}")

            async with engine.begin() as conn:
                await _clear_journey_zone_links(conn, journey_id)
                outcome = await self._persist_single_isochrone_zone(
                    conn,
                    journey_id=journey_id,
                    transport_point_id=None,
                    lat=float(lat),
                    lon=float(lon),
                    modal=modal,
                    max_time_minutes=max_time_minutes,
                    radius_meters=radius_meters,
                    dataset_version_id=dataset_version_id,
                )

            return {
                "zones": [outcome],
                "total": 1,
                "completed": 0 if outcome.reused else 1,
            }

        if transport_point_id is None or lat is None or lon is None:
            raise RuntimeError(f"No selected transport seed found for journey {journey_id}")

        public_transport_mode = _extract_public_transport_mode(input_snapshot)
        _validate_public_transport_seed(
            public_transport_mode,
            transport_point_source=context["transport_point_source"],
            transport_point_modal_types=context["transport_point_modal_types"],
        )

        candidate_zones = await generate_candidate_zones_for_seed(
            seed_lat=float(lat),
            seed_lon=float(lon),
            max_time_minutes=max_time_minutes,
            radius_meters=radius_meters,
            public_transport_mode=public_transport_mode,
        )

        candidate_entries = [
            (
                candidate,
                compute_candidate_zone_fingerprint(
                    seed_lat=float(lat),
                    seed_lon=float(lon),
                    legacy_zone_id=candidate.logical_id,
                    mode=candidate.mode,
                    source_point_id=candidate.source_point_id,
                    travel_time_minutes=candidate.travel_time_minutes,
                    radius_meters=radius_meters,
                    max_time_minutes=max_time_minutes,
                    dataset_version=dataset_version_id,
                ),
            )
            for candidate in candidate_zones
        ]

        zones = []
        async with engine.begin() as conn:
            await _clear_journey_zone_links(conn, journey_id)

            existing_by_fingerprint: dict[str, UUID] = {}
            fingerprints = [fingerprint for _, fingerprint in candidate_entries]
            if fingerprints:
                existing_result = await conn.execute(
                    _FIND_EXISTING_ZONES_BY_FINGERPRINT_SQL,
                    {"fingerprints": fingerprints},
                )
                existing_by_fingerprint = {
                    str(row["fingerprint"]): row["id"]
                    for row in existing_result.mappings().all()
                }

            association_payloads: list[dict[str, Any]] = []

            for candidate, fingerprint in candidate_entries:
                existing_zone_id = existing_by_fingerprint.get(fingerprint)
                if existing_zone_id is not None:
                    association_payloads.append(
                        {
                            "journey_id": journey_id,
                            "zone_id": existing_zone_id,
                            "transport_point_id": transport_point_id,
                        }
                    )
                    zones.append(
                        ZoneGenerationOutcome(
                            zone_id=existing_zone_id,
                            fingerprint=fingerprint,
                            reused=True,
                        )
                    )
                    continue

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
                            is_circle_fallback,
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
                            false,
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
                        "modal": candidate.mode or modal,
                        "max_time_minutes": max(1, int(round(candidate.travel_time_minutes))),
                        "radius_meters": radius_meters,
                        "fingerprint": fingerprint,
                        "isochrone_geom": json.dumps(candidate.geometry, ensure_ascii=True),
                        "dataset_version_id": dataset_version_id,
                    },
                )
                created = insert_result.mappings().one()
                association_payloads.append(
                    {
                        "journey_id": journey_id,
                        "zone_id": created["id"],
                        "transport_point_id": transport_point_id,
                    }
                )
                zones.append(
                    ZoneGenerationOutcome(
                        zone_id=created["id"],
                        fingerprint=fingerprint,
                        reused=False,
                    )
                )

            if association_payloads:
                await conn.execute(_UPSERT_JOURNEY_ZONES_SQL, association_payloads)

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

            modal, max_time_minutes, radius_meters, dataset_version_id = _extract_zone_config(
                context["input_snapshot"]
            )
            transport_point_id = context["transport_point_id"]
            lat = context["lat"]
            lon = context["lon"]
            if _is_direct_isochrone_modal(modal):
                reference_point = _extract_reference_point(context["input_snapshot"])
                if reference_point is not None:
                    lat, lon = reference_point
                transport_point_id = None
            if lat is None or lon is None:
                raise RuntimeError("Zone generation requires a valid reference point")
            if not _is_direct_isochrone_modal(modal) and transport_point_id is None:
                raise RuntimeError("Zone generation requires at least one transport point")

            return await self._persist_single_isochrone_zone(
                conn,
                journey_id=context["journey_id"],
                transport_point_id=transport_point_id,
                lat=float(lat),
                lon=float(lon),
                modal=modal,
                max_time_minutes=max_time_minutes,
                radius_meters=radius_meters,
                dataset_version_id=dataset_version_id,
            )

    async def list_zones_for_journey(self, journey_id: UUID) -> list[dict[str, Any]]:
        """Return all zones for a journey ordered by travel_time_minutes."""
        engine = get_engine()
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    """
                    SELECT
                        z.id,
                        jz.journey_id,
                        z.transport_point_id,
                        z.fingerprint,
                        z.state,
                        z.is_circle_fallback,
                        z.max_time_minutes  AS travel_time_minutes,
                        z.green_area_m2,
                        z.flood_area_m2,
                        z.safety_incidents_count,
                        z.poi_counts,
                        z.poi_points,
                        z.badges,
                        z.badges_provisional,
                        z.created_at,
                        z.updated_at
                    FROM journey_zones jz
                    JOIN zones z ON z.id = jz.zone_id
                    WHERE jz.journey_id = :journey_id
                    ORDER BY z.max_time_minutes ASC, z.created_at ASC
                    """
                ),
                {"journey_id": journey_id},
            )
            rows = result.mappings().fetchall()
            return [dict(row) for row in rows]
