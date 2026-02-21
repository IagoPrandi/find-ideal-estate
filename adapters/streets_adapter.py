from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def run_streets(
    lon: float,
    lat: float,
    radius_m: float,
    out_path: Path,
    step_m: float = 150.0,
    query_radius_m: float = 120.0,
    max_workers: int = 8,
) -> None:
    script_path = Path("cods_ok") / "encontrarRuasRaio.py"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    args = [
        sys.executable,
        str(script_path),
        "--lon",
        str(lon),
        "--lat",
        str(lat),
        "--radius",
        str(radius_m),
        "--step",
        str(step_m),
        "--query-radius",
        str(query_radius_m),
        "--max-workers",
        str(max_workers),
        "--format",
        "json",
        "--out",
        str(out_path),
    ]
    subprocess.run(args, check=True)
