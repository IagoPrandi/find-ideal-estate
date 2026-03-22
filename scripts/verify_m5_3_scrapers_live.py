from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / "apps" / "api" / "src"
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from modules.listings.scrapers import (  # noqa: E402
    QuintoAndarScraper,
    ScraperDisallowedError,
    ScraperError,
    VivaRealScraper,
    ZapImoveisScraper,
)

SCRAPERS = {
    "quintoandar": QuintoAndarScraper,
    "zapimoveis": ZapImoveisScraper,
    "vivareal": VivaRealScraper,
}


def _mode_key(search_type: str) -> str:
    return "buy" if search_type == "sale" else "rent"


def _load_template_payload(path: str) -> dict[str, Any]:
    template_path = Path(path)
    payload = json.loads(template_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("template JSON root must be an object")
    return payload


def _expected_count_from_template(
    payload: dict[str, Any],
    *,
    platform: str,
    address: str,
    search_type: str,
) -> int:
    query = payload.get("query")
    if not isinstance(query, dict):
        raise ValueError("template JSON must contain object field: query")

    tpl_address = str(query.get("address") or "").strip().lower()
    run_address = address.strip().lower()
    if tpl_address and tpl_address != run_address:
        raise ValueError(
            "template query.address does not match --address "
            f"(template={tpl_address!r}, run={run_address!r})"
        )

    tpl_mode = str(query.get("mode") or "").strip().lower()
    run_mode = _mode_key(search_type)
    if tpl_mode and tpl_mode != run_mode:
        raise ValueError(
            "template query.mode does not match --search-type "
            f"(template={tpl_mode!r}, run={run_mode!r})"
        )

    strict_counts = payload.get("strict_count_parity")
    if not isinstance(strict_counts, dict):
        raise ValueError("template JSON must contain object field: strict_count_parity")

    if platform not in strict_counts:
        raise ValueError(f"platform {platform!r} missing in strict_count_parity")

    return int(strict_counts[platform])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "M5.3 live verification: run one Playwright scraper and assert minimum "
            "listing count without scraper errors."
        )
    )
    parser.add_argument(
        "--platform",
        choices=sorted(SCRAPERS.keys()),
        default="vivareal",
        help="Platform scraper to validate.",
    )
    parser.add_argument(
        "--address",
        default="Avenida Paulista, 1000, Sao Paulo",
        help="Search address used in scraper query.",
    )
    parser.add_argument(
        "--search-type",
        choices=["rent", "sale"],
        default="rent",
        help="Listing mode.",
    )
    parser.add_argument(
        "--min-results",
        type=int,
        default=5,
        help="Minimum listings required for pass.",
    )
    parser.add_argument(
        "--template-json",
        default="",
        help=(
            "Path to legacy parity template JSON (e.g. runs/parity_template_v1.json). "
            "When provided with --strict-template-counts, validates exact count parity "
            "for this platform without rerunning legacy."
        ),
    )
    parser.add_argument(
        "--strict-template-counts",
        action="store_true",
        help=(
            "Require exact listing count match against strict_count_parity from "
            "--template-json for this platform."
        ),
    )
    return parser.parse_args()


async def run_verification() -> int:
    args = parse_args()

    scraper_cls = SCRAPERS[args.platform]
    scraper = scraper_cls(search_address=args.address, search_type=args.search_type)

    print(f"M5.3 live check starting: platform={args.platform} address={args.address!r}")
    try:
        listings = await scraper.scrape()
    except ScraperDisallowedError as exc:
        print(f"M5.3 FAIL: robots.txt disallowed this run: {exc}")
        return 2
    except ScraperError as exc:
        print(f"M5.3 FAIL: scraper runtime error: {exc}")
        return 3
    except Exception as exc:  # noqa: BLE001
        print(f"M5.3 FAIL: unexpected error: {exc}")
        return 4

    count = len(listings)
    print(f"M5.3 result_count={count}")

    if count < args.min_results:
        print(
            "M5.3 FAIL: insufficient listings "
            f"(expected>={args.min_results}, got={count})"
        )
        return 1

    if args.strict_template_counts:
        if not args.template_json.strip():
            print("M5.3 FAIL: --strict-template-counts requires --template-json")
            return 5
        try:
            payload = _load_template_payload(args.template_json)
            expected = _expected_count_from_template(
                payload,
                platform=args.platform,
                address=args.address,
                search_type=args.search_type,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"M5.3 FAIL: invalid template comparison config: {exc}")
            return 6

        delta = count - expected
        print(
            "M5.3 template parity: "
            f"expected={expected} got={count} delta={delta}"
        )
        if count != expected:
            print("M5.3 FAIL: strict template count mismatch")
            return 7

    print("M5.3 PASS: scraper returned enough listings without scraper errors.")
    return 0


def main() -> int:
    # Keep option to override from env for quick shell usage.
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    return asyncio.run(run_verification())


if __name__ == "__main__":
    raise SystemExit(main())
