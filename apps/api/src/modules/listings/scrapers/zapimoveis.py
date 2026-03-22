"""ZapImoveis Playwright scraper.

Reuses the same Glue API interception strategy as VivaReal (same OLX Group platform).
The only difference is the x-domain header and base URL.
"""

from __future__ import annotations

import asyncio
import re
import unicodedata
from typing import Any

from .base import ScraperBase, _get_by_path
from .vivareal import (
    _build_glue_ui_query,
    _glue_try_resolve_location_url,
    _build_glue_fallback_url,
    _count_primary_listings,
    _extract_from_glue_payload,
    _geocode_address_nominatim,
    _infer_city_state_from_address,
    _tweak_glue_listings_url,
)

ZAP_BASE = "https://www.zapimoveis.com.br"
ZAP_GLUE_HOST = "glue-api.zapimoveis.com.br"
ZAP_GLUE_ALT_HOST = "glue-api.zapimoveis.com"


def _is_zap_glue_listings_url(url: str) -> bool:
    if not isinstance(url, str):
        return False
    if ZAP_GLUE_HOST not in url and ZAP_GLUE_ALT_HOST not in url:
        return False
    return "/v2/listings" in url or "/v4/listings" in url


def _zap_slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_text.lower().strip()
    lowered = re.sub(r"\s+", " ", lowered)
    lowered = re.sub(r"[^a-z0-9\s\-]", "", lowered)
    slug = lowered.replace(" ", "-")
    return re.sub(r"-{2,}", "-", slug).strip("-")


def _zap_parse_br_address(address: str) -> dict[str, str]:
    parts = [p.strip() for p in (address or "").split(",") if p.strip()]
    street = parts[0] if parts else ""
    city = ""
    state = ""
    if len(parts) > 2:
        city_state = parts[2]
        match = re.search(r"^(.*?)(?:\s*-\s*([A-Za-z]{2}))?$", city_state)
        if match:
            city = (match.group(1) or "").strip()
            state = (match.group(2) or "").strip().lower()
    if len(parts) > 3 and not state:
        state = parts[3].strip().lower()
    return {
        "street": street,
        "city": city,
        "state": state,
    }


def _zap_state_to_code(state: str) -> str:
    raw = (state or "").strip().lower()
    if len(raw) == 2:
        return raw
    lookup = {
        "sao paulo": "sp",
        "rio de janeiro": "rj",
        "minas gerais": "mg",
        "parana": "pr",
        "rio grande do sul": "rs",
        "santa catarina": "sc",
        "bahia": "ba",
        "pernambuco": "pe",
        "ceara": "ce",
        "distrito federal": "df",
    }
    return lookup.get(raw, "")


def _build_zap_scrape_url(
    address: str,
    search_type: str,
    configured_start: list[str],
) -> str:
    parsed = _zap_parse_br_address(address)
    street_slug = _zap_slugify(parsed["street"])
    city_slug = _zap_slugify(parsed["city"] or "sao paulo")
    state_code = _zap_state_to_code(parsed["state"]) or "sp"
    tx = "aluguel" if search_type == "rent" else "venda"

    if street_slug:
        return f"{ZAP_BASE}/{tx}/imoveis/{state_code}+{city_slug}/{street_slug}/"

    if configured_start:
        return configured_start[0]
    return f"{ZAP_BASE}/{tx}/"


class ZapImoveisScraper(ScraperBase):
    platform = "zapimoveis"
    base_url = ZAP_BASE

    async def scrape(self) -> list[dict[str, Any]]:
        self._check_robots("/")

        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError(
                "playwright package is required for ZapImoveisScraper."
            ) from exc

        intercepted_payloads: list[dict[str, Any]] = []
        glue_urls: set[str] = set()
        live_glue_headers: dict[str, str] = {}
        last_listings_url: str | None = None

        async with async_playwright() as pw:
            context = await self._open_browser_context(pw)
            await context.set_extra_http_headers(
                {
                    "x-domain": "www.zapimoveis.com.br",
                    "referer": "https://www.zapimoveis.com.br/",
                    "accept-language": "pt-BR,pt;q=0.9,en;q=0.8",
                },
            )
            page = await context.new_page()

            async def _capture_response(response: Any) -> None:
                nonlocal last_listings_url
                url = response.url
                if (
                    (ZAP_GLUE_HOST in url or ZAP_GLUE_ALT_HOST in url)
                    and response.status == 200
                ):
                    glue_urls.add(url)
                    if _is_zap_glue_listings_url(url):
                        last_listings_url = url
                    try:
                        req_headers = await response.request.all_headers()
                        if isinstance(req_headers, dict):
                            for key, value in req_headers.items():
                                if isinstance(key, str) and isinstance(value, str):
                                    live_glue_headers[key] = value
                    except Exception:
                        pass
                    try:
                        body = await response.json()
                        intercepted_payloads.append(body)
                    except Exception:
                        pass

            page.on("response", _capture_response)

            configured_start = self._configured_start_urls()
            target_url = (
                configured_start[0]
                if configured_start
                else ("https://www.zapimoveis.com.br/aluguel/" if self.search_type == "rent" else "https://www.zapimoveis.com.br/venda/")
            )

            await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                # Some pages keep background requests open; continue with a
                # human-like pause so hydration can still complete.
                await self._human_delay(2000, 3000)

            if self.search_address.strip():
                glue_query = _build_glue_ui_query(self.search_address)
                resolved = await _glue_try_resolve_location_url(
                    page,
                    glue_query,
                    "zapimoveis",
                    full_address=self.search_address,
                )
                if not resolved:
                    fallback_slug_url = _build_zap_scrape_url(
                        self.search_address,
                        self.search_type,
                        configured_start,
                    )
                    if fallback_slug_url:
                        resolved = fallback_slug_url

                if resolved and resolved != page.url:
                    await page.goto(
                        resolved,
                        wait_until="domcontentloaded",
                        timeout=60000,
                    )
                    try:
                        await page.wait_for_load_state("networkidle", timeout=15000)
                    except Exception:
                        await self._human_delay(1600, 2600)

            max_pages = self._configured_max_pages(default=4)
            for _ in range(max_pages):
                try:
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                except Exception:
                    # Some runs trigger a page transition during hydration.
                    # Continue and keep collecting intercepted payloads.
                    pass
                try:
                    await page.wait_for_load_state("networkidle", timeout=4000)
                except Exception:
                    pass
                await self._human_delay(700, 1400)

            replay_seed_url = last_listings_url or (sorted(glue_urls)[-1] if glue_urls else None)
            if replay_seed_url and _is_zap_glue_listings_url(replay_seed_url):
                for page_idx in range(max_pages):
                    replay_url = _tweak_glue_listings_url(
                        replay_seed_url,
                        size=36,
                        from_=page_idx * 36,
                    )
                    try:
                        replay_headers = {
                            str(k): str(v)
                            for k, v in dict(live_glue_headers).items()
                            if isinstance(k, str)
                            and isinstance(v, str)
                            and not k.startswith(":")
                            and k.lower()
                            not in {
                                "host",
                                "content-length",
                                "accept-encoding",
                                "connection",
                            }
                        }
                        replay_headers.setdefault("x-domain", "www.zapimoveis.com.br")
                        replay_headers.setdefault("origin", "https://www.zapimoveis.com.br")
                        replay_headers.setdefault("referer", "https://www.zapimoveis.com.br/")
                        response = await context.request.get(
                            replay_url,
                            headers=replay_headers if replay_headers else None,
                        )
                        if response.ok:
                            payload = await response.json()
                            if isinstance(payload, (dict, list)):
                                intercepted_payloads.append(payload)
                    except Exception:
                        continue

            # Legacy-style in-page pagination for Zap (helps when direct Glue calls are blocked).
            next_selectors = [
                'button[aria-label="Próxima página"]',
                'a[aria-label="Próxima página"]',
                'button[title="Próxima página"]',
                'a[title="Próxima página"]',
                '[data-testid="next-page"]',
                'li.pagination__item--next a',
                'li.pagination__item--next button',
                'button:has-text("Próxima")',
                'a:has-text("Próxima")',
                '[class*="pagination"] button:last-child',
                '[class*="pagination"] a:last-child',
                '[class*="Pagination"] button:last-child',
                'button[class*="next"]',
                'a[class*="next"]',
            ]
            for _ in range(max_pages - 1):
                clicked = False
                for sel in next_selectors:
                    try:
                        btn = page.locator(sel).first
                        if await btn.count() > 0 and await btn.is_visible(timeout=1500):
                            await btn.scroll_into_view_if_needed(timeout=1500)
                            await page.wait_for_timeout(400)
                            await btn.click(timeout=2500)
                            clicked = True
                            break
                    except Exception:
                        continue
                if not clicked:
                    break
                try:
                    await page.wait_for_timeout(4500)
                except Exception:
                    pass
                for _scroll in range(3):
                    try:
                        await page.mouse.wheel(0, 1000)
                        await page.wait_for_timeout(600)
                    except Exception:
                        break
                await self._human_delay(1200, 2200)

            # Legacy behavior: direct Glue fallback only when intercepted preview is low.
            preview_count = 0
            for payload in intercepted_payloads:
                preview_count += _count_primary_listings(payload)
            if preview_count < 20:
                resolved = await asyncio.to_thread(
                    _geocode_address_nominatim,
                    self.search_address,
                )
                if resolved is None:
                    city, state = _infer_city_state_from_address(self.search_address)
                    resolved = (-23.55052, -46.633308, city, state)
                lat, lon, city, state = resolved
                business = "RENTAL" if self.search_type == "rent" else "SALE"
                page_size = 36
                fallback_headers = {
                    "x-domain": "www.zapimoveis.com.br",
                    "referer": "https://www.zapimoveis.com.br/",
                    "origin": "https://www.zapimoveis.com.br",
                    "accept": "application/json, text/plain, */*",
                    "accept-language": "pt-BR,pt;q=0.9,en;q=0.8",
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"
                    ),
                    "sec-ch-ua": '"Chromium";v="131", "Not_A Brand";v="24"',
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"Windows"',
                    "sec-fetch-dest": "empty",
                    "sec-fetch-mode": "cors",
                    "sec-fetch-site": "same-site",
                }
                fallback_headers.update(live_glue_headers)
                for glue_domain in (ZAP_GLUE_HOST, ZAP_GLUE_ALT_HOST):
                    for pg in range(max_pages):
                        from_ = pg * page_size
                        url = _build_glue_fallback_url(
                            glue_domain=glue_domain,
                            business=business,
                            lat=lat,
                            lon=lon,
                            city=city,
                            state=state,
                            size=page_size,
                            from_=from_,
                        )
                        try:
                            response = await context.request.fetch(
                                url,
                                headers=fallback_headers,
                            )
                            if not response.ok:
                                break
                            payload = await response.json()
                            if isinstance(payload, list):
                                if not payload:
                                    break
                                intercepted_payloads.append(payload)
                                continue
                            if not isinstance(payload, dict):
                                break
                            intercepted_payloads.append(payload)
                            listings = _get_by_path(payload, "search.result.listings")
                            if not isinstance(listings, list) or not listings:
                                break
                        except Exception:
                            break

            await context.close()

        listings: list[dict[str, Any]] = []
        for payload in intercepted_payloads:
            listings.extend(
                _extract_from_glue_payload(payload, "zapimoveis", self.search_type)
            )

        seen: set[str] = set()
        unique = []
        for item in listings:
            lid = item.get("platform_listing_id")
            if lid and lid not in seen:
                seen.add(lid)
                unique.append(item)

        return unique
