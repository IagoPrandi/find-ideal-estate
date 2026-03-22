from __future__ import annotations

import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = "127.0.0.1"
PORT = 18080

STATE: dict[str, object] = {
    "last_job_payload": None,
}


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class Handler(BaseHTTPRequestHandler):
    server_version = "m3_8_stub_api/1.0"

    def _send_json(self, status: int, payload: object) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1:5173")
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw) if raw else {}

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1:5173")
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/runs/run-e2e-1/status":
            self._send_json(
                200,
                {
                    "run_id": "run-e2e-1",
                    "status": {
                        "state": "success",
                        "stage": "transport_search",
                        "updated_at": _now_iso(),
                    },
                },
            )
            return

        if self.path == "/runs/run-e2e-1/zones":
            self._send_json(
                200,
                {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": {
                                "type": "Point",
                                "coordinates": [-46.6333, -23.5505],
                            },
                            "properties": {
                                "zone_uid": "zone-e2e-1",
                                "zone_name": "Zona E2E",
                                "centroid_lat": -23.5505,
                                "centroid_lon": -46.6333,
                                "score": 0.92,
                                "time_agg": 18,
                            },
                        }
                    ],
                },
            )
            return

        if self.path == "/journeys/journey-e2e-1/transport-points":
            self._send_json(
                200,
                [
                    {
                        "id": "tp-e2e-1",
                        "journey_id": "journey-e2e-1",
                        "source": "gtfs_stop",
                        "external_id": "s-101",
                        "name": "Parada E2E 1",
                        "lat": -23.5508,
                        "lon": -46.6330,
                        "walk_time_sec": 180,
                        "walk_distance_m": 220,
                        "route_ids": ["875A-10", "175T-10"],
                        "modal_types": ["bus"],
                        "route_count": 2,
                        "created_at": _now_iso(),
                    },
                    {
                        "id": "tp-e2e-2",
                        "journey_id": "journey-e2e-1",
                        "source": "geosampa_metro_station",
                        "external_id": "m-201",
                        "name": "Estacao E2E 2",
                        "lat": -23.5510,
                        "lon": -46.6327,
                        "walk_time_sec": 240,
                        "walk_distance_m": 300,
                        "route_ids": ["AZUL"],
                        "modal_types": ["metro"],
                        "route_count": 1,
                        "created_at": _now_iso(),
                    },
                ],
            )
            return

        if self.path == "/__e2e__/last-job":
            self._send_json(200, {"last_job_payload": STATE["last_job_payload"]})
            return

        self._send_json(404, {"detail": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/runs":
            _ = self._read_json()
            self._send_json(
                200,
                {
                    "run_id": "run-e2e-1",
                    "status": {
                        "state": "running",
                        "stage": "transport_search",
                        "created_at": _now_iso(),
                    },
                },
            )
            return

        if self.path == "/journeys":
            payload = self._read_json()
            self._send_json(
                201,
                {
                    "id": "journey-e2e-1",
                    "anonymous_session_id": "e2e-session",
                    "state": "draft",
                    "input_snapshot": payload.get("input_snapshot", {}),
                    "created_at": _now_iso(),
                    "updated_at": _now_iso(),
                },
            )
            return

        if self.path == "/jobs":
            payload = self._read_json()
            STATE["last_job_payload"] = payload
            self._send_json(
                201,
                {
                    "id": "job-e2e-1",
                    "journey_id": payload.get("journey_id"),
                    "job_type": payload.get("job_type", "zone_generation"),
                    "state": "pending",
                    "progress_percent": 0,
                    "current_stage": "queued",
                    "created_at": _now_iso(),
                },
            )
            return

        self._send_json(404, {"detail": "not found"})


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"[m3.8-stub] listening on http://{HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
