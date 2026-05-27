"""Loft Playwright scraper.

Strategy:
    1. Navigate to Loft public search pages for sale/rent.
    2. Parse the server-rendered Next.js dehydrated search data.
    3. Follow public pagination through the `pagina` query parameter.

robots.txt: Loft disallows /health_check and /explorar, but allows the public
search pages under /venda/imoveis and /aluguel/imoveis.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .base import ScraperBase, _as_float, _as_int, _get_by_path, _normalize_image_url

LOFT_BASE = "https://loft.com.br"
LOFT_IMAGE_BASE = "https://content.loft.com.br/homes"


def _build_loft_scrape_url(search_address: str, search_type: str, page: int = 0) -> str:
    transaction = "venda" if search_type == "sale" else "aluguel"
    params: dict[str, str] = {}
    query = (search_address or "").strip()
    if query:
        params["q"] = query
    if page > 0:
        params["pagina"] = str(page + 1)

    query_string = urlencode(params)
    suffix = f"?{query_string}" if query_string else ""
    return f"{LOFT_BASE}/{transaction}/imoveis/sp/sao-paulo{suffix}"


def _loft_url_with_page(url: str, page: int) -> str:
    if page <= 0:
        return url

    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["pagina"] = str(page + 1)
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(query),
            parts.fragment,
        )
    )


class LoftScraper(ScraperBase):
    platform = "loft"
    base_url = LOFT_BASE

    async def scrape(self) -> list[dict[str, Any]]:
        self._check_robots("/venda/imoveis/" if self.search_type == "sale" else "/aluguel/imoveis/")
        return await self._scrape_once_in_fresh_context()

    async def _scrape_with_context(self, context: Any) -> list[dict[str, Any]]:
        await context.set_extra_http_headers(
            {
                "referer": "https://loft.com.br/",
                "accept-language": "pt-BR,pt;q=0.9,en;q=0.8",
            }
        )

        page = await context.new_page()
        listings: list[dict[str, Any]] = []
        seen: set[str] = set()

        configured_start = self._configured_start_urls()
        if configured_start and not self.search_address.strip():
            first_url = configured_start[0]
        else:
            first_url = _build_loft_scrape_url(self.search_address, self.search_type)

        try:
            max_pages = self._configured_max_pages(default=2)
            total_pages: int | None = None

            for page_idx in range(max_pages):
                if total_pages is not None and page_idx >= total_pages:
                    break

                target_url = (
                    _loft_url_with_page(first_url, page_idx)
                    if configured_start and not self.search_address.strip()
                    else _build_loft_scrape_url(
                        self.search_address,
                        self.search_type,
                        page=page_idx,
                    )
                )
                await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    await self._human_delay(1000, 1800)

                next_data_raw = await page.evaluate(
                    "() => { const el = document.getElementById('__NEXT_DATA__'); "
                    "return el ? el.textContent : null; }"
                )
                if not next_data_raw:
                    break

                try:
                    payload = json.loads(next_data_raw)
                except json.JSONDecodeError:
                    break

                page_listings, pagination = _extract_from_loft_next_data(
                    payload,
                    self.search_type,
                )
                if total_pages is None:
                    total_pages = _as_int(
                        pagination.get("totalPages") if isinstance(pagination, dict) else None
                    )

                before_count = len(seen)
                for item in page_listings:
                    lid = str(item.get("platform_listing_id") or "").strip()
                    if not lid or lid in seen:
                        continue
                    seen.add(lid)
                    listings.append(item)

                if len(seen) == before_count:
                    break
        finally:
            await page.close()

        return listings


def _extract_from_loft_next_data(
    payload: dict[str, Any],
    search_type: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    queries = _get_by_path(payload, "props.pageProps.dehydratedState.queries")
    if not isinstance(queries, list):
        return [], {}

    for query in queries:
        data = _get_by_path(query, "state.data")
        if not isinstance(data, dict):
            continue
        raw_listings = data.get("listings")
        if not isinstance(raw_listings, list):
            continue

        parsed: list[dict[str, Any]] = []
        for row in raw_listings:
            for raw_listing in _iter_loft_listing_nodes(row):
                item = _parse_loft_listing(raw_listing, search_type)
                if item:
                    parsed.append(item)
        if parsed:
            pagination = data.get("pagination")
            return parsed, pagination if isinstance(pagination, dict) else {}

    return [], {}


def _iter_loft_listing_nodes(row: Any) -> list[dict[str, Any]]:
    if not isinstance(row, dict):
        return []

    nodes: list[dict[str, Any]] = []
    primary = row.get("listing")
    if isinstance(primary, dict):
        nodes.append(primary)

    grouped = row.get("groupedListings")
    if isinstance(grouped, list):
        for item in grouped:
            if isinstance(item, dict):
                nodes.append(item.get("listing") if isinstance(item.get("listing"), dict) else item)

    if not nodes and ("id" in row or "objectID" in row):
        nodes.append(row)

    return nodes


def _parse_loft_listing(raw: dict[str, Any], search_type: str) -> dict[str, Any] | None:
    listing_id = str(raw.get("id") or raw.get("objectID") or "").strip()
    if not listing_id:
        return None

    if search_type == "rent":
        price = _as_float(raw.get("rentalPrice") or raw.get("price"))
    else:
        price = _as_float(raw.get("price") or raw.get("rentalPrice"))
    if price is None:
        return None

    address_node = raw.get("address") if isinstance(raw.get("address"), dict) else {}
    lat = _as_geo_float(
        _get_by_path(raw, "location.lat")
        or _get_by_path(raw, "_geoloc.lat")
        or address_node.get("lat")
        or raw.get("lat")
        or raw.get("latitude")
    )
    lon = _as_geo_float(
        _get_by_path(raw, "location.lon")
        or _get_by_path(raw, "location.lng")
        or _get_by_path(raw, "_geoloc.lng")
        or _get_by_path(raw, "_geoloc.lon")
        or address_node.get("lng")
        or address_node.get("lon")
        or raw.get("lng")
        or raw.get("lon")
        or raw.get("longitude")
    )

    image_url = _loft_image_url(raw, listing_id)
    address = _loft_address(address_node)

    return {
        "platform": "loft",
        "platform_listing_id": listing_id,
        "url": f"{LOFT_BASE}/imovel/{listing_id}",
        "image_url": image_url,
        "lat": lat,
        "lon": lon,
        "price_brl": price,
        "area_m2": _as_float(raw.get("area") or raw.get("usableArea")),
        "bedrooms": _as_int(raw.get("bedrooms")),
        "bathrooms": _as_int(raw.get("restrooms") or raw.get("bathrooms")),
        "parking": _as_int(raw.get("parkingSpots") or raw.get("parking")),
        "address": address,
        "condo_fee_brl": _as_float(raw.get("complexFee") or raw.get("condoFee")),
        "iptu_brl": _as_float(raw.get("propertyTax") or raw.get("iptu")),
    }


def _loft_address(address_node: dict[str, Any]) -> str | None:
    if not address_node:
        return None

    street = (
        address_node.get("streetFullName")
        or " ".join(
            str(v).strip()
            for v in (
                address_node.get("streetType"),
                address_node.get("streetName"),
            )
            if str(v or "").strip()
        )
        or address_node.get("streetName")
    )
    parts = [
        street,
        address_node.get("number"),
        address_node.get("neighborhood") or _get_by_path(address_node, "neighbourhood.name"),
        address_node.get("city"),
        address_node.get("state"),
    ]
    cleaned = [str(part).strip() for part in parts if str(part or "").strip()]
    return ", ".join(cleaned) if cleaned else None


def _as_geo_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        normalized = value.strip().replace(" ", "")
        if not normalized:
            return None
        if "," in normalized and "." not in normalized:
            normalized = normalized.replace(",", ".")
        try:
            return float(normalized)
        except ValueError:
            return None
    return None


def _loft_image_url(raw: dict[str, Any], listing_id: str) -> str | None:
    candidates = [
        raw.get("image_url"),
        raw.get("imageUrl"),
        raw.get("image"),
        raw.get("image_thumbnail"),
        raw.get("image_icon"),
        _get_by_path(raw, "photos.0.url"),
        _get_by_path(raw, "photos.0"),
    ]
    for candidate in candidates:
        normalized = _normalize_image_url(
            candidate,
            platform_base=LOFT_BASE,
            filename_prefix=f"{LOFT_IMAGE_BASE}/{listing_id}",
        )
        if normalized:
            if normalized.endswith("/banner.jpg"):
                return f"{LOFT_IMAGE_BASE}/{listing_id}/mobile_banner.jpg"
            return normalized

    return f"{LOFT_IMAGE_BASE}/{listing_id}/mobile_banner.jpg"
