from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def run_pois(
    lon: float,
    lat: float,
    radius_m: float,
    out_path: Path,
    limit: int = 25,
) -> None:
    script_path = Path("cods_ok") / "pois_categoria_raio.py"
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
        "--limit",
        str(limit),
        "--format",
        "json",
        "--out",
        str(out_path),
    ]
    subprocess.run(args, check=True)
