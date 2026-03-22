"""ZapImoveis Playwright scraper — aligned with legacy cods_ok/realestate_meta_search.py.

Same Glue API strategy as VivaReal (same OLX Group platform) but with:
  - x-domain: www.zapimoveis.com.br
  - Different base URL for DOM fallback links
  - Own persistent profile directory
  - Glue route handler promoting count-only to full listings
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import parse_qsl, quote_plus, urlsplit

from .base import (
    PLAYWRIGHT_LAUNCH_ARGS,
    REALISTIC_USER_AGENT,
    STEALTH_JS,
    ScraperBase,
    _prepare_persistent_profile,
    is_cloudflare_block,
)
from .vivareal import (
    _extract_from_dom_rows,
    _extract_from_glue_payload,
    _fetch_glue_fallback_payloads,
    _tweak_glue_listings_url,
)

logger = logging.getLogger(__name__)

ZAP_BASE = "https://www.zapimoveis.com.br"
ZAP_GLUE_HOST = "glue-api.zapimoveis.com.br"
ZAP_GLUE_ALT_HOST = "glue-api.zapimoveis.com"


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

        user_data_dir = _prepare_persistent_profile("zapimoveis")

        async with async_playwright() as pw:
            try:
                context = await pw.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    headless=False,
                    locale="pt-BR",
                    timezone_id="America/Sao_Paulo",
                    viewport={"width": 1920, "height": 1080},
                    user_agent=REALISTIC_USER_AGENT,
                    args=PLAYWRIGHT_LAUNCH_ARGS,
                    ignore_default_args=["--enable-automation"],
                    ignore_https_errors=True,
                )
            except Exception:
                context = await pw.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    headless=True,
                    locale="pt-BR",
                    timezone_id="America/Sao_Paulo",
                    viewport={"width": 1920, "height": 1080},
                    user_agent=REALISTIC_USER_AGENT,
                    args=PLAYWRIGHT_LAUNCH_ARGS,
                    ignore_https_errors=True,
                )

            await context.add_init_script(STEALTH_JS)
            page = context.pages[0] if context.pages else await context.new_page()
            await page.add_init_script(STEALTH_JS)

            async def _capture_response(response: Any) -> None:
                try:
                    url = response.url
                    if (
                        (ZAP_GLUE_HOST in url or ZAP_GLUE_ALT_HOST in url)
                        and response.status == 200
                    ):
                        glue_urls.add(url)
                        try:
                            body = await response.json()
                            if isinstance(body, dict) and not is_cloudflare_block(body):
                                intercepted_payloads.append(body)
                        except Exception:
                            pass
                except Exception:
                    pass

            page.on("response", _capture_response)

            glue_domain = ZAP_GLUE_HOST
            glue_route_pattern = f"**/{glue_domain}/v2/listings**"

            async def _glue_route_handler(route: Any) -> None:
                """Promote count-only Glue requests to full listings (from legacy)."""
                req = route.request
                url_raw = req.url
                parts_ = urlsplit(url_raw)
                q_ = dict(parse_qsl(parts_.query, keep_blank_values=True))
                inc_ = q_.get("includeFields", "")
                if "totalCount" in inc_ and "listings" not in inc_.lower():
                    tweaked = _tweak_glue_listings_url(url_raw, size=36, from_=0)
                    logger.info("[zapimoveis] route: promoting count-only to listings")
                    await route.continue_(url=tweaked)
                else:
                    await route.continue_()

            await page.route(glue_route_pattern, _glue_route_handler)

            tx = "aluguel" if self.search_type == "rent" else "venda"
            search_encoded = quote_plus(self.search_address)
            configured_start = self._configured_start_urls()
            if configured_start:
                target_url = configured_start[0]
                if self.search_address and "q=" not in target_url:
                    sep = "&" if "?" in target_url else "?"
                    target_url = f"{target_url}{sep}q={search_encoded}"
            else:
                target_url = f"{ZAP_BASE}/{tx}/?q={search_encoded}"

            cf_retries = 3
            for attempt in range(cf_retries):
                try:
                    await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                    break
                except Exception:
                    if attempt < cf_retries - 1:
                        await asyncio.sleep(5 * (attempt + 1))
                    else:
                        raise

            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                await self._human_delay(2000, 3000)

            max_pages = self._configured_max_pages(default=4)
            for _ in range(max_pages):
                try:
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                except Exception:
                    pass
                try:
                    await page.wait_for_load_state("networkidle", timeout=4000)
                except Exception:
                    pass
                await self._human_delay(700, 1400)

            for raw_url in sorted(glue_urls):
                for page_idx in range(1, max_pages):
                    replay_url = _tweak_glue_listings_url(
                        raw_url,
                        size=36,
                        from_=page_idx * 36,
                    )
                    try:
                        response = await context.request.get(replay_url)
                        if response.ok:
                            payload = await response.json()
                            if isinstance(payload, dict) and not is_cloudflare_block(payload):
                                intercepted_payloads.append(payload)
                    except Exception:
                        continue
                    await asyncio.sleep(1.0)

            preview_count = 0
            for payload in intercepted_payloads:
                preview_count += len(
                    _extract_from_glue_payload(payload, "zapimoveis", self.search_type)
                )
            if preview_count < 20:
                for gd in (ZAP_GLUE_HOST, ZAP_GLUE_ALT_HOST):
                    intercepted_payloads.extend(
                        await _fetch_glue_fallback_payloads(
                            glue_domain=gd,
                            max_pages=max_pages,
                            search_type=self.search_type,
                            search_address=self.search_address,
                            x_domain="www.zapimoveis.com.br",
                            referer="https://www.zapimoveis.com.br/",
                        )
                    )

            dom_rows = await page.evaluate(
                """
                () => {
                    const anchors = Array.from(document.querySelectorAll('a[href*="/imovel/"]'));
                    return anchors.slice(0, 120).map((a) => ({
                        href: a.getAttribute('href') || '',
                        text: (a.closest('article') || a).innerText || '',
                    }));
                }
                """
            )

            await context.close()

        listings: list[dict[str, Any]] = []
        for payload in intercepted_payloads:
            listings.extend(
                _extract_from_glue_payload(payload, "zapimoveis", self.search_type)
            )

        if not listings and isinstance(dom_rows, list):
            listings.extend(_extract_from_dom_rows(dom_rows, "zapimoveis", ZAP_BASE))

        seen: set[str] = set()
        unique = []
        for item in listings:
            lid = item.get("platform_listing_id")
            if lid and lid not in seen:
                seen.add(lid)
                unique.append(item)
        return unique
