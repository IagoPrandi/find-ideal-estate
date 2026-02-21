from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def run_listings_all(
    config_path: Path,
    out_dir: Path,
    mode: str,
    address: str,
    center_lat: float,
    center_lon: float,
    radius_m: float,
    max_pages: int,
    headless: bool = True,
) -> Path:
    script_path = Path("cods_ok") / "realestate_meta_search.py"
    out_dir.mkdir(parents=True, exist_ok=True)

    base_cmd = [sys.executable, str(script_path)]
    xvfb = shutil.which("xvfb-run")
    if xvfb:
        base_cmd = [xvfb, "-a", *base_cmd]

    args = [
        *base_cmd,
        "all",
        "--config",
        str(config_path),
        "--mode",
        mode,
        "--lat",
        str(center_lat),
        "--lon",
        str(center_lon),
        "--address",
        address,
        "--radius-m",
        str(radius_m),
        "--out-dir",
        str(out_dir),
        "--max-pages",
        str(max_pages),
        "--out",
        str(out_dir / "results.csv"),
    ]

    if headless:
        args.append("--headless")

    subprocess.run(args, check=True)

    run_dirs = sorted([p for p in out_dir.glob("runs/run_*") if p.is_dir()])
    if not run_dirs:
        run_dirs = sorted([p for p in out_dir.iterdir() if p.is_dir() and p.name.startswith("run_")])
    if not run_dirs:
        raise FileNotFoundError("No listing run directory generated")
    return run_dirs[-1]
