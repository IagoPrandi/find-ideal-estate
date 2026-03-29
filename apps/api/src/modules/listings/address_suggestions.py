from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import unicodedata
from typing import Any

import httpx
from core.redis import get_redis

logger = logging.getLogger(__name__)

EARTH_RADIUS_M = 6_378_137.0
_SUGGESTIONS_CACHE_TTL_SECONDS = 1_800
_MAPBOX_TILEQUERY_URL = "https://api.mapbox.com/v4/mapbox.mapbox-streets-v8/tilequery/{lon:.6f},{lat:.6f}.json"
_MAPBOX_REVERSE_URL = "https://api.mapbox.com/geocoding/v5/mapbox.places/{lon:.6f},{lat:.6f}.json"
_DIRECT_ADDRESS_MODAL_STRATEGY = {"walking", "car"}


def _meters_to_lat_deg(meters: float) -> float:
    return (meters / EARTH_RADIUS_M) * (180.0 / math.pi)


def _meters_to_lon_deg(meters: float, lat_deg: float) -> float:
    lat_rad = math.radians(lat_deg)
    return (meters / (EARTH_RADIUS_M * max(1e-12, math.cos(lat_rad)))) * (180.0 / math.pi)


def _normalize_text(value: str) -> str:
    lowered = (value or "").strip().lower()
    lowered = unicodedata.normalize("NFKD", lowered)
    lowered = lowered.encode("ascii", "ignore").decode("ascii")
    return " ".join(lowered.split())


def _format_street_address(street: str, neighborhood: str, city: str, state: str) -> str:
    parts = [street.strip()]
    if neighborhood.strip():
        parts.append(neighborhood.strip())
    if city.strip():
        parts.append(city.strip())
    state_code = (state or "").strip().upper()
    if state_code:
        parts.append(state_code)
    label = ", ".join(part for part in parts if part)
    return label


def _cache_key(zone_fingerprint: str) -> str:
    digest = hashlib.sha256(zone_fingerprint.encode("utf-8")).hexdigest()[:20]
    return f"zone_address_suggestions:v3:{digest}"


def _normalize_modal(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"walk", "pedestrian"}:
        return "walking"
    if normalized in {"drive", "driving", "auto"}:
        return "car"
    return normalized


def _point_on_segment(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> bool:
    cross = (py - y1) * (x2 - x1) - (px - x1) * (y2 - y1)
    if abs(cross) > 1e-9:
        return False
    dot = (px - x1) * (px - x2) + (py - y1) * (py - y2)
    return dot <= 1e-9


def _point_in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    inside = False
    count = len(ring)
    if count < 3:
        return False
    for idx in range(count):
        x1, y1 = ring[idx]
        x2, y2 = ring[(idx + 1) % count]
        if _point_on_segment(lon, lat, x1, y1, x2, y2):
            return True
        intersects = ((y1 > lat) != (y2 > lat)) and (
            lon < ((x2 - x1) * (lat - y1) / ((y2 - y1) or 1e-12) + x1)
        )
        if intersects:
            inside = not inside
    return inside


def _point_in_polygon(lon: float, lat: float, polygon_coords: list[list[list[float]]]) -> bool:
    if not polygon_coords:
        return False
    if not _point_in_ring(lon, lat, polygon_coords[0]):
        return False
    for hole in polygon_coords[1:]:
        if _point_in_ring(lon, lat, hole):
            return False
    return True


def _point_in_geometry(lon: float, lat: float, geometry: dict[str, Any]) -> bool:
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geometry_type == "Polygon" and isinstance(coordinates, list):
        return _point_in_polygon(lon, lat, coordinates)
    if geometry_type == "MultiPolygon" and isinstance(coordinates, list):
        return any(_point_in_polygon(lon, lat, polygon) for polygon in coordinates)
    return False


def _generate_points_within_geometry(
    *,
    geometry: dict[str, Any],
    bbox: tuple[float, float, float, float],
    centroid: tuple[float, float],
    step_m: float,
) -> list[tuple[float, float]]:
    min_lon, min_lat, max_lon, max_lat = bbox
    lat_step = _meters_to_lat_deg(step_m)
    points: list[tuple[float, float]] = []
    seen: set[tuple[float, float]] = set()

    lat = min_lat
    while lat <= max_lat + 1e-12:
        lon_step = _meters_to_lon_deg(step_m, lat)
        lon = min_lon
        while lon <= max_lon + 1e-12:
            if _point_in_geometry(lon, lat, geometry):
                rounded = (round(lon, 6), round(lat, 6))
                if rounded not in seen:
                    seen.add(rounded)
                    points.append(rounded)
            lon += lon_step
        lat += lat_step

    centroid_point = (round(centroid[0], 6), round(centroid[1], 6))
    if _point_in_geometry(centroid_point[0], centroid_point[1], geometry) and centroid_point not in seen:
        points.append(centroid_point)

    return points


async def _tilequery_road_names(
    client: httpx.AsyncClient,
    *,
    access_token: str,
    lon: float,
    lat: float,
    radius_m: float,
    language_pref: str,
) -> set[str]:
    response = await client.get(
        _MAPBOX_TILEQUERY_URL.format(lon=lon, lat=lat),
        params={
            "access_token": access_token,
            "layers": "road",
            "geometry": "linestring",
            "radius": float(radius_m),
            "limit": 50,
            "dedupe": "true",
        },
    )
    response.raise_for_status()
    payload = response.json()

    results: set[str] = set()
    for feature in payload.get("features", []):
        props = feature.get("properties") or {}
        name = props.get(f"name_{language_pref}") or props.get("name")
        if isinstance(name, str) and name.strip():
            results.add(name.strip())
    return results


async def _reverse_geocode_context(
    client: httpx.AsyncClient,
    *,
    access_token: str,
    lon: float,
    lat: float,
    language_pref: str,
) -> tuple[str, str, str]:
    response = await client.get(
        _MAPBOX_REVERSE_URL.format(lon=lon, lat=lat),
        params={
            "access_token": access_token,
            "types": "neighborhood,locality,place,region",
            "language": language_pref,
        },
    )
    response.raise_for_status()
    payload = response.json()

    neighborhood = ""
    city = ""
    state = ""
    for feature in payload.get("features", []):
        place_type = feature.get("place_type", [])
        text = (feature.get("text") or "").strip()
        if not neighborhood and any(item in place_type for item in ("neighborhood", "locality")):
            neighborhood = text
        elif not city and "place" in place_type:
            city = text
        elif not state and "region" in place_type:
            short_code = ((feature.get("properties") or {}).get("short_code") or "").strip()
            if short_code and "-" in short_code:
                state = short_code.split("-")[-1].upper()
            elif len(text) == 2:
                state = text.upper()
    return neighborhood, city, state


async def _build_zone_address_suggestions(
    *,
    access_token: str,
    zone_fingerprint: str,
    geometry: dict[str, Any],
    bbox: tuple[float, float, float, float],
    centroid: tuple[float, float],
    step_m: float,
    tilequery_radius_m: float,
    max_concurrency: int,
    language_pref: str,
) -> list[dict[str, Any]]:
    del zone_fingerprint
    points = _generate_points_within_geometry(
        geometry=geometry,
        bbox=bbox,
        centroid=centroid,
        step_m=step_m,
    )
    if not points:
        return []

    semaphore = asyncio.Semaphore(max(1, int(max_concurrency)))
    street_to_point: dict[str, tuple[str, tuple[float, float]]] = {}

    async with httpx.AsyncClient(timeout=10.0) as client:
        async def run_tilequery(point: tuple[float, float]) -> tuple[tuple[float, float], set[str]]:
            async with semaphore:
                names = await _tilequery_road_names(
                    client,
                    access_token=access_token,
                    lon=point[0],
                    lat=point[1],
                    radius_m=tilequery_radius_m,
                    language_pref=language_pref,
                )
                return point, names

        tilequery_results = await asyncio.gather(
            *(run_tilequery(point) for point in points),
            return_exceptions=True,
        )
        for result in tilequery_results:
            if isinstance(result, Exception):
                logger.warning("tilequery failed while building address suggestions", exc_info=result)
                continue
            point, names = result
            for street_name in names:
                key = _normalize_text(street_name)
                if key and key not in street_to_point:
                    street_to_point[key] = (street_name, point)

        if not street_to_point:
            return []

        unique_points = sorted({item[1] for item in street_to_point.values()})

        async def run_reverse(point: tuple[float, float]) -> tuple[tuple[float, float], tuple[str, str, str]]:
            async with semaphore:
                context = await _reverse_geocode_context(
                    client,
                    access_token=access_token,
                    lon=point[0],
                    lat=point[1],
                    language_pref=language_pref,
                )
                return point, context

        reverse_results = await asyncio.gather(
            *(run_reverse(point) for point in unique_points),
            return_exceptions=True,
        )

    point_to_context: dict[tuple[float, float], tuple[str, str, str]] = {}
    for result in reverse_results:
        if isinstance(result, Exception):
            logger.warning("reverse geocode failed while building address suggestions", exc_info=result)
            continue
        point, context = result
        point_to_context[point] = context

    suggestions: list[dict[str, Any]] = []
    seen_labels: set[str] = set()
    for street_name, point in sorted(street_to_point.values(), key=lambda item: _normalize_text(item[0])):
        neighborhood, city, state = point_to_context.get(point, ("", "Sao Paulo", "SP"))
        city_name = city or "Sao Paulo"
        state_code = state or "SP"
        label = _format_street_address(street_name, neighborhood, city_name, state_code)
        normalized = _normalize_text(label)
        if normalized in seen_labels:
            continue
        seen_labels.add(normalized)
        suggestions.append(
            {
                "label": label,
                "normalized": normalized,
                "location_type": "street",
                "lat": point[1],
                "lon": point[0],
            }
        )

    return suggestions


async def _build_direct_radius_address_suggestions(
    *,
    access_token: str,
    centroid: tuple[float, float],
    search_radius_m: float,
    language_pref: str,
) -> list[dict[str, Any]]:
    if search_radius_m <= 0:
        return []

    center_lon = float(centroid[0])
    center_lat = float(centroid[1])

    async with httpx.AsyncClient(timeout=10.0) as client:
        street_names = await _tilequery_road_names(
            client,
            access_token=access_token,
            lon=center_lon,
            lat=center_lat,
            radius_m=search_radius_m,
            language_pref=language_pref,
        )
        if not street_names:
            return []

        neighborhood, city, state = await _reverse_geocode_context(
            client,
            access_token=access_token,
            lon=center_lon,
            lat=center_lat,
            language_pref=language_pref,
        )

    city_name = city or "Sao Paulo"
    state_code = state or "SP"
    suggestions: list[dict[str, Any]] = []
    seen_labels: set[str] = set()
    for street_name in sorted(street_names, key=_normalize_text):
        label = _format_street_address(street_name, neighborhood, city_name, state_code)
        normalized = _normalize_text(label)
        if normalized in seen_labels:
            continue
        seen_labels.add(normalized)
        suggestions.append(
            {
                "label": label,
                "normalized": normalized,
                "location_type": "street",
                "lat": center_lat,
                "lon": center_lon,
            }
        )

    return suggestions


async def get_zone_address_suggestions(
    *,
    access_token: str,
    zone_fingerprint: str,
    geometry: dict[str, Any],
    bbox: tuple[float, float, float, float],
    centroid: tuple[float, float],
    q: str,
    modal: str | None = None,
    search_radius_m: float | None = None,
    step_m: float = 150.0,
    tilequery_radius_m: float = 120.0,
    max_concurrency: int = 8,
    language_pref: str = "pt",
) -> list[dict[str, Any]]:
    redis = get_redis()
    cache_key = _cache_key(zone_fingerprint)
    cached = await redis.get(cache_key)

    if cached:
        suggestions = json.loads(cached)
    else:
        normalized_modal = _normalize_modal(modal)
        if normalized_modal in _DIRECT_ADDRESS_MODAL_STRATEGY and search_radius_m is not None:
            suggestions = await _build_direct_radius_address_suggestions(
                access_token=access_token,
                centroid=centroid,
                search_radius_m=float(search_radius_m),
                language_pref=language_pref,
            )
        else:
            suggestions = await _build_zone_address_suggestions(
                access_token=access_token,
                zone_fingerprint=zone_fingerprint,
                geometry=geometry,
                bbox=bbox,
                centroid=centroid,
                step_m=step_m,
                tilequery_radius_m=tilequery_radius_m,
                max_concurrency=max_concurrency,
                language_pref=language_pref,
            )
        await redis.set(
            cache_key,
            json.dumps(suggestions, ensure_ascii=False),
            ex=_SUGGESTIONS_CACHE_TTL_SECONDS,
        )

    normalized_query = _normalize_text(q)
    if not normalized_query:
        return suggestions
    return [item for item in suggestions if normalized_query in item.get("normalized", "")]