from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Dict


def run_candidate_zones(
    cache_dir: Path,
    out_dir: Path,
    seed_lat: float,
    seed_lon: float,
    params: Dict[str, float] | None = None,
) -> None:
    params = params or {}
    script_path = Path("cods_ok") / "candidate_zones_from_cache_v10_fixed2.py"
    args = [
        sys.executable,
        str(script_path),
        "--cache-dir",
        str(cache_dir),
        f"--seed-bus-coord={seed_lat},{seed_lon}",
        "--auto-rail-seed",
        "--out-dir",
        str(out_dir),
    ]

    # zone_radius_m is required — validated upstream in the pipeline.
    if "zone_radius_m" not in params:
        raise ValueError("zone_radius_m is required in params")
    args += ["--buffer-m", str(params["zone_radius_m"])]
    if "t_bus" in params:
        args += ["--t-bus", str(params["t_bus"])]
    if "t_rail" in params:
        args += ["--t-rail", str(params["t_rail"])]
    if "seed_bus_max_dist_m" in params:
        args += ["--seed-bus-max-dist-m", str(params["seed_bus_max_dist_m"])]
    if "seed_rail_max_dist_m" in params:
        args += ["--seed-rail-max-dist-m", str(params["seed_rail_max_dist_m"])]
    if "dedupe_radius_m" in params:
        args += ["--dedupe-radius-m", str(params["dedupe_radius_m"])]

    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    subprocess.run(args, check=True, env=env)
