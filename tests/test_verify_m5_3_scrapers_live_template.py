from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


def _load_module() -> object:
    root = Path(__file__).resolve().parents[1]
    module_path = root / "scripts" / "verify_m5_3_scrapers_live.py"
    spec = importlib.util.spec_from_file_location("verify_m5_3_scrapers_live", str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load verify_m5_3_scrapers_live module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_expected_count_from_template_success(tmp_path: Path) -> None:
    module = _load_module()

    template_path = tmp_path / "parity_template.json"
    payload = {
        "query": {
            "address": "Rua Guaipa, Vila Leopoldina, Sao Paulo - SP",
            "mode": "rent",
        },
        "strict_count_parity": {
            "vivareal": 30,
            "zapimoveis": 110,
            "quintoandar": 84,
        },
    }
    template_path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = module._load_template_payload(str(template_path))
    expected = module._expected_count_from_template(
        loaded,
        platform="vivareal",
        address="Rua Guaipa, Vila Leopoldina, Sao Paulo - SP",
        search_type="rent",
    )

    assert expected == 30


def test_expected_count_from_template_address_mismatch(tmp_path: Path) -> None:
    module = _load_module()

    template_path = tmp_path / "parity_template.json"
    payload = {
        "query": {
            "address": "Rua Guaipa, Vila Leopoldina, Sao Paulo - SP",
            "mode": "rent",
        },
        "strict_count_parity": {
            "vivareal": 30,
        },
    }
    template_path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = module._load_template_payload(str(template_path))
    with pytest.raises(ValueError, match="query.address"):
        module._expected_count_from_template(
            loaded,
            platform="vivareal",
            address="Avenida Paulista, 1000, Sao Paulo",
            search_type="rent",
        )


def test_expected_count_from_template_mode_mismatch(tmp_path: Path) -> None:
    module = _load_module()

    template_path = tmp_path / "parity_template.json"
    payload = {
        "query": {
            "address": "Rua Guaipa, Vila Leopoldina, Sao Paulo - SP",
            "mode": "buy",
        },
        "strict_count_parity": {
            "vivareal": 30,
        },
    }
    template_path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = module._load_template_payload(str(template_path))
    with pytest.raises(ValueError, match="query.mode"):
        module._expected_count_from_template(
            loaded,
            platform="vivareal",
            address="Rua Guaipa, Vila Leopoldina, Sao Paulo - SP",
            search_type="rent",
        )
