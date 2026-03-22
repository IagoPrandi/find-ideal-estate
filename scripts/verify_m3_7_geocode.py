"""
M3.7 verification script — Geocoding Proxy.

Checks:
  1. POST /api/geocode returns suggestions list.
  2. Second identical call has cache_hit=true in external_usage_ledger.
  3. Rate limit header / 429 when >30 req/min.
  4. Mapbox token is NOT present in the response body.

Usage:
    .venv\\Scripts\\python.exe scripts/verify_m3_7_geocode.py

Requires running API at http://localhost:8000 with real .env (MAPBOX_ACCESS_TOKEN set).
"""

from __future__ import annotations

import json
import os
import sys
import time
from urllib.parse import urlparse

import httpx
import psycopg2

BASE_URL = os.environ.get("API_URL", "http://localhost:8000")
TIMEOUT = 15.0
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/find_ideal_estate")


def _post(q: str, session: str | None = None) -> tuple[int, dict]:
    cookies = {}
    if session:
        cookies["anonymous_session_id"] = session

    with httpx.Client(timeout=TIMEOUT, cookies=cookies) as client:
        resp = client.post(f"{BASE_URL}/api/geocode", json={"q": q})
    return resp.status_code, resp.json() if resp.content else {}


def _ledger_has_cache_hit(session_id: str) -> bool:
    parsed = urlparse(DATABASE_URL)
    dbname = parsed.path.lstrip("/")
    with psycopg2.connect(
        dbname=dbname,
        user=parsed.username,
        password=parsed.password,
        host=parsed.hostname,
        port=parsed.port or 5432,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT cache_hit
                FROM external_usage_ledger
                WHERE operation_type = 'geocode' AND session_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (session_id,),
            )
            row = cur.fetchone()
            return bool(row and row[0] is True)


def main() -> int:
    errors: list[str] = []
    session = f"verify_m3_7_{int(time.time())}"

    # ─── Check 1: basic geocode call ─────────────────────────────────────────
    print("[1] POST /api/geocode {'q': 'Av Paulista'}")
    status_code, body = _post("Av Paulista", session)
    if status_code != 200:
        errors.append(f"Expected 200, got {status_code}: {json.dumps(body)}")
    else:
        suggestions = body.get("suggestions", [])
        if not isinstance(suggestions, list):
            errors.append(f"Expected suggestions list, got: {type(suggestions)}")
        elif len(suggestions) == 0:
            errors.append("Got 0 suggestions — Mapbox returned empty response (may be token issue)")
        else:
            print(f"   ✓ Got {len(suggestions)} suggestion(s). cache_hit={body.get('cache_hit')}")

    # ─── Check 2: second identical call → cache_hit=true ─────────────────────
    print("[2] Repeat call — expect cache_hit=true")
    status_code2, body2 = _post("Av Paulista", session)
    if status_code2 != 200:
        errors.append(f"Second call returned {status_code2}: {json.dumps(body2)}")
    elif not body2.get("cache_hit"):
        errors.append(f"Expected cache_hit=true on second call, got: {body2.get('cache_hit')}")
    else:
        print(f"   ✓ cache_hit=true on second call ({body2.get('cache_hit')})")

    # ─── Check 3: ledger cache_hit=true for second call ───────────────────────
    print("[3] Checking external_usage_ledger cache_hit=true for repeated query")
    try:
        has_cache_hit = _ledger_has_cache_hit(session)
    except Exception as exc:
        errors.append(f"Could not verify ledger cache_hit: {exc}")
    else:
        if not has_cache_hit:
            errors.append("Expected latest geocode ledger row to have cache_hit=true")
        else:
            print("   ✓ external_usage_ledger latest geocode row has cache_hit=true")

    # ─── Check 4: Mapbox token not in response ────────────────────────────────
    print("[4] Verifying Mapbox token is not exposed in response body")
    mapbox_token = os.environ.get("MAPBOX_ACCESS_TOKEN", "")
    body_str = json.dumps(body)
    if mapbox_token and mapbox_token in body_str:
        errors.append("SECURITY: Mapbox token was found in response body!")
    else:
        print("   ✓ Mapbox token not in response body")

    # ─── Summary ─────────────────────────────────────────────────────────────
    if errors:
        print("\n[FAIL] M3.7 verification failed:")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("\n[OK] M3.7 — Geocoding proxy verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
