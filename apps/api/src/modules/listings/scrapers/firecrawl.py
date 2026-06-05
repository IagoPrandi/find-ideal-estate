"""Experimental Firecrawl-backed scrapers for VivaReal and ZapImoveis.

These adapters keep the same normalized output shape as the Playwright scrapers,
but call Firecrawl's v2 scrape endpoint and parse the rendered Next.js payload
from rawHtml so coordinates are preserved.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .base import ScraperBase, ScraperError, _as_float, _as_int, _normalize_image_url
from .vivareal import _build_vivareal_scrape_url
from .zapimoveis import _build_zap_scrape_url

FIRECRAWL_API_URL = "https://api.firecrawl.dev/v2/scrape"


def _address_second_part_is_number(address: str) -> bool:
    parts = [part.strip() for part in (address or "").split(",") if part.strip()]
    return len(parts) > 1 and bool(re.fullmatch(r"\d+[A-Za-z]?", parts[1]))


def _extract_listing_id(url: str) -> str | None:
    match = re.search(r"-id-(\d+)(?:/|$)", url)
    if not match:
        match = re.search(r"/imovel/(\d+)(?:/|$)", url)
    if not match:
        match = re.search(r"(\d{6,})", url)
    return match.group(1) if match else None


def _as_firecrawl_links(raw_links: Any) -> list[str]:
    if not isinstance(raw_links, list):
        return []

    links: list[str] = []
    for entry in raw_links:
        if isinstance(entry, str):
            links.append(entry)
            continue
        if isinstance(entry, dict):
            value = entry.get("url") or entry.get("href")
            if isinstance(value, str):
                links.append(value)
    return links


def _normalize_platform_url(url: str, base_url: str) -> str | None:
    value = (url or "").strip()
    if not value:
        return None
    if value.startswith("//"):
        value = f"https:{value}"
    elif value.startswith("/"):
        value = f"{base_url.rstrip('/')}{value}"
    if not value.startswith(("http://", "https://")):
        return None

    base_host = urlsplit(base_url).netloc.lower().removeprefix("www.")
    host = urlsplit(value).netloc.lower().removeprefix("www.")
    if base_host not in host:
        return None
    if "/imovel/" not in urlsplit(value).path:
        return None
    return value


def _listing_markdown_context(markdown: str, url: str, window: int = 2200) -> str:
    idx = markdown.find(url)
    if idx < 0:
        # Firecrawl may escape slashes or strip query strings in markdown links.
        path = urlsplit(url).path
        idx = markdown.find(path) if path else -1
    if idx < 0:
        return ""
    start = max(0, idx - window)
    return markdown[start:idx]


def _extract_link_title(markdown: str, url: str) -> str | None:
    idx = markdown.find(url)
    if idx < 0:
        return None
    end = markdown.find(")", idx)
    if end < 0:
        return None
    link_tail = markdown[idx:end]
    match = re.search(r'"([^"]{12,})"', link_tail)
    return match.group(1).strip() if match else None


def _last_match(pattern: str, text: str, flags: int = 0) -> re.Match[str] | None:
    matches = list(re.finditer(pattern, text, flags))
    return matches[-1] if matches else None


def _parse_price(context: str) -> float | None:
    match = _last_match(r"R\$\s*[\d\.]+(?:,\d{2})?(?:/\w+)?", context)
    return _as_float(match.group(0)) if match else None


def _parse_area(url: str, context: str) -> float | None:
    match = re.search(r"(\d{1,4})m2", url, re.IGNORECASE)
    if not match:
        match = _last_match(r"(\d{1,4})\s*m(?:²|2)", context, re.IGNORECASE)
    return _as_float(match.group(1)) if match else None


def _parse_count_from_url_or_context(
    url_pattern: str,
    context_pattern: str,
    url: str,
    context: str,
) -> int | None:
    match = re.search(url_pattern, url, re.IGNORECASE)
    if not match:
        match = _last_match(context_pattern, context, re.IGNORECASE)
    if not match:
        return None
    for group in match.groups():
        if group is not None:
            return _as_int(group)
    return None


def _parse_image_url(context: str, base_url: str) -> str | None:
    matches = list(
        re.finditer(
            r"!\[[^\]]*\]\((https?://[^)\s]+|/[^)\s]+)",
            context,
            re.IGNORECASE,
        )
    )
    if not matches:
        return None
    raw_url = matches[-1].group(1).strip()
    return _normalize_image_url(raw_url, platform_base=base_url)


def _decode_next_f_chunks(raw_html: str) -> str:
    chunks: list[str] = []
    for match in re.finditer(
        r"self\.__next_f\.push\(\[\d+,\"(.*?)\"\]\)</script>",
        raw_html,
        re.DOTALL,
    ):
        encoded = match.group(1)
        try:
            chunks.append(json.loads(f'"{encoded}"'))
        except json.JSONDecodeError:
            continue
    return "\n".join(chunks)


def _extract_json_array_at(text: str, start: int) -> str | None:
    if start < 0 or start >= len(text) or text[start] != "[":
        return None

    depth = 0
    in_string = False
    escaped = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]
    return None


def _extract_nextjs_listing_payloads(raw_html: str) -> list[dict[str, Any]]:
    decoded = _decode_next_f_chunks(raw_html)
    if not decoded:
        return []

    listings: list[dict[str, Any]] = []
    search_from = 0
    marker = '"listings":'
    while True:
        idx = decoded.find(marker, search_from)
        if idx < 0:
            break
        array_start = decoded.find("[", idx + len(marker))
        array_text = _extract_json_array_at(decoded, array_start)
        search_from = idx + len(marker)
        if not array_text:
            continue
        try:
            payload = json.loads(array_text)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, list):
            continue
        for item in payload:
            if isinstance(item, dict):
                listings.append(item)
    return listings


def _format_firecrawl_image_url(value: Any, base_url: str) -> str | None:
    if not isinstance(value, str):
        return None
    if "{" in value or "}" in value:
        return None
    return _normalize_image_url(value, platform_base=base_url)


def _first_firecrawl_image(item: dict[str, Any], base_url: str) -> str | None:
    medias = item.get("medias")
    images = medias.get("images") if isinstance(medias, dict) else None
    if not isinstance(images, list):
        return None
    for image in images:
        if not isinstance(image, dict):
            continue
        url = _format_firecrawl_image_url(
            image.get("url")
            or image.get("src")
            or image.get("dangerousSrc")
            or image.get("imageUrl"),
            base_url,
        )
        if url:
            return url
    return None


def _price_info(item: dict[str, Any], search_type: str) -> dict[str, Any]:
    prices = item.get("prices")
    if not isinstance(prices, dict):
        return {}
    key = "sale" if search_type == "sale" else "rental"
    preferred = prices.get(key)
    if isinstance(preferred, dict):
        return preferred
    for candidate in prices.values():
        if isinstance(candidate, dict):
            return candidate
    return {}


def _address_text(address: Any) -> str | None:
    if not isinstance(address, dict):
        return None
    street = address.get("street")
    number = address.get("streetNumber")
    street_part = " ".join(str(p) for p in (street, number) if p)
    parts = [
        street_part,
        address.get("neighborhood"),
        address.get("city"),
        address.get("stateAcronym"),
    ]
    text = ", ".join(str(part) for part in parts if part)
    return text or None


def _coordinates(address: Any) -> tuple[float | None, float | None]:
    if not isinstance(address, dict):
        return None, None
    coords = address.get("coordinates")
    if not isinstance(coords, dict):
        return None, None
    lat = _as_float(coords.get("latitude") or coords.get("lat"))
    lon = _as_float(coords.get("longitude") or coords.get("lon") or coords.get("lng"))
    return lat, lon


def _extract_from_nextjs_payload(
    *,
    platform: str,
    base_url: str,
    search_type: str,
    raw_html: str,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in _extract_nextjs_listing_payloads(raw_html):
        listing_id = str(item.get("id") or "").strip()
        url = _normalize_platform_url(str(item.get("href") or ""), base_url)
        if not listing_id and url:
            listing_id = _extract_listing_id(url) or ""
        if not listing_id or listing_id in seen:
            continue

        lat, lon = _coordinates(item.get("address"))
        if lat is None or lon is None:
            continue

        seen.add(listing_id)
        price_info = _price_info(item, search_type)
        title = str(item.get("title") or "")
        url_for_parse = url or ""
        context = title
        results.append(
            {
                "platform": platform,
                "platform_listing_id": listing_id,
                "url": url,
                "image_url": _first_firecrawl_image(item, base_url),
                "lat": lat,
                "lon": lon,
                "price_brl": _as_float(price_info.get("value")),
                "area_m2": _as_float(item.get("usableArea") or item.get("area"))
                or _parse_area(url_for_parse, context),
                "bedrooms": _as_int(item.get("bedrooms"))
                or _parse_count_from_url_or_context(
                    r"(\d+)-quartos?",
                    r"com\s+(\d+)\s+quartos?",
                    url_for_parse,
                    context,
                ),
                "bathrooms": _as_int(item.get("bathrooms"))
                or _parse_count_from_url_or_context(
                    r"(\d+)-banheiros?",
                    r"(\d+)\s+banheiros?",
                    url_for_parse,
                    context,
                ),
                "parking": _as_int(item.get("parkingSpaces"))
                or _parse_count_from_url_or_context(
                    r"(\d+)-vagas?",
                    r"(\d+)\s+vagas?",
                    url_for_parse,
                    context,
                ),
                "address": _address_text(item.get("address")),
                "condo_fee_brl": _as_float(price_info.get("condominium")),
                "iptu_brl": _as_float(price_info.get("iptu")),
                "raw_payload": {
                    "provider": "firecrawl",
                    "source": "nextjs_raw_html",
                    "search_type": search_type,
                },
            }
        )

    return results


def extract_firecrawl_listings(
    *,
    platform: str,
    base_url: str,
    search_type: str,
    data: dict[str, Any],
) -> list[dict[str, Any]]:
    """Extract normalized listing rows from Firecrawl scrape data."""
    raw_html = str(data.get("rawHtml") or "")
    from_nextjs = _extract_from_nextjs_payload(
        platform=platform,
        base_url=base_url,
        search_type=search_type,
        raw_html=raw_html,
    )
    if from_nextjs:
        return from_nextjs

    markdown = str(data.get("markdown") or "")
    links = _as_firecrawl_links(data.get("links"))

    markdown_links = re.findall(r"\]\((https?://[^)\s]+|/[^)\s]+)", markdown)
    candidates = [*links, *markdown_links]

    seen: set[str] = set()
    listings: list[dict[str, Any]] = []
    for raw_url in candidates:
        url = _normalize_platform_url(raw_url, base_url)
        if url is None or url in seen:
            continue
        seen.add(url)

        listing_id = _extract_listing_id(url)
        if not listing_id:
            continue

        context = _listing_markdown_context(markdown, url)
        title = _extract_link_title(markdown, url)
        # Markdown is retained only as an auxiliary extraction path. Without
        # coordinates, these rows are not valid product listings.
        _ = (title, context)

    return listings


class FirecrawlScraperBase(ScraperBase):
    platform: str
    base_url: str

    def _firecrawl_api_key(self) -> str:
        key = (os.getenv("FIRECRAWL_API_KEY") or "").strip()
        if not key:
            raise ScraperError("FIRECRAWL_API_KEY não configurada para scraper Firecrawl.")
        return key

    def _firecrawl_timeout_ms(self) -> int:
        raw = self.platform_config.get("firecrawl_timeout_ms") or os.getenv(
            "SCRAPER_FIRECRAWL_TIMEOUT_MS",
            "45000",
        )
        try:
            return max(10000, int(raw))
        except (TypeError, ValueError):
            return 45000

    def _firecrawl_wait_ms(self) -> int:
        raw = self.platform_config.get("firecrawl_wait_ms") or os.getenv(
            "SCRAPER_FIRECRAWL_WAIT_MS",
            "3000",
        )
        try:
            return max(0, int(raw))
        except (TypeError, ValueError):
            return 3000

    def _firecrawl_proxy(self) -> str:
        proxy = (
            self.platform_config.get("firecrawl_proxy")
            or os.getenv("SCRAPER_FIRECRAWL_PROXY")
            or "stealth"
        )
        proxy = str(proxy).strip().lower()
        if proxy not in {"basic", "stealth", "auto"}:
            raise ScraperError(
                "SCRAPER_FIRECRAWL_PROXY inválido; use basic, stealth ou auto."
            )
        return proxy

    def _target_url(self) -> str:
        raise NotImplementedError

    async def _scrape_with_context(self, context: Any) -> list[dict[str, Any]]:
        raise ScraperError("Firecrawl scraper não usa contexto Playwright.")

    async def scrape(self) -> list[dict[str, Any]]:
        target_url = self._target_url()
        self._check_robots(urlsplit(target_url).path or "/")

        body = {
            "url": target_url,
            "formats": ["markdown", "links", "rawHtml", "html"],
            "onlyMainContent": False,
            "waitFor": self._firecrawl_wait_ms(),
            "timeout": self._firecrawl_timeout_ms(),
            "location": {"country": "BR", "languages": ["pt-BR"]},
            "proxy": self._firecrawl_proxy(),
            "storeInCache": False,
        }
        request = Request(
            FIRECRAWL_API_URL,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._firecrawl_api_key()}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=(self._firecrawl_timeout_ms() / 1000) + 10) as response:
                payload = json.loads(response.read().decode("utf-8", errors="ignore"))
        except Exception as exc:  # noqa: BLE001
            raise ScraperError(f"Falha na chamada Firecrawl para {self.platform}: {exc}") from exc

        if not isinstance(payload, dict) or not payload.get("success"):
            error = payload.get("error") if isinstance(payload, dict) else None
            raise ScraperError(
                f"Firecrawl retornou erro para {self.platform}: {error or payload!r}"
            )

        data = payload.get("data")
        if not isinstance(data, dict):
            raise ScraperError(f"Firecrawl retornou payload sem data para {self.platform}.")

        listings = extract_firecrawl_listings(
            platform=self.platform,
            base_url=self.base_url,
            search_type=self.search_type,
            data=data,
        )
        if not listings:
            raise ScraperError(
                f"Firecrawl não retornou imóveis com coordenadas para {self.platform}."
            )
        return listings


class FirecrawlVivaRealScraper(FirecrawlScraperBase):
    platform = "vivareal"
    base_url = "https://www.vivareal.com.br"

    def _target_url(self) -> str:
        configured_start = self._configured_start_urls()
        if _address_second_part_is_number(self.search_address):
            if configured_start:
                return configured_start[0]
            if self.search_type == "sale":
                return "https://www.vivareal.com.br/venda/sp/sao-paulo/"
            return "https://www.vivareal.com.br/aluguel/sp/sao-paulo/"
        return _build_vivareal_scrape_url(
            self.search_address,
            self.search_type,
            configured_start,
        )


class FirecrawlZapImoveisScraper(FirecrawlScraperBase):
    platform = "zapimoveis"
    base_url = "https://www.zapimoveis.com.br"

    def _target_url(self) -> str:
        return _build_zap_scrape_url(
            self.search_address,
            self.search_type,
            self._configured_start_urls(),
        )
