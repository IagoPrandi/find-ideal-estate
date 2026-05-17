from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / "apps" / "api" / "src"
CONTRACTS_SRC = ROOT / "packages" / "contracts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))
if str(CONTRACTS_SRC) not in sys.path:
    sys.path.insert(0, str(CONTRACTS_SRC))

from core.db import close_db, init_db  # noqa: E402
from core.redis import close_redis, init_redis  # noqa: E402
from contracts import JobType  # noqa: E402
from modules.jobs.service import get_job  # noqa: E402
from workers.handlers.prewarm import enqueue_manual_listings_prewarm, _listings_prewarm_step  # noqa: E402
from workers.queue import configure_broker  # noqa: E402
from workers.runtime import run_job_with_retry  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enqueue an internal manual listings prewarm job and optionally wait for completion."
    )
    parser.add_argument(
        "--address",
        action="append",
        default=[],
        help="Address to prewarm. Repeat the flag for multiple addresses.",
    )
    parser.add_argument(
        "--addresses-json",
        default=None,
        help="JSON array of addresses to prewarm.",
    )
    parser.add_argument("--search-type", default="rent", choices=["rent", "sale"])
    parser.add_argument("--usage-type", default="residential")
    parser.add_argument("--location-type", default="address")
    parser.add_argument("--max-address-duration-seconds", type=int, default=60)
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--inline", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--poll-interval-seconds", type=int, default=10)
    return parser.parse_args()


def _collect_addresses(args: argparse.Namespace) -> list[str]:
    addresses: list[str] = list(args.address or [])
    if args.addresses_json:
        payload = json.loads(args.addresses_json)
        if not isinstance(payload, list):
            raise ValueError("--addresses-json must be a JSON array")
        addresses.extend(str(item) for item in payload)
    cleaned = [str(item).strip() for item in addresses if str(item).strip()]
    if not cleaned:
        raise ValueError("Provide at least one address")
    return cleaned


async def _wait_for_job(job_id, *, timeout_seconds: int, poll_interval_seconds: int) -> dict[str, object]:
    deadline = asyncio.get_running_loop().time() + max(timeout_seconds, 1)
    while True:
        job = await get_job(job_id)
        if job is None:
            raise RuntimeError(f"Job {job_id} not found after enqueue")
        state = str(job.state)
        if state in {"completed", "failed", "cancelled", "cancelled_partial"}:
            return {
                "job_id": str(job.id),
                "state": state,
                "progress_percent": job.progress_percent,
                "result_ref": job.result_ref or {},
                "error_message": job.error_message,
            }
        if asyncio.get_running_loop().time() >= deadline:
            return {
                "job_id": str(job.id),
                "state": state,
                "progress_percent": job.progress_percent,
                "result_ref": job.result_ref or {},
                "timeout": True,
            }
        await asyncio.sleep(max(poll_interval_seconds, 1))


async def _main() -> None:
    args = _parse_args()
    addresses = _collect_addresses(args)
    database_url = os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/find_ideal_estate",
    )
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    broker_kind = os.environ.get("DRAMATIQ_BROKER", "stub").strip().lower() or "stub"

    init_db(
        database_url,
    )
    init_redis(redis_url)
    configure_broker(broker_kind, redis_url)
    from workers.handlers import enrichment, listings, prewarm, transport, zones  # noqa: F401

    try:
        job_id = await enqueue_manual_listings_prewarm(
            addresses,
            search_type=args.search_type,
            usage_type=args.usage_type,
            search_location_type=args.location_type,
            max_address_duration_seconds=args.max_address_duration_seconds,
        )
        print(json.dumps({"job_id": str(job_id), "addresses": addresses}, ensure_ascii=False))
        if args.inline:
            await run_job_with_retry(
                job_id,
                JobType.LISTINGS_PREWARM,
                stage="listings_prewarm",
                execute_step=lambda: _listings_prewarm_step(job_id),
            )
        if args.wait:
            summary = await _wait_for_job(
                job_id,
                timeout_seconds=args.timeout_seconds,
                poll_interval_seconds=args.poll_interval_seconds,
            )
            print(json.dumps(summary, ensure_ascii=False))
    finally:
        await close_db()
        await close_redis()


if __name__ == "__main__":
    os.environ.setdefault("DRAMATIQ_BROKER", "stub")
    asyncio.run(_main())
