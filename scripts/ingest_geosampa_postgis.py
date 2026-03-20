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
from src.modules.transport.geosampa_ingestion import ingest_geosampa_to_postgis  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ingest GeoSampa transport datasets into PostGIS tables."
    )
    parser.add_argument(
        "--dataset-type",
        default="geosampa_transport",
        help="Dataset type key stored in dataset_versions.",
    )
    parser.add_argument(
        "--geosampa-dir",
        default="data_cache/geosampa",
        help="Directory with GeoSampa *.gpkg files.",
    )
    return parser


async def _run(args: argparse.Namespace) -> dict[str, object]:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")

    init_db(database_url)
    try:
        result = await ingest_geosampa_to_postgis(
            get_engine(),
            database_url=database_url,
            dataset_type=args.dataset_type,
            geosampa_dir=Path(args.geosampa_dir),
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
