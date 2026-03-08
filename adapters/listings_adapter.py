from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import time
from types import ModuleType
from typing import Any, Callable, Dict, List, Optional
from pathlib import Path


def _load_module(module_path: Path, module_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, str(module_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Failed to build import spec for {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _safe_parse_with_module(
    module_path: Path,
    platform_dir: Path,
    module_name: str,
    log_fn: Optional[Callable[..., None]] = None,
) -> List[Dict[str, Any]]:
    if not module_path.exists() or not platform_dir.exists():
        if log_fn:
            log_fn(
                level="warning",
                stage="listings_parse",
                message="plataforma ausente: módulo ou diretório não encontrado",
                platform=module_name,
                module_path=str(module_path),
                platform_dir=str(platform_dir),
                module_exists=module_path.exists(),
                dir_exists=platform_dir.exists(),
            )
        return []
    try:
        module = _load_module(module_path, module_name)
        parse_run_dir: Callable[[str | Path], List[Dict[str, Any]]] = getattr(module, "parse_run_dir")
        items = parse_run_dir(platform_dir)
        result = items if isinstance(items, list) else []
        if log_fn:
            log_fn(
                level="info",
                stage="listings_parse",
                message="plataforma parseada",
                platform=module_name,
                items_count=len(result),
            )
        return result
    except Exception as exc:
        if log_fn:
            log_fn(
                level="error",
                stage="listings_parse",
                message="falha ao parsear plataforma",
                platform=module_name,
                error_type=type(exc).__name__,
                error=str(exc),
            )
        return []


def _build_standardized_compiled_listings(
    run_root: Path,
    log_fn: Optional[Callable[..., None]] = None,
) -> Path:
    cods_ok_dir = Path("cods_ok")
    parser_specs = [
        ("vivareal", cods_ok_dir / "vivaReal.py", "cods_ok_vivareal_parser"),
        ("quinto_andar", cods_ok_dir / "quintoAndar.py", "cods_ok_quintoandar_parser"),
        ("zapimoveis", cods_ok_dir / "zapImoveis.py", "cods_ok_zap_parser"),
    ]
    required_platforms = [spec[0] for spec in parser_specs]

    merged_items: List[Dict[str, Any]] = []
    seen = set()
    platform_counts: Dict[str, int] = {p: 0 for p in required_platforms}

    for platform_dir_name, module_path, module_name in parser_specs:
        platform_dir = run_root / platform_dir_name
        parsed_items = _safe_parse_with_module(module_path, platform_dir, module_name, log_fn=log_fn)
        for item in parsed_items:
            if not isinstance(item, dict):
                continue
            key = (str(item.get("platform") or ""), str(item.get("listing_id") or ""))
            if key in seen:
                continue
            seen.add(key)
            merged_items.append(item)
            platform = str(item.get("platform") or "").strip().lower()
            if platform in platform_counts:
                platform_counts[platform] += 1

    payload: Dict[str, Any] = {
        "schema_version": 1,
        "source": "dedicated_parsers",
        "required_platforms": required_platforms,
        "platform_counts": platform_counts,
        "items": merged_items,
        "count": len(merged_items),
    }
    output_path = run_root / "compiled_listings_parsed.json"
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


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
    log_fn: Optional[Callable[..., None]] = None,
) -> Path:
    zap_enabled_script = Path("cods_ok") / "realestate_meta_search_zapImoveis.py"
    default_script = Path("cods_ok") / "realestate_meta_search.py"
    script_path = zap_enabled_script if zap_enabled_script.exists() else default_script
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

    t0 = time.perf_counter()
    result = subprocess.run(args, capture_output=True, text=True)
    duration_ms = round((time.perf_counter() - t0) * 1000)

    if log_fn:
        log_fn(
            level="info" if result.returncode == 0 else "error",
            stage="listings_subprocess",
            message="subprocess de coleta concluído",
            cmd=args,
            returncode=result.returncode,
            duration_ms=duration_ms,
            stdout=result.stdout[-4000:] if result.stdout else None,
            stderr=result.stderr[-4000:] if result.stderr else None,
            script=str(script_path),
            address=address,
            mode=mode,
        )

    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, args, result.stdout, result.stderr)

    run_dirs = sorted([p for p in out_dir.glob("runs/run_*") if p.is_dir()])
    if not run_dirs:
        run_dirs = sorted([p for p in out_dir.iterdir() if p.is_dir() and p.name.startswith("run_")])
    if not run_dirs:
        raise FileNotFoundError("No listing run directory generated")
    run_root = run_dirs[-1]
    _build_standardized_compiled_listings(run_root, log_fn=log_fn)
    return run_root
