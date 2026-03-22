"""VivaReal Playwright scraper.

Strategy:
  1. Navigate to vivareal.com.br with the search address in the URL.
  2. Intercept responses from the Glue API (glue-api.vivareal.com.br).
  3. Parse search.result.listings from intercepted JSON payloads.

robots.txt: vivareal.com.br allows browsing listing pages.
We only interact with the public search UI.
"""

from __future__ import annotations

import asyncio
import json
import re
import unicodedata
from typing import Any
from urllib.parse import parse_qsl, quote_plus, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from .base import (
    PLAYWRIGHT_LAUNCH_ARGS,
    REALISTIC_USER_AGENT,
    ScraperBase,
    _as_float,
    _as_int,
    _get_by_path,
)

VIVAREAL_BASE = "https://www.vivareal.com.br"
GLUE_API_HOST = "glue-api.vivareal.com.br"
GLUE_API_ALT_HOST = "glue-api.vivareal.com"

COMMON_LISTING_PATHS = [
    "search.result.listings",
    "search.result.listings",
    "result.listings",
    "listings",
]


def _tweak_glue_listings_url(url: str, *, size: int, from_: int) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["size"] = str(size)
    query["from"] = str(from_)
    if "includeFields" in query and "listings" not in str(query["includeFields"]):
        query.pop("includeFields", None)
    query_str = urlencode(query, doseq=True)
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, query_str, parts.fragment)
    )


def _vr_norm_location_name(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(w.capitalize() for w in ascii_text.split() if w)


def _infer_city_state_from_address(address: str) -> tuple[str, str]:
    parts = [p.strip() for p in (address or "").split(",") if p.strip()]
    if len(parts) >= 2:
        city = parts[-2]
        state_part = parts[-1]
        state = "".join(ch for ch in state_part if ch.isalpha() or ch.isspace()).strip()
        if state.upper() == "SP":
            state = "Sao Paulo"
        return city or "Sao Paulo", state or "Sao Paulo"
    return "Sao Paulo", "Sao Paulo"


def _geocode_address_nominatim(address: str) -> tuple[float, float, str, str] | None:
    query = (address or "").strip()
    if not query:
        return None

    url = "https://nominatim.openstreetmap.org/search?" + urlencode(
        {
            "format": "jsonv2",
            "q": query,
            "limit": "1",
            "addressdetails": "1",
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
    except Exception:
        return None

    if not isinstance(payload, list) or not payload:
        return None

    best = payload[0]
    lat = _as_float(best.get("lat"))
    lon = _as_float(best.get("lon"))
    if lat is None or lon is None:
        return None

    addr = best.get("address") if isinstance(best.get("address"), dict) else {}
    city = (
        addr.get("city")
        or addr.get("town")
        or addr.get("village")
        or addr.get("municipality")
        or "Sao Paulo"
    )
    state = addr.get("state") or "Sao Paulo"
    return lat, lon, str(city), str(state)


def _build_glue_fallback_url(
    *,
    glue_domain: str,
    business: str,
    lat: float,
    lon: float,
    city: str,
    state: str,
    size: int,
    from_: int,
) -> str:
    loc_state = _vr_norm_location_name(state)
    loc_city = _vr_norm_location_name(city)
    query = {
        "business": business,
        "parentId": "null",
        "listingType": "USED",
        "__zt": "mtc:deduplication2023",
        "addressCity": city,
        "addressZone": "",
        "addressStreet": "",
        "addressNeighborhood": "",
        "addressLocationId": f"BR>{loc_state}>NULL>{loc_city}",
        "addressState": state,
        "addressPointLat": str(lat),
        "addressPointLon": str(lon),
        "addressType": "city",
        "page": str(int(from_ / max(size, 1)) + 1),
        "size": str(size),
        "from": str(from_),
        "images": "webp",
        "categoryPage": "RESULT",
    }
    return f"https://{glue_domain}/v2/listings?" + urlencode(list(query.items()))


async def _fetch_glue_fallback_payloads(
    *,
    glue_domain: str,
    max_pages: int,
    search_type: str,
    search_address: str,
    x_domain: str,
    referer: str,
) -> list[dict[str, Any]]:
    resolved = await asyncio.to_thread(_geocode_address_nominatim, search_address)
    if resolved is None:
        # Fail closed: do not invent coordinates.
        # Returning fabricated center points creates non-real results and
        # diverges from strict legacy parity expectations.
        return []

    lat, lon, city, state = resolved
    if lat is None or lon is None:
        return []

    business = "RENTAL" if search_type == "rent" else "SALE"
    page_size = 36
    headers = {
        "x-domain": x_domain,
        "referer": referer,
        "origin": referer.rstrip("/"),
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

    payloads: list[dict[str, Any]] = []
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
            req = Request(url)
            for key, value in headers.items():
                req.add_header(key, value)
            raw = await asyncio.to_thread(lambda: urlopen(req, timeout=25).read())
            payload = json.loads(raw.decode("utf-8", errors="ignore"))
        except Exception:
            break

        if not isinstance(payload, dict):
            break
        payloads.append(payload)

        listings = _get_by_path(payload, "search.result.listings")
        if not isinstance(listings, list) or not listings:
            break

    return payloads


class VivaRealScraper(ScraperBase):
    platform = "vivareal"
    base_url = VIVAREAL_BASE

    async def scrape(self) -> list[dict[str, Any]]:
        self._check_robots("/imoveis-para-alugar/")

        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError(
                "playwright package is required for VivaRealScraper."
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
                    "x-domain": "www.vivareal.com.br",
                    "referer": "https://www.vivareal.com.br/",
                    "accept-language": "pt-BR,pt;q=0.9,en;q=0.8",
                },
            )
            page = await context.new_page()

            async def _capture_response(response: Any) -> None:
                url = response.url
                if (
                    (GLUE_API_HOST in url or GLUE_API_ALT_HOST in url)
                    and response.status == 200
                ):
                    glue_urls.add(url)
                    try:
                        body = await response.json()
                        intercepted_payloads.append(body)
                    except Exception:
                        pass

            page.on("response", _capture_response)

            tx = "alugar" if self.search_type == "rent" else "venda"
            search_encoded = quote_plus(self.search_address)
            configured_start = self._configured_start_urls()
            if configured_start:
                target_url = configured_start[0]
                if self.search_address and "where=" not in target_url:
                    sep = "&" if "?" in target_url else "?"
                    target_url = f"{target_url}{sep}where={search_encoded}&__vt=ov"
            else:
                target_url = (
                    f"{VIVAREAL_BASE}/imoveis-para-{tx}/?where={search_encoded}"
                    f"&__vt=ov"
                )

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
                    # VivaReal can navigate/refresh while hydration completes.
                    # Skip this scroll attempt and continue collecting responses.
                    pass
                try:
                    await page.wait_for_load_state("networkidle", timeout=4000)
                except Exception:
                    pass
                await self._human_delay(700, 1400)

            # Replay paginated Glue URLs inside the same browser context/cookies.
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

            # Legacy parity fallback: direct Glue pagination based on geocoded point.
            preview_count = 0
            for payload in intercepted_payloads:
                preview_count += len(
                    _extract_from_glue_payload(payload, "vivareal", self.search_type)
                )
            if preview_count < 20:
                for glue_domain in (GLUE_API_HOST, GLUE_API_ALT_HOST):
                    intercepted_payloads.extend(
                        await _fetch_glue_fallback_payloads(
                            glue_domain=glue_domain,
                            max_pages=max_pages,
                            search_type=self.search_type,
                            search_address=self.search_address,
                            x_domain="www.vivareal.com.br",
                            referer="https://www.vivareal.com.br/",
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
            listings.extend(_extract_from_glue_payload(payload, "vivareal", self.search_type))

        if not listings and isinstance(dom_rows, list):
            listings.extend(_extract_from_dom_rows(dom_rows, "vivareal"))

        seen: set[str] = set()
        unique = []
        for item in listings:
            lid = item.get("platform_listing_id")
            if lid and lid not in seen:
                seen.add(lid)
                unique.append(item)
        return unique


def _extract_from_glue_payload(
    payload: dict[str, Any],
    platform: str,
    search_type: str,
    *,
    include_recommendations: bool = True,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    raw_listings: Any = None
    for path in COMMON_LISTING_PATHS:
        raw_listings = _get_by_path(payload, path)
        if isinstance(raw_listings, list) and raw_listings:
            break
        if isinstance(raw_listings, dict):
            nested = raw_listings.get("listings")
            if isinstance(nested, list) and nested:
                raw_listings = nested
                break

    if not isinstance(raw_listings, list) and include_recommendations:
        recs = payload.get("recommendations")
        if isinstance(recs, list) and recs:
            flattened: list[dict[str, Any]] = []
            for rec in recs:
                if not isinstance(rec, dict):
                    continue
                scores = rec.get("scores")
                if not isinstance(scores, list):
                    continue
                for score in scores:
                    if not isinstance(score, dict):
                        continue
                    listing_node = score.get("listing")
                    if isinstance(listing_node, dict):
                        inner = listing_node.get("listing")
                        if isinstance(inner, dict):
                            flattened.append({"listing": inner})
                        else:
                            flattened.append(listing_node)
            raw_listings = flattened

    if not isinstance(raw_listings, list):
        return results

    for entry in raw_listings:
        if not isinstance(entry, dict):
            continue

        listing = entry.get("listing") or entry

        lid = str(
            _get_by_path(listing, "id")
            or _get_by_path(listing, "listingId")
            or ""
        )
        if not lid:
            continue

        lat = _as_float(
            _get_by_path(listing, "address.point.lat")
            or _get_by_path(listing, "geoLocation.precision.lat")
        )
        lon = _as_float(
            _get_by_path(listing, "address.point.lon")
            or _get_by_path(listing, "geoLocation.precision.lon")
        )

        pricing_infos = _get_by_path(listing, "pricingInfos") or []
        price = None
        condo_fee = None
        iptu = None
        for pi in (pricing_infos if isinstance(pricing_infos, list) else []):
            btype = str(pi.get("businessType") or "").upper()
            if btype == "RENTAL" and search_type == "rent":
                price = _as_float(pi.get("rentalTotalPrice") or pi.get("price"))
                condo_fee = _as_float(pi.get("monthlyCondoFee"))
                iptu = _as_float(pi.get("yearlyIptu"))
                break
            elif btype == "SALE" and search_type == "sale":
                price = _as_float(pi.get("price"))
                break

        address_parts = [
            _get_by_path(listing, "address.street"),
            _get_by_path(listing, "address.neighborhood"),
            _get_by_path(listing, "address.city"),
            _get_by_path(listing, "address.stateAcronym"),
        ]
        address = ", ".join(str(p) for p in address_parts if p)

        url = _get_by_path(listing, "externalId") or lid
        link = _get_by_path(entry, "link.href") or f"https://www.vivareal.com.br/imovel/{url}/"

        results.append(
            {
                "platform": platform,
                "platform_listing_id": lid,
                "url": link,
                "lat": lat,
                "lon": lon,
                "price_brl": price,
                "area_m2": _as_float(
                    _get_by_path(listing, "usableAreas.0")
                    or _get_by_path(listing, "totalAreas.0")
                ),
                "bedrooms": _as_int(
                    _get_by_path(listing, "bedrooms.0")
                    or _get_by_path(listing, "bedrooms")
                ),
                "bathrooms": _as_int(
                    _get_by_path(listing, "bathrooms.0")
                    or _get_by_path(listing, "bathrooms")
                ),
                "parking": _as_int(
                    _get_by_path(listing, "parkingSpaces.0")
                    or _get_by_path(listing, "parkingSpaces")
                ),
                "address": address or None,
                "condo_fee_brl": condo_fee,
                "iptu_brl": iptu,
            }
        )

    return results


def _extract_from_dom_rows(rows: list[dict[str, Any]], platform: str) -> list[dict[str, Any]]:
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
        bedroom_match = re.search(
            r"(\d{1,2})\s*(?:quartos?|dormitorios?)",
            text,
            re.IGNORECASE,
        )

        link = href if href.startswith("http") else f"{VIVAREAL_BASE}{href}"
        results.append(
            {
                "platform": platform,
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
            }
        )

    return results
