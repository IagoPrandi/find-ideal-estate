from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from .valhalla_adapter import GeoPoint


class OTPCommunicationError(RuntimeError):
    """Raised when OTP cannot be reached or returns invalid payloads."""


class _OTPGraphQLUnavailable(Exception):
    """Internal: GraphQL endpoint not available; caller should try REST fallback."""


@dataclass(frozen=True)
class TransitLeg:
    mode: str
    modal_type: str
    duration_sec: float
    line: str | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class TransitOption:
    duration_sec: float
    walk_time_sec: float
    transit_time_sec: float
    transfers: int
    modal_types: list[str]
    lines: list[str]
    legs: list[TransitLeg]
    raw: dict[str, Any]


@dataclass(frozen=True)
class TransitItinerary:
    options: list[TransitOption]
    raw: dict[str, Any]


class OTPAdapter:
    _GRAPHQL_ENDPOINT = "/otp/transmodel/v3"
    _TRIP_QUERY = """
query Trip($from: Location!, $to: Location!, $dateTime: DateTime!, $numTripPatterns: Int) {
  trip(from: $from, to: $to, dateTime: $dateTime, numTripPatterns: $numTripPatterns) {
    tripPatterns {
      duration
      walkTime
      legs {
        mode
        duration
        line {
          publicCode
          name
        }
      }
    }
    routingErrors {
      code
    }
  }
}
"""

    _MODE_TO_MODAL_TYPE = {
        "WALK": "walk",
        "FOOT": "walk",  # OTP 2.x GraphQL uses lowercase "foot" → .upper() → "FOOT"
        "BUS": "bus",
        "SUBWAY": "metro",
        "RAIL": "train",
        "COMMUTER_RAIL": "train",
        "TRAM": "tram",
        "LIGHTRAIL": "tram",
        "FERRY": "ferry",
        "BICYCLE": "bike",
        "CAR": "car",
    }

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 5.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout_seconds),
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def plan(
        self,
        origin: GeoPoint,
        dest: GeoPoint,
        trip_datetime: datetime,
        *,
        num_itineraries: int = 3,
    ) -> TransitItinerary:
        # Try GraphQL (OTP 2.x) first
        try:
            payload = await self._post_graphql(origin, dest, trip_datetime, num_itineraries)
            trip = payload["data"]["trip"]
            options = self._parse_trip_patterns(trip.get("tripPatterns") or [])
            options.sort(key=lambda o: o.duration_sec)
            return TransitItinerary(options=options, raw=payload)
        except _OTPGraphQLUnavailable:
            pass  # fall through to REST fallback

        # REST fallback (OTP 1.x)
        params = {
            "fromPlace": f"{origin.lat},{origin.lon}",
            "toPlace": f"{dest.lat},{dest.lon}",
            "date": trip_datetime.strftime("%Y-%m-%d"),
            "time": trip_datetime.strftime("%H:%M:%S"),
            "numItineraries": str(num_itineraries),
        }
        payload = await self._get_plan_payload(params=params)
        options = self._parse_itineraries(payload)
        options.sort(key=lambda o: o.duration_sec)
        return TransitItinerary(options=options, raw=payload)

    async def _post_graphql(
        self,
        origin: GeoPoint,
        dest: GeoPoint,
        trip_datetime: datetime,
        num_itineraries: int,
    ) -> dict[str, Any]:
        variables = {
            "from": {"coordinates": {"latitude": origin.lat, "longitude": origin.lon}},
            "to": {"coordinates": {"latitude": dest.lat, "longitude": dest.lon}},
            "dateTime": trip_datetime.isoformat(),
            "numTripPatterns": num_itineraries,
        }
        try:
            response = await self._client.post(
                self._GRAPHQL_ENDPOINT,
                json={"query": self._TRIP_QUERY, "variables": variables},
            )
            if response.status_code in (404, 405):
                raise _OTPGraphQLUnavailable("GraphQL endpoint not found")
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException as exc:
            raise OTPCommunicationError("Timed out while calling OTP") from exc
        except _OTPGraphQLUnavailable:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise _OTPGraphQLUnavailable(str(exc)) from exc

        if not isinstance(data, dict):
            raise _OTPGraphQLUnavailable("OTP returned invalid GraphQL payload")

        trip_data = (data.get("data") or {}).get("trip")
        if not isinstance(trip_data, dict):
            raise _OTPGraphQLUnavailable("OTP GraphQL response missing trip data")

        routing_errors = trip_data.get("routingErrors") or []
        if routing_errors:
            codes = [e.get("code") for e in routing_errors if isinstance(e, dict)]
            raise OTPCommunicationError(f"OTP routing errors: {codes}")

        return data

    async def _get_plan_payload(self, *, params: dict[str, str]) -> dict[str, Any]:
        data = await self._get_json("/plan", params=params)

        error_obj = data.get("error")
        if isinstance(error_obj, dict):
            message = error_obj.get("message")
            if isinstance(message, str) and message.strip():
                raise OTPCommunicationError(message)
            raise OTPCommunicationError("OTP returned an error payload")

        plan_obj = data.get("plan")
        if not isinstance(plan_obj, dict):
            raise OTPCommunicationError("OTP response has no plan object")

        itineraries = plan_obj.get("itineraries")
        if itineraries is None:
            plan_obj["itineraries"] = []
        elif not isinstance(itineraries, list):
            raise OTPCommunicationError("OTP itineraries payload is invalid")

        return data

    async def _get_json(self, path: str, *, params: dict[str, str]) -> dict[str, Any]:
        try:
            response = await self._client.get(path, params=params)
            if response.status_code == 404 and path == "/plan":
                response = await self._client.get("/otp/routers/default/plan", params=params)
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException as exc:
            raise OTPCommunicationError("Timed out while calling OTP") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise OTPCommunicationError("OTP communication failed") from exc

        if not isinstance(data, dict):
            raise OTPCommunicationError("OTP returned invalid JSON payload")
        return data

    def _parse_trip_patterns(self, patterns: list[dict[str, Any]]) -> list[TransitOption]:
        parsed: list[TransitOption] = []
        for pattern in patterns:
            if not isinstance(pattern, dict):
                continue
            legs_payload = pattern.get("legs")
            legs = self._parse_legs(legs_payload if isinstance(legs_payload, list) else [])
            walk_time = self._to_float(pattern.get("walkTime"))
            total_dur = self._to_float(pattern.get("duration"))
            transit_time = max(0.0, total_dur - walk_time)
            transit_legs = [leg for leg in legs if leg.modal_type != "walk"]
            transfers = max(0, len(transit_legs) - 1)
            parsed.append(
                TransitOption(
                    duration_sec=total_dur,
                    walk_time_sec=walk_time,
                    transit_time_sec=transit_time,
                    transfers=transfers,
                    modal_types=self._unique_preserve_order([leg.modal_type for leg in legs]),
                    lines=self._unique_preserve_order(
                        [leg.line for leg in legs if isinstance(leg.line, str) and leg.line.strip()]
                    ),
                    legs=legs,
                    raw=pattern,
                )
            )
        return parsed

    def _parse_itineraries(self, payload: dict[str, Any]) -> list[TransitOption]:
        plan = payload.get("plan")
        if not isinstance(plan, dict):
            return []

        itineraries = plan.get("itineraries")
        if not isinstance(itineraries, list):
            return []

        parsed: list[TransitOption] = []
        for itinerary in itineraries:
            if not isinstance(itinerary, dict):
                continue

            legs_payload = itinerary.get("legs")
            legs = self._parse_legs(legs_payload if isinstance(legs_payload, list) else [])

            parsed.append(
                TransitOption(
                    duration_sec=self._to_float(itinerary.get("duration")),
                    walk_time_sec=self._to_float(itinerary.get("walkTime")),
                    transit_time_sec=self._to_float(itinerary.get("transitTime")),
                    transfers=self._to_int(itinerary.get("transfers")),
                    modal_types=self._unique_preserve_order([leg.modal_type for leg in legs]),
                    lines=self._unique_preserve_order(
                        [leg.line for leg in legs if isinstance(leg.line, str) and leg.line.strip()]
                    ),
                    legs=legs,
                    raw=itinerary,
                )
            )

        return parsed

    def _parse_legs(self, legs_payload: list[dict[str, Any]]) -> list[TransitLeg]:
        legs: list[TransitLeg] = []
        for leg in legs_payload:
            mode = str(leg.get("mode") or "UNKNOWN").upper()
            legs.append(
                TransitLeg(
                    mode=mode,
                    modal_type=self._map_mode_to_modal_type(mode),
                    duration_sec=self._to_float(leg.get("duration")),
                    line=self._extract_line(leg),
                    raw=leg,
                )
            )
        return legs

    def _map_mode_to_modal_type(self, mode: str) -> str:
        return self._MODE_TO_MODAL_TYPE.get(mode, "transit_unknown")

    @staticmethod
    def _extract_line(leg: dict[str, Any]) -> str | None:
        # OTP 2.x GraphQL: leg.line.publicCode or leg.line.name
        line_obj = leg.get("line")
        if isinstance(line_obj, dict):
            for key in ("publicCode", "name"):
                value = line_obj.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        # OTP 1.x REST: routeShortName, routeLongName, headsign
        for key in ("routeShortName", "routeLongName", "headsign"):
            value = leg.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _to_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _to_int(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _unique_preserve_order(values: list[str]) -> list[str]:
        unique: list[str] = []
        seen: set[str] = set()
        for value in values:
            if value not in seen:
                seen.add(value)
                unique.append(value)
        return unique
