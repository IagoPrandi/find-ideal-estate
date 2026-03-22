"""QuintoAndar Playwright scraper — aligned with legacy cods_ok/realestate_meta_search.py.

Strategy (from legacy):
  1. Launch persistent context with stealth JS + anti-automation flags.
  2. Navigate to quintoandar.com.br/{alugar|comprar}/imovel/{location-slug}.
  3. Intercept POST to /house-listing-search/.../search (capture body+headers).
  4. Intercept POST to /house-listing-search/v2/search/count (capture viewport body).
  5. Extract __NEXT_DATA__ from the page.
  6. Replay the search POST with paginated bodies (from/size offsets of 60).
  7. Parse houses map + ES hits from all intercepted payloads.
"""

from __future__ import annotations

import json
import re
import unicodedata
from copy import deepcopy
from typing import Any

from .base import (
    PLAYWRIGHT_LAUNCH_ARGS,
    REALISTIC_USER_AGENT,
    STEALTH_JS,
    ScraperBase,
    _as_float,
    _as_int,
    _get_by_path,
    _prepare_persistent_profile,
)


def _qa_body_with_pagination(body: Any, from_: int, size: int) -> Any:
    """Adjust offset/pagination in QuintoAndar POST bodies (from legacy)."""
    if not isinstance(body, dict):
        return body
    b = deepcopy(body)
    if "from" in b:
        b["from"] = from_
    if "size" in b:
        b["size"] = size
    if "offset" in b:
        b["offset"] = from_
    if "limit" in b:
        b["limit"] = size
    if "page" in b and isinstance(b.get("page"), int):
        b["page"] = int(from_ / max(size, 1))
    for key in ("pagination", "paging", "pageable"):
        if isinstance(b.get(key), dict):
            if "from" in b[key]:
                b[key]["from"] = from_
            if "size" in b[key]:
                b[key]["size"] = size
            if "offset" in b[key]:
                b[key]["offset"] = from_
            if "limit" in b[key]:
                b[key]["limit"] = size
            if "page" in b[key] and isinstance(b[key].get("page"), int):
                b[key]["page"] = int(from_ / max(size, 1))
    for key in ("search", "query", "filters"):
        if isinstance(b.get(key), dict):
            if isinstance(b[key].get("pagination"), dict):
                if "from" in b[key]["pagination"]:
                    b[key]["pagination"]["from"] = from_
                if "size" in b[key]["pagination"]:
                    b[key]["pagination"]["size"] = size
    return b


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

        qa_search_templates: list[dict[str, Any]] = []
        qa_count_body: Any = None

        user_data_dir = _prepare_persistent_profile("quintoandar")

        async with async_playwright() as pw:
            try:
                context = await pw.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    headless=True,
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
                nonlocal qa_count_body
                try:
                    url = response.url
                    req = response.request
                    rtype = req.resource_type
                    if rtype not in ("xhr", "fetch", "document"):
                        return

                    if (
                        "quintoandar.com.br" in url
                        and req.method.upper() == "POST"
                        and "/house-listing-search/v2/search/count" in url
                    ):
                        body_json = None
                        try:
                            body_json = req.post_data_json
                        except Exception:
                            pass
                        if body_json is None:
                            try:
                                pd = req.post_data or ""
                                body_json = json.loads(pd) if pd else None
                            except Exception:
                                pass
                        qa_count_body = body_json

                    if (
                        "quintoandar.com.br" in url
                        and req.method.upper() == "POST"
                        and "/house-listing-search/" in url
                        and "/search" in url
                        and "/coordinates" not in url
                        and "/count" not in url
                    ):
                        body_json = None
                        try:
                            body_json = req.post_data_json
                        except Exception:
                            pass
                        if body_json is None:
                            try:
                                pd = req.post_data or ""
                                body_json = json.loads(pd) if pd else None
                            except Exception:
                                pass
                        if body_json is not None:
                            qa_search_templates.append({
                                "url": url,
                                "headers": (
                            dict(req.headers)
                            if getattr(req, "headers", None)
                            else {}
                        ),
                                "body": body_json,
                            })

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
                await self._human_delay(2000, 3000)

            await _qa_try_dismiss_overlays(page)

            max_pages = self._configured_max_pages(default=4)

            for _ in range(max_pages):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await self._human_delay(700, 1400)

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

            next_data_raw = await page.evaluate(
                "() => { const el = document.getElementById('__NEXT_DATA__'); "
                "return el ? el.textContent : null; }"
            )
            if next_data_raw:
                try:
                    intercepted_payloads.append(json.loads(next_data_raw))
                except Exception:
                    pass

            if qa_search_templates and max_pages > 1:
                tmpl = qa_search_templates[0]
                for page_idx in range(1, max_pages):
                    paginated_body = _qa_body_with_pagination(
                        tmpl["body"], from_=page_idx * 60, size=60,
                    )
                    try:
                        resp = await context.request.post(
                            tmpl["url"],
                            data=json.dumps(paginated_body),
                            headers={
                                **tmpl.get("headers", {}),
                                "content-type": "application/json",
                            },
                        )
                        if resp.ok:
                            payload = await resp.json()
                            if isinstance(payload, dict):
                                intercepted_payloads.append(payload)
                    except Exception:
                        continue
                    await self._human_delay(500, 1200)

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

        for payload in intercepted_payloads:
            extracted = _extract_from_quintoandar_payload(payload, self.search_type)
            listings.extend(extracted)

        if not listings and isinstance(dom_rows, list):
            listings.extend(_extract_from_quintoandar_dom_rows(dom_rows))

        seen: set[str] = set()
        unique = []
        for item in listings:
            lid = item.get("platform_listing_id")
            if lid and lid not in seen:
                seen.add(lid)
                unique.append(item)
        return unique


async def _qa_try_dismiss_overlays(page: Any) -> None:
    """Best-effort dismissal of cookie/modal overlays (from legacy)."""
    candidates = [
        "button:has-text('Aceitar')",
        "button:has-text('Concordo')",
        "button:has-text('Entendi')",
        "button:has-text('Fechar')",
        "[aria-label='Fechar']",
        "[aria-label='Close']",
        "button[aria-label='Close']",
    ]
    for sel in candidates:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                try:
                    await loc.click(timeout=800)
                    await page.wait_for_timeout(200)
                except Exception:
                    pass
        except Exception:
            continue
    try:
        await page.keyboard.press("Escape")
    except Exception:
        pass


def _extract_from_quintoandar_payload(
    payload: dict[str, Any],
    search_type: str,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    houses_map = (
        _get_by_path(payload, "props.pageProps.initialState.houses")
        or _get_by_path(payload, "props.pageProps.houses")
        or _get_by_path(payload, "houses")
        or _get_by_path(payload, "entities.houses")
        or _get_by_path(payload, "search.houses")
        or _get_by_path(payload, "search.entities.houses")
    )
    if isinstance(houses_map, dict):
        visible_ids = _extract_quintoandar_ids_from_visible_pages(payload)
        if visible_ids:
            for hid in visible_ids:
                h = houses_map.get(hid)
                if not isinstance(h, dict):
                    continue
                item = _parse_quintoandar_house(str(hid), h, search_type)
                if item:
                    results.append(item)
        else:
            for house_id, h in houses_map.items():
                if not isinstance(h, dict):
                    continue
                item = _parse_quintoandar_house(str(house_id), h, search_type)
                if item:
                    results.append(item)

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


def _extract_quintoandar_ids_from_visible_pages(state: dict) -> list[str]:
    """Extract visible house IDs from visibleHouses.pages (from legacy)."""
    pages = (
        _get_by_path(state, "props.pageProps.initialState.search.visibleHouses.pages")
        or _get_by_path(state, "search.visibleHouses.pages")
        or _get_by_path(state, "visibleHouses.pages")
        or _get_by_path(state, "search.visibleHouses")
        or _get_by_path(state, "visibleHouses")
    )
    out: list[str] = []
    if isinstance(pages, dict):
        nested_pages = pages.get("pages") or pages.get("items") or pages.get("results")
        if isinstance(nested_pages, dict):
            ordered_values = []
            def _sort_key(x: Any) -> Any:
                return int(x) if str(x).isdigit() else str(x)

            for key in sorted(nested_pages.keys(), key=_sort_key):
                ordered_values.append(nested_pages[key])
            pages = ordered_values
        elif nested_pages is not None:
            pages = nested_pages
        else:
            ordered_values = []
            for key in sorted(pages.keys(), key=lambda x: int(x) if str(x).isdigit() else str(x)):
                ordered_values.append(pages[key])
            pages = ordered_values
    if isinstance(pages, list):
        for p in pages:
            if isinstance(p, list):
                for hid in p:
                    if hid is None:
                        continue
                    out.append(str(hid))
            elif isinstance(p, (str, int)):
                out.append(str(p))
    seen: set[str] = set()
    uniq: list[str] = []
    for x in out:
        if x in seen:
            continue
        seen.add(x)
        uniq.append(x)
    return uniq


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
    lat, lon = _quintoandar_latlon_from_house(h)

    price = None
    for k in ("totalCost", "rent", "salePrice", "price", "monthlyRent", "totalPrice", "rentPrice"):
        if k in h:
            v = _as_int(h.get(k))
            if v is not None:
                price = float(v)
                break
    if price is None:
        pricing = h.get("pricing") if isinstance(h.get("pricing"), dict) else {}
        for k in ("totalCost", "rent", "salePrice", "price"):
            v = _as_int(pricing.get(k))
            if v is not None:
                price = float(v)
                break
    if price is None:
        price = _as_float(_get_by_path(h, "pricingInfo.price"))

    address = _format_address(h)

    url = f"https://www.quintoandar.com.br/imovel/{house_id}"
    if isinstance(h.get("uri"), str) and h["uri"].startswith("/"):
        url = "https://www.quintoandar.com.br" + h["uri"]
    elif isinstance(h.get("slug"), str) and h["slug"].startswith("/"):
        url = "https://www.quintoandar.com.br" + h["slug"]
    elif isinstance(h.get("url"), str) and h["url"].startswith("http"):
        url = h["url"]

    if not house_id:
        return None

    return {
        "platform": "quintoandar",
        "platform_listing_id": house_id,
        "url": url,
        "lat": lat,
        "lon": lon,
        "price_brl": price,
        "area_m2": _as_float(
            h.get("area") or h.get("usableArea")
            or h.get("size") or h.get("totalArea")
        ),
        "bedrooms": _as_int(
            h.get("bedrooms") or h.get("bedroomCount")
            or h.get("rooms") or h.get("dormitories")
        ),
        "bathrooms": _as_int(
            h.get("bathrooms") or h.get("bathroomCount")
            or h.get("suites")
        ),
        "parking": _as_int(
            h.get("parkingSpaces") or h.get("parking")
            or h.get("garage") or h.get("parkingSpots")
            or h.get("garageSpaces")
        ),
        "address": address,
        "condo_fee_brl": _as_float(h.get("condoFee") or h.get("condominiumFee")),
        "iptu_brl": _as_float(h.get("iptu")),
    }


def _quintoandar_latlon_from_house(h: dict) -> tuple[float | None, float | None]:
    """Extract lat/lon from house dict using multiple candidate paths (from legacy)."""
    candidates = [
        ("address", "point", "lat", "lon"),
        ("location", "point", "lat", "lon"),
        ("geoLocation", "lat", "lon"),
        ("geolocation", "lat", "lon"),
        ("coordinates", "lat", "lon"),
        ("coordinates", "latitude", "longitude"),
        ("address", "geoLocation", "lat", "lon"),
        ("address", "geolocation", "lat", "lon"),
    ]
    for cand in candidates:
        *prefix, lat_k, lon_k = cand
        cur: Any = h
        ok = True
        for k in prefix:
            if isinstance(cur, dict) and k in cur:
                cur = cur[k]
            else:
                ok = False
                break
        if not ok or not isinstance(cur, dict):
            continue
        lat = _as_float(cur.get(lat_k))
        lon = _as_float(cur.get(lon_k))
        if lat is not None and lon is not None:
            return lat, lon

    lat = _as_float(h.get("lat"))
    lon = _as_float(h.get("lon"))
    if lat is not None and lon is not None:
        return lat, lon
    return None, None


def _format_address(h: dict) -> str | None:
    """Build address string (from legacy)."""
    if isinstance(h.get("address"), str) and h["address"].strip():
        street = h["address"].strip()
    else:
        street = None

    addr = h.get("address") if isinstance(h.get("address"), dict) else {}
    neigh = (
        addr.get("neighbourhood") or addr.get("neighborhood")
        or h.get("neighbourhood") or h.get("neighborhood")
    )
    city = addr.get("city") or h.get("city")
    state = addr.get("state") or h.get("state")

    parts: list[str] = []
    if street:
        parts.append(street)
    elif isinstance(addr.get("street"), str) and addr["street"].strip():
        parts.append(addr["street"].strip())
    if isinstance(neigh, str) and neigh.strip():
        parts.append(neigh.strip())
    if isinstance(city, str) and city.strip():
        parts.append(city.strip())
    if isinstance(state, str) and state.strip():
        parts.append(state.strip())
    return ", ".join(parts) if parts else None


def _extract_from_quintoandar_dom_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fallback extraction from DOM anchor elements."""
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
