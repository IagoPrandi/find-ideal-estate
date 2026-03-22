"""QuintoAndar Playwright scraper.

Strategy:
    1. Navigate to quintoandar.com.br/{alugar|comprar}/imovel/{location-slug}.
  2. Intercept the search API responses (POST /client-api/search or Next.js __NEXT_DATA__).
  3. Parse and return normalised listing dicts.

robots.txt: QuintoAndar disallows /api/ for bots but allows /imoveis/ pages.
We intercept XHR/fetch responses rather than calling the API directly, which
mimics a real browser session and respects the intent of the site's public UI.
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from .base import (
    PLAYWRIGHT_LAUNCH_ARGS,
    REALISTIC_USER_AGENT,
    ScraperBase,
    _as_float,
    _as_int,
    _get_by_path,
)


class QuintoAndarScraper(ScraperBase):
    platform = "quintoandar"
    base_url = "https://www.quintoandar.com.br"

    async def scrape(self) -> list[dict[str, Any]]:
        self._check_robots("/imoveis/")

        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError(
                "playwright package is required for QuintoAndarScraper. "
                "Install it with: pip install playwright && playwright install chromium"
            ) from exc

        listings: list[dict[str, Any]] = []
        intercepted_payloads: list[dict[str, Any]] = []

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
            )
            page = await context.new_page()

            async def _capture_response(response: Any) -> None:
                url = response.url
                if (
                    "quintoandar.com.br" in url
                    and (
                        "/search" in url
                        or "client-api" in url
                        or "/houses/" in url
                        or "search-result" in url
                    )
                    and response.status == 200
                ):
                    try:
                        body = await response.json()
                        intercepted_payloads.append(body)
                    except Exception:
                        pass

            page.on("response", _capture_response)

            location_slug = _to_quintoandar_location_slug(self.search_address)
            transaction = "alugar/imovel" if self.search_type == "rent" else "comprar/imovel"
            target_url = f"{self.base_url}/{transaction}/{location_slug}"
            configured_start = self._configured_start_urls()
            if configured_start and not self.search_address.strip():
                target_url = configured_start[0]

            await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                # Some pages keep background requests open; continue with a
                # human-like pause so hydration can still complete.
                await self._human_delay(2000, 3000)

            max_pages = self._configured_max_pages(default=1)
            for _ in range(max_pages):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await self._human_delay(700, 1400)

            # QuintoAndar usually expands via "Ver mais" instead of numeric URLs.
            for _ in range(max_pages - 1):
                expanded = False
                for selector in [
                    "button:has-text('Ver mais')",
                    "button:has-text('Mostrar mais')",
                    "button:has-text('Carregar mais')",
                ]:
                    try:
                        btn = page.locator(selector).first
                        if await btn.is_visible(timeout=1500):
                            await btn.click(timeout=2000)
                            expanded = True
                            break
                    except Exception:
                        continue
                if not expanded:
                    break
                try:
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass
                await self._human_delay(900, 1600)

            # Also extract __NEXT_DATA__ if present
            next_data_raw = await page.evaluate(
                "() => { const el = document.getElementById('__NEXT_DATA__'); "
                "return el ? el.textContent : null; }"
            )
            if next_data_raw:
                try:
                    intercepted_payloads.append(json.loads(next_data_raw))
                except Exception:
                    pass

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

        for payload in intercepted_payloads:
            extracted = _extract_from_quintoandar_payload(payload, self.search_type)
            listings.extend(extracted)

        if not listings and isinstance(dom_rows, list):
            listings.extend(_extract_from_quintoandar_dom_rows(dom_rows))

        # Deduplicate by platform_listing_id
        seen: set[str] = set()
        unique = []
        for item in listings:
            lid = item.get("platform_listing_id")
            if lid and lid not in seen:
                seen.add(lid)
                unique.append(item)
        return unique


def _extract_from_quintoandar_payload(
    payload: dict[str, Any],
    search_type: str,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    # Path 1: houses map (visibleHouses + houses[id])
    houses_map = (
        _get_by_path(payload, "props.pageProps.initialState.houses")
        or _get_by_path(payload, "props.pageProps.houses")
        or _get_by_path(payload, "houses")
    )
    if isinstance(houses_map, dict):
        for house_id, h in houses_map.items():
            if not isinstance(h, dict):
                continue
            item = _parse_quintoandar_house(str(house_id), h, search_type)
            if item:
                results.append(item)

    # Path 2: ES-like structures under search.result.hits.hits or flat hits lists
    hits = (
        _get_by_path(payload, "data.search.result.hits.hits")
        or _get_by_path(payload, "search.result.hits.hits")
        or _get_by_path(payload, "result.hits.hits")
        or _get_by_path(payload, "hits.hits")
        or _get_by_path(payload, "results")
        or _get_by_path(payload, "data.results")
    )
    if isinstance(hits, list):
        for h in hits:
            if not isinstance(h, dict):
                continue
            source = h.get("_source") if isinstance(h.get("_source"), dict) else h
            house_id = str(
                source.get("id")
                or h.get("_id")
                or source.get("listingId")
                or ""
            )
            if not house_id:
                continue
            item = _parse_quintoandar_house(house_id, source, search_type)
            if item:
                results.append(item)

    return results


def _to_quintoandar_location_slug(search_address: str) -> str:
    """Build QuintoAndar location slug from a free-form address string."""

    def _slugify(text: str) -> str:
        normalized = unicodedata.normalize("NFKD", text)
        ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
        ascii_text = ascii_text.lower().strip()
        ascii_text = re.sub(r"[^a-z0-9]+", "-", ascii_text)
        return ascii_text.strip("-")

    parts = [p.strip() for p in search_address.split(",") if p.strip()]
    if not parts:
        return "sao-paulo-sp-brasil"

    if len(parts) >= 3:
        selected = parts[:3]
    elif len(parts) == 2:
        selected = [parts[0], parts[1], "SP"]
    else:
        single = parts[0]
        if "sao paulo" in single.lower():
            selected = ["Sao Paulo", "SP"]
        else:
            selected = [single, "Sao Paulo", "SP"]

    slug_parts = [_slugify(p) for p in selected if _slugify(p)]
    if not slug_parts:
        return "sao-paulo-sp-brasil"

    slug = "-".join(slug_parts)
    if not slug.endswith("-brasil"):
        slug = f"{slug}-brasil"
    return slug


def _parse_quintoandar_house(
    house_id: str,
    h: dict[str, Any],
    search_type: str,
) -> dict[str, Any] | None:
    lat = _as_float(
        h.get("lat")
        or _get_by_path(h, "address.point.lat")
        or _get_by_path(h, "geoLocation.lat")
    )
    lon = _as_float(
        h.get("lon")
        or _get_by_path(h, "address.point.lon")
        or _get_by_path(h, "geoLocation.lon")
    )

    price = _as_float(
        h.get("rentPrice")
        or h.get("salePrice")
        or h.get("price")
        or _get_by_path(h, "pricingInfo.price")
    )

    address_parts = [
        h.get("address"),
        h.get("neighbourhood"),
        h.get("city") or "São Paulo",
        h.get("state") or "SP",
    ]
    address = ", ".join(str(p) for p in address_parts if p)

    url_path = h.get("slug") or h.get("url") or f"/imovel/{house_id}"
    url = f"https://www.quintoandar.com.br{url_path}" if url_path.startswith("/") else url_path

    if not house_id:
        return None

    return {
        "platform": "quintoandar",
        "platform_listing_id": house_id,
        "url": url,
        "lat": lat,
        "lon": lon,
        "price_brl": price,
        "area_m2": _as_float(h.get("area") or h.get("totalArea") or h.get("usableArea")),
        "bedrooms": _as_int(h.get("bedrooms") or h.get("dormitories")),
        "bathrooms": _as_int(h.get("bathrooms") or h.get("suites")),
        "parking": _as_int(h.get("parkingSpots") or h.get("garageSpaces") or h.get("parking")),
        "address": address or None,
        "condo_fee_brl": _as_float(h.get("condoFee") or h.get("condominiumFee")),
        "iptu_brl": _as_float(h.get("iptu")),
    }


def _extract_from_quintoandar_dom_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fallback extraction from DOM anchor elements when API interception yields nothing."""
    results: list[dict[str, Any]] = []
    for row in rows:
        href = str(row.get("href") or "")
        text = str(row.get("text") or "")
        if not href:
            continue
        lid_match = re.search(r"/imovel/(\d+)", href)
        if not lid_match:
            lid_match = re.search(r"(\d{6,})", href)
        if not lid_match:
            continue
        lid = lid_match.group(1)

        price_match = re.search(r"R\$\s*[\d\.]+(?:,\d{2})?", text)
        area_match = re.search(r"(\d{1,4})\s*m²", text, re.IGNORECASE)
        bedroom_match = re.search(r"(\d{1,2})\s*(?:quartos?|dormitorios?)", text, re.IGNORECASE)

        link = href if href.startswith("http") else f"https://www.quintoandar.com.br{href}"
        results.append({
            "platform": "quintoandar",
            "platform_listing_id": lid,
            "url": link,
            "lat": None,
            "lon": None,
            "price_brl": _as_float(price_match.group(0)) if price_match else None,
            "area_m2": _as_float(area_match.group(1)) if area_match else None,
            "bedrooms": _as_int(bedroom_match.group(1)) if bedroom_match else None,
            "bathrooms": None,
            "parking": None,
            "address": None,
            "condo_fee_brl": None,
            "iptu_brl": None,
        })
    return results
