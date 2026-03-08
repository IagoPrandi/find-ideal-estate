from __future__ import annotations

import asyncio
from pathlib import Path
from typing import List

from adapters.candidate_zones_adapter import run_candidate_zones
from adapters.zone_enrich_adapter import run_zone_enrich
from app.store import RunStore
from core.consolidate import consolidate_zones
from core.public_safety_ops import (
    build_public_safety_artifacts,
    is_public_safety_enabled,
    is_public_safety_fail_on_error,
)


class Runner:
    def __init__(self, store: RunStore) -> None:
        self.store = store

    async def run_pipeline(self, run_id: str) -> None:
        current_stage = "validate"
        self.store.update_status(run_id, state="running", stage="validate")
        self.store.append_log(run_id, level="info", stage="validate", message="pipeline started")

        try:
            self._stage_mark(run_id, "validate", "running")
            await asyncio.sleep(0.01)

            payload = self.store.get_input(run_id)
            reference_points = payload.get("reference_points") or []
            params = payload.get("params") or {}

            if not params.get("zone_radius_m"):
                raise ValueError(
                    "zone_radius_m is required. Set the zone radius slider before starting a run."
                )

            self._stage_mark(run_id, "validate", "success")
            self.store.append_log(
                run_id,
                level="info",
                stage="validate",
                message=(
                    f"pipeline inputs: refs={len(reference_points)} "
                    f"zone_radius_m={params.get('zone_radius_m', '(not set)')} "
                    f"listing_mode={params.get('listing_mode', 'rent')} "
                    f"listing_max_pages={params.get('listing_max_pages', 2)} "
                    f"max_streets_per_zone={params.get('max_streets_per_zone', 3)} "
                    f"public_safety_enabled={params.get('public_safety_enabled', False)} "
                    f"zone_dedupe_m={params.get('zone_dedupe_m', 50)}"
                ),
            )

            runs_dir = Path(self.store.runs_dir)
            run_dir = runs_dir / run_id
            cache_dir = Path(params.get("cache_dir", "data_cache"))
            geodir = cache_dir / "geosampa"

            # M1: segurança pública (SSP + CEM) opcional
            if is_public_safety_enabled(params):
                current_stage = "public_safety"
                self._stage_mark(run_id, current_stage, "running")
                try:
                    aggregate_path, ref_paths = await asyncio.to_thread(
                        build_public_safety_artifacts,
                        run_dir=run_dir,
                        reference_points=reference_points,
                        params=params,
                    )
                    self.store.append_log(
                        run_id,
                        level="info",
                        stage=current_stage,
                        message=(
                            f"public safety artifacts generated: aggregate={aggregate_path} refs={len(ref_paths)}"
                        ),
                    )
                    self._stage_mark(run_id, current_stage, "success")
                except Exception as ex:
                    if is_public_safety_fail_on_error(params):
                        raise
                    self.store.append_log(
                        run_id,
                        level="warning",
                        stage=current_stage,
                        message=f"public safety skipped due to non-fatal error: {ex}",
                        error_type=type(ex).__name__,
                    )
                    self._stage_mark(run_id, current_stage, "success")
            else:
                self.store.append_stage(run_id, name="public_safety", state="skipped")
                self.store.append_log(
                    run_id,
                    level="info",
                    stage="public_safety",
                    message="public_safety_enabled=false (stage skipped)",
                )

            # M2: zonas por ponto de referência
            current_stage = "zones_by_ref"
            self._stage_mark(run_id, current_stage, "running")
            for idx, ref in enumerate(reference_points):
                ref_dir = run_dir / "zones" / "by_ref" / f"ref_{idx}" / "raw"
                ref_dir.mkdir(parents=True, exist_ok=True)
                await asyncio.to_thread(
                    run_candidate_zones,
                    cache_dir=cache_dir,
                    out_dir=ref_dir,
                    seed_lat=float(ref["lat"]),
                    seed_lon=float(ref["lon"]),
                    params=params,
                )
            self._stage_mark(run_id, current_stage, "success")

            # M2: enriquecimento por ref
            current_stage = "zones_enrich"
            self._stage_mark(run_id, current_stage, "running")
            for idx, _ref in enumerate(reference_points):
                raw_outputs = run_dir / "zones" / "by_ref" / f"ref_{idx}" / "raw" / "outputs"
                enriched_dir = run_dir / "zones" / "by_ref" / f"ref_{idx}" / "enriched"
                enriched_dir.mkdir(parents=True, exist_ok=True)
                await asyncio.to_thread(
                    run_zone_enrich,
                    runs_dir=raw_outputs,
                    geodir=geodir,
                    out_dir=enriched_dir,
                    params=params,
                )
            self._stage_mark(run_id, current_stage, "success")

            # M3: consolidação
            current_stage = "zones_consolidate"
            self._stage_mark(run_id, current_stage, "running")
            zone_dedupe_m = float(params.get("zone_dedupe_m", 50.0))
            await asyncio.to_thread(consolidate_zones, run_dir, zone_dedupe_m=zone_dedupe_m)
            # Log how many zones were produced
            try:
                import json as _json
                consolidated_path = run_dir / "zones" / "consolidated" / "zones_consolidated.geojson"
                zones_count = 0
                if consolidated_path.exists():
                    zones_count = len(_json.loads(consolidated_path.read_text(encoding="utf-8")).get("features", []))
                self.store.append_log(
                    run_id,
                    level="info",
                    stage=current_stage,
                    message=f"consolidação concluída: zones_count={zones_count} zone_dedupe_m={zone_dedupe_m}",
                )
            except Exception:
                pass
            self._stage_mark(run_id, current_stage, "success")

            self.store.update_status(run_id, state="success", stage="done")
            self.store.append_log(run_id, level="info", stage="done", message="pipeline finished successfully")
        except Exception as ex:
            self._stage_mark(run_id, current_stage, "failed")
            self.store.set_failed(run_id, stage=current_stage, error_type=type(ex).__name__, message=str(ex))
            self.store.append_log(
                run_id,
                level="error",
                stage=current_stage,
                message=str(ex),
                error_type=type(ex).__name__,
            )

    def _stage_mark(self, run_id: str, name: str, state: str) -> None:
        self.store.append_stage(run_id, name=name, state=state)
        self.store.update_status(run_id, state="running", stage=name)
        self.store.append_log(run_id, level="info", stage=name, message=f"stage={name} state={state}")
