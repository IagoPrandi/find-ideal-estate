from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from adapters.candidate_zones_adapter import run_candidate_zones
from adapters.listings_adapter import run_listings_all
from core.consolidate import consolidate_zones
from core.listings_ops import finalize_run
from core.zone_ops import build_zone_detail, get_zone_feature, zone_centroid_lonlat


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _items_from_compiled(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    data = _load_json(path)
    if isinstance(data, dict):
        items = data.get("items")
        return items if isinstance(items, list) else []
    if isinstance(data, list):
        return data
    return []


def _has_state(v: Any) -> bool:
    return bool(str(v or "").strip())


def _has_coord(it: Dict[str, Any]) -> bool:
    lat = it.get("lat", it.get("latitude"))
    lon = it.get("lon", it.get("longitude"))
    return lat not in (None, "") and lon not in (None, "")


def main() -> None:
    run_id = f"manual_noapi_both_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    run_dir = Path("/app/runs") / run_id
    params = {
        "max_streets_per_zone": 1,
        "listing_max_pages": 1,
        "listings_headless": True,
        "listing_radius_m": 1500,
    }

    print(f"[STEP] create_run_dir run_id={run_id}")
    run_dir.mkdir(parents=True, exist_ok=True)

    # 1) Point -> zones
    ref_raw = run_dir / "zones" / "by_ref" / "ref_0" / "raw"
    ref_raw.mkdir(parents=True, exist_ok=True)
    print("[STEP] candidate_zones start")
    run_candidate_zones(
        cache_dir=Path("/app/data_cache"),
        out_dir=ref_raw,
        seed_lat=-23.585068145112295,
        seed_lon=-46.690640014541714,
        params=params,
    )
    print("[STEP] candidate_zones done")

    # 2) Skip enrich (mirror)
    raw_outputs = ref_raw / "outputs"
    enriched_dir = run_dir / "zones" / "by_ref" / "ref_0" / "enriched"
    enriched_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(raw_outputs / "zones.geojson", enriched_dir / "zones_enriched.geojson")
    shutil.copy2(raw_outputs / "ranking.csv", enriched_dir / "ranking_enriched.csv")
    print("[STEP] zone_enrich skipped (raw mirrored into enriched)")

    # 3) Consolidate
    print("[STEP] consolidate start")
    consolidate_zones(run_dir=run_dir, zone_dedupe_m=50.0)
    print("[STEP] consolidate done")

    # 4) Select one zone
    zones_path = run_dir / "zones" / "consolidated" / "zones_consolidated.geojson"
    features = (_load_json(zones_path).get("features") or [])
    if not features:
        raise RuntimeError("no consolidated zones")
    zone_uid = str((features[0].get("properties") or {}).get("zone_uid"))
    (run_dir / "selected_zones.json").write_text(
        json.dumps({"zone_uids": [zone_uid]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[STEP] select_zone zone_uid={zone_uid} total_zones={len(features)}")

    # 5) Build detail (streets + pois + transport)
    print("[STEP] detail_zone start")
    detail = build_zone_detail(run_dir=run_dir, zone_uid=zone_uid, params=params)
    print(f"[STEP] detail_zone done streets_path={detail['streets']}")

    streets_data = _load_json(detail["streets"])
    streets = streets_data.get("streets") or []
    if not streets:
        raise RuntimeError("no streets found for selected zone")

    zone_feature = get_zone_feature(run_dir=run_dir, zone_uid=zone_uid)
    center_lon, center_lat = zone_centroid_lonlat(zone_feature)

    print(f"[STEP] listings_probe start candidate_streets={len(streets)}")
    selected_street = None

    for idx, street in enumerate(streets[:12], start=1):
        slug = street.strip().lower().replace(" ", "-")
        probe_out = run_dir / "_probe" / slug / "listings"
        try:
            run_root = run_listings_all(
                config_path=Path("/app/platforms.yaml"),
                out_dir=probe_out,
                mode="rent",
                address=f"{street}, São Paulo, SP",
                center_lat=center_lat,
                center_lon=center_lon,
                radius_m=float(params["listing_radius_m"]),
                max_pages=int(params["listing_max_pages"]),
                headless=bool(params["listings_headless"]),
            )
        except Exception as ex:
            print(f"[STEP] listings_probe street_idx={idx} street='{street}' ERROR={type(ex).__name__}: {ex}")
            continue

        items = _items_from_compiled(run_root / "compiled_listings.json")
        qa_state = [it for it in items if str(it.get("platform")) == "quinto_andar" and _has_state(it.get("state"))]
        vr_state = [it for it in items if str(it.get("platform")) == "vivareal" and _has_state(it.get("state"))]
        qa_state_coord = [it for it in qa_state if _has_coord(it)]
        vr_state_coord = [it for it in vr_state if _has_coord(it)]

        print(
            f"[STEP] listings_probe street_idx={idx} street='{street}' total_items={len(items)} "
            f"qa_with_state={len(qa_state)} vr_with_state={len(vr_state)} "
            f"qa_with_state_coord={len(qa_state_coord)} vr_with_state_coord={len(vr_state_coord)}"
        )

        if qa_state_coord and vr_state_coord:
            selected_street = street
            break

    if not selected_street:
        raise RuntimeError("no street returned both platforms with state+coords in probe set")

    # 6) Persist only chosen street output under expected path
    print(f"[STEP] listings_selected street='{selected_street}'")
    streets_root = run_dir / "zones" / "detail" / zone_uid / "streets"
    if streets_root.exists():
        shutil.rmtree(streets_root)

    selected_slug = selected_street.strip().lower().replace(" ", "-")
    final_out = streets_root / selected_slug / "listings"
    final_out.mkdir(parents=True, exist_ok=True)

    run_root = run_listings_all(
        config_path=Path("/app/platforms.yaml"),
        out_dir=final_out,
        mode="rent",
        address=f"{selected_street}, São Paulo, SP",
        center_lat=center_lat,
        center_lon=center_lon,
        radius_m=float(params["listing_radius_m"]),
        max_pages=int(params["listing_max_pages"]),
        headless=bool(params["listings_headless"]),
    )
    shutil.copy2(run_root / "compiled_listings.json", final_out / "compiled_listings.json")
    shutil.copy2(run_root / "compiled_listings.csv", final_out / "compiled_listings.csv")

    # 7) Finalize
    print("[STEP] finalize start")
    out = finalize_run(run_dir=run_dir, selected_zone_uids=[zone_uid], params=params)
    print("[STEP] finalize done")

    final_items = _load_json(out["listings_final_json"])
    qa_final = [it for it in final_items if str(it.get("platform")) == "quinto_andar"]
    vr_final = [it for it in final_items if str(it.get("platform")) == "vivareal"]
    qa_state_missing = sum(1 for it in qa_final if not _has_state(it.get("state")))
    vr_state_missing = sum(1 for it in vr_final if not _has_state(it.get("state")))

    print(f"RESULT_RUN_ID={run_id}")
    print(f"RESULT_ZONE_UID={zone_uid}")
    print(f"RESULT_SELECTED_STREET={selected_street}")
    print(f"RESULT_FINAL_COUNT={len(final_items)}")
    print(f"RESULT_QA_COUNT={len(qa_final)}")
    print(f"RESULT_VR_COUNT={len(vr_final)}")
    print(f"RESULT_QA_STATE_MISSING={qa_state_missing}")
    print(f"RESULT_VR_STATE_MISSING={vr_state_missing}")
    print(f"RESULT_FINAL_JSON={out['listings_final_json']}")


if __name__ == "__main__":
    main()
