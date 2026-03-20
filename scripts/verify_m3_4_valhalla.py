"""
M3.4 Verification script — ValhallaAdapter timing thresholds.

PRD criteria:
  • 1st call (network)  < 300 ms
  • 2nd call (Redis cache) < 50 ms

Usage (Valhalla + Redis must be reachable):
  python scripts/verify_m3_4_valhalla.py [--valhalla-url URL] [--redis-url URL]

Defaults:
  --valhalla-url  http://localhost:8002
  --redis-url     redis://localhost:6379/0
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time

import redis.asyncio as aioredis

# ── make sure the api src tree is importable ─────────────────────────────────
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))

from modules.transport.valhalla_adapter import GeoPoint, ValhallaAdapter  # noqa: E402

# Two landmark points in São Paulo (Av. Paulista → Ibirapuera)
ORIGIN = GeoPoint(lat=-23.550520, lon=-46.633310)
DEST = GeoPoint(lat=-23.587690, lon=-46.657560)
COSTING = "pedestrian"

THRESHOLD_FIRST_MS = 300
THRESHOLD_CACHE_MS = 50


async def run(valhalla_url: str, redis_url: str) -> None:
    redis_client = aioredis.from_url(redis_url, decode_responses=True)

    # Pre-clean any stale cache entry so the first call always hits the network
    key = f"valhalla:{COSTING}:{ORIGIN.lat:.6f}:{ORIGIN.lon:.6f}:{DEST.lat:.6f}:{DEST.lon:.6f}"
    await redis_client.delete(key)

    adapter = ValhallaAdapter(base_url=valhalla_url, redis_client=redis_client)

    try:
        # ── 1st call: network ─────────────────────────────────────────────
        t0 = time.perf_counter()
        result1 = await adapter.route(ORIGIN, DEST, COSTING)
        elapsed1_ms = (time.perf_counter() - t0) * 1000

        print(f"[1st call] {elapsed1_ms:.1f} ms  "
              f"— {result1.distance_km:.2f} km / {result1.duration_sec:.0f} s  "
              f"(threshold < {THRESHOLD_FIRST_MS} ms)")

        ok1 = elapsed1_ms < THRESHOLD_FIRST_MS
        print("  PASS" if ok1 else f"  FAIL  ({elapsed1_ms:.1f} ms >= {THRESHOLD_FIRST_MS} ms)")

        # ── 2nd call: cache hit ───────────────────────────────────────────
        t0 = time.perf_counter()
        result2 = await adapter.route(ORIGIN, DEST, COSTING)
        elapsed2_ms = (time.perf_counter() - t0) * 1000

        print(f"[2nd call] {elapsed2_ms:.1f} ms  "
              f"(cache hit, threshold < {THRESHOLD_CACHE_MS} ms)")

        ok2 = elapsed2_ms < THRESHOLD_CACHE_MS
        print("  PASS" if ok2 else f"  FAIL  ({elapsed2_ms:.1f} ms >= {THRESHOLD_CACHE_MS} ms)")

        # Consistency check
        assert result1.distance_km == result2.distance_km, "Cache returned different distance!"

        # Clean up
        await redis_client.delete(key)

        if not (ok1 and ok2):
            sys.exit(1)

        print("\nM3.4 verification PASSED")

    finally:
        await adapter._client.aclose()
        await redis_client.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description="M3.4 timing verification")
    parser.add_argument("--valhalla-url", default="http://localhost:8002")
    parser.add_argument("--redis-url", default="redis://localhost:6379/0")
    args = parser.parse_args()

    print(f"Valhalla: {args.valhalla_url}")
    print(f"Redis:    {args.redis_url}")
    print(f"Route:    ({ORIGIN.lat}, {ORIGIN.lon}) -> ({DEST.lat}, {DEST.lon})  costing={COSTING}\n")

    asyncio.run(run(args.valhalla_url, args.redis_url))


if __name__ == "__main__":
    main()
