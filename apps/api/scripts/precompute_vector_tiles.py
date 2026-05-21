"""Precompute vector tiles by requesting the API tile endpoints.

Run this from the API container or EC2 host after migrations/deploy. The API
route writes misses into vector_tile_cache, so this script only needs HTTP
access to the backend.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import math
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Iterable


LAYER_PATHS = {
    "lines": "/transport/tiles/lines/{z}/{x}/{y}.pbf",
    "stops": "/transport/tiles/stops/{z}/{x}/{y}.pbf",
    "green": "/transport/tiles/environment/green/{z}/{x}/{y}.pbf",
    "flood": "/transport/tiles/environment/flood/{z}/{x}/{y}.pbf",
    "safety": "/transport/tiles/environment/safety/{z}/{x}/{y}.pbf",
}


@dataclass(frozen=True)
class TileRequest:
    layer: str
    z: int
    x: int
    y: int


def _parse_csv_ints(value: str) -> list[int]:
    return [int(part.strip()) for part in value.split(",") if part.strip()]


def _parse_csv_layers(value: str) -> list[str]:
    layers = [part.strip() for part in value.split(",") if part.strip()]
    unknown = sorted(set(layers) - set(LAYER_PATHS))
    if unknown:
        raise argparse.ArgumentTypeError(f"camadas desconhecidas: {', '.join(unknown)}")
    return layers


def _parse_bbox(value: str) -> tuple[float, float, float, float]:
    parts = [float(part.strip()) for part in value.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("bbox deve usar minLon,minLat,maxLon,maxLat")
    min_lon, min_lat, max_lon, max_lat = parts
    if min_lon >= max_lon or min_lat >= max_lat:
        raise argparse.ArgumentTypeError("bbox invalida: min deve ser menor que max")
    return min_lon, min_lat, max_lon, max_lat


def _lon_to_tile_x(lon: float, zoom: int) -> int:
    n = 2**zoom
    return max(0, min(n - 1, int((lon + 180.0) / 360.0 * n)))


def _lat_to_tile_y(lat: float, zoom: int) -> int:
    n = 2**zoom
    lat_rad = math.radians(max(-85.05112878, min(85.05112878, lat)))
    y = (1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n
    return max(0, min(n - 1, int(y)))


def _iter_tiles(
    *,
    bbox: tuple[float, float, float, float],
    zooms: Iterable[int],
    layers: Iterable[str],
) -> list[TileRequest]:
    min_lon, min_lat, max_lon, max_lat = bbox
    requests: list[TileRequest] = []
    for z in zooms:
        x_min = _lon_to_tile_x(min_lon, z)
        x_max = _lon_to_tile_x(max_lon, z)
        y_min = _lat_to_tile_y(max_lat, z)
        y_max = _lat_to_tile_y(min_lat, z)
        for layer in layers:
            for x in range(min(x_min, x_max), max(x_min, x_max) + 1):
                for y in range(min(y_min, y_max), max(y_min, y_max) + 1):
                    requests.append(TileRequest(layer=layer, z=z, x=x, y=y))
    return requests


def _fetch_tile(base_url: str, timeout: float, request: TileRequest) -> tuple[TileRequest, int, str, int, int]:
    path = LAYER_PATHS[request.layer].format(z=request.z, x=request.x, y=request.y)
    url = f"{base_url.rstrip('/')}{path}"
    started_at = time.perf_counter()
    http_request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.mapbox-vector-tile",
            "User-Agent": "betterplace-vector-tile-precompute/1.0",
        },
    )
    try:
        with urllib.request.urlopen(http_request, timeout=timeout) as response:
            body = response.read()
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            cache_status = response.headers.get("X-Vector-Tile-Cache", "")
            return request, response.status, cache_status, len(body), elapsed_ms
    except urllib.error.HTTPError as exc:
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        return request, exc.code, "ERROR", len(exc.read()), elapsed_ms
    except urllib.error.URLError:
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        return request, 0, "ERROR", 0, elapsed_ms


def main() -> int:
    parser = argparse.ArgumentParser(description="Preprocessa vector tiles no cache persistente do banco.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="URL base da API.")
    parser.add_argument(
        "--bbox",
        type=_parse_bbox,
        required=True,
        help="minLon,minLat,maxLon,maxLat da area a aquecer.",
    )
    parser.add_argument("--zooms", type=_parse_csv_ints, default=_parse_csv_ints("13,14,15"), help="Lista CSV de zooms.")
    parser.add_argument(
        "--layers",
        type=_parse_csv_layers,
        default=_parse_csv_layers("stops,lines,green,flood,safety"),
        help="Lista CSV de camadas: lines,stops,green,flood,safety.",
    )
    parser.add_argument("--concurrency", type=int, default=4, help="Requests paralelos.")
    parser.add_argument("--timeout", type=float, default=45.0, help="Timeout por tile, em segundos.")
    parser.add_argument("--max-tiles", type=int, default=5000, help="Limite de seguranca para evitar prewarm acidental enorme.")
    args = parser.parse_args()

    requests = _iter_tiles(bbox=args.bbox, zooms=args.zooms, layers=args.layers)
    if len(requests) > args.max_tiles:
        print(f"Abortado: {len(requests)} tiles excedem --max-tiles={args.max_tiles}.")
        return 2

    print(
        f"Preprocessando {len(requests)} tiles em {args.base_url} "
        f"layers={','.join(args.layers)} zooms={','.join(str(z) for z in args.zooms)}"
    )

    counts: dict[int, int] = {}
    cache_counts: dict[str, int] = {}
    total_bytes = 0
    started_at = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as executor:
        futures = [
            executor.submit(_fetch_tile, args.base_url, args.timeout, tile_request)
            for tile_request in requests
        ]
        for index, future in enumerate(concurrent.futures.as_completed(futures), start=1):
            request, status, cache_status, byte_size, elapsed_ms = future.result()
            counts[status] = counts.get(status, 0) + 1
            cache_counts[cache_status or "NONE"] = cache_counts.get(cache_status or "NONE", 0) + 1
            total_bytes += byte_size
            if status >= 400 or status == 0:
                print(
                    f"ERRO {status} {request.layer} z={request.z} x={request.x} y={request.y} "
                    f"{elapsed_ms}ms bytes={byte_size}"
                )
            elif index % 50 == 0 or index == len(requests):
                print(f"{index}/{len(requests)} tiles processados")

    elapsed_seconds = time.perf_counter() - started_at
    print(
        "Resumo: "
        f"status={counts} cache={cache_counts} bytes={total_bytes} elapsed_s={elapsed_seconds:.1f}"
    )
    return 0 if all(status < 400 and status != 0 for status in counts) else 1


if __name__ == "__main__":
    raise SystemExit(main())
