from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))

from modules.transport.otp_adapter import OTPAdapter  # noqa: E402
from modules.transport.valhalla_adapter import GeoPoint  # noqa: E402


async def main() -> None:
    adapter = OTPAdapter(base_url="http://localhost:8080")
    try:
        result = await adapter.plan(
            origin=GeoPoint(lat=-23.55052, lon=-46.63331),
            dest=GeoPoint(lat=-23.58769, lon=-46.65756),
            trip_datetime=datetime(2026, 3, 18, 8, 30, 0),
        )
        print(f"itineraries={len(result.options)}")
        for idx, option in enumerate(result.options[:3], start=1):
            print(
                f"option_{idx}: duration_sec={option.duration_sec:.1f}; "
                f"modal_types={option.modal_types}; lines={option.lines}"
            )

        with_lines = [option for option in result.options if option.lines]
        print(f"itineraries_with_lines={len(with_lines)}")
    finally:
        await adapter.aclose()


if __name__ == "__main__":
    asyncio.run(main())
