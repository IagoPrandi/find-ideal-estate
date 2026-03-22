"""Base scraper class shared by all platform adapters.

Aligned with the working legacy scraper (cods_ok/realestate_meta_search.py) for
anti-detection, stealth JS injection, and persistent-context support.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
from abc import ABC, abstractmethod
from typing import Any
from urllib.request import Request, urlopen

# Windows UA matches what a real desktop user would send.
# Legacy uses this exact UA string successfully.
REALISTIC_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

PLAYWRIGHT_LAUNCH_ARGS: list[str] = [
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-infobars",
    "--disable-extensions",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-setuid-sandbox",
]

STEALTH_JS = """
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    window.chrome = {runtime: {}, loadTimes: function(){}, csi: function(){}};
    Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
    Object.defineProperty(navigator, 'languages', {get: () => ['pt-BR','pt','en-US','en']});
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) =>
        parameters.name === 'notifications'
            ? Promise.resolve({state: Notification.permission})
            : originalQuery(parameters);
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
        return True

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
            s = x.strip()
            if not s:
                return None
            # Preserve sign
            sign = ""
            if s.startswith("-"):
                sign = "-"
                s = s[1:]
            elif s.startswith("+"):
                s = s[1:]
            # Remove currency symbols, R$, spaces
            s = re.sub(r"[^\d,.]", "", s)
            if not s:
                return None
            has_dot = "." in s
            has_comma = "," in s
            if has_dot and has_comma:
                # pt-BR price: "3.500,00" → "3500.00"
                s = s.replace(".", "").replace(",", ".")
            elif has_comma and not has_dot:
                # pt-BR decimal: "3500,50" → "3500.50"
                s = s.replace(",", ".")
            # If only dot, treat as standard decimal (e.g. "-23.5672")
            return float(sign + s)
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


def is_cloudflare_block(payload: Any) -> bool:
    """Detect Cloudflare challenge/block pages in payloads."""
    try:
        if isinstance(payload, dict):
            body = payload.get("body") or payload.get("html") or payload.get("text")
            if isinstance(body, str):
                s = body.lower()
                if "cloudflare" in s and "attention required" in s:
                    return True
                if "cf-ray" in s or "__cf" in s:
                    return True
            msg = payload.get("error") or payload.get("message")
            if isinstance(msg, str):
                s = msg.lower()
                if "cloudflare" in s:
                    return True
        if isinstance(payload, str):
            s = payload.lower()
            if "cloudflare" in s and "attention required" in s:
                return True
    except Exception:
        return False
    return False


def _prepare_persistent_profile(platform_name: str) -> str:
    """Clear and return a fresh persistent profile directory for Glue platforms."""
    base_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        ".profiles",
        platform_name,
    )
    if os.path.isdir(base_dir):
        shutil.rmtree(base_dir, ignore_errors=True)
    os.makedirs(base_dir, exist_ok=True)
    return base_dir


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
        self.search_type = search_type
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
