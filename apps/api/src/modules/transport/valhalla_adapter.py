from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx
from redis.asyncio import Redis


class ValhallaCommunicationError(RuntimeError):
    """Raised when Valhalla cannot be reached or times out."""


@dataclass(frozen=True)
class GeoPoint:
    lat: float
    lon: float


@dataclass(frozen=True)
class RouteResult:
    distance_km: float
    duration_sec: float
    raw: dict[str, Any]


class ValhallaAdapter:
    def __init__(
        self,
        *,
        base_url: str,
        redis_client: Redis | None = None,
        timeout_seconds: float = 5.0,
        cache_ttl_seconds: int = 24 * 60 * 60,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._redis = redis_client
        self._cache_ttl_seconds = cache_ttl_seconds
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout_seconds),
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    @staticmethod
    def _format_coord(value: float) -> str:
        return f"{value:.6f}"

    def _cache_key(self, *, costing: str, origin: GeoPoint, dest: GeoPoint) -> str:
        return (
            "valhalla:"
            f"{costing}:"
            f"{self._format_coord(origin.lat)}:"
            f"{self._format_coord(origin.lon)}:"
            f"{self._format_coord(dest.lat)}:"
            f"{self._format_coord(dest.lon)}"
        )

    async def route(self, origin: GeoPoint, dest: GeoPoint, costing: str) -> RouteResult:
        cache_key = self._cache_key(costing=costing, origin=origin, dest=dest)
        cached = await self._read_cache(cache_key)
        if cached is not None:
            return self._route_result_from_payload(cached)

        payload = {
            "locations": [
                {"lat": origin.lat, "lon": origin.lon},
                {"lat": dest.lat, "lon": dest.lon},
            ],
            "costing": costing,
            "directions_options": {"units": "kilometers"},
        }
        response_payload = await self._post_json("/route", payload)
        await self._write_cache(cache_key, response_payload)
        return self._route_result_from_payload(response_payload)

    async def isochrone(
        self,
        origin: GeoPoint,
        costing: str,
        contours_minutes: list[int],
    ) -> dict[str, Any]:
        payload = {
            "locations": [{"lat": origin.lat, "lon": origin.lon}],
            "costing": costing,
            "contours": [{"time": minute} for minute in contours_minutes],
            "polygons": True,
        }
        return await self._post_json("/isochrone", payload)

    async def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._client.post(path, json=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException as exc:
            raise ValhallaCommunicationError("Timed out while calling Valhalla") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise ValhallaCommunicationError("Valhalla communication failed") from exc

        if not isinstance(data, dict):
            raise ValhallaCommunicationError("Valhalla returned invalid JSON payload")
        return data

    async def _read_cache(self, key: str) -> dict[str, Any] | None:
        if self._redis is None:
            return None
        cached = await self._redis.get(key)
        if not cached:
            return None
        try:
            parsed = json.loads(cached)
        except json.JSONDecodeError:
            return None
        if not isinstance(parsed, dict):
            return None
        return parsed

    async def _write_cache(self, key: str, payload: dict[str, Any]) -> None:
        if self._redis is None:
            return
        await self._redis.setex(key, self._cache_ttl_seconds, json.dumps(payload))

    @staticmethod
    def _route_result_from_payload(payload: dict[str, Any]) -> RouteResult:
        summary = payload.get("trip", {}).get("summary", {})
        try:
            distance_km = float(summary.get("length", 0.0))
            duration_sec = float(summary.get("time", 0.0))
        except (TypeError, ValueError) as exc:
            raise ValhallaCommunicationError("Valhalla route summary is invalid") from exc
        return RouteResult(distance_km=distance_km, duration_sec=duration_sec, raw=payload)
