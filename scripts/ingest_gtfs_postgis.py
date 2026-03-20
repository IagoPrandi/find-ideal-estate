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

from src.core.db import close_db, init_db, get_engine  # noqa: E402
from src.modules.transport.gtfs_ingestion import ingest_gtfs_to_postgis  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest GTFS into PostGIS tables with hash check and atomic swap.")
    parser.add_argument("--dataset-type", default="gtfs_sptrans", help="Dataset type key stored in dataset_versions.")
    parser.add_argument("--gtfs-url", default=None, help="Remote GTFS zip URL.")
    parser.add_argument("--gtfs-zip", default=None, help="Local GTFS zip path.")
    parser.add_argument("--gtfs-dir", default="data_cache/gtfs", help="Directory with GTFS *.txt files.")
    return parser


async def _run(args: argparse.Namespace) -> dict[str, object]:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")

    init_db(database_url)
    try:
        result = await ingest_gtfs_to_postgis(
            get_engine(),
            dataset_type=args.dataset_type,
            source_url=args.gtfs_url,
            gtfs_zip_path=Path(args.gtfs_zip) if args.gtfs_zip else None,
            gtfs_dir=Path(args.gtfs_dir) if not args.gtfs_url and not args.gtfs_zip else None,
        )
        return {
            "dataset_type": result.dataset_type,
            "version_hash": result.version_hash,
            "skipped": result.skipped,
            "source_label": result.source_label,
            "row_counts": result.row_counts,
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