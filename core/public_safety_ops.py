from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List, Tuple


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return default


def is_public_safety_enabled(params: Dict[str, Any]) -> bool:
    return _to_bool(params.get("public_safety_enabled"), default=False)


def is_public_safety_fail_on_error(params: Dict[str, Any]) -> bool:
    return _to_bool(params.get("public_safety_fail_on_error"), default=False)


def _load_public_safety_module() -> ModuleType:
    script_path = Path("cods_ok") / "segurancaRegiao.py"
    if not script_path.exists():
        raise FileNotFoundError(f"public safety script not found: {script_path}")

    spec = importlib.util.spec_from_file_location("segurancaRegiao", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load module spec for: {script_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "run_query"):
        raise AttributeError("segurancaRegiao.py does not expose run_query")
    return module


def build_public_safety_artifacts(
    run_dir: Path,
    reference_points: List[Dict[str, Any]],
    params: Dict[str, Any],
) -> Tuple[Path, List[Path]]:
    radius_km = float(params.get("public_safety_radius_km", 1.0))
    ano = int(params.get("public_safety_year", 2025))

    module = _load_public_safety_module()

    by_ref: List[Dict[str, Any]] = []
    artifact_paths: List[Path] = []
    for idx, ref in enumerate(reference_points):
        ref_name = ref.get("name") or f"ref_{idx}"
        ref_lat = float(ref["lat"])
        ref_lon = float(ref["lon"])
        result = module.run_query(ref_lat=ref_lat, ref_lon=ref_lon, radius_km=radius_km, ano=ano)

        out_dir = run_dir / "security" / "by_ref" / f"ref_{idx}"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "public_safety.json"
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        artifact_paths.append(out_path)

        by_ref.append(
            {
                "ref_index": idx,
                "ref_name": ref_name,
                "lat": ref_lat,
                "lon": ref_lon,
                "artifact": str(out_path).replace("\\", "/"),
                "result": result,
            }
        )

    aggregate = {
        "public_safety_enabled": True,
        "year": ano,
        "radius_km": radius_km,
        "reference_points_count": len(reference_points),
        "by_ref": by_ref,
    }
    aggregate_path = run_dir / "security" / "public_safety.json"
    aggregate_path.parent.mkdir(parents=True, exist_ok=True)
    aggregate_path.write_text(json.dumps(aggregate, ensure_ascii=False, indent=2), encoding="utf-8")
    return aggregate_path, artifact_paths