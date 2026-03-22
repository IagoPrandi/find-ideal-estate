from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from modules.listings.platform_registry import (  # noqa: E402
    PlatformRegistry,
    PlatformRegistryError,
    normalize_platform_name,
)


def test_normalize_platform_name_aliases() -> None:
    assert normalize_platform_name("quinto_andar") == "quintoandar"
    assert normalize_platform_name("Quinto-Andar") == "quintoandar"
    assert normalize_platform_name(" ZAPIMOVEIS ") == "zapimoveis"


def test_registry_loads_known_platforms() -> None:
    root = Path(__file__).resolve().parents[3]
    registry = PlatformRegistry(root / "platforms.yaml")

    available = registry.available_platforms()
    assert "quintoandar" in available
    assert "zapimoveis" in available
    assert "vivareal" in available


def test_registry_resolves_alias_and_scraper_config() -> None:
    root = Path(__file__).resolve().parents[3]
    registry = PlatformRegistry(root / "platforms.yaml")

    canonical = registry.resolve_name("quinto_andar")
    assert canonical == "quintoandar"

    cfg = registry.scraper_config_for("quinto_andar")
    assert cfg["canonical_name"] == "quintoandar"
    assert isinstance(cfg["start_urls"].get("rent"), list)


def test_registry_rejects_unknown_platform() -> None:
    root = Path(__file__).resolve().parents[3]
    registry = PlatformRegistry(root / "platforms.yaml")

    with pytest.raises(PlatformRegistryError):
        registry.resolve_name("unknown_platform")


def test_registry_requires_existing_yaml() -> None:
    with pytest.raises(PlatformRegistryError):
        PlatformRegistry(Path("does_not_exist_platforms.yaml"))
