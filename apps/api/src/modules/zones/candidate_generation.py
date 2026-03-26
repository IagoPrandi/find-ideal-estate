from __future__ import annotations

from dataclasses import dataclass
import json
import math
import re
from typing import Any

import networkx as nx
from core.db import get_engine
from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import linemerge, transform as shp_transform
from sqlalchemy import text

EPSG_WGS84 = "EPSG:4326"
EPSG_UTM_SP = "EPSG:31983"
_TO_UTM = Transformer.from_crs(EPSG_WGS84, EPSG_UTM_SP, always_xy=True)
_TO_WGS = Transformer.from_crs(EPSG_UTM_SP, EPSG_WGS84, always_xy=True)
_GTFS_TIME_RE = re.compile(r"^[0-9]+:[0-9]{2}:[0-9]{2}$")


class CandidateZoneGenerationError(RuntimeError):
    """Raised when candidate zones cannot be generated from current datasets."""


@dataclass(frozen=True)
class CandidateZone:
    logical_id: str
    mode: str
    source_point_id: str
    travel_time_minutes: float
    centroid_lon: float
    centroid_lat: float
    geometry: dict[str, Any]


@dataclass(frozen=True)
class PointCandidate:
    candidate_id: str
    mode: str
    source_point_id: str
    travel_time_minutes: float
    lon: float
    lat: float


@dataclass(frozen=True)
class RailStation:
    station_id: str
    mode: str
    line_name: str
    short_name: str
    point_wgs: BaseGeometry
    point_utm: BaseGeometry


@dataclass(frozen=True)
class RailLine:
    line_id: str
    mode: str
    line_name: str
    short_name: str
    geometry_utm: BaseGeometry


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(str(value).strip().lower().split())


def _normalize_public_transport_mode(value: Any) -> str:
    normalized = _normalize_text(str(value) if value is not None else None)
    if normalized in {"", "mixed", "transit", "public", "public_transport", "bus+rail", "bus+metro+trem"}:
        return "mixed"
    if normalized in {"bus", "onibus"}:
        return "bus"
    if normalized in {"rail", "metro", "train", "trem", "subway"}:
        return "rail"
    return "mixed"


def _to_utm(geometry: BaseGeometry) -> BaseGeometry:
    return shp_transform(_TO_UTM.transform, geometry)


def _to_wgs(geometry: BaseGeometry) -> BaseGeometry:
    return shp_transform(_TO_WGS.transform, geometry)


def _distance_squared(x1: float, y1: float, x2: float, y2: float) -> float:
    dx = x1 - x2
    dy = y1 - y2
    return dx * dx + dy * dy


def _bucketize_candidates(candidates: list[PointCandidate], step_minutes: int) -> list[PointCandidate]:
    step = max(step_minutes, 1)
    selected: dict[int, PointCandidate] = {}
    for candidate in sorted(candidates, key=lambda item: item.travel_time_minutes):
        bucket = int(math.floor(candidate.travel_time_minutes / step))
        current = selected.get(bucket)
        if current is None or candidate.travel_time_minutes < current.travel_time_minutes:
            selected[bucket] = candidate
    return list(selected.values())


def _dedupe_point_candidates(candidates: list[PointCandidate], radius_meters: float) -> list[PointCandidate]:
    if not candidates:
        return []

    radius_squared = float(radius_meters) * float(radius_meters)
    kept: list[PointCandidate] = []
    kept_xy: list[tuple[float, float]] = []

    for candidate in sorted(candidates, key=lambda item: item.travel_time_minutes):
        x, y = _TO_UTM.transform(candidate.lon, candidate.lat)
        duplicate = False
        for kept_x, kept_y in kept_xy:
            if _distance_squared(x, y, kept_x, kept_y) <= radius_squared:
                duplicate = True
                break
        if duplicate:
            continue
        kept.append(candidate)
        kept_xy.append((x, y))

    return kept


def _buffer_candidate(candidate: PointCandidate, radius_meters: int) -> CandidateZone:
    point_wgs = Point(candidate.lon, candidate.lat)
    point_utm = _to_utm(point_wgs)
    buffer_wgs = _to_wgs(point_utm.buffer(radius_meters))
    centroid = buffer_wgs.centroid
    return CandidateZone(
        logical_id=candidate.candidate_id,
        mode=candidate.mode,
        source_point_id=candidate.source_point_id,
        travel_time_minutes=candidate.travel_time_minutes,
        centroid_lon=float(centroid.x),
        centroid_lat=float(centroid.y),
        geometry=json.loads(json.dumps(buffer_wgs.__geo_interface__, ensure_ascii=True)),
    )


_BUS_DOWNSTREAM_SQL = text(
    """
    WITH reference AS (
        SELECT ST_SetSRID(ST_MakePoint(CAST(:seed_lon AS DOUBLE PRECISION), CAST(:seed_lat AS DOUBLE PRECISION)), 4326) AS geom
    ),
    nearby_origins AS (
        SELECT
            s.stop_id,
            ST_Distance(s.location::geography, reference.geom::geography) AS distance_m
        FROM gtfs_stops s
        CROSS JOIN reference
        WHERE ST_DWithin(s.location::geography, reference.geom::geography, CAST(:seed_max_distance_meters AS DOUBLE PRECISION))
    ),
    origin_times_raw AS (
        SELECT
            nearby.stop_id AS origin_stop_id,
            st.trip_id,
            st.stop_sequence AS origin_sequence,
            (
                split_part(st.departure_time, ':', 1)::int * 3600
                + split_part(st.departure_time, ':', 2)::int * 60
                + split_part(st.departure_time, ':', 3)::int
            ) AS origin_departure_sec
        FROM nearby_origins nearby
        JOIN gtfs_stop_times st ON st.stop_id = nearby.stop_id
        WHERE st.departure_time ~ :time_pattern
    ),
    origin_times AS (
        SELECT DISTINCT ON (origin_stop_id, trip_id)
            origin_stop_id,
            trip_id,
            origin_sequence,
            origin_departure_sec
        FROM origin_times_raw
        ORDER BY origin_stop_id, trip_id, origin_departure_sec ASC, origin_sequence ASC
    ),
    downstream AS (
        SELECT
            candidate.stop_id,
            trips.route_id,
            (
                split_part(candidate.arrival_time, ':', 1)::int * 3600
                + split_part(candidate.arrival_time, ':', 2)::int * 60
                + split_part(candidate.arrival_time, ':', 3)::int
            ) AS arrival_sec,
            origin.origin_departure_sec
        FROM origin_times origin
        JOIN gtfs_stop_times candidate
          ON candidate.trip_id = origin.trip_id
         AND candidate.stop_sequence > origin.origin_sequence
        JOIN gtfs_trips trips ON trips.trip_id = candidate.trip_id
        WHERE candidate.arrival_time ~ :time_pattern
                    AND candidate.stop_id <> origin.origin_stop_id
                    AND NOT EXISTS (
                            SELECT 1
                            FROM nearby_origins seed_area
                            WHERE seed_area.stop_id = candidate.stop_id
                    )
    )
    SELECT
        d.stop_id,
        COALESCE(NULLIF(s.stop_name, ''), d.stop_id) AS stop_name,
        s.stop_lon,
        s.stop_lat,
        MIN((d.arrival_sec - d.origin_departure_sec) / 60.0) AS travel_time_minutes,
        ARRAY_AGG(DISTINCT d.route_id) FILTER (WHERE d.route_id IS NOT NULL) AS route_ids
    FROM downstream d
    JOIN gtfs_stops s ON s.stop_id = d.stop_id
    WHERE d.arrival_sec > d.origin_departure_sec
      AND d.arrival_sec - d.origin_departure_sec <= :max_time_seconds
    GROUP BY d.stop_id, s.stop_name, s.stop_lon, s.stop_lat
    ORDER BY travel_time_minutes ASC, d.stop_id ASC
    """
)


_RAIL_STATIONS_SQL = text(
    """
    SELECT
        CAST(:prefix AS text) || md5(ST_AsEWKB(ST_PointOnSurface(geometry))::text) AS station_id,
        CAST(:mode AS text) AS mode,
        COALESCE(NULLIF(nm_linha_metro_trem, ''), '') AS line_name,
        ''::text AS short_name,
        ST_AsGeoJSON(ST_PointOnSurface(geometry)) AS point_geojson
    FROM {table_name}
    WHERE geometry IS NOT NULL
    """
)


_METRO_LINES_SQL = text(
    """
    SELECT
        md5(ST_AsEWKB(ST_LineMerge(geometry))::text) AS line_id,
        CAST(:mode AS text) AS mode,
        COALESCE(NULLIF(nm_linha_metro_trem, ''), NULLIF(nr_nome_linha, ''), :fallback_name) AS line_name,
        COALESCE(NULLIF(nr_nome_linha, ''), '') AS short_name,
        ST_AsGeoJSON(ST_LineMerge(geometry)) AS line_geojson
    FROM {table_name}
    WHERE geometry IS NOT NULL
    """
)


_TREM_LINES_SQL = text(
    """
    SELECT
        md5(ST_AsEWKB(ST_LineMerge(geometry))::text) AS line_id,
        CAST(:mode AS text) AS mode,
        COALESCE(NULLIF(nm_linha_metro_trem, ''), :fallback_name) AS line_name,
        ''::text AS short_name,
        ST_AsGeoJSON(ST_LineMerge(geometry)) AS line_geojson
    FROM {table_name}
    WHERE geometry IS NOT NULL
    """
)


_BUS_DATASET_AVAILABILITY_SQL = text(
    """
    SELECT
        CASE
            WHEN to_regclass('gtfs_stops') IS NULL THEN 0
            ELSE (SELECT count(*)::bigint FROM gtfs_stops)
        END AS gtfs_stops_count,
        CASE
            WHEN to_regclass('gtfs_trips') IS NULL THEN 0
            ELSE (SELECT count(*)::bigint FROM gtfs_trips)
        END AS gtfs_trips_count,
        CASE
            WHEN to_regclass('gtfs_stop_times') IS NULL THEN 0
            ELSE (SELECT count(*)::bigint FROM gtfs_stop_times)
        END AS gtfs_stop_times_count
    """
)


_RAIL_DATASET_AVAILABILITY_SQL = text(
    """
    SELECT
        CASE
            WHEN to_regclass('geosampa_metro_stations') IS NULL THEN 0
            ELSE (SELECT count(*)::bigint FROM geosampa_metro_stations)
        END AS metro_stations_count,
        CASE
            WHEN to_regclass('geosampa_trem_stations') IS NULL THEN 0
            ELSE (SELECT count(*)::bigint FROM geosampa_trem_stations)
        END AS trem_stations_count,
        CASE
            WHEN to_regclass('geosampa_metro_lines') IS NULL THEN 0
            ELSE (SELECT count(*)::bigint FROM geosampa_metro_lines)
        END AS metro_lines_count,
        CASE
            WHEN to_regclass('geosampa_trem_lines') IS NULL THEN 0
            ELSE (SELECT count(*)::bigint FROM geosampa_trem_lines)
        END AS trem_lines_count
    """
)


async def _load_bus_candidates(
    seed_lat: float,
    seed_lon: float,
    max_time_minutes: int,
    *,
    seed_max_distance_meters: float,
    bucket_minutes: int,
    max_candidates: int,
    dedupe_radius_meters: float,
) -> list[PointCandidate]:
    engine = get_engine()
    async with engine.connect() as conn:
        availability_result = await conn.execute(_BUS_DATASET_AVAILABILITY_SQL)
        availability = availability_result.mappings().one()
        if (
            int(availability["gtfs_stops_count"] or 0) <= 0
            or int(availability["gtfs_trips_count"] or 0) <= 0
            or int(availability["gtfs_stop_times_count"] or 0) <= 0
        ):
            raise CandidateZoneGenerationError(
                "GTFS dataset is unavailable or empty in database (required: gtfs_stops, gtfs_trips, gtfs_stop_times). Run phase-3 GTFS ingestion before generating bus candidate zones"
            )

        downstream_result = await conn.execute(
            _BUS_DOWNSTREAM_SQL,
            {
                "seed_lat": seed_lat,
                "seed_lon": seed_lon,
                "seed_max_distance_meters": float(seed_max_distance_meters),
                "max_time_seconds": int(max_time_minutes) * 60,
                "time_pattern": _GTFS_TIME_RE.pattern,
            },
        )
        rows = downstream_result.mappings().all()

    candidates = [
        PointCandidate(
            candidate_id=f"bus:{row['stop_id']}",
            mode="bus",
            source_point_id=str(row["stop_id"]),
            travel_time_minutes=float(row["travel_time_minutes"]),
            lon=float(row["stop_lon"]),
            lat=float(row["stop_lat"]),
        )
        for row in rows
        if row["stop_id"]
    ]
    candidates = _bucketize_candidates(candidates, bucket_minutes)
    candidates.sort(key=lambda item: item.travel_time_minutes)
    candidates = candidates[: max(1, max_candidates)]
    return _dedupe_point_candidates(candidates, dedupe_radius_meters)


async def _load_rail_records() -> tuple[list[RailStation], list[RailLine]]:
    engine = get_engine()
    stations: list[RailStation] = []
    lines: list[RailLine] = []

    station_sources = (
        ("geosampa_metro_stations", "M:", "rail"),
        ("geosampa_trem_stations", "T:", "rail"),
    )
    line_sources = (
        (text(_METRO_LINES_SQL.text.format(table_name="geosampa_metro_lines")), "rail", "Linha de metro"),
        (text(_TREM_LINES_SQL.text.format(table_name="geosampa_trem_lines")), "rail", "Linha de trem"),
    )

    async with engine.connect() as conn:
        availability_result = await conn.execute(_RAIL_DATASET_AVAILABILITY_SQL)
        availability = availability_result.mappings().one()
        total_station_rows = int(availability["metro_stations_count"] or 0) + int(availability["trem_stations_count"] or 0)
        total_line_rows = int(availability["metro_lines_count"] or 0) + int(availability["trem_lines_count"] or 0)
        if total_station_rows <= 0 or total_line_rows <= 0:
            return [], []

        for table_name, prefix, mode in station_sources:
            sql = text(_RAIL_STATIONS_SQL.text.format(table_name=table_name))
            result = await conn.execute(sql, {"prefix": prefix, "mode": mode})
            for row in result.mappings():
                point_wgs = shape(json.loads(row["point_geojson"]))
                stations.append(
                    RailStation(
                        station_id=str(row["station_id"]),
                        mode=mode,
                        line_name=str(row["line_name"] or ""),
                        short_name=str(row["short_name"] or ""),
                        point_wgs=point_wgs,
                        point_utm=_to_utm(point_wgs),
                    )
                )

        for sql, mode, fallback_name in line_sources:
            result = await conn.execute(
                sql,
                {"mode": mode, "fallback_name": fallback_name},
            )
            for row in result.mappings():
                line_geometry = shape(json.loads(row["line_geojson"]))
                line_geometry_utm = _to_utm(line_geometry)
                if line_geometry_utm.geom_type == "MultiLineString":
                    merged = linemerge(line_geometry_utm)
                    line_geometry_utm = merged if not merged.is_empty else line_geometry_utm
                lines.append(
                    RailLine(
                        line_id=str(row["line_id"]),
                        mode=mode,
                        line_name=str(row["line_name"] or ""),
                        short_name=str(row["short_name"] or ""),
                        geometry_utm=line_geometry_utm,
                    )
                )

    return stations, lines


def _station_matches_line(station: RailStation, line: RailLine, snap_distance_meters: float) -> bool:
    station_line = _normalize_text(station.line_name)
    station_short = _normalize_text(station.short_name)
    line_name = _normalize_text(line.line_name)
    line_short = _normalize_text(line.short_name)
    if station_line and station_line in {line_name, line_short}:
        return True
    if station_short and station_short in {line_name, line_short}:
        return True
    return station.point_utm.distance(line.geometry_utm) <= snap_distance_meters


def _build_rail_graph(
    stations: list[RailStation],
    lines: list[RailLine],
    *,
    transfer_walk_meters: float,
    transfer_penalty_minutes: float,
    walk_speed_mps: float,
    rail_speed_kmh: float,
    snap_distance_meters: float,
) -> nx.Graph:
    graph = nx.Graph()
    for station in stations:
        graph.add_node(station.station_id)

    rail_speed_mps = max((rail_speed_kmh * 1000.0) / 3600.0, 0.1)
    for line in lines:
        matches = [station for station in stations if _station_matches_line(station, line, snap_distance_meters)]
        if len(matches) < 2:
            continue
        ordered = sorted(matches, key=lambda station: line.geometry_utm.project(station.point_utm))
        for current, nxt in zip(ordered[:-1], ordered[1:]):
            distance_m = current.point_utm.distance(nxt.point_utm)
            if distance_m <= 0:
                continue
            weight = (distance_m / rail_speed_mps) / 60.0
            if graph.has_edge(current.station_id, nxt.station_id):
                existing = graph[current.station_id][nxt.station_id].get("weight", float("inf"))
                if weight >= existing:
                    continue
            graph.add_edge(current.station_id, nxt.station_id, weight=weight, line_id=line.line_id)

    transfer_radius_squared = float(transfer_walk_meters) * float(transfer_walk_meters)
    for index, current in enumerate(stations):
        current_x = current.point_utm.x
        current_y = current.point_utm.y
        for nxt in stations[index + 1 :]:
            distance_squared = _distance_squared(current_x, current_y, nxt.point_utm.x, nxt.point_utm.y)
            if distance_squared > transfer_radius_squared:
                continue
            distance_m = math.sqrt(distance_squared)
            weight = (distance_m / max(walk_speed_mps, 0.1)) / 60.0 + transfer_penalty_minutes
            if graph.has_edge(current.station_id, nxt.station_id):
                existing = graph[current.station_id][nxt.station_id].get("weight", float("inf"))
                if weight >= existing:
                    continue
            graph.add_edge(current.station_id, nxt.station_id, weight=weight, line_id="transfer")

    return graph


def _nearest_rail_seed(
    seed_lat: float,
    seed_lon: float,
    stations: list[RailStation],
    *,
    seed_max_distance_meters: float,
) -> RailStation | None:
    if not stations:
        return None
    seed_point_utm = _to_utm(Point(seed_lon, seed_lat))
    best_station: RailStation | None = None
    best_distance = float("inf")
    for station in stations:
        distance = seed_point_utm.distance(station.point_utm)
        if distance < best_distance:
            best_station = station
            best_distance = distance
    if best_station is None or best_distance > seed_max_distance_meters:
        return None
    return best_station


async def _load_rail_candidates(
    seed_lat: float,
    seed_lon: float,
    max_time_minutes: int,
    *,
    seed_max_distance_meters: float,
    dedupe_radius_meters: float,
    transfer_walk_meters: float,
    transfer_penalty_minutes: float,
    walk_speed_mps: float,
    rail_speed_kmh: float,
    snap_distance_meters: float,
    require_dataset: bool = False,
) -> list[PointCandidate]:
    stations, lines = await _load_rail_records()
    if require_dataset and (not stations or not lines):
        raise CandidateZoneGenerationError(
            "GeoSampa rail dataset is unavailable or empty in database (required: geosampa_metro_stations/trem_stations and geosampa_metro_lines/trem_lines). Run phase-3 GeoSampa ingestion before generating rail candidate zones"
        )
    if not stations or not lines:
        return []

    seed_station = _nearest_rail_seed(
        seed_lat,
        seed_lon,
        stations,
        seed_max_distance_meters=seed_max_distance_meters,
    )
    if seed_station is None:
        return []

    graph = _build_rail_graph(
        stations,
        lines,
        transfer_walk_meters=transfer_walk_meters,
        transfer_penalty_minutes=transfer_penalty_minutes,
        walk_speed_mps=walk_speed_mps,
        rail_speed_kmh=rail_speed_kmh,
        snap_distance_meters=snap_distance_meters,
    )
    if seed_station.station_id not in graph:
        return []

    reachable = nx.single_source_dijkstra_path_length(
        graph,
        seed_station.station_id,
        cutoff=float(max_time_minutes),
        weight="weight",
    )

    candidates = []
    for station in stations:
        if station.station_id == seed_station.station_id:
            continue
        travel_time = reachable.get(station.station_id)
        if travel_time is None:
            continue
        candidates.append(
            PointCandidate(
                candidate_id=f"rail:{station.station_id}",
                mode="rail",
                source_point_id=station.station_id,
                travel_time_minutes=float(travel_time),
                lon=float(station.point_wgs.x),
                lat=float(station.point_wgs.y),
            )
        )

    return _dedupe_point_candidates(candidates, dedupe_radius_meters)


async def generate_candidate_zones_for_seed(
    *,
    seed_lat: float,
    seed_lon: float,
    max_time_minutes: int,
    radius_meters: int,
    public_transport_mode: str | None = None,
    bus_seed_max_distance_meters: float = 250.0,
    rail_seed_max_distance_meters: float = 1200.0,
    dedupe_radius_meters: float = 50.0,
    bus_bucket_minutes: int = 2,
    bus_max_candidates: int = 60,
    transfer_walk_meters: float = 500.0,
    transfer_penalty_minutes: float = 4.0,
    walk_speed_mps: float = 1.25,
    rail_speed_kmh: float = 45.0,
    line_snap_distance_meters: float = 80.0,
) -> list[CandidateZone]:
    normalized_public_transport_mode = _normalize_public_transport_mode(public_transport_mode)
    bus_candidates: list[PointCandidate] = []
    rail_candidates: list[PointCandidate] = []

    if normalized_public_transport_mode in {"bus", "mixed"}:
        bus_candidates = await _load_bus_candidates(
            seed_lat,
            seed_lon,
            max_time_minutes,
            seed_max_distance_meters=bus_seed_max_distance_meters,
            bucket_minutes=bus_bucket_minutes,
            max_candidates=bus_max_candidates,
            dedupe_radius_meters=dedupe_radius_meters,
        )
    if normalized_public_transport_mode in {"rail", "mixed"}:
        rail_candidates = await _load_rail_candidates(
            seed_lat,
            seed_lon,
            max_time_minutes,
            seed_max_distance_meters=rail_seed_max_distance_meters,
            dedupe_radius_meters=dedupe_radius_meters,
            transfer_walk_meters=transfer_walk_meters,
            transfer_penalty_minutes=transfer_penalty_minutes,
            walk_speed_mps=walk_speed_mps,
            rail_speed_kmh=rail_speed_kmh,
            snap_distance_meters=line_snap_distance_meters,
            require_dataset=normalized_public_transport_mode == "rail",
        )

    combined = _dedupe_point_candidates(
        bus_candidates + rail_candidates,
        dedupe_radius_meters,
    )
    if not combined:
        if normalized_public_transport_mode == "bus":
            raise CandidateZoneGenerationError(
                "No bus candidate zones could be generated from GTFS/GeoSampa for the selected seed"
            )
        if normalized_public_transport_mode == "rail":
            raise CandidateZoneGenerationError(
                "No rail candidate zones could be generated from GTFS/GeoSampa for the selected seed"
            )
        raise CandidateZoneGenerationError(
            "No candidate zones could be generated from GTFS/GeoSampa for the selected seed"
        )

    combined.sort(key=lambda candidate: (candidate.travel_time_minutes, candidate.mode, candidate.source_point_id))
    return [_buffer_candidate(candidate, radius_meters) for candidate in combined]