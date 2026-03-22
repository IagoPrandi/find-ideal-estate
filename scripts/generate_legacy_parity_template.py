from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "scripts" / "schemas" / "parity_template.schema.json"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PLATFORMS = ("quintoandar", "vivareal", "zapimoveis")
REQUIRED_FIELDS = (
    "platform",
    "listing_id",
    "url",
    "lat",
    "lon",
    "price_brl",
    "area_m2",
    "bedrooms",
    "bathrooms",
    "parking",
    "address",
)

PLATFORM_ALIASES = {
    "quinto_andar": "quintoandar",
    "quintoandar": "quintoandar",
    "vivareal": "vivareal",
    "zapimoveis": "zapimoveis",
}


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    v = _safe_float(value)
    return int(round(v)) if v is not None else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate strict legacy parity template from cods_ok scraper outputs."
    )
    parser.add_argument(
        "--address",
        required=True,
        help="Address used for the legacy scraper baseline run.",
    )
    parser.add_argument("--lat", type=float, required=True, help="Search center latitude.")
    parser.add_argument("--lon", type=float, required=True, help="Search center longitude.")
    parser.add_argument(
        "--mode",
        choices=["rent", "buy", "sale"],
        default="rent",
        help="Legacy scraper mode.",
    )
    parser.add_argument(
        "--radius-m",
        type=float,
        default=1500.0,
        help="Radius in meters used by legacy run.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=4,
        help="Max page depth used in legacy scraping.",
    )
    parser.add_argument(
        "--config",
        default=str(ROOT / "platforms.yaml"),
        help="Path to scraping config yaml.",
    )
    parser.add_argument(
        "--work-dir",
        default=str(ROOT / "runs" / "parity_template_build"),
        help="Directory used to store temporary legacy run artifacts.",
    )
    parser.add_argument(
        "--template-version",
        default="v1.0",
        help="Template version identifier.",
    )
    parser.add_argument(
        "--out-json",
        default=str(ROOT / "runs" / "parity_template_v1.json"),
        help="Output path for generated parity template JSON.",
    )
    return parser.parse_args()


def _normalize_platform(value: Any) -> str:
    key = str(value or "").strip().lower()
    return PLATFORM_ALIASES.get(key, key)


def _load_legacy_items(run_root: Path) -> list[dict[str, Any]]:
    candidates = (
        run_root / "compiled_listings.json",
        run_root / "compiled_listings_parsed.json",
    )
    payload_path = next((p for p in candidates if p.exists()), None)
    if payload_path is None:
        raise FileNotFoundError("Legacy run did not produce compiled listings JSON")

    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = payload.get("items")
    else:
        items = None

    if not isinstance(items, list):
        raise ValueError(f"Unexpected legacy payload format in {payload_path}")
    return [item for item in items if isinstance(item, dict)]


def _build_field_presence(items: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {platform: [] for platform in PLATFORMS}
    for item in items:
        platform = _normalize_platform(item.get("platform"))
        if platform in grouped:
            grouped[platform].append(item)

    stats: dict[str, Any] = {}
    for platform in PLATFORMS:
        platform_items = grouped[platform]
        total = len(platform_items)
        presence: dict[str, Any] = {}
        for field in REQUIRED_FIELDS:
            present = sum(
                1
                for entry in platform_items
                if entry.get(field) not in (None, "", [], {})
            )
            missing = max(total - present, 0)
            rate = float(present / total) if total > 0 else 0.0
            presence[field] = {
                "present": present,
                "missing": missing,
                "rate": round(rate, 4),
            }
        stats[platform] = {
            "count": total,
            "presence": presence,
        }

    return stats


def _build_canonical_results(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {platform: [] for platform in PLATFORMS}
    seen: dict[str, set[str]] = {platform: set() for platform in PLATFORMS}

    for item in items:
        platform = _normalize_platform(item.get("platform"))
        if platform not in grouped:
            continue
        listing_id = str(item.get("listing_id") or item.get("platform_listing_id") or "").strip()
        if not listing_id or listing_id in seen[platform]:
            continue
        seen[platform].add(listing_id)

        grouped[platform].append(
            {
                "platform": platform,
                "listing_id": listing_id,
                "url": item.get("url"),
                "lat": _safe_float(item.get("lat")),
                "lon": _safe_float(item.get("lon")),
                "price_brl": _safe_float(item.get("price_brl")),
                "area_m2": _safe_float(item.get("area_m2")),
                "bedrooms": _safe_int(item.get("bedrooms")),
                "bathrooms": _safe_int(item.get("bathrooms")),
                "parking": _safe_int(item.get("parking")),
                "address": item.get("address"),
            }
        )

    return grouped


def _lightweight_schema_check(template: dict[str, Any]) -> None:
    # Keep validation dependency-free while still fail-closing on malformed templates.
    required_top = {
        "template_version",
        "generated_at",
        "source",
        "query",
        "strict_count_parity",
        "required_fields",
        "platform_field_presence",
        "canonical_results",
    }
    missing_top = sorted(required_top.difference(template.keys()))
    if missing_top:
        raise ValueError(f"Template missing required keys: {missing_top}")

    counts = template.get("strict_count_parity")
    if not isinstance(counts, dict):
        raise ValueError("strict_count_parity must be an object")

    for platform in PLATFORMS:
        value = counts.get(platform)
        if not isinstance(value, int) or value < 0:
            raise ValueError(f"strict_count_parity[{platform}] must be integer >= 0")

    canonical = template.get("canonical_results")
    if not isinstance(canonical, dict):
        raise ValueError("canonical_results must be an object")
    for platform in PLATFORMS:
        platform_items = canonical.get(platform)
        if not isinstance(platform_items, list):
            raise ValueError(f"canonical_results[{platform}] must be an array")


def main() -> int:
    from adapters.listings_adapter import run_listings_all

    args = parse_args()

    run_root = run_listings_all(
        config_path=Path(args.config),
        out_dir=Path(args.work_dir),
        mode=args.mode,
        address=args.address,
        center_lat=float(args.lat),
        center_lon=float(args.lon),
        radius_m=float(args.radius_m),
        max_pages=int(args.max_pages),
        headless=True,
    )

    items = _load_legacy_items(run_root)
    platform_field_presence = _build_field_presence(items)
    canonical_results = _build_canonical_results(items)
    strict_count_parity = {
        platform: int(platform_field_presence[platform]["count"])
        for platform in PLATFORMS
    }

    template: dict[str, Any] = {
        "template_version": str(args.template_version),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "type": "legacy_cods_ok",
            "script": "cods_ok/realestate_meta_search.py",
            "config": str(Path(args.config)),
        },
        "query": {
            "address": args.address,
            "mode": args.mode,
            "center": {
                "lat": float(args.lat),
                "lon": float(args.lon),
            },
            "radius_m": float(args.radius_m),
            "max_pages": int(args.max_pages),
        },
        "strict_count_parity": strict_count_parity,
        "required_fields": list(REQUIRED_FIELDS),
        "platform_field_presence": platform_field_presence,
        "canonical_results": canonical_results,
    }

    _lightweight_schema_check(template)

    out_path = Path(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[template] Generated legacy parity template")
    print(f"[template] run_root={run_root}")
    print(f"[template] schema={SCHEMA_PATH}")
    print(f"[template] out={out_path}")
    print(f"[template] counts={strict_count_parity}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
