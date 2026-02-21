from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app.schemas import RunCreateRequest, RunStatus


class RunStore:
    def __init__(self, runs_dir: str) -> None:
        self.runs_dir = Path(runs_dir)

    def create_run(self, payload: RunCreateRequest) -> str:
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        run_id = self._generate_run_id(payload)
        run_path = self.runs_dir / run_id
        run_path.mkdir(parents=True, exist_ok=True)
        (run_path / "logs").mkdir(exist_ok=True)
        (run_path / "artifacts").mkdir(exist_ok=True)

        now = self._now_iso()
        status = RunStatus(
            state="created",
            stage="queued",
            stages=[{"name": "init", "state": "created", "updated_at": now}],
            created_at=now,
            updated_at=now,
        )
        self._write_json(run_path / "status.json", status.model_dump())
        self._write_json(run_path / "input.json", payload.model_dump())
        return run_id

    def get_status(self, run_id: str) -> Optional[RunStatus]:
        run_path = self.runs_dir / run_id
        status_path = run_path / "status.json"
        if not status_path.exists():
            return None
        data = self._read_json(status_path)
        return RunStatus(**data)

    def get_input(self, run_id: str) -> Dict[str, Any]:
        run_path = self.runs_dir / run_id
        input_path = run_path / "input.json"
        if not input_path.exists():
            raise FileNotFoundError(f"input.json not found for run_id={run_id}")
        return self._read_json(input_path)

    def update_status(self, run_id: str, state: str, stage: str) -> None:
        run_path = self.runs_dir / run_id
        status_path = run_path / "status.json"
        data = self._read_json(status_path)
        now = self._now_iso()
        data["state"] = state
        data["stage"] = stage
        data["updated_at"] = now
        self._write_json(status_path, data)

    def append_stage(self, run_id: str, name: str, state: str) -> None:
        run_path = self.runs_dir / run_id
        status_path = run_path / "status.json"
        data = self._read_json(status_path)
        now = self._now_iso()
        data.setdefault("stages", []).append(
            {"name": name, "state": state, "updated_at": now}
        )
        data["updated_at"] = now
        self._write_json(status_path, data)

    def _generate_run_id(self, payload: RunCreateRequest) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        payload_json = json.dumps(payload.model_dump(), sort_keys=True)
        digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()[:8]
        return f"{stamp}_{digest}"

    def _write_json(self, path: Path, data: Dict[str, Any]) -> None:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _read_json(self, path: Path) -> Dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()
