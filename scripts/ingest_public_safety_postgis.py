from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1] / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from src.core.db import close_db, get_engine, init_db  # noqa: E402
from src.modules.public_safety import ingest_public_safety_to_postgis  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ingest SSP public safety incidents into PostGIS."
    )
    parser.add_argument(
        "--year",
        type=int,
        default=2025,
        help="Source year used to resolve data_cache/dados_criminais_<year>.xlsx.",
    )
    parser.add_argument(
        "--cache-dir",
        default="data_cache",
        help="Directory containing the SSP XLSX cache files.",
    )
    return parser


async def _run(args: argparse.Namespace) -> dict[str, object]:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")

    init_db(database_url)
    try:
        result = await ingest_public_safety_to_postgis(
            get_engine(),
            cache_dir=Path(args.cache_dir),
            source_year=args.year,
        )
        return {
            "dataset_type": result.dataset_type,
            "source_year": result.source_year,
            "source_label": result.source_label,
            "deleted_rows": result.deleted_rows,
            "inserted_rows": result.inserted_rows,
            "dropped_rows": result.dropped_rows,
            "elapsed_seconds": round(result.elapsed_seconds, 3),
        }
    finally:
        await close_db()


def main() -> None:
    args = _parser().parse_args()
    payload = asyncio.run(_run(args))
    print(json.dumps(payload, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()