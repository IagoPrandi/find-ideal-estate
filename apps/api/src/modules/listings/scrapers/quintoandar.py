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
    ScraperBase,
    _as_float,
    _as_int,
    _get_by_path,
)


def _qa_body_with_pagination(body: Any, from_: int, size: int) -> Any:
    if not isinstance(body, dict):
        return body
    payload = json.loads(json.dumps(body))
    if "from" in payload:
        payload["from"] = from_
    if "size" in payload:
        payload["size"] = size
    if "offset" in payload:
        payload["offset"] = from_
    if "limit" in payload:
        payload["limit"] = size
    if "page" in payload and isinstance(payload.get("page"), int):
        payload["page"] = int(from_ / max(size, 1))
    for key in ("pagination", "paging", "pageable"):
        if isinstance(payload.get(key), dict):
            node = payload[key]
            if "from" in node:
                node["from"] = from_
            if "size" in node:
                node["size"] = size
            if "offset" in node:
                node["offset"] = from_
            if "limit" in node:
                node["limit"] = size
            if "page" in node and isinstance(node.get("page"), int):
                node["page"] = int(from_ / max(size, 1))
    return payload


async def _qa_dom_listing_ids(page: Any) -> list[str]:
    """Collect visible listing ids from DOM anchors (/imovel/<id>)."""
    try:
        ids = await page.evaluate(
            r"""() => {
                const out = new Set();
                const anchors = Array.from(document.querySelectorAll('a[href]'));
                for (const a of anchors) {
                    const href = (a.getAttribute('href') || '').trim();
                    const m = href.match(/\/imovel\/(\d+)/);
                    if (m && m[1]) out.add(m[1]);
                }
                return Array.from(out);
            }"""
        )
        if isinstance(ids, list):
            return [str(x) for x in ids if str(x).strip()]
    except Exception:
        pass
    return []


async def _qa_load_more(page: Any, clicks: int) -> int:
    """Click 'Ver mais' up to N times, ensuring visible listing count grows after each click."""
    if clicks <= 0:
        return 0

    selectors = [
        "button:has-text('Ver mais')",
        "button:has-text('Mostrar mais')",
        "button:has-text('Carregar mais')",
        "a:has-text('Ver mais')",
        "[data-testid*='load']:has-text('Ver mais')",
    ]

    dismiss_selectors = [
        "button:has-text('Aceitar')",
        "button:has-text('Concordo')",
        "button:has-text('Entendi')",
        "button:has-text('Fechar')",
        "[aria-label='Fechar']",
        "[aria-label='Close']",
        "button[aria-label='Close']",
    ]

    increased = 0
    prev = set(await _qa_dom_listing_ids(page))

    for _ in range(clicks):
        # Best-effort dismiss of cookie/modals that can block list expansion.
        for sel in dismiss_selectors:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible(timeout=400):
                    try:
                        await loc.click(timeout=800)
                        await page.wait_for_timeout(150)
                    except Exception:
                        pass
            except Exception:
                continue
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass

        btn = None
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible(timeout=1500):
                    btn = loc
                    break
            except Exception:
                continue

        if btn is None:
            try:
                await page.mouse.wheel(0, 2600)
                await page.wait_for_timeout(800)
            except Exception:
                pass
            break

        try:
            await btn.scroll_into_view_if_needed(timeout=1500)
        except Exception:
            pass

        try:
            await btn.click(timeout=2500)
        except Exception:
            try:
                await btn.evaluate("(el) => el.click()")
            except Exception:
                break

        try:
            await page.wait_for_timeout(2200)
        except Exception:
            pass

        try:
            await page.mouse.wheel(0, 1200)
            await page.wait_for_timeout(350)
        except Exception:
            pass

        grew = False
        for _ in range(20):
            cur = set(await _qa_dom_listing_ids(page))
            if len(cur) > len(prev):
                prev = cur
                grew = True
                break
            try:
                await page.wait_for_timeout(250)
            except Exception:
                pass

        if not grew:
            break
        increased += 1

    return increased


def _build_quintoandar_scrape_url(search_address: str, search_type: str) -> str:
    location_slug = _to_quintoandar_location_slug(search_address)
    transaction = "alugar/imovel" if search_type == "rent" else "comprar/imovel"
    return f"https://www.quintoandar.com.br/{transaction}/{location_slug}"


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
        search_templates: list[dict[str, Any]] = []

        async with async_playwright() as pw:
            context = await self._open_browser_context(pw)
            page = await context.new_page()

            async def _capture_response(response: Any) -> None:
                url = response.url
                req = response.request
                if (
                    "quintoandar.com.br" in url
                    and req.method.upper() == "POST"
                    and "/house-listing-search/" in url
                    and "/search" in url
                    and "/coordinates" not in url
                    and "/count" not in url
                ):
                    try:
                        body = None
                        post_data = req.post_data
                        if isinstance(post_data, str) and post_data.strip():
                            body = json.loads(post_data)
                        headers = dict(getattr(req, "headers", {}) or {})
                        if isinstance(body, dict) and isinstance(headers, dict):
                            search_templates.append(
                                {
                                    "url": url,
                                    "headers": {
                                        str(k): str(v)
                                        for k, v in headers.items()
                                        if isinstance(k, str) and isinstance(v, str)
                                    },
                                    "body": body,
                                }
                            )
                    except Exception:
                        pass
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

            target_url = _build_quintoandar_scrape_url(
                self.search_address,
                self.search_type,
            )
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

            max_pages = self._configured_max_pages(default=4)
            for _ in range(max_pages):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await self._human_delay(700, 1400)

            # QuintoAndar expands results via "Ver mais"; use growth-validated clicking.
            await _qa_load_more(page, max_pages - 1)

            max_pages = self._configured_max_pages(default=4)
            if search_templates and max_pages > 1:
                # Legacy uses size=60 per page for QA search replay (_qa_body_with_pagination from_=i*60, size=60)
                page_size = 60
                for page_idx in range(1, max_pages):
                    from_ = page_idx * page_size
                    for template in search_templates:
                        body = _qa_body_with_pagination(
                            template.get("body"),
                            from_=from_,
                            size=page_size,
                        )
                        if not isinstance(body, dict):
                            continue
                        # Keep only safe request headers for replay; strip hop-by-hop and pseudo headers.
                        raw_headers = dict(template.get("headers") or {})
                        headers = {
                            str(k): str(v)
                            for k, v in raw_headers.items()
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
                        headers.setdefault("content-type", "application/json")
                        headers.setdefault("origin", "https://www.quintoandar.com.br")
                        headers.setdefault("referer", target_url)
                        try:
                            response = await context.request.post(
                                template["url"],
                                headers=headers,
                                data=json.dumps(body),
                            )
                            if response.ok:
                                payload = await response.json()
                                if isinstance(payload, dict):
                                    intercepted_payloads.append(payload)
                        except Exception:
                            continue

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

            await context.close()

        for payload in intercepted_payloads:
            extracted = _extract_from_quintoandar_payload(payload, self.search_type)
            listings.extend(extracted)

        coordinate_map: dict[str, tuple[float, float]] = {}
        for payload in intercepted_payloads:
            coordinate_map.update(_extract_quintoandar_coordinate_map(payload))

        if coordinate_map:
            for item in listings:
                if item.get("lat") is not None and item.get("lon") is not None:
                    continue
                house_id = str(item.get("platform_listing_id") or "").strip()
                if not house_id or house_id not in coordinate_map:
                    continue
                item["lat"], item["lon"] = coordinate_map[house_id]

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

    # Path A: ES-like search list format — /house-listing-search/v2/search/list response.
    # Must be checked FIRST (before __NEXT_DATA__ paths) because the POST /search
    # replay payloads use this format and contain richer price/location data.
    # Detection: hits.hits present and at least one _source has listing-like keys.
    raw_hits = _get_by_path(payload, "hits.hits")
    if not isinstance(raw_hits, list):
        # unwrap common wrapper keys ({data, result, response, ...})
        for _wrapper in ("data", "result", "results", "response"):
            _cand = payload.get(_wrapper)
            if isinstance(_cand, dict):
                _h2 = _get_by_path(_cand, "hits.hits")
                if isinstance(_h2, list) and _h2:
                    raw_hits = _h2
                    break
    if isinstance(raw_hits, list) and raw_hits:
        # Verify it looks like a QA search list (has listing-specific keys in _source)
        _sample_src = (raw_hits[0].get("_source") or {}) if isinstance(raw_hits[0], dict) else {}
        if any(k in _sample_src for k in ("totalCost", "rent", "salePrice", "area", "bedrooms", "bathrooms", "id")):
            for h in raw_hits:
                if not isinstance(h, dict):
                    continue
                src = h.get("_source") if isinstance(h.get("_source"), dict) else h
                lid = str(src.get("id") or h.get("_id") or src.get("listingId") or "")
                if not lid:
                    continue
                item = _parse_quintoandar_house(lid, src, search_type)
                if item:
                    results.append(item)
            return results

    # Path B: __NEXT_DATA__ houses map (id → house dict with rentPrice/area/bedrooms).
    state = (
        _get_by_path(payload, "props.pageProps.initialState")
        or _get_by_path(payload, "pageProps.initialState")
    )
    if not isinstance(state, dict):
        for _k in ("data", "result", "results"):
            _cand = payload.get(_k)
            if isinstance(_cand, dict) and ("houses" in _cand or "search" in _cand):
                state = _cand
                break
        if not isinstance(state, dict):
            state = payload

    houses_map = (
        _get_by_path(state, "houses")
        or _get_by_path(state, "houses.houses")
        or _get_by_path(state, "search.houses")
        # legacy direct paths
        or _get_by_path(payload, "props.pageProps.initialState.houses")
        or _get_by_path(payload, "props.pageProps.houses")
        or _get_by_path(payload, "houses")
    )
    if isinstance(houses_map, dict) and houses_map:
        # Verify values are house dicts, not nested maps
        _sample_v = next(iter(houses_map.values()), None)
        if isinstance(_sample_v, dict):
            visible_ids = _extract_quintoandar_visible_ids(state)
            if visible_ids:
                iterable = [(hid, houses_map.get(hid) or houses_map.get(str(hid))) for hid in visible_ids]
            else:
                # Fallback only when visible ids are unavailable.
                iterable = list(houses_map.items())
            for house_id, h in iterable:
                if not isinstance(h, dict):
                    continue
                item = _parse_quintoandar_house(str(house_id), h, search_type)
                if item:
                    results.append(item)
            if results:
                return results

    # Path C: other ES-like nested paths (broader fallback)
    hits_nested = (
        _get_by_path(payload, "data.search.result.hits.hits")
        or _get_by_path(payload, "search.result.hits.hits")
        or _get_by_path(payload, "result.hits.hits")
        or _get_by_path(payload, "results")
        or _get_by_path(payload, "data.results")
    )
    if isinstance(hits_nested, list):
        for h in hits_nested:
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


def _extract_quintoandar_coordinate_map(payload: dict[str, Any]) -> dict[str, tuple[float, float]]:
    coordinates: dict[str, tuple[float, float]] = {}

    def _store(node: dict[str, Any], fallback_id: str | None = None) -> None:
        house_id = str(node.get("id") or node.get("listingId") or fallback_id or "").strip()
        if not house_id:
            return
        lat = _as_float(
            node.get("lat")
            or _get_by_path(node, "location.lat")
            or _get_by_path(node, "address.point.lat")
            or _get_by_path(node, "geoLocation.lat")
        )
        lon = _as_float(
            node.get("lon")
            or node.get("lng")
            or _get_by_path(node, "location.lon")
            or _get_by_path(node, "location.lng")
            or _get_by_path(node, "address.point.lon")
            or _get_by_path(node, "geoLocation.lon")
        )
        if lat is None or lon is None:
            return
        coordinates[house_id] = (lat, lon)

    raw_hits = _get_by_path(payload, "hits.hits")
    if not isinstance(raw_hits, list):
        for wrapper in ("data", "result", "results", "response"):
            candidate = payload.get(wrapper)
            if not isinstance(candidate, dict):
                continue
            nested_hits = _get_by_path(candidate, "hits.hits")
            if isinstance(nested_hits, list):
                raw_hits = nested_hits
                break
    if isinstance(raw_hits, list):
        for hit in raw_hits:
            if not isinstance(hit, dict):
                continue
            source = hit.get("_source") if isinstance(hit.get("_source"), dict) else hit
            if isinstance(source, dict):
                _store(source, fallback_id=str(hit.get("_id") or ""))

    houses = payload.get("houses")
    if isinstance(houses, dict):
        for fallback_id, raw in houses.items():
            if isinstance(raw, dict):
                _store(raw, fallback_id=str(fallback_id))

    return coordinates


def _extract_quintoandar_visible_ids(state: dict[str, Any]) -> list[str]:
    """Return visible listing ids from Next.js state (visibleHouses.pages), preserving order."""
    pages = (
        _get_by_path(state, "search.visibleHouses.pages")
        or _get_by_path(state, "houses.visibleHouses.pages")
        or _get_by_path(state, "search.searchResults.visibleHouses.pages")
        or _get_by_path(state, "search.searchResult.visibleHouses.pages")
        or _get_by_path(state, "route.visibleHouses.pages")
    )

    def _iter_pages(raw: Any) -> list[Any]:
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict):
            # Stable order for keys "0", "1", ...
            out: list[Any] = []
            for k in sorted(raw.keys(), key=lambda x: int(str(x)) if str(x).isdigit() else str(x)):
                out.append(raw.get(k))
            return out
        return []

    ids: list[str] = []
    seen: set[str] = set()
    for pg in _iter_pages(pages):
        if isinstance(pg, list):
            seq = pg
        elif isinstance(pg, dict):
            seq = pg.get("ids") or pg.get("houseIds") or pg.get("items") or pg.get("results") or []
        else:
            seq = []
        if not isinstance(seq, list):
            continue
        for val in seq:
            sid = str(val or "").strip()
            if not sid or sid in seen:
                continue
            seen.add(sid)
            ids.append(sid)
    return ids


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

    def _looks_like_street(text: str) -> bool:
        return bool(
            re.match(
                r"^(rua|r\.?|avenida|av\.?|alameda|travessa|tv\.?|praca|praça|largo|estrada|rodovia)\b",
                text.strip().lower(),
            )
        )

    # Skip parts[0] (street name) — QuintoAndar does not have street-level slug pages.
    # Use neighborhood + city/state: e.g. "Vila Leopoldina", "Sao Paulo - SP" → vila-leopoldina-sao-paulo-sp-brasil.
    if len(parts) >= 4:
        selected = [parts[1], parts[2], parts[3]]
    elif len(parts) == 3:
        selected = parts[1:3]
    elif len(parts) == 2:
        selected = [parts[1]] if _looks_like_street(parts[0]) else parts
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
    # lat/lon: supports both __NEXT_DATA__ (address.point.lat, geoLocation.lat)
    # and ES search list format (_source.location.lat / _source.latitude)
    lat = _as_float(
        h.get("lat")
        or _get_by_path(h, "address.point.lat")
        or _get_by_path(h, "geoLocation.lat")
        or _get_by_path(h, "location.lat")   # ES /house-listing-search format
        or h.get("latitude")
    )
    lon = _as_float(
        h.get("lon")
        or _get_by_path(h, "address.point.lon")
        or _get_by_path(h, "geoLocation.lon")
        or _get_by_path(h, "location.lon")   # ES /house-listing-search format
        or h.get("longitude")
    )

    # price: supports both __NEXT_DATA__ (rentPrice/salePrice)
    # and ES format (totalCost = rent + condo + iptu, rent = base rent)
    price = _as_float(
        h.get("rentPrice")
        or h.get("totalCost")  # ES: total monthly cost
        or h.get("rent")        # ES: base rent
        or h.get("salePrice")
        or h.get("price")
        or _get_by_path(h, "pricingInfo.price")
    )
    # Guard against non-listing payloads (e.g., coordinates-only/search metadata) that
    # may carry ids but no pricing info; legacy canonical output expects priced cards.
    if price is None:
        return None

    # address: in __NEXT_DATA__ may be a dict; in ES format it is a plain string (street)
    addr_field = h.get("address")
    if isinstance(addr_field, dict):
        # __NEXT_DATA__ nested address dict
        addr_str = addr_field.get("full") or addr_field.get("address") or addr_field.get("street")
    else:
        addr_str = addr_field  # ES format: plain street string

    address_parts = [
        addr_str,
        h.get("neighbourhood") or h.get("neighborhood"),
        h.get("city") or "São Paulo",
        h.get("state") or h.get("stateAcronym") or h.get("uf") or "SP",
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
        "image_url": (
            _get_by_path(h, "coverImageUrl")
            or _get_by_path(h, "coverImage.url")
            or _get_by_path(h, "images.0.url")
            or _get_by_path(h, "gallery.0.url")
        ),
        "lat": lat,
        "lon": lon,
        "price_brl": price,
        "area_m2": _as_float(h.get("area") or h.get("totalArea") or h.get("usableArea")),
        "bedrooms": _as_int(h.get("bedrooms") or h.get("dormitories")),
        "bathrooms": _as_int(h.get("bathrooms") or h.get("suites")),
        # ES: parkingSpaces; __NEXT_DATA__: parkingSpots, garageSpaces, parking
        "parking": _as_int(
            h.get("parkingSpaces")
            or h.get("parkingSpots")
            or h.get("garageSpaces")
            or h.get("parking")
        ),
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
        })
    return results
