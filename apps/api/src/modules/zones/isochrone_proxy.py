"""Helpers to represent an isochrone as a centroid-based equivalent-area circle."""

from __future__ import annotations

import math
from typing import Any

EARTH_RADIUS_M = 6_378_137.0
ISOCHRONE_PROXY_SEARCH_STRATEGY = "centroid_equivalent_circle"


def _meters_to_lat_deg(meters: float) -> float:
    return (meters / EARTH_RADIUS_M) * (180.0 / math.pi)


def _meters_to_lon_deg(meters: float, lat_deg: float) -> float:
    lat_rad = math.radians(lat_deg)
    return (meters / (EARTH_RADIUS_M * max(1e-12, math.cos(lat_rad)))) * (180.0 / math.pi)


def equivalent_circle_radius_m(*, area_m2: float) -> float:
    area = float(area_m2)
    if area <= 0:
        raise ValueError("Isochrone area_m2 must be positive to build a proxy circle")
    return math.sqrt(area / math.pi)


def build_isochrone_proxy_circle(
    *,
    lon: float,
    lat: float,
    area_m2: float,
    segments: int = 64,
) -> dict[str, Any]:
    radius_m = equivalent_circle_radius_m(area_m2=area_m2)
    center_lon = float(lon)
    center_lat = float(lat)
    lat_delta = _meters_to_lat_deg(radius_m)
    lon_delta = _meters_to_lon_deg(radius_m, center_lat)

    ring: list[list[float]] = []
    total_segments = max(16, int(segments))
    for index in range(total_segments):
        theta = (2.0 * math.pi * index) / total_segments
        lat_offset_m = radius_m * math.sin(theta)
        point_lat = center_lat + _meters_to_lat_deg(lat_offset_m)
        lon_offset_m = radius_m * math.cos(theta)
        point_lon = center_lon + _meters_to_lon_deg(lon_offset_m, point_lat)
        ring.append([point_lon, point_lat])
    ring.append(ring[0])

    return {
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "bbox": (
            center_lon - lon_delta,
            center_lat - lat_delta,
            center_lon + lon_delta,
            center_lat + lat_delta,
        ),
        "radius_m": radius_m,
    }