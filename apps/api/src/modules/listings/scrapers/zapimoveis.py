"""ZapImoveis Playwright scraper.

Reuses the same Glue API interception strategy as VivaReal (same OLX Group platform).
The only difference is the x-domain header and base URL.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

from .base import PLAYWRIGHT_LAUNCH_ARGS, REALISTIC_USER_AGENT, ScraperBase
from .vivareal import (
    _extract_from_dom_rows,
    _extract_from_glue_payload,
    _fetch_glue_fallback_payloads,
    _tweak_glue_listings_url,
)

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

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=not self._prefer_headful(),
                args=PLAYWRIGHT_LAUNCH_ARGS,
            )
            context = await browser.new_context(
                user_agent=REALISTIC_USER_AGENT,
                locale="pt-BR",
                timezone_id="America/Sao_Paulo",
                viewport={"width": 1280, "height": 800},
                extra_http_headers={
                    "x-domain": "www.zapimoveis.com.br",
                    "referer": "https://www.zapimoveis.com.br/",
                    "accept-language": "pt-BR,pt;q=0.9,en;q=0.8",
                },
            )
            page = await context.new_page()

            async def _capture_response(response: Any) -> None:
                url = response.url
                if (
                    (ZAP_GLUE_HOST in url or ZAP_GLUE_ALT_HOST in url)
                    and response.status == 200
                ):
                    glue_urls.add(url)
                    try:
                        body = await response.json()
                        intercepted_payloads.append(body)
                    except Exception:
                        pass

            page.on("response", _capture_response)

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

            await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                # Some pages keep background requests open; continue with a
                # human-like pause so hydration can still complete.
                await self._human_delay(2000, 3000)

            max_pages = self._configured_max_pages(default=1)
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
                            if isinstance(payload, dict):
                                intercepted_payloads.append(payload)
                    except Exception:
                        continue

            preview_count = 0
            for payload in intercepted_payloads:
                preview_count += len(
                    _extract_from_glue_payload(payload, "zapimoveis", self.search_type)
                )
            if preview_count < 20:
                for glue_domain in (ZAP_GLUE_HOST, ZAP_GLUE_ALT_HOST):
                    intercepted_payloads.extend(
                        await _fetch_glue_fallback_payloads(
                            glue_domain=glue_domain,
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

            await browser.close()

        listings: list[dict[str, Any]] = []
        for payload in intercepted_payloads:
            listings.extend(
                _extract_from_glue_payload(payload, "zapimoveis", self.search_type)
            )

        if not listings and isinstance(dom_rows, list):
            listings.extend(_extract_from_dom_rows(dom_rows, "zapimoveis"))

        seen: set[str] = set()
        unique = []
        for item in listings:
            lid = item.get("platform_listing_id")
            if lid and lid not in seen:
                seen.add(lid)
                unique.append(item)
        return unique
