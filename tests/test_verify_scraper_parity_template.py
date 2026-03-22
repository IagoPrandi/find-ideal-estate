from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


def _load_verify_module() -> object:
    root = Path(__file__).resolve().parents[1]
    module_path = root / "scripts" / "verify_scraper_parity.py"
    spec = importlib.util.spec_from_file_location("verify_scraper_parity", str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load verify_scraper_parity module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_load_expected_counts_from_template(tmp_path: Path) -> None:
    module = _load_verify_module()

    template_path = tmp_path / "parity_template.json"
    payload = {
        "template_version": "v1.0",
        "generated_at": "2026-03-21T00:00:00+00:00",
        "strict_count_parity": {
            "quintoandar": 12,
            "vivareal": 34,
            "zapimoveis": 56,
        },
    }
    template_path.write_text(json.dumps(payload), encoding="utf-8")

    expected, meta = module._load_expected_counts_from_template(str(template_path))

    assert expected == {
        "quintoandar": 12,
        "vivareal": 34,
        "zapimoveis": 56,
    }
    assert meta["template_version"] == "v1.0"
    assert str(template_path) in meta["template_path"]


def test_template_without_strict_count_parity_raises(tmp_path: Path) -> None:
    module = _load_verify_module()

    template_path = tmp_path / "invalid_template.json"
    template_path.write_text(json.dumps({"template_version": "v1.0"}), encoding="utf-8")

    with pytest.raises(ValueError, match="strict_count_parity"):
        module._load_expected_counts_from_template(str(template_path))
