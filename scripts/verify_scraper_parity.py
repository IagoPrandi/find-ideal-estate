from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / "apps" / "api" / "src"
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from modules.listings.scrapers import (  # noqa: E402
    QuintoAndarScraper,
    ScraperError,
    VivaRealScraper,
    ZapImoveisScraper,
)

SCRAPERS: dict[str, type] = {
    "quintoandar": QuintoAndarScraper,
    "vivareal": VivaRealScraper,
    "zapimoveis": ZapImoveisScraper,
}

DEFAULT_EXPECTED_COUNTS = {
    "quintoandar": 20,
    "vivareal": 20,
    "zapimoveis": 20,
}

PLATFORMS = tuple(sorted(SCRAPERS.keys()))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate apps/api scraper counts against fixed expected benchmark values "
            "for a known test address."
        )
    )
    parser.add_argument(
        "--address",
        default="Rua Guaipa, Vila Leopoldina, Sao Paulo - SP",
        help="Benchmark address used by both legacy and API scrapers.",
    )
    parser.add_argument(
        "--mode",
        choices=["rent", "buy", "sale"],
        default="rent",
        help="Search mode for API scrapers.",
    )
    parser.add_argument(
        "--min-results",
        type=int,
        default=20,
        help="Minimum listings required per platform for both outputs.",
    )
    parser.add_argument(
        "--expected",
        default="",
        help=(
            "Expected counts as JSON object, e.g. "
            "'{\"quintoandar\":20,\"vivareal\":20,\"zapimoveis\":20}'. "
            "If omitted, built-in defaults are used."
        ),
    )
    parser.add_argument(
        "--template-json",
        default="",
        help=(
            "Path to a legacy-generated parity template JSON. "
            "When provided, strict_count_parity values become the expected counts."
        ),
    )
    parser.add_argument(
        "--out-json",
        default=str(ROOT / "runs" / "parity_report.json"),
        help="Path to write detailed parity report.",
    )
    return parser.parse_args()


async def _run_api_counts(address: str, mode: str) -> tuple[dict[str, int], dict[str, str]]:
    search_type = "sale" if mode in {"buy", "sale"} else "rent"
    counts: dict[str, int] = {}
    errors: dict[str, str] = {}

    for platform, scraper_cls in SCRAPERS.items():
        try:
            scraper = scraper_cls(search_address=address, search_type=search_type)
            listings = await scraper.scrape()
            counts[platform] = len(listings)
        except ScraperError as exc:
            errors[platform] = str(exc)
            counts[platform] = 0
        except Exception as exc:  # noqa: BLE001
            errors[platform] = f"{type(exc).__name__}: {exc}"
            counts[platform] = 0

    return counts, errors


def _parse_expected_counts(raw: str) -> dict[str, int]:
    if not raw.strip():
        return dict(DEFAULT_EXPECTED_COUNTS)

    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("--expected must be a JSON object")

    expected: dict[str, int] = {}
    for platform in SCRAPERS:
        value = payload.get(platform, DEFAULT_EXPECTED_COUNTS[platform])
        expected[platform] = int(value)
    return expected


def _normalize_expected_counts(payload: dict[str, Any]) -> dict[str, int]:
    expected: dict[str, int] = {}
    for platform in PLATFORMS:
        value = payload.get(platform, DEFAULT_EXPECTED_COUNTS[platform])
        expected[platform] = int(value)
    return expected


def _load_expected_counts_from_template(
    template_json: str,
) -> tuple[dict[str, int], dict[str, Any]]:
    template_path = Path(template_json)
    payload = json.loads(template_path.read_text(encoding="utf-8"))
    strict_counts = payload.get("strict_count_parity")
    if not isinstance(strict_counts, dict):
        raise ValueError("template JSON must contain object field: strict_count_parity")
    expected = _normalize_expected_counts(strict_counts)
    return expected, {
        "template_path": str(template_path),
        "template_version": payload.get("template_version"),
        "generated_at": payload.get("generated_at"),
    }


async def main() -> int:
    args = parse_args()
    template_meta: dict[str, Any] = {}
    parity_mode = "benchmark_expected"

    if args.template_json.strip():
        expected_counts, template_meta = _load_expected_counts_from_template(args.template_json)
        parity_mode = "strict_template_counts"
    else:
        expected_counts = _parse_expected_counts(args.expected)

    print(f"[parity] Running API scrapers for: {args.address!r}")
    api_counts, api_errors = await _run_api_counts(args.address, args.mode)

    expected_platforms = list(PLATFORMS)
    report: dict[str, Any] = {
        "address": args.address,
        "mode": args.mode,
        "parity_mode": parity_mode,
        "min_results": args.min_results,
        "expected_counts": {p: int(expected_counts.get(p, 0)) for p in expected_platforms},
        "api_counts": {p: int(api_counts.get(p, 0)) for p in expected_platforms},
        "api_errors": api_errors,
        "expected_pass": {
            p: int(expected_counts.get(p, 0)) >= args.min_results for p in expected_platforms
        },
        "api_pass": {
            p: int(api_counts.get(p, 0)) >= args.min_results for p in expected_platforms
        },
        "delta_api_minus_expected": {
            p: int(api_counts.get(p, 0)) - int(expected_counts.get(p, 0))
            for p in expected_platforms
        },
        "strict_count_parity": {
            p: int(api_counts.get(p, 0)) == int(expected_counts.get(p, 0))
            for p in expected_platforms
        },
    }
    if template_meta:
        report["template"] = template_meta

    out_path = Path(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[parity] Summary")
    for platform in expected_platforms:
        expected = report["expected_counts"][platform]
        api = report["api_counts"][platform]
        expected_ok = report["expected_pass"][platform]
        api_ok = report["api_pass"][platform]
        strict_ok = report["strict_count_parity"][platform]
        print(
            f"  - {platform}: expected={expected} api={api} "
            f"(pass expected={expected_ok} api={api_ok} strict={strict_ok})"
        )

    print(f"[parity] Report written to: {out_path}")

    all_expected_ok = all(report["expected_pass"].values())
    all_api_ok = all(report["api_pass"].values())
    all_strict_ok = all(report["strict_count_parity"].values())
    strict_required = parity_mode == "strict_template_counts"
    parity_ok = all_strict_ok if strict_required else True

    if all_expected_ok and all_api_ok and parity_ok and not api_errors:
        print("[parity] PASS")
        return 0

    print("[parity] FAIL")
    if strict_required and not all_strict_ok:
        print("[parity] Strict template parity mismatch detected")
    if api_errors:
        print(f"[parity] API scraper errors: {api_errors}")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
