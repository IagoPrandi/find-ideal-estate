"""Base scraper class shared by all platform adapters."""

from __future__ import annotations

import asyncio
import re
from abc import ABC, abstractmethod
from typing import Any
from urllib.request import Request, urlopen

# Linux UA matches container runtime. A Windows UA inside Linux containers can
# increase bot-detection score on target sites.
REALISTIC_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

# Chromium needs these flags in containerized environments.
PLAYWRIGHT_LAUNCH_ARGS: list[str] = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-setuid-sandbox",
]


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
