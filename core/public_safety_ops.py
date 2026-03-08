from __future__ import annotations

import importlib.util
import json
import logging
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


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

    module_name = "segurancaRegiao"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load module spec for: {script_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    if not hasattr(module, "run_query"):
        raise AttributeError("segurancaRegiao.py does not expose run_query")
    return module


def build_public_safety_artifacts(
    run_dir: Path,
    reference_points: List[Dict[str, Any]],
    params: Dict[str, Any],
) -> Tuple[Path, List[Path]]:
    t0 = time.perf_counter()
    # zone_radius_m is required — validated upstream in the pipeline.
    if params.get("zone_radius_m") is None:
        raise ValueError("zone_radius_m is required in params")
    radius_km = float(params["zone_radius_m"]) / 1000.0
    ano = int(params.get("public_safety_year", 2025))
    logger.info(
        '{"service": "public_safety_ops", "fn": "build_public_safety_artifacts", "event": "start", '
        '"run_id": "%s", "refs": %d, "radius_km": %s, "ano": %d}',
        run_dir.name, len(reference_points), radius_km, ano,
    )
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
    duration_ms = round((time.perf_counter() - t0) * 1000)
    logger.info(
        '{"service": "public_safety_ops", "fn": "build_public_safety_artifacts", "event": "done", '
        '"run_id": "%s", "artifacts": %d, "duration_ms": %d}',
        run_dir.name, len(artifact_paths), duration_ms,
    )
    return aggregate_path, artifact_paths


def _build_public_safety_summary(result: Dict[str, Any]) -> Dict[str, Any]:
    crimes = result.get("ocorrencias_por_tipo_no_raio")
    crimes_dict = crimes if isinstance(crimes, dict) else {}
    total_no_raio = 0
    for value in crimes_dict.values():
        try:
            total_no_raio += int(value)
        except Exception:
            continue

    comparativo = result.get("comparativo_regiao_vs_cidade_sp")
    comparativo_dict = comparativo if isinstance(comparativo, dict) else {}
    top_crimes: List[Dict[str, Any]] = []
    for crime, value in sorted(crimes_dict.items(), key=lambda item: int(item[1]), reverse=True)[:5]:
        try:
            qtd = int(value)
        except Exception:
            continue
        top_crimes.append({"tipo_delito": str(crime), "qtd": qtd})

    delegacias = result.get("duas_delegacias_mais_proximas")
    delegacias_dict = delegacias if isinstance(delegacias, dict) else {}
    dps_proximas: List[Dict[str, Any]] = []
    for nome, info in delegacias_dict.items():
        if not isinstance(info, dict):
            continue
        dps_proximas.append(
            {
                "nome": str(nome),
                "dist_km": info.get("dist_km"),
                "total_ocorrencias": info.get("total_ocorrencias"),
            }
        )

    return {
        "ocorrencias_no_raio_total": total_no_raio,
        "top_delitos_no_raio": top_crimes,
        "delta_pct_vs_cidade": comparativo_dict.get("delta_pct_vs_cidade"),
        "regiao_media_dia": comparativo_dict.get("regiao_media_dia"),
        "cidade_media_dia": comparativo_dict.get("cidade_media_dia"),
        "delegacias_mais_proximas": dps_proximas,
    }


def get_zone_public_safety(
    run_dir: Path,
    zone_uid: str,
    lat: float,
    lon: float,
    params: Dict[str, Any],
) -> Dict[str, Any]:
    if not is_public_safety_enabled(params):
        logger.debug(
            '{"service": "public_safety_ops", "fn": "get_zone_public_safety", "event": "skipped", '
            '"run_id": "%s", "zone_uid": "%s", "reason": "disabled"}',
            run_dir.name, zone_uid,
        )
        return {"enabled": False, "reason": "public_safety_enabled=false"}

    # zone_radius_m is required — validated upstream in the pipeline.
    if params.get("zone_radius_m") is None:
        raise ValueError("zone_radius_m is required in params")
    radius_km = float(params["zone_radius_m"]) / 1000.0
    ano = int(params.get("public_safety_year", 2025))
    fail_on_error = is_public_safety_fail_on_error(params)

    out_path = run_dir / "zones" / "detail" / zone_uid / "public_safety.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    logger.info(
        '{"service": "public_safety_ops", "fn": "get_zone_public_safety", "event": "start", '
        '"run_id": "%s", "zone_uid": "%s", "cache_hit": %s}',
        run_dir.name, zone_uid, str(out_path.exists()).lower(),
    )
    result: Dict[str, Any]
    if out_path.exists():
        try:
            loaded = json.loads(out_path.read_text(encoding="utf-8"))
            result = loaded if isinstance(loaded, dict) else {}
        except Exception as ex:
            if fail_on_error:
                raise RuntimeError(f"could not read cached public safety for zone {zone_uid}: {ex}") from ex
            return {
                "enabled": False,
                "year": ano,
                "radius_km": radius_km,
                "error": f"could not read cached public safety for zone {zone_uid}: {ex}",
            }
    else:
        try:
            module = _load_public_safety_module()
            raw = module.run_query(ref_lat=lat, ref_lon=lon, radius_km=radius_km, ano=ano)
            result = raw if isinstance(raw, dict) else {}
            out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as ex:
            if fail_on_error:
                raise
            return {
                "enabled": False,
                "year": ano,
                "radius_km": radius_km,
                "error": str(ex),
            }

    summary = _build_public_safety_summary(result)
    duration_ms = round((time.perf_counter() - t0) * 1000)
    logger.info(
        '{"service": "public_safety_ops", "fn": "get_zone_public_safety", "event": "done", '
        '"run_id": "%s", "zone_uid": "%s", "total_occurrences": %s, "duration_ms": %d}',
        run_dir.name, zone_uid,
        str(summary.get("ocorrencias_no_raio_total", "null")),
        duration_ms,
    )
    return {
        "enabled": True,
        "year": ano,
        "radius_km": radius_km,
        "result": result,
        "summary": summary,
    }