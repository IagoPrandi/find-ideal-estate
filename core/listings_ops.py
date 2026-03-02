from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

from adapters.listings_adapter import run_listings_all
from core.zone_ops import get_zone_feature, haversine_m, zone_centroid_lonlat


def _slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:80] or "street"


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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
    streets_path = run_dir / "zones" / "detail" / zone_uid / "streets.json"
    if not streets_path.exists():
        raise FileNotFoundError(f"streets.json not found for zone {zone_uid}")

    street_filter = params.get("street_filter")
    if street_filter and str(street_filter).strip():
        streets = [str(street_filter).strip()]
        if not _address_has_valid_street_type(streets[0]):
            streets = []
    else:
        streets = _extract_streets(streets_path, max_items=int(params.get("max_streets_per_zone", 3)))
    mode = str(params.get("listing_mode", "rent"))
    radius_m = float(params.get("listing_radius_m", 1500))
    max_pages = int(params.get("listing_max_pages", 2))
    config_path = Path(params.get("listings_config", "platforms.yaml"))

    out_paths: List[Path] = []
    for street in streets:
        slug = _slugify(street)
        base_out = run_dir / "zones" / "detail" / zone_uid / "streets" / slug / "listings"
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
            )
        except Exception:
            # Falha por rua/plataforma não deve derrubar o run inteiro.
            continue

        src_json = run_root / "compiled_listings.json"
        src_csv = run_root / "compiled_listings.csv"
        if src_json.exists():
            dst_json = base_out / "compiled_listings.json"
            dst_json.write_text(src_json.read_text(encoding="utf-8"), encoding="utf-8")
            out_paths.append(dst_json)
        if src_csv.exists():
            dst_csv = base_out / "compiled_listings.csv"
            dst_csv.write_text(src_csv.read_text(encoding="utf-8"), encoding="utf-8")

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


def _address_has_valid_street_type(v: Any) -> bool:
    if v is None:
        return False
    s = str(v).strip()
    if not s:
        return False
    if _FORBIDDEN_ADDRESS_TOKEN_RE.search(s) is not None:
        return False
    return _VALID_STREET_TYPE_RE.search(s) is not None


def finalize_run(run_dir: Path, selected_zone_uids: List[str], params: Dict[str, Any]) -> Dict[str, Path]:
    result: List[Dict[str, Any]] = []

    for zone_uid in selected_zone_uids:
        zone = get_zone_feature(run_dir, zone_uid)
        z_props = zone.get("properties") or {}
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
                if lat is None or lon is None:
                    continue

                address = it.get("address")
                if not _address_has_valid_street_type(address):
                    continue

                state = it.get("state")
                if state is None or str(state).strip() == "":
                    continue

                min_poi = min([haversine_m(lat, lon, p_lat, p_lon) for p_lat, p_lon in poi_points], default=None)
                min_transport = min([haversine_m(lat, lon, t_lat, t_lon) for t_lat, t_lon in transport_points], default=None)

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
                        **it,
                    }
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
