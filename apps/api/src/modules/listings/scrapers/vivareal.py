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
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from .base import (
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

_VR_SP_ZONE_BY_NEIGHBORHOOD = {
    "vila leopoldina": "zona-oeste",
    "pinheiros": "zona-oeste",
    "perdizes": "zona-oeste",
    "itaim bibi": "zona-sul",
    "moema": "zona-sul",
    "tatuape": "zona-leste",
    "santana": "zona-norte",
}


def _tweak_glue_listings_url(url: str, *, size: int, from_: int) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["size"] = str(size)
    query["from"] = str(from_)
    # Reset page param (Glue uses from= as primary, page= is secondary)
    if "page" in query:
        query["page"] = str(int(from_ / max(size, 1)) + 1)
    # Strip count-only includeFields (no actual listings returned when totalCount-only)
    inc = query.get("includeFields") or ""
    if "search(totalCount)" in inc or inc.strip() in (
        "facets,search(totalCount)",
        "facets%2Csearch%28totalCount%29",
    ):
        query.pop("includeFields", None)
    query_str = urlencode(query, doseq=True)
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, query_str, parts.fragment)
    )


def _is_glue_listings_url(url: str) -> bool:
    if not isinstance(url, str):
        return False
    if GLUE_API_HOST not in url and GLUE_API_ALT_HOST not in url:
        return False
    return "/v2/listings" in url or "/v4/listings" in url


def _is_street_scope_listings_url(url: str) -> bool:
    if not _is_glue_listings_url(url):
        return False
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    address_type = str(query.get("addressType") or "").strip().lower()
    address_street = str(query.get("addressStreet") or "").strip()
    return address_type == "street" or bool(address_street)


def _vr_norm_location_name(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(w.capitalize() for w in ascii_text.split() if w)


def _vr_slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_text.lower().strip()
    lowered = re.sub(r"\s+", " ", lowered)
    lowered = re.sub(r"[^a-z0-9\s\-]", "", lowered)
    slug = lowered.replace(" ", "-")
    return re.sub(r"-{2,}", "-", slug).strip("-")


def _vr_parse_br_address(address: str) -> dict[str, str]:
    parts = [p.strip() for p in (address or "").split(",") if p.strip()]
    street = parts[0] if parts else ""
    neighborhood = parts[1] if len(parts) > 1 else ""
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
        "neighborhood": neighborhood,
        "city": city,
        "state": state,
    }


def _vr_state_to_code(state: str) -> str:
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


def _build_vivareal_scrape_url(
    address: str,
    search_type: str,
    configured_start: list[str],
) -> str:
    parsed = _vr_parse_br_address(address)
    street_slug = _vr_slugify(parsed["street"])
    neighborhood_slug = _vr_slugify(parsed["neighborhood"])
    city_slug = _vr_slugify(parsed["city"] or "sao paulo")
    state_code = _vr_state_to_code(parsed["state"]) or "sp"
    tx = "aluguel" if search_type == "rent" else "venda"

    if street_slug:
        path = [tx, state_code, city_slug]
        zone = _VR_SP_ZONE_BY_NEIGHBORHOOD.get(parsed["neighborhood"].strip().lower())
        if zone and neighborhood_slug:
            path.extend([zone, neighborhood_slug, street_slug])
        elif neighborhood_slug:
            path.extend(["bairros", neighborhood_slug, street_slug])
        else:
            path.append(street_slug)
        return f"{VIVAREAL_BASE}/" + "/".join(path)

    if configured_start:
        return configured_start[0]
    return f"{VIVAREAL_BASE}/imoveis-para-{'alugar' if search_type == 'rent' else 'venda'}/"


def _infer_city_state_from_address(address: str) -> tuple[str, str]:
    parsed = _vr_parse_br_address(address or "")
    city = (parsed.get("city") or "").strip()
    state_code = (parsed.get("state") or "").strip().lower()

    if city:
        if len(state_code) == 2 and state_code == "sp":
            return city, "Sao Paulo"
        if len(state_code) == 2 and state_code:
            # Keep behavior simple for non-SP while preserving city.
            return city, state_code.upper()
        return city, "Sao Paulo"

    # Fallback for incomplete addresses
    return "Sao Paulo", "Sao Paulo"


def _build_glue_ui_query(address: str) -> str:
    parsed = _vr_parse_br_address(address or "")
    street = (parsed.get("street") or "").strip()
    city = (parsed.get("city") or "").strip()
    if street and city:
        return f"{street}, {city}"
    if street:
        return street
    return (address or "").strip()


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
    # Nominatim returns decimal strings with dot separator; do not parse with BRL helper
    # (it strips dots as thousands separators and corrupts coordinates).
    try:
        lat = float(str(best.get("lat") or "").replace(",", "."))
        lon = float(str(best.get("lon") or "").replace(",", "."))
    except Exception:
        return None
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


def _url_path_depth(url: str) -> int:
    return len([s for s in urlsplit(url).path.split("/") if s])


def _glue_best_option_index(options_texts: list[str], full_address: str) -> list[int]:
    # Prioritize options that contain more parts from the full address.
    q = (full_address or "").lower()
    parts = [p.strip().lower() for p in re.split(r"[,\-]", q) if p.strip()]
    scores: list[tuple[int, int]] = []
    for i, txt in enumerate(options_texts):
        t = (txt or "").lower()
        score = 0
        for part in parts:
            if part and part in t:
                score += len(part)
        scores.append((score, i))
    scores.sort(key=lambda x: -x[0])
    return [idx for _, idx in scores]


async def _glue_fill_search_and_get_options(page: Any, query: str) -> tuple[Any, list[tuple[int, str, Any]]]:
    filled_input = None
    input_selectors = [
        'input[role="combobox"]',
        'dialog input',
        '[class*="modal"] input',
        '[class*="Modal"] input',
        '[class*="overlay"] input',
        '[class*="Overlay"] input',
        'input[placeholder]',
    ]
    for inp_sel in input_selectors:
        try:
            inp = page.locator(inp_sel).first
            if await inp.is_visible(timeout=1800):
                await inp.click()
                await inp.fill("")
                await inp.fill(query)
                filled_input = inp
                break
        except Exception:
            continue

    if not filled_input:
        try:
            await page.keyboard.press("Control+a")
            await page.keyboard.type(query, delay=35)
        except Exception:
            pass

    await page.wait_for_timeout(2500)

    options: list[tuple[int, str, Any]] = []
    try:
        all_opts = page.get_by_role("option")
        count = await all_opts.count()
        for i in range(min(count, 4)):
            loc = all_opts.nth(i)
            try:
                if await loc.is_visible(timeout=1000):
                    txt = (await loc.text_content() or "").strip()
                    options.append((i, txt, loc))
            except Exception:
                continue
    except Exception:
        pass

    if not options:
        for opt_sel in ['[role="option"]', 'li[class*="suggestion"]', 'li[class*="option"]']:
            try:
                all_opts = page.locator(opt_sel)
                count = await all_opts.count()
                for i in range(min(count, 4)):
                    loc = all_opts.nth(i)
                    try:
                        if await loc.is_visible(timeout=1000):
                            txt = (await loc.text_content() or "").strip()
                            options.append((i, txt, loc))
                    except Exception:
                        continue
                if options:
                    break
            except Exception:
                continue

    return filled_input, options


async def _glue_try_resolve_location_url(
    page: Any,
    query: str,
    platform_name: str,
    *,
    full_address: str | None = None,
    min_listings: int = 5,
) -> str | None:
    if not query:
        return None

    q0 = str(query).strip()
    if q0.lower().startswith("http://") or q0.lower().startswith("https://"):
        return q0

    compare_addr = full_address or query
    url_before = page.url
    depth_before = _url_path_depth(url_before)

    combo = page.locator('[role="combobox"]:not([aria-label*="Ordenar"])').first
    try:
        await combo.wait_for(state="visible", timeout=5000)
    except Exception:
        return None

    try:
        await combo.click()
        await page.wait_for_timeout(1200)

        _input, options = await _glue_fill_search_and_get_options(page, query)
        if not options:
            try:
                await page.keyboard.press("Escape")
            except Exception:
                pass
            return None

        opt_texts = [t for _, t, _ in options]
        ranked = _glue_best_option_index(opt_texts, compare_addr)

        for attempt, best_idx in enumerate(ranked[:2]):
            _, _, opt_loc = options[best_idx]
            if attempt > 0:
                await combo.click()
                await page.wait_for_timeout(1200)
                _input, options = await _glue_fill_search_and_get_options(page, query)
                if not options or best_idx >= len(options):
                    break
                _, _, opt_loc = options[best_idx]

            await opt_loc.click()
            await page.wait_for_timeout(3500)

            if page.url == url_before:
                try:
                    await page.wait_for_url(lambda u: u != url_before, timeout=9000)
                except Exception:
                    pass

            new_url = page.url
            if new_url == url_before:
                continue

            if _url_path_depth(new_url) < depth_before:
                await page.goto(url_before, wait_until="domcontentloaded")
                continue

            if attempt == 0 and len(ranked) > 1:
                await page.wait_for_timeout(2000)
                try:
                    cards = page.locator('a[href*="/imovel/"], a[href*="/imoveis/"], [class*="ListingCard"], [class*="listing-card"], [data-type="property"]')
                    n_cards = await cards.count()
                except Exception:
                    n_cards = 99

                if n_cards < min_listings:
                    await page.goto(url_before, wait_until="domcontentloaded")
                    await page.wait_for_timeout(1500)
                    continue

            return new_url

        if page.url != url_before and _url_path_depth(page.url) >= depth_before:
            return page.url
        return None
    except Exception:
        return None


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
        live_glue_headers: dict[str, str] = {}
        last_listings_url: str | None = None

        async with async_playwright() as pw:
            context = await self._open_browser_context(pw)
            await context.set_extra_http_headers(
                {
                    "x-domain": "www.vivareal.com.br",
                    "referer": "https://www.vivareal.com.br/",
                    "accept-language": "pt-BR,pt;q=0.9,en;q=0.8",
                }
            )
            page = await context.new_page()

            async def _glue_route_handler(route: Any) -> None:
                req = route.request
                url_raw = req.url
                parts = urlsplit(url_raw)
                query = dict(parse_qsl(parts.query, keep_blank_values=True))
                inc = str(query.get("includeFields") or "")
                if "totalCount" in inc and "listings" not in inc.lower():
                    tweaked = _tweak_glue_listings_url(url_raw, size=36, from_=0)
                    await route.continue_(url=tweaked)
                    return
                await route.continue_()

            await page.route("**/glue-api.vivareal.com/v2/listings**", _glue_route_handler)

            async def _capture_response(response: Any) -> None:
                nonlocal last_listings_url
                url = response.url
                if _is_glue_listings_url(url) and response.status == 200:
                    glue_urls.add(url)
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
                        if _is_street_scope_listings_url(url):
                            intercepted_payloads.append(body)
                    except Exception:
                        pass

            page.on("response", _capture_response)

            configured_start = self._configured_start_urls()
            target_url = (
                configured_start[0]
                if configured_start
                else ("https://www.vivareal.com.br/aluguel/sp/sao-paulo/" if self.search_type == "rent" else "https://www.vivareal.com.br/venda/sp/sao-paulo/")
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
                    "vivareal",
                    full_address=self.search_address,
                )
                if not resolved:
                    fallback_slug_url = _build_vivareal_scrape_url(
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
                    # VivaReal can navigate/refresh while hydration completes.
                    # Skip this scroll attempt and continue collecting responses.
                    pass
                try:
                    await page.wait_for_load_state("networkidle", timeout=4000)
                except Exception:
                    pass
                await self._human_delay(700, 1400)

            # Replay paginated Glue URL inside the same browser context/cookies.
            # Legacy behavior uses one captured listings URL and paginates pages 2..N.
            # Keep VivaReal aligned with the legacy baseline used in parity templates:
            # consume first-page captured listings and avoid replay pagination here.

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
                # Legacy capture flow paginates Glue with size=36.
                page_size = 36
                fallback_headers = {
                    "x-domain": "www.vivareal.com.br",
                    "referer": "https://www.vivareal.com.br/",
                    "origin": "https://www.vivareal.com.br",
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
                for glue_domain in (GLUE_API_HOST, GLUE_API_ALT_HOST):
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
            listings.extend(_extract_from_glue_payload(payload, "vivareal", self.search_type))

        seen: set[str] = set()
        unique = []
        for item in listings:
            lid = item.get("platform_listing_id")
            if lid and lid not in seen:
                seen.add(lid)
                unique.append(item)

        return unique


def _extract_from_glue_payload(
    payload: Any,
    platform: str,
    search_type: str,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    raw_listings: Any = None

    if isinstance(payload, list):
        raw_listings = payload

    if isinstance(payload, dict) and not isinstance(raw_listings, list):
        for path in COMMON_LISTING_PATHS:
            raw_listings = _get_by_path(payload, path)
            if isinstance(raw_listings, list) and raw_listings:
                break
            if isinstance(raw_listings, dict):
                nested = raw_listings.get("listings")
                if isinstance(nested, list) and nested:
                    raw_listings = nested
                    break

    if not isinstance(raw_listings, list):
        return results

    for entry in raw_listings:
        if not isinstance(entry, dict):
            continue

        listing = entry.get("listing")
        if not isinstance(listing, dict):
            listing = entry

        lid_field = (
            _get_by_path(entry, "listing.id")
            or _get_by_path(entry, "id")
            or _get_by_path(listing, "id")
            or _get_by_path(listing, "listingId")
            or _get_by_path(listing, "propertyId")
        )

        lat = _as_float(
            _get_by_path(listing, "address.point.lat")
            or _get_by_path(listing, "address.point.approximateLat")
            or _get_by_path(listing, "address.point.latitude")
            or _get_by_path(listing, "geoLocation.precision.lat")
            or _get_by_path(listing, "geoLocation.location.lat")
        )
        lon = _as_float(
            _get_by_path(listing, "address.point.lon")
            or _get_by_path(listing, "address.point.approximateLon")
            or _get_by_path(listing, "address.point.lng")
            or _get_by_path(listing, "address.point.longitude")
            or _get_by_path(listing, "geoLocation.precision.lon")
            or _get_by_path(listing, "geoLocation.precision.lng")
            or _get_by_path(listing, "geoLocation.location.lon")
            or _get_by_path(listing, "geoLocation.location.lng")
        )

        if lat is None or lon is None:
            coordinates = _get_by_path(listing, "geoLocation.location.coordinates")
            if isinstance(coordinates, (list, tuple)) and len(coordinates) >= 2:
                maybe_lon = _as_float(coordinates[0])
                maybe_lat = _as_float(coordinates[1])
                if lat is None:
                    lat = maybe_lat
                if lon is None:
                    lon = maybe_lon

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
            if btype == "SALE" and search_type == "sale":
                price = _as_float(pi.get("price"))
                break

        address_parts = [
            _get_by_path(listing, "address.street"),
            _get_by_path(listing, "address.neighborhood"),
            _get_by_path(listing, "address.city"),
            _get_by_path(listing, "address.stateAcronym"),
        ]
        address = ", ".join(str(p) for p in address_parts if p)

        url = _get_by_path(listing, "externalId") or lid_field or ""
        link = _get_by_path(entry, "link.href") or f"https://www.vivareal.com.br/imovel/{url}/"

        # Legacy canonical ids follow URL suffix pattern: ...-id-<digits>/
        lid_url = None
        if isinstance(link, str):
            m = re.search(r"-id-(\d+)(?:/|$)", link)
            if not m:
                m = re.search(r"/imovel/(\d+)(?:/|$)", link)
            if m:
                lid_url = m.group(1)

        lid = str(lid_url or lid_field or "")
        if not lid:
            continue

        results.append(
            {
                "platform": platform,
                "platform_listing_id": lid,
                "url": link,
                "image_url": (
                    _get_by_path(listing, "medias.0.url")
                    or _get_by_path(listing, "medias.0.imageUrl")
                    or _get_by_path(listing, "images.0.url")
                    or _get_by_path(listing, "images.0")
                ),
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


def _count_primary_listings(payload: Any) -> int:
    if isinstance(payload, list):
        return len([item for item in payload if isinstance(item, dict)])
    if not isinstance(payload, dict):
        return 0

    for path in COMMON_LISTING_PATHS:
        raw_listings = _get_by_path(payload, path)
        if isinstance(raw_listings, list):
            return len(raw_listings)
        if isinstance(raw_listings, dict):
            nested = raw_listings.get("listings")
            if isinstance(nested, list):
                return len(nested)
    return 0


def _extract_from_dom_rows(rows: list[dict[str, Any]], platform: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for row in rows:
        href = str(row.get("href") or "")
        text = str(row.get("text") or "")
        if not href:
            continue

        lid_match = re.search(r"-id-(\d+)(?:/|$)", href)
        if not lid_match:
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
                "image_url": None,
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
