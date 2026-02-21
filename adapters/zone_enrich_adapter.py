from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Dict


def run_zone_enrich(
    runs_dir: Path,
    geodir: Path,
    out_dir: Path,
    params: Dict[str, float] | None = None,
) -> None:
    params = params or {}
    script_path = Path("cods_ok") / "zone_enrich_green_flood_v3.py"
    args = [
        sys.executable,
        str(script_path),
        "--runs-dir",
        str(runs_dir),
        "--geodir",
        str(geodir),
        "--out-dir",
        str(out_dir),
    ]

    if "r_flood_m" in params:
        args += ["--r-flood-m", str(params["r_flood_m"])]
    if "r_green_m" in params:
        args += ["--r-green-m", str(params["r_green_m"])]

    subprocess.run(args, check=True)
