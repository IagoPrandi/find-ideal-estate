from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

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

    print("M5.3 PASS: scraper returned enough listings without scraper errors.")
    return 0


def main() -> int:
    # Keep option to override from env for quick shell usage.
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    return asyncio.run(run_verification())


if __name__ == "__main__":
    raise SystemExit(main())
