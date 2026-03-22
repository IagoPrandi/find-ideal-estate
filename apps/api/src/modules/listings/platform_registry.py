"""Runtime platform registry loaded from platforms.yaml.

This module restores config-driven platform behavior while preserving compatibility
with current canonical platform names used by the API runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from core.config import ConfigurationError, get_settings
from modules.listings.models import FREE_PLATFORMS
from modules.listings.scrapers import (
    QuintoAndarScraper,
    ScraperBase,
    VivaRealScraper,
    ZapImoveisScraper,
)


class PlatformRegistryError(RuntimeError):
    """Raised when the platform registry is invalid."""


def normalize_platform_name(name: str) -> str:
    """Normalize aliases such as quinto_andar/quinto-andar to quintoandar."""
    return "".join(ch for ch in name.strip().lower() if ch.isalnum())


@dataclass(frozen=True)
class PlatformRuntimeConfig:
    """Canonical runtime settings for one platform."""

    canonical_name: str
    source_key: str
    enabled: bool
    tier: str | None
    start_urls_rent: list[str]
    start_urls_buy: list[str]
    include_url_substrings: list[str]
    prefer_headful: bool
    max_pages: int

    def as_scraper_config(self) -> dict[str, Any]:
        """Return shape consumed by scraper classes."""
        return {
            "canonical_name": self.canonical_name,
            "source_key": self.source_key,
            "enabled": self.enabled,
            "tier": self.tier,
            "start_urls": {
                "rent": list(self.start_urls_rent),
                "buy": list(self.start_urls_buy),
            },
            "include_url_substrings": list(self.include_url_substrings),
            "prefer_headful": self.prefer_headful,
            "max_pages": self.max_pages,
        }


class PlatformRegistry:
    """Registry of configured platforms and scraper class mappings."""

    _SCRAPER_MAP: dict[str, type[ScraperBase]] = {
        "quintoandar": QuintoAndarScraper,
        "zapimoveis": ZapImoveisScraper,
        "vivareal": VivaRealScraper,
    }

    def __init__(self, yaml_path: Path) -> None:
        self._yaml_path = yaml_path
        self._platforms: dict[str, PlatformRuntimeConfig] = {}
        self._load()

    @property
    def yaml_path(self) -> Path:
        return self._yaml_path

    def _load(self) -> None:
        if not self._yaml_path.exists():
            raise PlatformRegistryError(
                f"platforms.yaml not found at: {self._yaml_path}"
            )

        try:
            payload = yaml.safe_load(self._yaml_path.read_text(encoding="utf-8")) or {}
        except Exception as exc:  # noqa: BLE001
            raise PlatformRegistryError(
                f"Failed to parse platforms.yaml at {self._yaml_path}: {exc}"
            ) from exc

        raw_platforms = payload.get("platforms")
        if not isinstance(raw_platforms, dict) or not raw_platforms:
            raise PlatformRegistryError(
                "platforms.yaml must define a non-empty 'platforms' mapping"
            )

        parsed: dict[str, PlatformRuntimeConfig] = {}
        for source_key, cfg in raw_platforms.items():
            if not isinstance(cfg, dict):
                continue

            canonical = normalize_platform_name(str(source_key))
            if not canonical:
                continue

            start_urls = cfg.get("start_urls") or {}
            rent_urls = list(start_urls.get("rent") or [])
            buy_urls = list(start_urls.get("buy") or [])

            runtime_cfg = PlatformRuntimeConfig(
                canonical_name=canonical,
                source_key=str(source_key),
                enabled=bool(cfg.get("enabled", True)),
                tier=str(cfg.get("tier")) if cfg.get("tier") is not None else None,
                start_urls_rent=[str(u) for u in rent_urls if isinstance(u, str) and u.strip()],
                start_urls_buy=[str(u) for u in buy_urls if isinstance(u, str) and u.strip()],
                include_url_substrings=[
                    str(v)
                    for v in (cfg.get("include_url_substrings") or [])
                    if isinstance(v, str) and v.strip()
                ],
                prefer_headful=bool(cfg.get("prefer_headful", False)),
                max_pages=max(1, int(cfg.get("max_pages", 1) or 1)),
            )

            if runtime_cfg.enabled:
                parsed[canonical] = runtime_cfg

        if not parsed:
            raise PlatformRegistryError("No enabled platforms found in platforms.yaml")

        missing_scrapers = [name for name in parsed if name not in self._SCRAPER_MAP]
        if missing_scrapers:
            raise PlatformRegistryError(
                "Configured platforms without scraper implementation: "
                + ", ".join(sorted(missing_scrapers))
            )

        self._platforms = parsed

    def available_platforms(self) -> list[str]:
        return sorted(self._platforms.keys())

    def default_free_platforms(self) -> list[str]:
        from_tier = sorted(
            p.canonical_name for p in self._platforms.values() if p.tier == "free"
        )
        if from_tier:
            return from_tier

        configured_free = sorted(
            p for p in FREE_PLATFORMS if normalize_platform_name(p) in self._platforms
        )
        if configured_free:
            return configured_free

        return self.available_platforms()

    def resolve_name(self, name: str) -> str:
        canonical = normalize_platform_name(name)
        if canonical not in self._platforms:
            raise PlatformRegistryError(
                f"Unknown platform '{name}'. Available: {self.available_platforms()}"
            )
        return canonical

    def resolve_names(self, names: list[str]) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        for name in names:
            canonical = self.resolve_name(name)
            if canonical in seen:
                continue
            seen.add(canonical)
            ordered.append(canonical)
        return ordered

    def scraper_class_for(self, platform: str) -> type[ScraperBase]:
        canonical = self.resolve_name(platform)
        scraper_cls = self._SCRAPER_MAP.get(canonical)
        if scraper_cls is None:
            raise PlatformRegistryError(
                f"No scraper class registered for platform '{canonical}'"
            )
        return scraper_cls

    def scraper_config_for(self, platform: str) -> dict[str, Any]:
        canonical = self.resolve_name(platform)
        return self._platforms[canonical].as_scraper_config()


def _default_platforms_yaml_path() -> Path:
    # <repo>/apps/api/src/modules/listings/platform_registry.py -> parents[5] is repo root
    return Path(__file__).resolve().parents[5] / "platforms.yaml"


@lru_cache(maxsize=1)
def get_platform_registry() -> PlatformRegistry:
    configured = None
    try:
        settings = get_settings()
        configured = getattr(settings, "platforms_yaml_path", None)
    except ConfigurationError:
        # Test and script environments may not load full runtime env vars.
        configured = None

    if configured:
        yaml_path = Path(configured)
        if not yaml_path.is_absolute():
            yaml_path = _default_platforms_yaml_path().parent / yaml_path
    else:
        yaml_path = _default_platforms_yaml_path()
    return PlatformRegistry(yaml_path=yaml_path)
