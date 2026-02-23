from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from adapters.candidate_zones_adapter import run_candidate_zones
from core.consolidate import consolidate_zones
from core.zone_ops import build_zone_detail
from core.listings_ops import finalize_run, scrape_zone_listings


def main() -> None:
    run_id = f"manual_no_enrich_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    run_dir = Path("/app/runs") / run_id
    params = {
        "max_streets_per_zone": 1,
        "listing_max_pages": 1,
        "listings_headless": True,
    }

    print(f"[STEP] create_run_dir run_id={run_id}")
    run_dir.mkdir(parents=True, exist_ok=True)

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

    raw_outputs = ref_raw / "outputs"
    enriched_dir = run_dir / "zones" / "by_ref" / "ref_0" / "enriched"
    enriched_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(raw_outputs / "zones.geojson", enriched_dir / "zones_enriched.geojson")
    shutil.copy2(raw_outputs / "ranking.csv", enriched_dir / "ranking_enriched.csv")
    print("[STEP] zone_enrich skipped (raw mirrored into enriched)")

    print("[STEP] consolidate start")
    consolidate_zones(run_dir=run_dir, zone_dedupe_m=50.0)
    print("[STEP] consolidate done")

    zones_path = run_dir / "zones" / "consolidated" / "zones_consolidated.geojson"
    features = json.loads(zones_path.read_text(encoding="utf-8")).get("features") or []
    if not features:
        raise RuntimeError("no consolidated zones")

    zone_uid = str((features[0].get("properties") or {}).get("zone_uid"))
    (run_dir / "selected_zones.json").write_text(
        json.dumps({"zone_uids": [zone_uid]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[STEP] select_zone zone_uid={zone_uid} total_zones={len(features)}")

    print("[STEP] detail_zone start")
    detail = build_zone_detail(run_dir=run_dir, zone_uid=zone_uid, params=params)
    print(f"[STEP] detail_zone done streets={detail['streets']}")

    print("[STEP] listings start")
    listing_files = scrape_zone_listings(run_dir=run_dir, zone_uid=zone_uid, params=params)
    print(f"[STEP] listings done listing_files={len(listing_files)}")

    print("[STEP] finalize start")
    out = finalize_run(run_dir=run_dir, selected_zone_uids=[zone_uid], params=params)
    print("[STEP] finalize done")

    final_json = json.loads(Path(out["listings_final_json"]).read_text(encoding="utf-8"))
    bad_coords = sum(1 for x in final_json if x.get("lat") is None or x.get("lon") is None)
    bad_state = sum(1 for x in final_json if not str(x.get("state") or "").strip())

    print(f"RESULT_RUN_ID={run_id}")
    print(f"RESULT_ZONE_UID={zone_uid}")
    print(f"RESULT_FINAL_COUNT={len(final_json)}")
    print(f"RESULT_BAD_COORDS={bad_coords}")
    print(f"RESULT_BAD_STATE={bad_state}")
    print(f"RESULT_LISTINGS_FILES={len(listing_files)}")
    print(f"RESULT_FINAL_JSON={out['listings_final_json']}")


if __name__ == "__main__":
    main()
