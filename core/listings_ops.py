from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from adapters.listings_adapter import run_listings_all
from core.public_safety_ops import get_zone_public_safety
from core.zone_ops import get_zone_feature, haversine_m, zone_centroid_lonlat



def _slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:80] or "street"


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _append_run_log(run_dir: Path, level: str, stage: str, message: str, **extra: Any) -> None:
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "events.jsonl"
    event: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "run_id": run_dir.name,
        "level": level,
        "stage": stage,
        "message": message,
    }
    if extra:
        event.update(extra)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def _extract_streets(streets_path: Path, max_items: int) -> List[str]:
    data = _load_json(streets_path)
    streets = data.get("streets") if isinstance(data, dict) else None
    if not isinstance(streets, list):
        streets = []

    selected: List[str] = []
    for street in streets:
        street_name = str(street)
        if not _address_has_valid_street_type(street_name):
            continue
        selected.append(street_name)
        if len(selected) >= max_items:
            break
    return selected


def scrape_zone_listings(run_dir: Path, zone_uid: str, params: Dict[str, Any]) -> List[Path]:
    zone = get_zone_feature(run_dir, zone_uid)
    lon, lat = zone_centroid_lonlat(zone)

    # zone_radius_m is required — validated upstream in the pipeline.
    if params.get("zone_radius_m") is None:
        raise ValueError("zone_radius_m is required in params")
    radius_m = float(params["zone_radius_m"])

    streets_path = run_dir / "zones" / "detail" / zone_uid / "streets.json"
    if not streets_path.exists():
        raise FileNotFoundError(f"streets.json not found for zone {zone_uid}")

    require_all_platforms = bool(params.get("require_all_listing_platforms", True))
    street_filter = params.get("street_filter")
    if street_filter and str(street_filter).strip():
        # User explicitly chose a street — scrape only that street, no fallbacks.
        primary_street = str(street_filter).strip()
        streets = []
        if _address_has_valid_street_type(primary_street):
            streets.append(primary_street)
        if not streets:
            # Street name doesn't match valid type patterns but user still sent it;
            # include it anyway so the user gets feedback rather than an empty run.
            streets = [primary_street]
    else:
        streets = _extract_streets(streets_path, max_items=int(params.get("max_streets_per_zone", 3)))
        if not streets:
            raw = _load_json(streets_path)
            raw_streets = raw.get("streets") if isinstance(raw, dict) else []
            if isinstance(raw_streets, list):
                streets = [str(item).strip() for item in raw_streets if str(item).strip()][: int(params.get("max_streets_per_zone", 3))]
    mode = str(params.get("listing_mode", "rent"))
    max_pages = int(params.get("listing_max_pages", 2))
    config_path = Path(params.get("listings_config", "platforms.yaml"))

    _append_run_log(
        run_dir,
        level="info",
        stage="zone_listings",
        message="iniciando coleta de imóveis",
        zone_uid=zone_uid,
        street_filter=street_filter,
        streets_total=len(streets),
        listing_mode=mode,
        listing_radius_m=radius_m,
        listing_max_pages=max_pages,
    )

    out_paths: List[Path] = []
    platform_counts_total: Dict[str, int] = {platform: 0 for platform in _REQUIRED_LISTING_PLATFORMS}
    failed_streets = 0
    skipped_no_json = 0
    for street in streets:
        slug = _slugify(street)
        base_out = run_dir / "zones" / "detail" / zone_uid / "streets" / slug / "listings"
        _append_run_log(
            run_dir,
            level="info",
            stage="zone_listings",
            message="coletando rua",
            zone_uid=zone_uid,
            street=street,
            street_slug=slug,
        )
        def _log_fn(level: str, stage: str, message: str, **kw: Any) -> None:
            _append_run_log(run_dir, level=level, stage=stage, message=message, zone_uid=zone_uid, street=street, **kw)

        try:
            run_root = run_listings_all(
                config_path=config_path,
                out_dir=base_out,
                mode=mode,
                address=f"{street}, São Paulo, SP",
                center_lat=lat,
                center_lon=lon,
                radius_m=radius_m,
                max_pages=max_pages,
                headless=bool(params.get("listings_headless", True)),
                log_fn=_log_fn,
            )
        except Exception as ex:
            # Falha por rua/plataforma não deve derrubar o run inteiro.
            failed_streets += 1
            _append_run_log(
                run_dir,
                level="warning",
                stage="zone_listings",
                message="falha ao coletar rua",
                zone_uid=zone_uid,
                street=street,
                street_slug=slug,
                error_type=type(ex).__name__,
                error=str(ex),
            )
            continue

        # Use compiled_listings.json (correct data), not _parsed.json which has scraper bugs
        src_json = run_root / "compiled_listings.json"
        if not src_json.exists():
            src_json = None
        src_csv = run_root / "compiled_listings.csv"
        if src_json is not None and src_json.exists():
            dst_json = base_out / "compiled_listings.json"
            dst_json.write_text(src_json.read_text(encoding="utf-8"), encoding="utf-8")
            out_paths.append(dst_json)
            try:
                payload = _load_json(dst_json)
                payload_platform_counts = _platform_counts_from_payload(payload)
                for platform in _REQUIRED_LISTING_PLATFORMS:
                    platform_counts_total[platform] += int(payload_platform_counts.get(platform) or 0)
                if isinstance(payload, dict):
                    items = payload.get("items")
                elif isinstance(payload, list):
                    items = payload
                else:
                    items = []
                count = len(items) if isinstance(items, list) else 0
            except Exception:
                count = 0
            _append_run_log(
                run_dir,
                level="info",
                stage="zone_listings",
                message="rua coletada com sucesso",
                zone_uid=zone_uid,
                street=street,
                street_slug=slug,
                source_json=src_json.name,
                listings_count=count,
            )
        else:
            skipped_no_json += 1
            _append_run_log(
                run_dir,
                level="warning",
                stage="zone_listings",
                message="coleta sem arquivo de saída json",
                zone_uid=zone_uid,
                street=street,
                street_slug=slug,
            )
        if src_csv.exists():
            dst_csv = base_out / "compiled_listings.csv"
            dst_csv.write_text(src_csv.read_text(encoding="utf-8"), encoding="utf-8")

    _append_run_log(
        run_dir,
        level="info",
        stage="zone_listings",
        message="coleta de imóveis finalizada",
        zone_uid=zone_uid,
        streets_total=len(streets),
        streets_failed=failed_streets,
        streets_without_json=skipped_no_json,
        outputs_json=len(out_paths),
        platform_counts=platform_counts_total,
    )

    if require_all_platforms and not street_filter:
        missing_platforms = [
            platform
            for platform, count in platform_counts_total.items()
            if int(count or 0) <= 0
        ]
        if missing_platforms:
            raise RuntimeError(
                "Coleta de imóveis inválida: plataformas sem resultados. "
                f"missing={missing_platforms}; counts={platform_counts_total}; zone_uid={zone_uid}"
            )

    return out_paths


def _safe_float(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except Exception:
        return None


_VALID_STREET_TYPE_PATTERNS = [
    r"\brua\b",
    r"\br\.?\b",
    r"\bavenida\b",
    r"\bav\.?\b",
    r"\balameda\b",
    r"\btravessa\b",
    r"\btrv\.?\b",
    r"\bestrada\b",
    r"\best\.?\b",
    r"\brodovia\b",
    r"\brod\.?\b",
    r"\bpraca\b",
    r"\bpraça\b",
    r"\blargo\b",
    r"\bviela\b",
    r"\bbeco\b",
]
_VALID_STREET_TYPE_RE = re.compile("|".join(_VALID_STREET_TYPE_PATTERNS), flags=re.IGNORECASE)
_FORBIDDEN_ADDRESS_TOKEN_RE = re.compile(r"\bacesso\b", flags=re.IGNORECASE)
_STATE_IN_ADDRESS_RE = re.compile(r",\s*([A-Z]{2})\b")
_REQUIRED_LISTING_PLATFORMS = ("quinto_andar", "vivareal", "zapimoveis")


def _address_has_valid_street_type(v: Any) -> bool:
    if v is None:
        return False
    s = str(v).strip()
    if not s:
        return False
    if _FORBIDDEN_ADDRESS_TOKEN_RE.search(s) is not None:
        return False
    return _VALID_STREET_TYPE_RE.search(s) is not None


def _infer_state_from_address(address: Any) -> str | None:
    if not isinstance(address, str):
        return None
    match = _STATE_IN_ADDRESS_RE.search(address.upper())
    if not match:
        return None
    return match.group(1)


def _platform_counts_from_payload(payload: Any) -> Dict[str, int]:
    counts: Dict[str, int] = {platform: 0 for platform in _REQUIRED_LISTING_PLATFORMS}
    if not isinstance(payload, dict):
        return counts

    explicit = payload.get("platform_counts")
    if isinstance(explicit, dict):
        for platform in _REQUIRED_LISTING_PLATFORMS:
            try:
                counts[platform] = int(explicit.get(platform) or 0)
            except Exception:
                counts[platform] = 0
        return counts

    items = payload.get("items")
    if not isinstance(items, list):
        return counts

    for item in items:
        if not isinstance(item, dict):
            continue
        platform = str(item.get("platform") or "").strip().lower()
        if platform in counts:
            counts[platform] += 1

    return counts


def finalize_run(run_dir: Path, selected_zone_uids: List[str], params: Dict[str, Any]) -> Dict[str, Path]:
    # zone_radius_m is required for distance filtering
    if params.get("zone_radius_m") is None:
        raise ValueError("zone_radius_m is required in params for finalize")
    zone_radius_m = float(params["zone_radius_m"])

    _append_run_log(
        run_dir,
        level="info",
        stage="finalize",
        message="iniciando finalização",
        selected_zones=selected_zone_uids,
        zones_count=len(selected_zone_uids),
        zone_radius_m=zone_radius_m,
        params_price_ref=params.get("price_ref"),
        params_w_price=params.get("w_price"),
        params_w_transport=params.get("w_transport"),
        params_w_pois=params.get("w_pois"),
        params_require_state=params.get("require_state_in_listing"),
    )
    result: List[Dict[str, Any]] = []
    filtered_distance_count = 0

    for zone_uid in selected_zone_uids:
        zone = get_zone_feature(run_dir, zone_uid)
        zone_lon, zone_lat = zone_centroid_lonlat(zone)
        z_props = zone.get("properties") or {}
        zone_public_safety = get_zone_public_safety(
            run_dir=run_dir,
            zone_uid=zone_uid,
            lat=zone_lat,
            lon=zone_lon,
            params=params,
        )
        zone_ps_summary = zone_public_safety.get("summary") if isinstance(zone_public_safety, dict) else {}
        if not isinstance(zone_ps_summary, dict):
            zone_ps_summary = {}

        pois_path = run_dir / "zones" / "detail" / zone_uid / "pois.json"
        transport_path = run_dir / "zones" / "detail" / zone_uid / "transport.json"

        pois_data = _load_json(pois_path) if pois_path.exists() else {"results": []}
        transport_data = _load_json(transport_path) if transport_path.exists() else {"bus_stops": [], "stations": []}

        poi_points = []
        for item in pois_data.get("results", []):
            lat = _safe_float(item.get("lat"))
            lon = _safe_float(item.get("lon"))
            if lat is not None and lon is not None:
                poi_points.append((lat, lon))

        transport_points = []
        for item in (transport_data.get("bus_stops", []) + transport_data.get("stations", [])):
            lat = _safe_float(item.get("lat"))
            lon = _safe_float(item.get("lon"))
            if lat is not None and lon is not None:
                transport_points.append((lat, lon))

        listing_files = list((run_dir / "zones" / "detail" / zone_uid / "streets").glob("*/listings/compiled_listings.json"))
        for lf in listing_files:
            data = _load_json(lf)
            if isinstance(data, dict):
                items = data.get("items")
            elif isinstance(data, list):
                items = data
            else:
                items = []
            if not isinstance(items, list) or not items:
                continue

            for it in items:
                lat = _safe_float(it.get("lat") or it.get("latitude"))
                lon = _safe_float(it.get("lon") or it.get("longitude"))

                # Filter out listings outside zone radius (bad scraper results)
                if lat is not None and lon is not None:
                    distance_m = haversine_m(lat, lon, zone_lat, zone_lon)
                    if distance_m > zone_radius_m:
                        filtered_distance_count += 1
                        continue

                address = it.get("address")
                if not _address_has_valid_street_type(address):
                    continue

                state = it.get("state")
                if state is None or str(state).strip() == "":
                    state = _infer_state_from_address(address)

                require_state = bool(params.get("require_state_in_listing", False))
                if require_state and (state is None or str(state).strip() == ""):
                    continue

                if state is not None and str(state).strip() != "":
                    it["state"] = str(state).strip().upper()

                min_poi = None
                min_transport = None
                if lat is not None and lon is not None:
                    min_poi = min([haversine_m(lat, lon, p_lat, p_lon) for p_lat, p_lon in poi_points], default=None)
                    min_transport = min(
                        [haversine_m(lat, lon, t_lat, t_lon) for t_lat, t_lon in transport_points],
                        default=None,
                    )

                price = _safe_float(it.get("price") or it.get("price_brl"))
                price_score = 0.0 if price is None else max(0.0, 1.0 - (price / float(params.get("price_ref", 5000))))
                transport_score = 0.0 if min_transport is None else max(0.0, 1.0 - (min_transport / float(params.get("transport_ref_m", 1500))))
                poi_score = 0.0 if min_poi is None else max(0.0, 1.0 - (min_poi / float(params.get("pois_ref_m", 1500))))

                score = (
                    float(params.get("w_price", 0.5)) * price_score
                    + float(params.get("w_transport", 0.3)) * transport_score
                    + float(params.get("w_pois", 0.2)) * poi_score
                )

                result.append(
                    {
                        "zone_uid": zone_uid,
                        "score_listing_v1": score,
                        "price": price,
                        "distance_transport_m": min_transport,
                        "distance_poi_m": min_poi,
                        "zone_time_agg": z_props.get("time_agg"),
                        "zone_flood_ratio": z_props.get("flood_ratio_r800"),
                        "zone_green_ratio": z_props.get("green_ratio_r700"),
                        "zone_public_safety_enabled": bool(zone_public_safety.get("enabled")),
                        "zone_public_safety_year": zone_public_safety.get("year"),
                        "zone_public_safety_radius_km": zone_public_safety.get("radius_km"),
                        "zone_public_safety_occurrences_total": zone_ps_summary.get("ocorrencias_no_raio_total"),
                        "zone_public_safety_delta_pct_vs_cidade": zone_ps_summary.get("delta_pct_vs_cidade"),
                        **it,
                    }
                )

    with_coords = 0
    without_coords = 0
    for row in result:
        lat = _safe_float(row.get("lat") or row.get("latitude"))
        lon = _safe_float(row.get("lon") or row.get("longitude"))
        if lat is None or lon is None:
            without_coords += 1
        else:
            with_coords += 1

    _append_run_log(
        run_dir,
        level="info",
        stage="finalize",
        message="consolidação de imóveis finalizada",
        listings_total=len(result),
        listings_with_coords=with_coords,
        listings_without_coords=without_coords,
        filtered_by_distance=filtered_distance_count,
    )

    result = sorted(result, key=lambda x: x.get("score_listing_v1", 0.0), reverse=True)

    final_dir = run_dir / "final"
    final_dir.mkdir(parents=True, exist_ok=True)

    final_json = final_dir / "listings_final.json"
    final_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    final_csv = final_dir / "listings_final.csv"
    if result:
        keys = sorted({k for r in result for k in r.keys()})
        import csv

        with final_csv.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            for row in result:
                w.writerow(row)
    else:
        final_csv.write_text("", encoding="utf-8")

    features = []
    for row in result:
        lat = _safe_float(row.get("lat") or row.get("latitude"))
        lon = _safe_float(row.get("lon") or row.get("longitude"))
        if lat is None or lon is None:
            continue
        props = dict(row)
        props.pop("lat", None)
        props.pop("lon", None)
        props.pop("latitude", None)
        props.pop("longitude", None)
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": props,
            }
        )

    final_geojson = final_dir / "listings_final.geojson"
    final_geojson.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False),
        encoding="utf-8",
    )

    zones_src = run_dir / "zones" / "consolidated" / "zones_consolidated.geojson"
    zones_dst = final_dir / "zones_final.geojson"
    if zones_src.exists():
        zones_dst.write_text(zones_src.read_text(encoding="utf-8"), encoding="utf-8")

    return {
        "listings_final_json": final_json,
        "listings_final_csv": final_csv,
        "listings_final_geojson": final_geojson,
        "zones_final_geojson": zones_dst,
    }
