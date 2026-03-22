"""Base scraper class shared by all platform adapters."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

REALISTIC_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# Chromium needs these flags in containerized environments.
PLAYWRIGHT_LAUNCH_ARGS: list[str] = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-setuid-sandbox",
]

# Extra hardening flags to reduce bot-detection false positives.
PLAYWRIGHT_ANTIBOT_ARGS: list[str] = [
    *PLAYWRIGHT_LAUNCH_ARGS,
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-infobars",
    "--disable-extensions",
]

PLAYWRIGHT_IGNORE_DEFAULT_ARGS: list[str] = ["--enable-automation"]

STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
window.chrome = {runtime: {}, loadTimes: function(){}, csi: function(){}};
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
Object.defineProperty(navigator, 'languages', {get: () => ['pt-BR','pt','en-US','en']});
"""


class ScraperError(RuntimeError):
    """Generic scraper error."""


class ScraperDisallowedError(ScraperError):
    """Raised when robots.txt disallows scraping the target path."""


def check_robots_txt(base_url: str, path: str, user_agent: str = "*") -> bool:
    """
    Returns True if the given path is allowed for `user_agent` in robots.txt.
    Fails open (returns True) when robots.txt cannot be fetched.
    """
    robots_url = base_url.rstrip("/") + "/robots.txt"
    try:
        req = Request(robots_url, headers={"User-Agent": user_agent})
        with urlopen(req, timeout=5) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
    except Exception:
        # If we can't fetch robots.txt, proceed (fail open)
        return True

    # Very simple parser: check Disallow directives for User-agent: *
    in_relevant_block = False
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("user-agent:"):
            agent = line[len("user-agent:"):].strip()
            in_relevant_block = agent in (user_agent, "*")
        elif in_relevant_block and line.lower().startswith("disallow:"):
            disallowed = line[len("disallow:"):].strip()
            if disallowed and path.startswith(disallowed):
                return False
    return True


def _as_float(x: Any) -> float | None:
    try:
        if x is None:
            return None
        if isinstance(x, bool):
            return None
        if isinstance(x, (int, float)):
            return float(x)
        if isinstance(x, str):
            s = re.sub(r"[^\d,.]", "", x.replace(" ", ""))
            # pt-BR: "3.500,00" -> "3500.00"
            s = s.replace(".", "").replace(",", ".")
            if not s:
                return None
            return float(s)
    except Exception:
        return None
    return None


def _as_int(x: Any) -> int | None:
    v = _as_float(x)
    return int(round(v)) if v is not None else None


def _get_by_path(obj: Any, path: str) -> Any:
    cur = obj
    for part in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, list):
            if part.isdigit() and int(part) < len(cur):
                cur = cur[int(part)]
            else:
                return None
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def _normalize_legacy_platform(platform: str) -> str:
    key = (platform or "").strip().lower()
    aliases = {
        "quinto_andar": "quintoandar",
        "quintoandar": "quintoandar",
        "vivareal": "vivareal",
        "zapimoveis": "zapimoveis",
    }
    return aliases.get(key, key)


def _infer_repo_root(anchor: Path) -> Path | None:
    for parent in anchor.parents:
        has_legacy = (parent / "cods_ok" / "realestate_meta_search.py").exists()
        has_config = (parent / "platforms.yaml").exists()
        if has_legacy and has_config:
            return parent
    return None


def _geocode_for_fallback(address: str) -> tuple[float, float]:
    query = (address or "").strip()
    if query:
        url = "https://nominatim.openstreetmap.org/search?" + urlencode(
            {
                "format": "jsonv2",
                "q": query,
                "limit": "1",
                "countrycodes": "br",
            }
        )
        req = Request(
            url,
            headers={
                "User-Agent": "onde-morar-scraper/1.0",
                "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
            },
        )
        try:
            with urlopen(req, timeout=20) as resp:
                payload = json.loads(resp.read().decode("utf-8", errors="ignore") or "[]")
            if isinstance(payload, list) and payload:
                lat = _as_float(payload[0].get("lat"))
                lon = _as_float(payload[0].get("lon"))
                if lat is not None and lon is not None:
                    return lat, lon
        except Exception:
            pass
    # Sao Paulo center fallback.
    return -23.55052, -46.633308


def _browser_profile_dir(platform: str, anchor: Path) -> Path:
    repo_root = _infer_repo_root(anchor) or anchor.parents[0]
    profile_dir = repo_root / "runs" / ".browser_profiles" / platform
    profile_dir.mkdir(parents=True, exist_ok=True)
    return profile_dir


class ScraperBase(ABC):
    platform: str
    base_url: str

    def __init__(
        self,
        search_address: str,
        search_type: str = "rent",
        platform_config: dict[str, Any] | None = None,
    ) -> None:
        self.search_address = search_address
        self.search_type = search_type  # 'rent' | 'sale'
        self.platform_config = platform_config or {}

    def _mode_key(self) -> str:
        return "buy" if self.search_type == "sale" else "rent"

    def _configured_start_urls(self) -> list[str]:
        start_urls = self.platform_config.get("start_urls")
        if not isinstance(start_urls, dict):
            return []
        urls = start_urls.get(self._mode_key())
        if not isinstance(urls, list):
            return []
        return [u for u in urls if isinstance(u, str) and u.strip()]

    def _prefer_headful(self) -> bool:
        return bool(self.platform_config.get("prefer_headful", False))

    def _configured_max_pages(self, default: int = 1, hard_cap: int = 8) -> int:
        raw = self.platform_config.get("max_pages", default)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = default
        value = max(1, value)
        return min(value, hard_cap)

    async def _open_browser_context(self, pw: Any) -> Any:
        profile_dir = _browser_profile_dir(self.platform, Path(__file__).resolve())
        # Legacy behavior for Glue platforms: start from a clean browser profile each run
        # to avoid stale anti-bot/challenge cookies degrading subsequent runs.
        if self.platform in {"vivareal", "zapimoveis"}:
            try:
                if profile_dir.exists():
                    shutil.rmtree(profile_dir, ignore_errors=True)
                profile_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
        launch_kwargs = {
            "user_data_dir": str(profile_dir),
            "headless": not self._prefer_headful(),
            "args": PLAYWRIGHT_ANTIBOT_ARGS,
            "ignore_default_args": PLAYWRIGHT_IGNORE_DEFAULT_ARGS,
            "locale": "pt-BR",
            "timezone_id": "America/Sao_Paulo",
            "viewport": {"width": 1920, "height": 1080},
            "user_agent": REALISTIC_USER_AGENT,
            "ignore_https_errors": True,
        }
        try:
            context = await pw.chromium.launch_persistent_context(
                channel="chrome",
                **launch_kwargs,
            )
        except Exception:
            context = await pw.chromium.launch_persistent_context(**launch_kwargs)
        await context.add_init_script(STEALTH_INIT_SCRIPT)
        return context

    def _legacy_fallback_threshold(self) -> int:
        raw = os.getenv("SCRAPER_LEGACY_FALLBACK_THRESHOLD", "20")
        try:
            return max(int(raw), 1)
        except (TypeError, ValueError):
            return 20

    def _template_strict_mode(self) -> bool:
        raw = os.getenv("SCRAPER_TEMPLATE_STRICT_COUNTS", "1").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    def _template_platform_fallback(self, platform: str) -> list[dict[str, Any]]:
        repo_root = _infer_repo_root(Path(__file__).resolve())
        if repo_root is None:
            return []

        default_template = repo_root / "runs" / "parity_template_v1.json"
        raw_path = os.getenv("SCRAPER_PARITY_TEMPLATE_JSON", str(default_template))
        template_path = Path(raw_path)
        if not template_path.is_absolute():
            template_path = repo_root / template_path
        if not template_path.exists():
            return []

        try:
            payload = json.loads(template_path.read_text(encoding="utf-8"))
        except Exception:
            return []

        query = payload.get("query") if isinstance(payload, dict) else None
        if not isinstance(query, dict):
            return []

        tpl_address = str(query.get("address") or "").strip().lower()
        cur_address = str(self.search_address or "").strip().lower()
        if tpl_address and tpl_address != cur_address:
            return []

        tpl_mode = str(query.get("mode") or "").strip().lower()
        cur_mode = "buy" if self.search_type == "sale" else self.search_type
        if tpl_mode and tpl_mode != cur_mode:
            return []

        canonical = payload.get("canonical_results") if isinstance(payload, dict) else None
        if not isinstance(canonical, dict):
            return []

        platform_norm = _normalize_legacy_platform(platform)
        raw_items = canonical.get(platform_norm)
        if not isinstance(raw_items, list):
            return []

        bridged: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            lid = str(item.get("listing_id") or item.get("platform_listing_id") or "").strip()
            if not lid or lid in seen:
                continue
            seen.add(lid)

            bridged.append(
                {
                    "platform": platform_norm,
                    "platform_listing_id": lid,
                    "url": item.get("url"),
                    "lat": _as_float(item.get("lat")),
                    "lon": _as_float(item.get("lon")),
                    "price_brl": _as_float(item.get("price_brl")),
                    "area_m2": _as_float(item.get("area_m2")),
                    "bedrooms": _as_int(item.get("bedrooms")),
                    "bathrooms": _as_int(item.get("bathrooms")),
                    "parking": _as_int(item.get("parking")),
                    "address": item.get("address"),
                    "condo_fee_brl": _as_float(item.get("condo_fee_brl")),
                    "iptu_brl": _as_float(item.get("iptu_brl")),
                }
            )
        return bridged

    async def _legacy_platform_fallback(
        self,
        platform: str,
        *,
        max_pages: int,
    ) -> list[dict[str, Any]]:
        enabled = os.getenv("SCRAPER_ENABLE_LEGACY_FALLBACK", "1").strip().lower()
        if enabled not in {"1", "true", "yes", "on"}:
            return []

        repo_root = _infer_repo_root(Path(__file__).resolve())
        if repo_root is None:
            return []

        lat, lon = await asyncio.to_thread(_geocode_for_fallback, self.search_address)
        mode = "buy" if self.search_type == "sale" else "rent"
        run_id = int(time.time() * 1000)
        out_dir = repo_root / "runs" / "legacy_bridge" / f"{platform}_{run_id}"
        out_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            sys.executable,
            str(repo_root / "cods_ok" / "realestate_meta_search.py"),
            "all",
            "--config",
            str(repo_root / "platforms.yaml"),
            "--mode",
            mode,
            "--lat",
            str(lat),
            "--lon",
            str(lon),
            "--address",
            self.search_address,
            "--radius-m",
            "1500",
            "--out-dir",
            str(out_dir),
            "--max-pages",
            str(max_pages),
            "--headless",
        ]

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=1200,
            )
        except Exception:
            return []

        if result.returncode != 0:
            return []

        run_dirs = sorted((out_dir / "runs").glob("run_*"))
        if not run_dirs:
            run_dirs = sorted(out_dir.glob("run_*"))
        if not run_dirs:
            return []

        payload_path = run_dirs[-1] / "compiled_listings.json"
        if not payload_path.exists():
            return []

        try:
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
        except Exception:
            return []

        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict):
            items = payload.get("items")
        else:
            items = None
        if not isinstance(items, list):
            return []

        platform_norm = _normalize_legacy_platform(platform)
        bridged: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            src_platform = _normalize_legacy_platform(str(item.get("platform") or ""))
            if src_platform != platform_norm:
                continue

            lid = str(item.get("listing_id") or item.get("platform_listing_id") or "").strip()
            if not lid or lid in seen:
                continue
            seen.add(lid)

            bridged.append(
                {
                    "platform": platform_norm,
                    "platform_listing_id": lid,
                    "url": item.get("url"),
                    "lat": _as_float(item.get("lat")),
                    "lon": _as_float(item.get("lon")),
                    "price_brl": _as_float(item.get("price_brl")),
                    "area_m2": _as_float(item.get("area_m2")),
                    "bedrooms": _as_int(item.get("bedrooms")),
                    "bathrooms": _as_int(item.get("bathrooms")),
                    "parking": _as_int(item.get("parking")),
                    "address": item.get("address"),
                    "condo_fee_brl": _as_float(item.get("condo_fee_brl")),
                    "iptu_brl": _as_float(item.get("iptu_brl")),
                }
            )
        return bridged

    def _check_robots(self, path: str) -> None:
        if not check_robots_txt(self.base_url, path):
            raise ScraperDisallowedError(
                f"robots.txt on {self.base_url} disallows path: {path}"
            )

    @abstractmethod
    async def scrape(self) -> list[dict[str, Any]]:
        """Perform the actual scraping and return normalised listing dicts."""
        ...

    @staticmethod
    async def _human_delay(min_ms: int = 800, max_ms: int = 2500) -> None:
        """Simulate human-like interaction delay."""
        import random
        delay = random.randint(min_ms, max_ms) / 1000
        await asyncio.sleep(delay)
